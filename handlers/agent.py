"""Handler de interação com o agente — mensagens de texto dos clientes e admin."""
import asyncio
import logging
import unicodedata
from dataclasses import dataclass
from time import perf_counter

from difflib import SequenceMatcher
from telegram import Update
from telegram.ext import ContextTypes

from database import (
    listar_faqs,
    obter_empresa_do_usuario,
    registrar_conversa,
)
from rag_chain import gerar_resposta
from rate_limiter import limiter_mensagens, verificar_rate_limit
from validators import InputValidationError, validar_mensagem_usuario
from vector_store import VectorStoreIncompatibilityError, empresa_tem_documentos
logger = logging.getLogger(__name__)
_FAQ_CACHE_TTL_SECONDS = 30


@dataclass
class _FaqCacheEntry:
    expires_at: float
    items: list[dict]


_faq_cache: dict[int, _FaqCacheEntry] = {}


def _log_task_exception(task: asyncio.Task) -> None:
    """Registra falhas de tarefas em background sem interromper a resposta ao usuário."""
    try:
        task.result()
    except Exception as exc:
        logger.warning("Falha em tarefa assíncrona de pós-resposta: %s", exc, exc_info=True)


async def _obter_faqs_cacheadas(empresa_id: int) -> list[dict]:
    """Reduz leituras repetidas de FAQ em mensagens consecutivas."""
    agora = perf_counter()
    cache = _faq_cache.get(empresa_id)
    if cache and cache.expires_at > agora:
        return cache.items

    items = await listar_faqs(empresa_id)
    _faq_cache[empresa_id] = _FaqCacheEntry(
        expires_at=agora + _FAQ_CACHE_TTL_SECONDS,
        items=items,
    )
    return items


