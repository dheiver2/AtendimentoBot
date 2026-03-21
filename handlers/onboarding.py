"""Handlers de onboarding — registro de empresa e configuração inicial."""
import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from database import (
    criar_empresa,
    atualizar_empresa,
    excluir_empresa_com_dados,
    obter_empresa_do_cliente,
    obter_empresa_por_admin,
    obter_empresa_por_link_token,
    vincular_cliente_empresa,
)
from document_processor import listar_formatos_suportados
from validators import (
    InputValidationError,
    validar_instrucoes,
    validar_nome_bot,
    validar_nome_empresa,
    validar_saudacao,
)
from vector_store import empresa_tem_documentos

from .common import (
    AGUARDANDO_INSTRUCOES,
    AGUARDANDO_NOME_BOT,
    AGUARDANDO_NOME_EMPRESA,
    AGUARDANDO_SAUDACAO,
    _enviar_boas_vindas_cliente,
    _limpar_estado_usuario,
    _mensagem_somente_admin,
    _obter_payload_start,
    _remover_arquivos_empresa,
    _obter_empresa_admin_ou_responder,
    _sincronizar_comandos_do_chat,
)

logger = logging.getLogger(__name__)


async def _iniciar_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia a primeira etapa do onboarding para um novo usuário."""
    mensagem = update.effective_message
    _limpar_estado_usuario(context)

    await mensagem.reply_text(
        "👋 **Vamos configurar seu agente de atendimento.**\n\n"
        "Neste onboarding você vai definir:\n"
        "1. Nome da empresa\n"
        "2. Nome do assistente\n"
        "3. Saudação inicial\n"
        "4. Instruções de comportamento\n\n"
        "Para começar, qual é o **nome da sua empresa**?\n"
        "Se quiser sair, envie /cancelar.",
        parse_mode="Markdown",
    )
    return AGUARDANDO_NOME_EMPRESA


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start — resolve admin, cliente por link ou inicia onboarding."""
    mensagem = update.effective_message
    user_id = update.effective_user.id
    payload = _obter_payload_start(context)
    empresa_admin = await obter_empresa_por_admin(user_id)
    empresa_cliente = await obter_empresa_do_cliente(user_id)
    formatos = listar_formatos_suportados()

    if payload:
        empresa_link = await obter_empresa_por_link_token(payload)
        if not empresa_link:
            await _sincronizar_comandos_do_chat(update, context, "padrao")
            await mensagem.reply_text(
                "❌ Este link de atendimento é inválido ou expirou.\n"
                "Peça um novo link ao atendimento."
            )
            return ConversationHandler.END

        if empresa_admin:
            await _sincronizar_comandos_do_chat(update, context, "admin")
            if empresa_admin["id"] == empresa_link["id"]:
                await mensagem.reply_text(
                    f"Você já é o admin de {empresa_admin['nome']}.\n"
                    "Use /painel para gerenciar o agente e /link para compartilhar com seus clientes."
                )
            else:
                await mensagem.reply_text(
                    "🔒 Este link é destinado a clientes.\n"
                    "Seu usuário já está cadastrado como admin de outro atendimento."
                )
            return ConversationHandler.END

        await vincular_cliente_empresa(empresa_link["id"], user_id)
        await _sincronizar_comandos_do_chat(update, context, "cliente")
        await _enviar_boas_vindas_cliente(mensagem, empresa_link)
        return ConversationHandler.END

    if empresa_admin:
        await _sincronizar_comandos_do_chat(update, context, "admin")
        tem_docs = empresa_tem_documentos(empresa_admin["id"])
        dica_teste = (
            "Envie uma pergunta neste chat para testar o agente."
            if tem_docs
            else f"Envie documentos com /upload para o agente começar a funcionar. Formatos aceitos: {formatos}."
        )
        await mensagem.reply_text(
            f"👋 Sua configuração para {empresa_admin['nome']} já está ativa.\n\n"
            f"Use /painel para gerenciar o agente.\n"
            f"Use /link para gerar o link dos clientes.\n"
            f"Use o Menu do Telegram ou /ajuda para ver os comandos.\n"
            f"{dica_teste}",
        )
        return ConversationHandler.END

    if empresa_cliente:
        await _sincronizar_comandos_do_chat(update, context, "cliente")
        await _enviar_boas_vindas_cliente(mensagem, empresa_cliente)
        return ConversationHandler.END

    await _sincronizar_comandos_do_chat(update, context, "padrao")
    return await _iniciar_onboarding(update, context)


