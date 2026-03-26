"""Handler de interacao com o agente para mensagens de texto no Telegram."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from agent_service import (
    invalidar_cache_faq,
    processar_pergunta,
)
from database import (
    criar_feedback_resposta,
    listar_faqs,
    obter_empresa_do_usuario,
    registrar_conversa,
    registrar_feedback_resposta,
)
from rag_chain import gerar_resposta
from rate_limiter import limiter_mensagens, verificar_rate_limit
from validators import InputValidationError, validar_mensagem_usuario
from vector_store import empresa_tem_documentos

from .common import _pode_iniciar_admin_telegram_sem_link

__all__ = ["feedback_resposta_callback", "interagir_com_agente"]


def _extrair_resposta_e_conversa_id(resultado: object) -> tuple[str, int | None]:
    """Normaliza o retorno do serviço para suportar contexto rico sem quebrar mocks."""
    if isinstance(resultado, str):
        return resultado, None

    texto = getattr(resultado, "text", None)
    conversa_id = getattr(resultado, "conversation_id", None)
    if isinstance(texto, str):
        return texto, conversa_id if isinstance(conversa_id, int) else None
    return str(resultado), None


def _teclado_feedback(feedback_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("👍", callback_data=f"feedback:up:{feedback_id}"),
            InlineKeyboardButton("👎", callback_data=f"feedback:down:{feedback_id}"),
        ]]
    )


async def _responder_e_registrar(update: Update, empresa: dict, pergunta: str, resposta: str):
    """Responde ao usuario e registra a conversa no historico."""
    await update.message.reply_text(resposta)
    await registrar_conversa(empresa["id"], update.effective_user.id, pergunta, resposta)


async def interagir_com_agente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens do proprio usuario e responde com FAQ ou RAG."""
    usuario_id = update.effective_user.id

    rate_msg = verificar_rate_limit(limiter_mensagens, usuario_id)
    if rate_msg:
        await update.message.reply_text(rate_msg)
        return

    try:
        pergunta = validar_mensagem_usuario(update.message.text or "")
    except InputValidationError as exc:
        await update.message.reply_text(f"⚠️ {exc.message}")
        return

    empresa = await obter_empresa_do_usuario(usuario_id)
    if not empresa:
        if _pode_iniciar_admin_telegram_sem_link(usuario_id):
            mensagem = (
                "👋 Este atendimento ainda não está configurado para você.\n"
                "Seu usuário está autorizado como admin. Use /start para configurar uma empresa "
                "ou /empresas para escolher um atendimento."
            )
        else:
            mensagem = (
                "👋 Este atendimento ainda não está configurado para você.\n"
                "Se você recebeu um link de admin, abra-o para liberar a gestão. "
                "Se é cliente, use /empresas ou abra o link recebido do atendimento."
            )
        await update.message.reply_text(mensagem)
        return

    await update.message.chat.send_action("typing")
    resultado = await processar_pergunta(
        empresa=empresa,
        pergunta_bruta=pergunta,
        usuario_id=usuario_id,
        usuario_admin=bool(empresa.get("_usuario_admin")),
        faq_loader=listar_faqs,
        registrar_conversa_fn=registrar_conversa,
        rate_limit_checker=verificar_rate_limit,
        message_validator=validar_mensagem_usuario,
        document_checker=empresa_tem_documentos,
        rag_responder=gerar_resposta,
        skip_rate_limit=True,
        skip_validation=True,
        return_context=True,
    )
    resposta, conversa_id = _extrair_resposta_e_conversa_id(resultado)
    reply_markup = None
    if conversa_id is not None:
        feedback_id = await criar_feedback_resposta(
            conversa_id,
            empresa["id"],
            usuario_id,
            canal="telegram",
            resposta_bot=resposta,
        )
        reply_markup = _teclado_feedback(feedback_id)
    await update.message.reply_text(resposta, reply_markup=reply_markup)


async def feedback_resposta_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registra o feedback 👍/👎 sobre uma resposta já enviada."""
    query = update.callback_query
    if not query:
        return

    _, direcao, raw_feedback_id = (query.data or "").split(":", 2)
    feedback_id = int(raw_feedback_id)
    avaliacao = 1 if direcao == "up" else -1
    salvo = await registrar_feedback_resposta(feedback_id, avaliacao)

    if not salvo:
        await query.answer("Esse feedback já foi registrado.", show_alert=False)
        return

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    await query.answer("Feedback registrado. Obrigado.", show_alert=False)
