"""Handler de interação com o agente — mensagens de texto dos clientes e admin."""
import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter

from telegram import Update
from telegram.ext import ContextTypes

from database import (
    listar_faqs,
    obter_empresa_do_usuario,
    registrar_conversa,
)
from metrics import registrar_metrica_atendimento
from rag_chain import gerar_resposta
from rate_limiter import limiter_mensagens, verificar_rate_limit
from response_intelligence import (
    buscar_resposta_faq as _buscar_resposta_faq_inteligencia,
    decidir_resposta,
    detectar_pergunta_horario as _detectar_pergunta_horario_inteligencia,
    detectar_pedido_humano as _detectar_pedido_humano_inteligencia,
    normalizar_texto as _normalizar_texto_inteligencia,
)
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
    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.warning("Falha em tarefa assíncrona de pós-resposta: %s", exc, exc_info=True)


def invalidar_cache_faq(empresa_id: int | None = None) -> None:
    """Remove entradas de FAQ em memória após alterações administrativas."""
    if empresa_id is None:
        _faq_cache.clear()
        return

    _faq_cache.pop(empresa_id, None)


async def _obter_faqs_cacheadas(empresa_id: int) -> list[dict]:
    """Reduz leituras repetidas de FAQ em mensagens consecutivas."""
    agora = perf_counter()
    cache = _faq_cache.get(empresa_id)
    if cache and cache.expires_at > agora:
        return cache.items

    items = await listar_faqs(empresa_id)
    if items:
        _faq_cache[empresa_id] = _FaqCacheEntry(
            expires_at=agora + _FAQ_CACHE_TTL_SECONDS,
            items=items,
        )
    else:
        _faq_cache.pop(empresa_id, None)
    return items


def _buscar_resposta_faq(pergunta: str, faqs: list[dict]) -> str | None:
    return _buscar_resposta_faq_inteligencia(pergunta, faqs)


def _normalizar_texto(texto: str) -> str:
    return _normalizar_texto_inteligencia(texto)


def _detectar_pedido_humano(pergunta: str) -> bool:
    return _detectar_pedido_humano_inteligencia(pergunta)


def _detectar_pergunta_horario(pergunta: str) -> bool:
    return _detectar_pergunta_horario_inteligencia(pergunta)


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
    tem_documentos = empresa_tem_documentos(empresa["id"])
    decisao = decidir_resposta(
        pergunta=pergunta,
        empresa=empresa,
        faqs=faqs,
        usuario_admin=usuario_admin,
        tem_documentos=tem_documentos,
        resposta_pausado=_formatar_resposta_pausado(empresa),
        resposta_sem_base=_formatar_resposta_sem_base(empresa, usuario_admin=usuario_admin),
    )
    logger.info(
        "Inteligencia resposta empresa=%s usuario=%s decisao=%s motivo=%s",
        empresa["id"],
        user_id,
        decisao.kind,
        decisao.reason,
    )

    if decisao.kind != "rag":
        await update.message.chat.send_action("typing")
        await _responder_e_registrar(update, empresa, pergunta, decisao.answer or "")
        registrar_metrica_atendimento(
            empresa_id=empresa["id"],
            decisao=decisao.kind,
            total_segundos=perf_counter() - inicio,
            usou_rag=False,
            sucesso=True,
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
        registrar_metrica_atendimento(
            empresa_id=empresa["id"],
            decisao=decisao.kind,
            total_segundos=perf_counter() - inicio,
            usou_rag=True,
            sucesso=True,
        )
        logger.info(
            "Tempo atendimento empresa=%s usuario=%s total=%.2fs",
            empresa["id"],
            user_id,
            perf_counter() - inicio,
        )

    except VectorStoreIncompatibilityError as e:
        logger.warning("Base vetorial incompatível para a empresa %s: %s", empresa["id"], e)
        await update.message.reply_text(str(e))
        registrar_metrica_atendimento(
            empresa_id=empresa["id"],
            decisao="rag_incompatibility",
            total_segundos=perf_counter() - inicio,
            usou_rag=True,
            sucesso=False,
        )
    except TimeoutError:
        resposta = (
            "A consulta demorou mais do que o esperado. "
            "Tente reformular a pergunta de forma mais específica."
        )
        if empresa.get("fallback_contato"):
            resposta += f"\n\nSe preferir atendimento humano: {empresa['fallback_contato']}"
        await update.message.reply_text(resposta)
        registrar_metrica_atendimento(
            empresa_id=empresa["id"],
            decisao="rag_timeout",
            total_segundos=perf_counter() - inicio,
            usou_rag=True,
            sucesso=False,
        )
    except Exception as e:
        logger.error("Erro ao gerar resposta: %s", e, exc_info=True)
        await update.message.reply_text(
            "Desculpe, ocorreu um erro ao processar sua pergunta. Tente novamente em alguns instantes."
        )
        registrar_metrica_atendimento(
            empresa_id=empresa["id"],
            decisao="rag_error",
            total_segundos=perf_counter() - inicio,
            usou_rag=True,
            sucesso=False,
        )
