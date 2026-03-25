"""Servico reutilizavel para processar mensagens do agente em diferentes canais."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Awaitable, Callable

from database import listar_faqs, registrar_conversa
from metrics import registrar_metrica_atendimento
from rag_chain import gerar_resposta
from rate_limiter import limiter_mensagens, verificar_rate_limit
from response_intelligence import (
    buscar_resposta_faq as _buscar_resposta_faq_inteligencia,
)
from response_intelligence import (
    decidir_resposta,
)
from response_intelligence import (
    normalizar_texto as _normalizar_texto_inteligencia,
)
from validators import InputValidationError, validar_mensagem_usuario
from vector_store import VectorStoreIncompatibilityError, empresa_tem_documentos

logger = logging.getLogger(__name__)
_FAQ_CACHE_TTL_SECONDS = 30

FaqLoader = Callable[[int], Awaitable[list[dict]]]
ConversaRegistrar = Callable[[int, int, str, str], Awaitable[None]]
RateLimitChecker = Callable[[object, int], str | None]
MessageValidator = Callable[[str], str]
DocumentChecker = Callable[[int], bool]
RagResponder = Callable[[int, str, str, str, str], Awaitable[str]]


@dataclass
class _FaqCacheEntry:
    expires_at: float
    items: list[dict]


_faq_cache: dict[int, _FaqCacheEntry] = {}


def _log_task_exception(task: asyncio.Task) -> None:
    """Registra falhas de tarefas em background sem interromper a resposta ao usuario."""
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.warning("Falha em tarefa assincrona de pos-resposta: %s", exc, exc_info=True)


def invalidar_cache_faq(empresa_id: int | None = None) -> None:
    """Remove entradas de FAQ em memoria apos alteracoes administrativas."""
    if empresa_id is None:
        _faq_cache.clear()
        return

    _faq_cache.pop(empresa_id, None)


async def _obter_faqs_cacheadas(
    empresa_id: int,
    *,
    faq_loader: FaqLoader,
) -> list[dict]:
    """Reduz leituras repetidas de FAQ em mensagens consecutivas."""
    if faq_loader is not listar_faqs:
        return await faq_loader(empresa_id)

    agora = perf_counter()
    cache = _faq_cache.get(empresa_id)
    if cache and cache.expires_at > agora:
        return cache.items

    items = await faq_loader(empresa_id)
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


def _formatar_resposta_pausado(empresa: dict) -> str:
    """Monta a resposta padrao quando o agente esta pausado."""
    linhas = ["⏸️ Seu agente esta pausado no momento."]
    if empresa.get("horario_atendimento"):
        linhas.append(f"🕒 Horario informado: {empresa['horario_atendimento']}")
    if empresa.get("fallback_contato"):
        linhas.append(f"🆘 Contato humano: {empresa['fallback_contato']}")
    return "\n".join(linhas)


def _formatar_resposta_sem_base(empresa: dict, usuario_admin: bool) -> str:
    """Monta a resposta padrao quando ainda nao ha base carregada."""
    linhas = ["📄 Este atendimento ainda nao tem base de conhecimento carregada."]
    if usuario_admin:
        linhas.append("Envie documentos neste chat ou use /upload para concluir a configuracao.")
    else:
        linhas.append("O atendimento ainda esta sendo preparado. Tente novamente em instantes.")
    if empresa.get("horario_atendimento"):
        linhas.append(f"🕒 Horario informado: {empresa['horario_atendimento']}")
    if empresa.get("fallback_contato"):
        linhas.append(f"🆘 Contato humano: {empresa['fallback_contato']}")
    return "\n".join(linhas)


def _instrucoes_operacionais_empresa(empresa: dict) -> str:
    """Adiciona horario e fallback as instrucoes do agente quando configurados."""
    instrucoes_base = str(empresa.get("instrucoes") or "")
    extras: list[str] = []
    if empresa.get("horario_atendimento"):
        extras.append(f"Horario de atendimento da empresa: {empresa['horario_atendimento']}.")
    if empresa.get("fallback_contato"):
        extras.append(
            "Se o usuario pedir atendimento humano ou voce nao tiver a informacao, "
            f"oriente este contato: {empresa['fallback_contato']}."
        )

    if not extras:
        return instrucoes_base

    return f"{instrucoes_base}\n\nINFORMAÇÕES OPERACIONAIS:\n- " + "\n- ".join(extras)


def _registrar_conversa(
    empresa_id: int,
    usuario_id: int,
    pergunta: str,
    resposta: str,
    *,
    registrar_conversa_fn: ConversaRegistrar,
) -> None:
    task = asyncio.create_task(
        registrar_conversa_fn(empresa_id, usuario_id, pergunta, resposta)
    )
    task.add_done_callback(_log_task_exception)


async def processar_pergunta(
    *,
    empresa: dict,
    pergunta_bruta: str,
    usuario_id: int,
    usuario_admin: bool,
    faq_loader: FaqLoader = listar_faqs,
    registrar_conversa_fn: ConversaRegistrar = registrar_conversa,
    rate_limit_checker: RateLimitChecker = verificar_rate_limit,
    message_validator: MessageValidator = validar_mensagem_usuario,
    document_checker: DocumentChecker = empresa_tem_documentos,
    rag_responder: RagResponder = gerar_resposta,
    skip_rate_limit: bool = False,
    skip_validation: bool = False,
) -> str:
    """Processa uma pergunta de um usuario e retorna a resposta final."""
    inicio = perf_counter()

    if skip_rate_limit:
        rate_msg = None
    else:
        rate_msg = rate_limit_checker(limiter_mensagens, usuario_id)

    if rate_msg:
        return rate_msg

    if skip_validation:
        pergunta = pergunta_bruta
    else:
        try:
            pergunta = message_validator(pergunta_bruta)
        except InputValidationError as exc:
            return f"⚠️ {exc.message}"

    faqs = await _obter_faqs_cacheadas(empresa["id"], faq_loader=faq_loader)
    tem_documentos = document_checker(empresa["id"])
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
        usuario_id,
        decisao.kind,
        decisao.reason,
    )

    if decisao.kind != "rag":
        resposta_imediata = decisao.answer or ""
        _registrar_conversa(
            empresa["id"],
            usuario_id,
            pergunta,
            resposta_imediata,
            registrar_conversa_fn=registrar_conversa_fn,
        )
        registrar_metrica_atendimento(
            empresa_id=empresa["id"],
            decisao=decisao.kind,
            total_segundos=perf_counter() - inicio,
            usou_rag=False,
            sucesso=True,
        )
        return resposta_imediata

    try:
        resposta = await rag_responder(
            empresa["id"],
            empresa["nome"],
            empresa["nome_bot"],
            _instrucoes_operacionais_empresa(empresa),
            pergunta,
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

        _registrar_conversa(
            empresa["id"],
            usuario_id,
            pergunta,
            resposta,
            registrar_conversa_fn=registrar_conversa_fn,
        )
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
            usuario_id,
            perf_counter() - inicio,
        )
        return resposta
    except VectorStoreIncompatibilityError as exc:
        logger.warning("Base vetorial incompatível para a empresa %s: %s", empresa["id"], exc)
        registrar_metrica_atendimento(
            empresa_id=empresa["id"],
            decisao="rag_incompatibility",
            total_segundos=perf_counter() - inicio,
            usou_rag=True,
            sucesso=False,
        )
        return str(exc)
    except TimeoutError:
        resposta_timeout = (
            "A consulta demorou mais do que o esperado. "
            "Tente reformular a pergunta de forma mais especifica."
        )
        if empresa.get("fallback_contato"):
            resposta_timeout += f"\n\nSe preferir atendimento humano: {empresa['fallback_contato']}"
        registrar_metrica_atendimento(
            empresa_id=empresa["id"],
            decisao="rag_timeout",
            total_segundos=perf_counter() - inicio,
            usou_rag=True,
            sucesso=False,
        )
        return resposta_timeout
    except Exception as exc:
        logger.error("Erro ao gerar resposta: %s", exc, exc_info=True)
        registrar_metrica_atendimento(
            empresa_id=empresa["id"],
            decisao="rag_error",
            total_segundos=perf_counter() - inicio,
            usou_rag=True,
            sucesso=False,
        )
        return (
            "Desculpe, ocorreu um erro ao processar sua pergunta. "
            "Tente novamente em alguns instantes."
        )
