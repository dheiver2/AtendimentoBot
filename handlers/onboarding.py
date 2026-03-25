"""Handlers de onboarding — registro de empresa e configuração inicial."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from database import (
    adicionar_admin_empresa,
    atualizar_empresa,
    criar_empresa,
    desvincular_cliente,
    excluir_empresa_com_dados,
    obter_empresa_do_cliente,
    obter_empresa_por_admin,
    obter_empresa_por_admin_link_token,
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
    AGUARDANDO_CONFIRMACAO_REGISTRO,
    AGUARDANDO_CONFIRMACAO_RESET,
    AGUARDANDO_INSTRUCOES,
    AGUARDANDO_NOME_BOT,
    AGUARDANDO_NOME_EMPRESA,
    AGUARDANDO_SAUDACAO,
    _enviar_boas_vindas_cliente,
    _extrair_token_link_admin,
    _limpar_estado_usuario,
    _mensagem_somente_admin,
    _obter_empresa_admin_ou_responder,
    _obter_payload_start,
    _remover_arquivos_empresa,
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
        admin_link_token = _extrair_token_link_admin(payload)
        if admin_link_token:
            empresa_link_admin = await obter_empresa_por_admin_link_token(admin_link_token)
            if not empresa_link_admin:
                await _sincronizar_comandos_do_chat(update, context, "padrao")
                await mensagem.reply_text(
                    "❌ Este link de admin é inválido ou expirou.\n"
                    "Peça um novo link administrativo ao responsável."
                )
                return ConversationHandler.END

            if empresa_admin:
                await _sincronizar_comandos_do_chat(update, context, "admin")
                if empresa_admin["id"] == empresa_link_admin["id"]:
                    await mensagem.reply_text(
                        f"Você já é admin de {empresa_admin['nome']}.\n"
                        "Use /painel para gerenciar o agente e /link para compartilhar os acessos."
                    )
                else:
                    await mensagem.reply_text(
                        "🔒 Este link de admin pertence a outra empresa.\n"
                        "Seu usuário já está cadastrado como admin de outro atendimento."
                    )
                return ConversationHandler.END

            await adicionar_admin_empresa(empresa_link_admin["id"], user_id)
            await _sincronizar_comandos_do_chat(update, context, "admin")
            await mensagem.reply_text(
                f"🔐 Seu acesso de admin para {empresa_link_admin['nome']} foi ativado.\n\n"
                "Use /painel para gerenciar o agente, /link para compartilhar os acessos "
                "e envie uma pergunta neste chat para testar."
            )
            return ConversationHandler.END

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
        context.user_data.pop("identidade_visual_enviada", None)
        await _enviar_boas_vindas_cliente(mensagem, empresa_link)
        context.user_data["identidade_visual_enviada"] = True
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
            f"Use /link para gerar os links de admin e cliente.\n"
            f"Use o Menu do Telegram ou /ajuda para ver os comandos.\n"
            f"{dica_teste}",
        )
        return ConversationHandler.END

    if empresa_cliente:
        await _sincronizar_comandos_do_chat(update, context, "cliente")
        context.user_data.pop("identidade_visual_enviada", None)
        await _enviar_boas_vindas_cliente(mensagem, empresa_cliente)
        context.user_data["identidade_visual_enviada"] = True
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
    """Exibe confirmação antes de apagar a configuração do usuário."""
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return ConversationHandler.END

    _limpar_estado_usuario(context)

    botoes = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Sim, apagar tudo", callback_data="reset_confirmar"),
            InlineKeyboardButton("❌ Cancelar", callback_data="reset_cancelar"),
        ]
    ])
    await mensagem.reply_text(
        f"⚠️ Tem certeza que deseja apagar toda a configuração de *{empresa['nome']}*?\n\n"
        "Isso irá remover documentos, FAQs, histórico e todos os dados associados. "
        "Esta ação é irreversível.",
        reply_markup=botoes,
        parse_mode="Markdown",
    )
    return AGUARDANDO_CONFIRMACAO_RESET


async def reset_confirmar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma e executa o reset após aprovação do usuário."""
    await update.callback_query.answer()
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return ConversationHandler.END

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
        f"♻️ A configuração de *{empresa['nome']}* foi apagada.\n"
        "Vamos configurar seu agente novamente.",
        parse_mode="Markdown",
    )

    await _sincronizar_comandos_do_chat(update, context, "padrao")
    return await _iniciar_onboarding(update, context)


