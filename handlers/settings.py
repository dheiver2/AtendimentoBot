"""Handlers de configurações operacionais — horário, fallback, editar, pausar/ativar."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from database import atualizar_empresa
from instruction_templates import listar_templates_instrucao, obter_template_instrucao
from validators import (
    InputValidationError,
    validar_fallback,
    validar_horario,
    validar_instrucoes,
    validar_nome_bot,
    validar_nome_empresa,
    validar_saudacao,
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

VALIDADORES_CAMPOS_EDITAVEIS = {
    "nome": validar_nome_empresa,
    "nome_bot": validar_nome_bot,
    "saudacao": validar_saudacao,
    "instrucoes": validar_instrucoes,
}


def _formatar_templates_instrucao(template_key_atual: str | None) -> str:
    """Gera o texto compacto com os templates disponíveis para o admin."""
    template_atual = obter_template_instrucao(template_key_atual)
    linhas = [
        "🧩 Templates de instruções disponíveis:",
        "",
        (
            f"Atual: {template_atual.nome} ({template_atual.key})"
            if template_atual
            else "Atual: Personalizado"
        ),
        "",
    ]
    for template in listar_templates_instrucao():
        linhas.append(f"- {template.key}: {template.nome} — {template.descricao}")
    linhas.extend(
        [
            "",
            "Use /template <slug> para aplicar um template.",
            "Exemplo: /template clinica",
            "Use /template limpar para manter as instruções atuais como personalizadas.",
        ]
    )
    return "\n".join(linhas)


def _validar_valor_campo_editavel(campo: str, valor: str) -> str:
    """Aplica a mesma validação do onboarding aos campos editáveis."""
    validador = VALIDADORES_CAMPOS_EDITAVEIS.get(campo)
    if not validador:
        raise InputValidationError("Campo de edição inválido.")
    return validador(valor)


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


async def cmd_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista e aplica templates de instruções por setor."""
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return

    args = context.args or []
    if not args or args[0].lower() in {"listar", "lista"}:
        await mensagem.reply_text(_formatar_templates_instrucao(empresa.get("instruction_template_key")))
        return

    acao = args[0].lower()
    if acao in {"limpar", "personalizado"}:
        await atualizar_empresa(empresa["id"], instruction_template_key=None)
        await mensagem.reply_text(
            "✅ O vínculo com o template foi removido.\n"
            "Suas instruções atuais continuam salvas como personalizadas."
        )
        return

    template_key = args[1] if acao in {"aplicar", "usar"} and len(args) > 1 else args[0]
    template = obter_template_instrucao(template_key)
    if not template:
        await mensagem.reply_text(
            "⚠️ Template não encontrado.\n\n"
            + _formatar_templates_instrucao(empresa.get("instruction_template_key"))
        )
        return

    await atualizar_empresa(
        empresa["id"],
        instrucoes=template.texto,
        instruction_template_key=template.key,
    )
    await mensagem.reply_text(
        f"✅ Template aplicado: {template.nome}\n\n"
        f"{template.descricao}\n\n"
        "Se quiser ajustar o texto depois, use /editar e altere as instruções."
    )


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

    try:
        novo_valor = _validar_valor_campo_editavel(campo, update.message.text)
    except InputValidationError as e:
        await update.message.reply_text(f"⚠️ {e.message}")
        return EDITANDO_CAMPO

    await atualizar_empresa(empresa_id, **{campo: novo_valor})

    await update.message.reply_text(
        f"✅ {nome_campo.title()} atualizado para: {novo_valor}",
    )

    for k in ["empresa_editar_id", "campo_editando", "campo_editando_nome"]:
        context.user_data.pop(k, None)

    return ConversationHandler.END
