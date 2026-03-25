"""Handlers de configurações operacionais — horário, fallback, editar, pausar/ativar."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from database import atualizar_empresa
from validators import (
    InputValidationError,
    validar_fallback,
    validar_horario,
)

from .common import (
    AGUARDANDO_FALLBACK,
    AGUARDANDO_HORARIO,
    EDITANDO_CAMPO,
    _obter_empresa_admin_ou_responder,
)

logger = logging.getLogger(__name__)


CAMPOS_EDITAVEIS = {
    "editar_nome": ("nome", "nome da empresa"),
    "editar_nome_bot": ("nome_bot", "nome do assistente"),
    "editar_saudacao": ("saudacao", "mensagem de saudação"),
    "editar_instrucoes": ("instrucoes", "instruções do bot"),
}


async def _definir_status_agente(update: Update, context: ContextTypes.DEFAULT_TYPE, ativo: bool):
    """Ativa ou pausa o agente do usuário."""
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return

    ativo_atual = bool(empresa.get("ativo", 1))
    if ativo_atual == ativo:
        texto = (
            "ℹ️ Seu agente já está ativo."
            if ativo
            else "ℹ️ Seu agente já está pausado."
        )
        await mensagem.reply_text(texto)
        return

    await atualizar_empresa(empresa["id"], ativo=1 if ativo else 0)
    texto = (
        "▶️ Seu agente foi ativado e já pode voltar a responder neste chat."
        if ativo
        else "⏸️ Seu agente foi pausado. Enquanto estiver pausado, as pessoas verão apenas sua orientação operacional."
    )
    await mensagem.reply_text(texto)

    if update.callback_query:
        from .panel import cmd_painel
        await cmd_painel(update, context)


async def cmd_pausar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pausa o agente do usuário."""
    await _definir_status_agente(update, context, ativo=False)


async def cmd_ativar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ativa o agente do usuário."""
    await _definir_status_agente(update, context, ativo=True)


async def cmd_horario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia ou aplica a configuração de horário de atendimento."""
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return ConversationHandler.END

    if context.args:
        acao = context.args[0].lower()
        if acao in {"limpar", "remover", "apagar"}:
            await atualizar_empresa(empresa["id"], horario_atendimento="")
            await mensagem.reply_text("✅ O horário de atendimento foi removido.")
            return ConversationHandler.END

        try:
            horario = validar_horario(" ".join(context.args))
        except InputValidationError as e:
            await mensagem.reply_text(f"⚠️ {e.message}")
            return ConversationHandler.END

        await atualizar_empresa(empresa["id"], horario_atendimento=horario)
        await mensagem.reply_text(f"✅ Horário atualizado para: {horario}")
        return ConversationHandler.END

    horario_atual = empresa.get("horario_atendimento") or "Não configurado"
    await mensagem.reply_text(
        "🕒 Horário de atendimento\n\n"
        f"Atual: {horario_atual}\n\n"
        "Envie o texto completo do horário do seu atendimento.\n"
        "Exemplo: Seg a Sex, 08h às 18h.\n"
        "Se quiser remover, use /horario limpar."
    )
    return AGUARDANDO_HORARIO


async def receber_horario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o novo horário de atendimento do agente."""
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return ConversationHandler.END

    try:
        horario = validar_horario(update.message.text)
    except InputValidationError as e:
        await update.message.reply_text(f"⚠️ {e.message}")
        return AGUARDANDO_HORARIO

    await atualizar_empresa(empresa["id"], horario_atendimento=horario)
    await update.message.reply_text(f"✅ Horário atualizado para: {horario}")
    return ConversationHandler.END


async def cmd_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia ou aplica a configuração do fallback para atendimento humano."""
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return ConversationHandler.END

    if context.args:
        acao = context.args[0].lower()
        if acao in {"limpar", "remover", "apagar"}:
            await atualizar_empresa(empresa["id"], fallback_contato="")
            await mensagem.reply_text("✅ O fallback para atendimento humano foi removido.")
            return ConversationHandler.END

        try:
            fallback = validar_fallback(" ".join(context.args))
        except InputValidationError as e:
            await mensagem.reply_text(f"⚠️ {e.message}")
            return ConversationHandler.END

        await atualizar_empresa(empresa["id"], fallback_contato=fallback)
        await mensagem.reply_text(f"✅ Fallback atualizado para: {fallback}")
        return ConversationHandler.END

    fallback_atual = empresa.get("fallback_contato") or "Não configurado"
    await mensagem.reply_text(
        "🆘 Fallback para humano\n\n"
        f"Atual: {fallback_atual}\n\n"
        "Envie o contato que deve ser usado quando o usuário quiser atendimento humano.\n"
        "Exemplo: WhatsApp (11) 99999-9999 ou suporte@empresa.com.\n"
        "Se quiser remover, use /fallback limpar."
    )
    return AGUARDANDO_FALLBACK


async def receber_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o novo contato de fallback do agente."""
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return ConversationHandler.END

    try:
        fallback = validar_fallback(update.message.text)
    except InputValidationError as e:
        await update.message.reply_text(f"⚠️ {e.message}")
        return AGUARDANDO_FALLBACK

    await atualizar_empresa(empresa["id"], fallback_contato=fallback)
    await update.message.reply_text(f"✅ Fallback atualizado para: {fallback}")
    return ConversationHandler.END


async def cmd_editar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra opções de edição."""
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return ConversationHandler.END

    context.user_data["empresa_editar_id"] = empresa["id"]
    botoes = [
        [InlineKeyboardButton("✏️ Nome da empresa", callback_data="editar_nome")],
        [InlineKeyboardButton("🤖 Nome do bot", callback_data="editar_nome_bot")],
        [InlineKeyboardButton("👋 Saudação", callback_data="editar_saudacao")],
        [InlineKeyboardButton("📝 Instruções", callback_data="editar_instrucoes")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="editar_cancelar")],
    ]
    await mensagem.reply_text(
        "⚙️ **O que deseja editar?**",
        reply_markup=InlineKeyboardMarkup(botoes),
        parse_mode="Markdown",
    )
    return EDITANDO_CAMPO


async def editar_campo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para seleção do campo a editar."""
    query = update.callback_query
    await query.answer()

    if query.data == "editar_cancelar":
        await query.edit_message_text("❌ Edição cancelada.")
        return ConversationHandler.END

    campo_info = CAMPOS_EDITAVEIS.get(query.data)
    if not campo_info:
        await query.edit_message_text("❌ Opção inválida.")
        return ConversationHandler.END

    context.user_data["campo_editando"] = campo_info[0]
    context.user_data["campo_editando_nome"] = campo_info[1]

    await query.edit_message_text(f"📝 Envie o novo valor para **{campo_info[1]}**:", parse_mode="Markdown")
    return EDITANDO_CAMPO


async def receber_valor_editado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o novo valor do campo editado."""
    empresa_id = context.user_data.get("empresa_editar_id")
    campo = context.user_data.get("campo_editando")
    nome_campo = context.user_data.get("campo_editando_nome")

    if not all([empresa_id, campo, nome_campo]):
        await update.message.reply_text("❌ Erro interno. Use /editar novamente.")
        return ConversationHandler.END

    novo_valor = update.message.text.strip()
    await atualizar_empresa(empresa_id, **{campo: novo_valor})

    await update.message.reply_text(
        f"✅ {nome_campo.title()} atualizado para: {novo_valor}",
    )

    for k in ["empresa_editar_id", "campo_editando", "campo_editando_nome"]:
        context.user_data.pop(k, None)

    return ConversationHandler.END