async def cmd_registrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o fluxo de registro de empresa."""
    user_id = update.effective_user.id
    empresa_admin = await obter_empresa_por_admin(user_id)
    empresa_cliente = await obter_empresa_do_cliente(user_id)
    if empresa_admin:
        await update.message.reply_text(
            f"Você já tem a empresa {empresa_admin['nome']} registrada.\n"
            f"Use /painel para gerenciar, /editar para ajustar a configuração ou /reset para recomeçar do zero.",
        )
        return ConversationHandler.END

    if empresa_cliente:
        await update.message.reply_text(_mensagem_somente_admin())
        return ConversationHandler.END

    return await _iniciar_onboarding(update, context)


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apaga a configuração atual do usuário e reinicia o onboarding."""
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return ConversationHandler.END

    _limpar_estado_usuario(context)

    try:
        await excluir_empresa_com_dados(empresa["id"])
        _remover_arquivos_empresa(empresa["id"])
    except Exception as e:
        logger.error("Erro ao resetar configuração: %s", e, exc_info=True)
        await mensagem.reply_text(
            "❌ Não foi possível resetar sua configuração agora. Tente novamente em instantes."
        )
        return ConversationHandler.END

    await mensagem.reply_text(
        f"♻️ A configuração atual de {empresa['nome']} foi apagada.\n"
        "Vamos configurar seu agente novamente."
    )

    await _sincronizar_comandos_do_chat(update, context, "padrao")
    return await _iniciar_onboarding(update, context)


async def receber_nome_empresa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o nome da empresa."""
    try:
        nome = validar_nome_empresa(update.message.text)
    except InputValidationError as e:
        await update.message.reply_text(f"⚠️ {e.message}")
        return AGUARDANDO_NOME_EMPRESA

    context.user_data["nome_empresa"] = nome
    await update.message.reply_text(
        "✅ Ótimo!\n\n"
        "Agora, qual **nome** você quer dar ao seu assistente virtual?\n"
        "_(Ex: Ana, Assistente Virtual, Suporte)_",
        parse_mode="Markdown",
    )
    return AGUARDANDO_NOME_BOT


async def receber_nome_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o nome do bot."""
    try:
        nome = validar_nome_bot(update.message.text)
    except InputValidationError as e:
        await update.message.reply_text(f"⚠️ {e.message}")
        return AGUARDANDO_NOME_BOT

    context.user_data["nome_bot"] = nome
    await update.message.reply_text(
        "👋 Qual **mensagem de saudação** o agente deve enviar quando alguém iniciar uma conversa?\n"
        "_(Ex: Olá! Bem-vindo à TechCorp. Como posso ajudar?)_",
        parse_mode="Markdown",
    )
    return AGUARDANDO_SAUDACAO


async def receber_saudacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe a saudação."""
    try:
        saudacao = validar_saudacao(update.message.text)
    except InputValidationError as e:
        await update.message.reply_text(f"⚠️ {e.message}")
        return AGUARDANDO_SAUDACAO

    context.user_data["saudacao"] = saudacao
    await update.message.reply_text(
        "📝 Por último, envie **instruções especiais** para o comportamento do bot:\n"
        "_(Ex: Sempre ofereça o telefone 0800-123-456. Não fale sobre preços de concorrentes.)_\n\n"
        "Ou envie /pular para usar as instruções padrão.",
        parse_mode="Markdown",
    )
    return AGUARDANDO_INSTRUCOES


async def receber_instrucoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe as instruções personalizadas."""
    try:
        instrucoes = validar_instrucoes(update.message.text)
    except InputValidationError as e:
        await update.message.reply_text(f"⚠️ {e.message}")
        return AGUARDANDO_INSTRUCOES

    context.user_data["instrucoes"] = instrucoes
    return await _finalizar_registro(update, context)


async def pular_instrucoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pula as instruções, usando o padrão."""
    context.user_data["instrucoes"] = "Você é um assistente de atendimento ao cliente. Responda de forma educada e profissional."
    return await _finalizar_registro(update, context)


async def _finalizar_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliza o registro da empresa."""
    user_id = update.effective_user.id
    dados = context.user_data
    formatos = listar_formatos_suportados()

    empresa_id = await criar_empresa(dados["nome_empresa"], user_id)
    await atualizar_empresa(
        empresa_id,
        nome_bot=dados["nome_bot"],
        saudacao=dados["saudacao"],
        instrucoes=dados["instrucoes"],
    )
    await _sincronizar_comandos_do_chat(update, context, "admin")

    await update.message.reply_text(
        f"🎉 Empresa cadastrada com sucesso!\n\n"
        f"📌 Empresa: {dados['nome_empresa']}\n"
        f"🤖 Assistente: {dados['nome_bot']}\n"
        f"👋 Saudação: {dados['saudacao']}\n\n"
        f"Agora envie seus documentos neste chat ou use /upload para iniciar o envio guiado.\n"
        "Use /link quando quiser gerar o link dos seus clientes.\n"
        f"Formatos aceitos: {formatos}.\n"
        "Se quiser, use /imagem para definir a imagem do seu agente.",
    )

    for key in ["nome_empresa", "nome_bot", "saudacao", "instrucoes"]:
        context.user_data.pop(key, None)

    return ConversationHandler.END


async def cancelar_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela o fluxo de registro."""
    _limpar_estado_usuario(context)
    await update.message.reply_text("❌ Registro cancelado.")
    return ConversationHandler.END