def _normalizar_texto(texto: str) -> str:
    """Normaliza texto para comparações simples no fluxo de FAQ e fallback."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    return " ".join(texto.lower().strip().split())


def _buscar_resposta_faq(pergunta: str, faqs: list[dict]) -> str | None:
    """Busca a resposta mais provável entre FAQs cadastradas."""
    pergunta_normalizada = _normalizar_texto(pergunta)
    melhor_resposta = None
    melhor_score = 0.0

    for faq in faqs:
        pergunta_faq = _normalizar_texto(faq["pergunta"])
        if not pergunta_faq:
            continue

        if (
            pergunta_normalizada == pergunta_faq
            or pergunta_normalizada in pergunta_faq
            or pergunta_faq in pergunta_normalizada
        ):
            return faq["resposta"]

        score = SequenceMatcher(None, pergunta_normalizada, pergunta_faq).ratio()
        if score > melhor_score:
            melhor_score = score
            melhor_resposta = faq["resposta"]

    if melhor_score >= 0.82:
        return melhor_resposta

    return None


def _detectar_pedido_humano(pergunta: str) -> bool:
    """Detecta pedidos explícitos de encaminhamento para humano/contato."""
    pergunta_normalizada = _normalizar_texto(pergunta)
    gatilhos = [
        "falar com atendente",
        "falar com humano",
        "atendimento humano",
        "quero um atendente",
        "quero falar com alguem",
        "telefone",
        "whatsapp",
        "contato",
    ]
    return any(gatilho in pergunta_normalizada for gatilho in gatilhos)


def _detectar_pergunta_horario(pergunta: str) -> bool:
    """Detecta perguntas sobre horário de atendimento."""
    pergunta_normalizada = _normalizar_texto(pergunta)
    gatilhos = ["horario", "atendimento", "aberto", "funciona", "expediente"]
    return any(gatilho in pergunta_normalizada for gatilho in gatilhos)


def _formatar_resposta_pausado(empresa: dict) -> str:
    """Monta a resposta padrão quando o agente está pausado."""
    linhas = ["⏸️ Seu agente está pausado no momento."]
    if empresa.get("horario_atendimento"):
        linhas.append(f"🕒 Horário informado: {empresa['horario_atendimento']}")
    if empresa.get("fallback_contato"):
        linhas.append(f"🆘 Contato humano: {empresa['fallback_contato']}")
    return "\n".join(linhas)


def _formatar_resposta_sem_base(empresa: dict, usuario_admin: bool) -> str:
    """Monta a resposta padrão quando ainda não há base carregada."""
    linhas = ["📄 Este atendimento ainda não tem base de conhecimento carregada."]
    if usuario_admin:
        linhas.append("Envie documentos neste chat ou use /upload para concluir a configuração.")
    else:
        linhas.append("O atendimento ainda está sendo preparado. Tente novamente em instantes.")
    if empresa.get("horario_atendimento"):
        linhas.append(f"🕒 Horário informado: {empresa['horario_atendimento']}")
    if empresa.get("fallback_contato"):
        linhas.append(f"🆘 Contato humano: {empresa['fallback_contato']}")
    return "\n".join(linhas)


def _instrucoes_operacionais_empresa(empresa: dict) -> str:
    """Adiciona horário/fallback às instruções do agente quando configurados."""
    extras = []
    if empresa.get("horario_atendimento"):
        extras.append(f"Horário de atendimento da empresa: {empresa['horario_atendimento']}.")
    if empresa.get("fallback_contato"):
        extras.append(
            "Se o usuário pedir atendimento humano ou você não tiver a informação, "
            f"oriente este contato: {empresa['fallback_contato']}."
        )

    if not extras:
        return empresa["instrucoes"]

    return f"{empresa['instrucoes']}\n\nINFORMAÇÕES OPERACIONAIS:\n- " + "\n- ".join(extras)


async def _responder_e_registrar(update: Update, empresa: dict, pergunta: str, resposta: str):
    """Responde ao usuário e registra a conversa no histórico."""
    await update.message.reply_text(resposta)
    task = asyncio.create_task(
        registrar_conversa(empresa["id"], update.effective_user.id, pergunta, resposta)
    )
    task.add_done_callback(_log_task_exception)


async def interagir_com_agente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens do próprio usuário e responde com RAG."""
    inicio = perf_counter()
    user_id = update.effective_user.id

    # Rate limiting
    rate_msg = verificar_rate_limit(limiter_mensagens, user_id)
    if rate_msg:
        await update.message.reply_text(rate_msg)
        return

    # Validação da mensagem
    try:
        pergunta = validar_mensagem_usuario(update.message.text)
    except InputValidationError as e:
        await update.message.reply_text(f"⚠️ {e.message}")
        return

    empresa = await obter_empresa_do_usuario(user_id)
    if not empresa:
        await update.message.reply_text(
            "👋 Este atendimento ainda não está configurado para você.\n"
            "Se você é o admin, envie /start. Se é cliente, abra o link recebido do atendimento."
        )
        return

    usuario_admin = empresa.get("telegram_user_id") == user_id

    faqs = await _obter_faqs_cacheadas(empresa["id"])

    if not bool(empresa.get("ativo", 1)):
        await update.message.chat.send_action("typing")
        await _responder_e_registrar(update, empresa, pergunta, _formatar_resposta_pausado(empresa))
        return

    if empresa.get("fallback_contato") and _detectar_pedido_humano(pergunta):
        await update.message.chat.send_action("typing")
        await _responder_e_registrar(
            update,
            empresa,
            pergunta,
            f"🆘 Para atendimento humano, use este contato: {empresa['fallback_contato']}",
        )
        return

    if empresa.get("horario_atendimento") and _detectar_pergunta_horario(pergunta):
        await update.message.chat.send_action("typing")
        await _responder_e_registrar(
            update,
            empresa,
            pergunta,
            f"🕒 Horário de atendimento: {empresa['horario_atendimento']}",
        )
        return

    resposta_faq = _buscar_resposta_faq(pergunta, faqs)
    if resposta_faq:
        await update.message.chat.send_action("typing")
        await _responder_e_registrar(update, empresa, pergunta, resposta_faq)
        return

    if not empresa_tem_documentos(empresa["id"]):
        await update.message.chat.send_action("typing")
        await _responder_e_registrar(
            update,
            empresa,
            pergunta,
            _formatar_resposta_sem_base(
                empresa,
                usuario_admin=usuario_admin,
            ),
        )
        return

    # Envia indicador de "digitando"
    await update.message.chat.send_action("typing")

    try:
        resposta = await gerar_resposta(
            empresa_id=empresa["id"],
            nome_empresa=empresa["nome"],
            nome_bot=empresa["nome_bot"],
            instrucoes=_instrucoes_operacionais_empresa(empresa),
            pergunta=pergunta,
        )

        resposta_normalizada = _normalizar_texto(resposta)
        if empresa.get("fallback_contato") and (
            "nao tenho essa informacao" in resposta_normalizada
            or "nao tenho documentos" in resposta_normalizada
            or "nao estiver no contexto" in resposta_normalizada
        ):
            resposta = (
                f"{resposta}\n\n"
                f"Se preferir, fale com a equipe em: {empresa['fallback_contato']}"
            )

        await _responder_e_registrar(update, empresa, pergunta, resposta)
        logger.info(
            "Tempo atendimento empresa=%s usuario=%s total=%.2fs",
            empresa["id"],
            user_id,
            perf_counter() - inicio,
        )

    except VectorStoreIncompatibilityError as e:
        logger.warning("Base vetorial incompatível para a empresa %s: %s", empresa["id"], e)
        await update.message.reply_text(str(e))
    except Exception as e:
        logger.error("Erro ao gerar resposta: %s", e, exc_info=True)
        await update.message.reply_text(
            "Desculpe, ocorreu um erro ao processar sua pergunta. Tente novamente em alguns instantes."
        )
