"""Handler de interacao com o agente para mensagens de texto no Telegram."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from agent_service import (
    invalidar_cache_faq,
    processar_pergunta,
)
from database import listar_faqs, obter_empresa_do_usuario, registrar_conversa
from rag_chain import gerar_resposta
from rate_limiter import limiter_mensagens, verificar_rate_limit
from validators import InputValidationError, validar_mensagem_usuario
from vector_store import empresa_tem_documentos

from .common import _pode_iniciar_admin_telegram_sem_link

__all__ = ["interagir_com_agente", "invalidar_cache_faq"]


async def _responder_e_registrar(update: Update, empresa: dict, pergunta: str, resposta: str):
    """Responde ao usuario e registra a conversa no historico."""
    await update.message.reply_text(resposta)
    await registrar_conversa(empresa["id"], update.effective_user.id, pergunta, resposta)


async def interagir_com_agente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens do proprio usuario e responde com FAQ ou RAG."""
    user_id = update.effective_user.id

    rate_msg = verificar_rate_limit(limiter_mensagens, user_id)
    if rate_msg:
        await update.message.reply_text(rate_msg)
        return

    try:
        pergunta = validar_mensagem_usuario(update.message.text or "")
    except InputValidationError as exc:
        await update.message.reply_text(f"⚠️ {exc.message}")
        return

    empresa = await obter_empresa_do_usuario(user_id)
    if not empresa:
        if _pode_iniciar_admin_telegram_sem_link(user_id):
            mensagem = (
                "👋 Este atendimento ainda não está configurado para você.\n"
                "Seu usuário está autorizado como admin. Envie /start para iniciar a configuração."
            )
        else:
            mensagem = (
                "👋 Este atendimento ainda não está configurado para você.\n"
                "Se você recebeu um link de admin, abra-o para liberar a gestão. "
                "Se é cliente, abra o link recebido do atendimento."
            )
        await update.message.reply_text(mensagem)
        return

    await update.message.chat.send_action("typing")
    resposta = await processar_pergunta(
        empresa=empresa,
        pergunta_bruta=pergunta,
        usuario_id=user_id,
        usuario_admin=bool(empresa.get("_usuario_admin")),
        faq_loader=listar_faqs,
        registrar_conversa_fn=registrar_conversa,
        rate_limit_checker=verificar_rate_limit,
        message_validator=validar_mensagem_usuario,
        document_checker=empresa_tem_documentos,
        rag_responder=gerar_resposta,
        skip_rate_limit=True,
        skip_validation=True,
    )
    await update.message.reply_text(resposta)