async def reset_cancelar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela o reset e avisa o usuário."""
    await update.callback_query.answer()
    await update.effective_message.reply_text(
        "✅ Reset cancelado. Sua configuração está intacta."
    )
    return ConversationHandler.END


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
    """Recebe as instruções personalizadas e exibe o resumo para confirmação."""
    try:
        instrucoes = validar_instrucoes(update.message.text)
    except InputValidationError as e:
        await update.message.reply_text(f"⚠️ {e.message}")
        return AGUARDANDO_INSTRUCOES

    context.user_data["instrucoes"] = instrucoes
    return await _mostrar_resumo_registro(update, context)


async def pular_instrucoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pula as instruções, usando o padrão, e exibe o resumo para confirmação."""
    context.user_data["instrucoes"] = "Você é um assistente de atendimento ao cliente. Responda de forma educada e profissional."
    return await _mostrar_resumo_registro(update, context)


async def _mostrar_resumo_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe o resumo da configuração para o admin revisar antes de confirmar."""
    dados = context.user_data
    instrucoes_resumidas = dados["instrucoes"]
    if len(instrucoes_resumidas) > 100:
        instrucoes_resumidas = instrucoes_resumidas[:100] + "..."

    botoes = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirmar", callback_data="registro_confirmar"),
            InlineKeyboardButton("🔄 Recomeçar", callback_data="registro_recomecar"),
        ]
    ])
    await update.effective_message.reply_text(
        "📋 *Revise sua configuração antes de confirmar:*\n\n"
        f"📌 Empresa: {dados['nome_empresa']}\n"
        f"🤖 Assistente: {dados['nome_bot']}\n"
        f"👋 Saudação: {dados['saudacao']}\n"
        f"📝 Instruções: {instrucoes_resumidas}\n\n"
        "Confirma estas informações?",
        reply_markup=botoes,
        parse_mode="Markdown",
    )
    return AGUARDANDO_CONFIRMACAO_REGISTRO


async def confirmar_registro_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma e finaliza o registro da empresa."""
    await update.callback_query.answer()
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

    await update.effective_message.reply_text(
        f"🎉 Empresa cadastrada com sucesso!\n\n"
        f"Agora envie seus documentos neste chat ou use /upload para iniciar o envio guiado.\n"
        "Use /link quando quiser gerar o link dos seus clientes.\n"
        f"Formatos aceitos: {formatos}.\n"
        "Se quiser, use /imagem para definir a imagem do seu agente.",
    )

    for key in ["nome_empresa", "nome_bot", "saudacao", "instrucoes"]:
        context.user_data.pop(key, None)

    return ConversationHandler.END


async def recomecar_registro_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Descarta os dados e reinicia o onboarding do zero."""
    await update.callback_query.answer()
    _limpar_estado_usuario(context)
    await update.effective_message.reply_text(
        "🔄 Vamos recomeçar. Qual é o nome da sua empresa?"
    )
    return AGUARDANDO_NOME_EMPRESA


async def cancelar_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela o fluxo de registro."""
    _limpar_estado_usuario(context)
    await update.message.reply_text("❌ Registro cancelado.")
    return ConversationHandler.END


async def cmd_sair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Desvincula o cliente do atendimento atual."""
    user_id = update.effective_user.id
    empresa_admin = await obter_empresa_por_admin(user_id)
    if empresa_admin:
        await update.message.reply_text(
            "🔒 Admins não podem usar /sair. Use /reset para reconfigurar do zero."
        )
        return

    empresa = await obter_empresa_do_cliente(user_id)
    if not empresa:
        await update.message.reply_text(
            "Você não está vinculado a nenhum atendimento no momento."
        )
        return

    desvinculado = await desvincular_cliente(user_id)
    if desvinculado:
        context.user_data.pop("identidade_visual_enviada", None)
        await _sincronizar_comandos_do_chat(update, context, "padrao")
        await update.message.reply_text(
            f"✅ Você saiu do atendimento de *{empresa['nome']}*.\n\n"
            "Se quiser entrar novamente, use o link de atendimento enviado pelo administrador.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "❌ Não foi possível sair do atendimento agora. Tente novamente em instantes."
        )
