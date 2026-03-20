"""Handlers do bot Telegram — fluxo de onboarding, configuração e teste."""
import logging
import os
import shutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from database import (
    criar_empresa,
    obter_empresa_por_usuario,
    atualizar_empresa,
    excluir_empresa_com_dados,
    excluir_documento,
    obter_documento_por_id,
    registrar_documento,
    listar_documentos,
    registrar_conversa,
)
from bot_profile_photo import (
    empresa_tem_imagem,
    excluir_imagem_empresa,
    obter_caminho_imagem_empresa,
    imagem_suportada,
    listar_formatos_imagem_suportados,
    salvar_imagem_empresa,
)
from config import IMAGES_DIR, PDFS_DIR, VECTOR_STORES_DIR
from document_processor import (
    arquivo_suportado,
    listar_formatos_suportados,
    processar_documento,
    processar_documento_salvo,
)
from vector_store import adicionar_documentos, empresa_tem_documentos, substituir_documentos
from rag_chain import gerar_resposta

logger = logging.getLogger(__name__)

# ── Estados do ConversationHandler de onboarding ──
(
    AGUARDANDO_NOME_EMPRESA,
    AGUARDANDO_NOME_BOT,
    AGUARDANDO_SAUDACAO,
    AGUARDANDO_INSTRUCOES,
    AGUARDANDO_DOCUMENTO,
    EDITANDO_CAMPO,
    AGUARDANDO_IMAGEM_BOT,
) = range(7)


def _limpar_estado_usuario(context: ContextTypes.DEFAULT_TYPE):
    """Remove estados temporários do usuário no bot."""
    for key in [
        "nome_empresa",
        "nome_bot",
        "saudacao",
        "instrucoes",
        "empresa_upload_id",
        "empresa_editar_id",
        "aguardando_imagem_bot",
        "campo_editando",
        "campo_editando_nome",
    ]:
        context.user_data.pop(key, None)


def _remover_arquivos_empresa(empresa_id: int):
    """Apaga documentos e vector store da empresa resetada."""
    for diretorio_base in [PDFS_DIR, VECTOR_STORES_DIR, IMAGES_DIR]:
        caminho = os.path.join(diretorio_base, str(empresa_id))
        if os.path.isdir(caminho):
            shutil.rmtree(caminho, ignore_errors=True)


async def _enviar_preview_imagem_empresa(
    mensagem,
    empresa_id: int,
    legenda: str,
):
    """Envia a imagem atual da empresa como preview, quando existir."""
    caminho = obter_caminho_imagem_empresa(empresa_id)
    if not os.path.exists(caminho):
        return

    with open(caminho, "rb") as arquivo:
        await mensagem.reply_photo(photo=arquivo, caption=legenda)


def _teclado_painel() -> InlineKeyboardMarkup:
    """Retorna o teclado inline principal do painel."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📄 Upload", callback_data="painel_upload"),
                InlineKeyboardButton("📚 Documentos", callback_data="painel_documentos"),
            ],
            [
                InlineKeyboardButton("🖼️ Imagem", callback_data="painel_imagem"),
                InlineKeyboardButton("⚙️ Editar", callback_data="painel_editar"),
            ],
            [
                InlineKeyboardButton("📊 Status", callback_data="painel_status"),
                InlineKeyboardButton("❓ Ajuda", callback_data="painel_ajuda"),
            ],
            [
                InlineKeyboardButton("🔄 Atualizar", callback_data="painel_refresh"),
                InlineKeyboardButton("♻️ Reset", callback_data="painel_reset"),
            ],
        ]
    )


def _caminho_documento(empresa_id: int, nome_arquivo: str) -> str:
    """Retorna o caminho absoluto do documento salvo no disco."""
    return os.path.join(PDFS_DIR, str(empresa_id), nome_arquivo)


def _rotulo_documento(nome_arquivo: str, indice: int) -> str:
    """Gera um rótulo curto para um documento na interface."""
    extensao = os.path.splitext(nome_arquivo)[1].lower()
    base = os.path.splitext(nome_arquivo)[0]
    if len(base) > 18:
        base = f"{base[:15]}..."
    return f"{indice}. {base}{extensao}"


def _teclado_documentos(documentos: list[dict]) -> InlineKeyboardMarkup:
    """Retorna o teclado inline de gestão da base de conhecimento."""
    botoes = [
        [
            InlineKeyboardButton("📄 Upload", callback_data="painel_upload"),
            InlineKeyboardButton("🔁 Reindexar Base", callback_data="docs_reindexar"),
        ],
        [
            InlineKeyboardButton("🔄 Atualizar", callback_data="docs_refresh"),
            InlineKeyboardButton("⬅️ Painel", callback_data="docs_painel"),
        ],
    ]

    for indice, documento in enumerate(documentos, 1):
        rotulo = _rotulo_documento(documento["nome_arquivo"], indice)
        botoes.append(
            [
                InlineKeyboardButton(f"🔄 {rotulo}", callback_data=f"docs_reprocessar:{documento['id']}"),
                InlineKeyboardButton(f"🗑 {indice}", callback_data=f"docs_excluir:{documento['id']}"),
            ]
        )

    return InlineKeyboardMarkup(botoes)


async def _editar_ou_responder(update: Update, texto: str, reply_markup: InlineKeyboardMarkup | None = None):
    """Edita a mensagem de callback quando possível, ou envia uma nova resposta."""
    mensagem = update.effective_message
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(texto, reply_markup=reply_markup)
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        return

    await mensagem.reply_text(texto, reply_markup=reply_markup)


async def _reindexar_base_empresa(empresa_id: int) -> tuple[int, list[str]]:
    """Reconstrói o índice vetorial da empresa a partir dos documentos salvos."""
    documentos = await listar_documentos(empresa_id)
    documentos_processados: list[tuple[list[str], dict]] = []
    avisos: list[str] = []

    for documento in documentos:
        caminho = _caminho_documento(empresa_id, documento["nome_arquivo"])
        if not os.path.exists(caminho):
            avisos.append(f"{documento['nome_arquivo']}: arquivo não encontrado no disco.")
            continue

        try:
            chunks = processar_documento_salvo(caminho)
        except Exception as e:
            avisos.append(f"{documento['nome_arquivo']}: {e}")
            continue

        documentos_processados.append(
            (
                chunks,
                {
                    "arquivo": documento["nome_arquivo"],
                    "documento_id": documento["id"],
                },
            )
        )

    substituir_documentos(empresa_id, documentos_processados)
    return len(documentos_processados), avisos


# ═══════════════════════════════════════════════════
#  COMANDOS GERAIS
# ═══════════════════════════════════════════════════

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
    """Comando /start — abre a configuração do usuário ou inicia o onboarding."""
    user_id = update.effective_user.id
    empresa = await obter_empresa_por_usuario(user_id)
    formatos = listar_formatos_suportados()

    if empresa:
        tem_docs = empresa_tem_documentos(empresa["id"])
        dica_teste = (
            "Envie uma pergunta neste chat para testar o agente."
            if tem_docs
            else f"Envie documentos com /upload para o agente começar a funcionar. Formatos aceitos: {formatos}."
        )
        await update.message.reply_text(
            f"👋 Sua configuração para {empresa['nome']} já está ativa.\n\n"
            f"Use /painel para gerenciar o agente.\n"
            f"Use o Menu do Telegram ou /ajuda para ver os comandos.\n"
            f"{dica_teste}",
        )
        return ConversationHandler.END

    return await _iniciar_onboarding(update, context)


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ajuda."""
    mensagem = update.effective_message
    formatos = listar_formatos_suportados()
    formatos_imagem = listar_formatos_imagem_suportados()
    texto = (
        "📋 Comandos disponíveis:\n\n"
        "Cada usuário do Telegram configura seu próprio agente neste bot.\n\n"
        "/start — Iniciar a configuração inicial\n"
        "/registrar — Iniciar o cadastro da empresa\n"
        "/painel — Painel de gerenciamento\n"
        "/upload — Entrar no modo de envio de documentos\n"
        "/imagem — Atualizar a imagem do agente\n"
        "/documentos — Gerenciar a base de conhecimento\n"
        "/editar — Editar configurações do bot\n"
        "/reset — Apagar a configuração atual e começar de novo\n"
        "/status — Ver status do bot\n\n"
        f"Você pode enviar documentos diretamente neste chat a qualquer momento.\n"
        f"Formatos aceitos: {formatos}.\n"
        f"Para /imagem, envie foto do Telegram ou imagem em: {formatos_imagem}.\n"
        "Use /documentos para reprocessar, excluir arquivos e reconstruir a base.\n"
        "Use o botão Menu do Telegram ou /painel para navegar mais rápido.\n"
        "A imagem enviada em /imagem fica vinculada só ao seu agente.\n"
        "Depois de configurar e enviar documentos, envie uma mensagem de texto para testar seu agente."
    )
    await mensagem.reply_text(texto)


# ═══════════════════════════════════════════════════
#  ONBOARDING — Registro de empresa
# ═══════════════════════════════════════════════════

async def cmd_registrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o fluxo de registro de empresa."""
    user_id = update.effective_user.id
    empresa = await obter_empresa_por_usuario(user_id)
    if empresa:
        await update.message.reply_text(
            f"Você já tem a empresa {empresa['nome']} registrada.\n"
            f"Use /painel para gerenciar, /editar para ajustar a configuração ou /reset para recomeçar do zero.",
        )
        return ConversationHandler.END

    return await _iniciar_onboarding(update, context)


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apaga a configuração atual do usuário e reinicia o onboarding."""
    mensagem = update.effective_message
    user_id = update.effective_user.id
    empresa = await obter_empresa_por_usuario(user_id)

    _limpar_estado_usuario(context)

    if empresa:
        try:
            await excluir_empresa_com_dados(empresa["id"])
            _remover_arquivos_empresa(empresa["id"])
        except Exception as e:
            logger.error(f"Erro ao resetar configuração: {e}", exc_info=True)
            await mensagem.reply_text(
                "❌ Não foi possível resetar sua configuração agora. Tente novamente em instantes."
            )
            return ConversationHandler.END

        await mensagem.reply_text(
            f"♻️ A configuração atual de {empresa['nome']} foi apagada.\n"
            "Vamos configurar seu agente novamente."
        )
    else:
        await mensagem.reply_text(
            "♻️ Nenhuma configuração ativa foi encontrada.\n"
            "Vamos iniciar o onboarding do zero."
        )

    return await _iniciar_onboarding(update, context)


async def receber_nome_empresa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o nome da empresa."""
    context.user_data["nome_empresa"] = update.message.text.strip()
    await update.message.reply_text(
        "✅ Ótimo!\n\n"
        "Agora, qual **nome** você quer dar ao seu assistente virtual?\n"
        "_(Ex: Ana, Assistente Virtual, Suporte)_",
        parse_mode="Markdown",
    )
    return AGUARDANDO_NOME_BOT


async def receber_nome_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o nome do bot."""
    context.user_data["nome_bot"] = update.message.text.strip()
    await update.message.reply_text(
        "👋 Qual **mensagem de saudação** o agente deve enviar quando alguém iniciar uma conversa?\n"
        "_(Ex: Olá! Bem-vindo à TechCorp. Como posso ajudar?)_",
        parse_mode="Markdown",
    )
    return AGUARDANDO_SAUDACAO


async def receber_saudacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe a saudação."""
    context.user_data["saudacao"] = update.message.text.strip()
    await update.message.reply_text(
        "📝 Por último, envie **instruções especiais** para o comportamento do bot:\n"
        "_(Ex: Sempre ofereça o telefone 0800-123-456. Não fale sobre preços de concorrentes.)_\n\n"
        "Ou envie /pular para usar as instruções padrão.",
        parse_mode="Markdown",
    )
    return AGUARDANDO_INSTRUCOES


async def receber_instrucoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe as instruções personalizadas."""
    instrucoes = update.message.text.strip()
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

    await update.message.reply_text(
        f"🎉 Empresa cadastrada com sucesso!\n\n"
        f"📌 Empresa: {dados['nome_empresa']}\n"
        f"🤖 Assistente: {dados['nome_bot']}\n"
        f"👋 Saudação: {dados['saudacao']}\n\n"
        f"Agora envie seus documentos neste chat ou use /upload para iniciar o envio guiado.\n"
        f"Formatos aceitos: {formatos}.\n"
        "Se quiser, use /imagem para definir a imagem do seu agente.",
    )

    # Limpa dados temporários
    for key in ["nome_empresa", "nome_bot", "saudacao", "instrucoes"]:
        context.user_data.pop(key, None)

    return ConversationHandler.END


async def cancelar_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela o fluxo de registro."""
    _limpar_estado_usuario(context)
    await update.message.reply_text("❌ Registro cancelado.")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════
#  UPLOAD DE DOCUMENTOS
# ═══════════════════════════════════════════════════

async def cmd_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o fluxo de upload de documentos."""
    mensagem = update.effective_message
    user_id = update.effective_user.id
    empresa = await obter_empresa_por_usuario(user_id)
    if not empresa:
        await mensagem.reply_text("❌ Seu agente ainda não foi configurado. Use /start primeiro.")
        return ConversationHandler.END

    context.user_data["empresa_upload_id"] = empresa["id"]
    formatos = listar_formatos_suportados()
    await mensagem.reply_text(
        "📄 Envio de documentos\n\n"
        "Envie seus arquivos agora. Você pode enviar vários, um de cada vez.\n"
        f"Formatos aceitos: {formatos}.\n"
        "Quando terminar, envie /pronto.\n"
        "Se preferir, também pode mandar documentos diretamente fora deste modo e eles serão processados.",
    )
    return AGUARDANDO_DOCUMENTO


async def _processar_documento_enviado(
    update: Update,
    empresa_id: int,
    modo_upload: bool,
):
    """Processa um documento enviado e responde ao usuário."""
    documento = update.message.document
    nome_arquivo = documento.file_name or ""

    if not documento or not arquivo_suportado(nome_arquivo):
        await update.message.reply_text(
            f"⚠️ Formato não suportado. Envie um destes formatos: {listar_formatos_suportados()}."
        )
        return AGUARDANDO_DOCUMENTO if modo_upload else None

    await update.message.reply_text("⏳ Processando documento...")

    try:
        arquivo = await documento.get_file()
        conteudo = await arquivo.download_as_bytearray()
        arquivo_existia = os.path.exists(_caminho_documento(empresa_id, nome_arquivo))

        chunks = processar_documento(empresa_id, nome_arquivo, bytes(conteudo))
        await registrar_documento(empresa_id, nome_arquivo)

        if arquivo_existia:
            quantidade_processada, avisos = await _reindexar_base_empresa(empresa_id)
            resumo = _resumo_reindexacao(quantidade_processada, avisos)
            mensagem_sucesso = (
                f"✅ {nome_arquivo} atualizado com sucesso!\n"
                f"{resumo}\n\n"
                + (
                    "Envie mais arquivos ou /pronto para finalizar."
                    if modo_upload
                    else "Você pode enviar mais documentos ou já testar o agente com uma pergunta."
                )
            )
            await update.message.reply_text(mensagem_sucesso)
            return AGUARDANDO_DOCUMENTO if modo_upload else None

        adicionar_documentos(empresa_id, chunks, {"arquivo": nome_arquivo})

        mensagem_sucesso = (
            f"✅ {nome_arquivo} processado com sucesso!\n"
            f"📊 {len(chunks)} trechos indexados.\n\n"
            + (
                "Envie mais arquivos ou /pronto para finalizar."
                if modo_upload
                else "Você pode enviar mais documentos ou já testar o agente com uma pergunta."
            )
        )

        await update.message.reply_text(
            mensagem_sucesso,
        )
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
    except Exception as e:
        logger.error(f"Erro ao processar documento: {e}", exc_info=True)
        await update.message.reply_text("❌ Erro ao processar o documento. Tente novamente.")

    return AGUARDANDO_DOCUMENTO if modo_upload else None


async def receber_documento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe e processa um documento no fluxo guiado de upload."""
    empresa_id = context.user_data.get("empresa_upload_id")
    if not empresa_id:
        await update.message.reply_text("❌ Erro interno. Use /upload novamente.")
        return ConversationHandler.END

    return await _processar_documento_enviado(update, empresa_id, modo_upload=True)


async def receber_documento_direto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa documentos enviados diretamente no chat, sem exigir /upload."""
    user_id = update.effective_user.id
    empresa = await obter_empresa_por_usuario(user_id)
    if not empresa:
        await update.message.reply_text(
            "👋 Seu agente ainda não foi configurado.\n"
            "Envie /start para iniciar a configuração antes de mandar documentos."
        )
        return

    await _processar_documento_enviado(update, empresa["id"], modo_upload=False)


async def finalizar_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliza o fluxo de upload."""
    context.user_data.pop("empresa_upload_id", None)
    await update.message.reply_text(
        "✅ **Upload concluído!**\n\n"
        "Seus documentos foram indexados e o bot já pode responder perguntas baseadas neles.\n"
        "Você pode voltar a usar /upload a qualquer momento para adicionar novos arquivos.\n"
        "Use /status para ver o estado do seu bot ou envie uma pergunta para testar.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════
#  IMAGEM DO AGENTE
# ═══════════════════════════════════════════════════

async def cmd_imagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o fluxo para atualizar a imagem própria do agente."""
    mensagem = update.effective_message
    user_id = update.effective_user.id
    empresa = await obter_empresa_por_usuario(user_id)
    if not empresa:
        await mensagem.reply_text("❌ Seu agente ainda não foi configurado. Use /start primeiro.")
        return ConversationHandler.END

    if context.args and context.args[0].lower() in {"remover", "apagar"}:
        try:
            removida = excluir_imagem_empresa(empresa["id"])
            if removida:
                await mensagem.reply_text("✅ A imagem do seu agente foi removida.")
            else:
                await mensagem.reply_text("ℹ️ Seu agente não tinha uma imagem configurada.")
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Erro ao remover imagem do agente: {e}", exc_info=True)
            await mensagem.reply_text(
                "❌ Não foi possível remover a imagem do seu agente agora. Tente novamente em instantes."
            )
        return ConversationHandler.END

    formatos_imagem = listar_formatos_imagem_suportados()
    status_imagem = "já configurada" if empresa_tem_imagem(empresa["id"]) else "ainda não configurada"
    await mensagem.reply_text(
        "🖼️ Imagem do agente\n\n"
        "Envie uma foto do Telegram ou um arquivo de imagem agora.\n"
        f"Formatos aceitos: {formatos_imagem}.\n"
        "A imagem será convertida para JPG se necessário e ficará vinculada apenas ao seu agente.\n"
        f"Status atual: {status_imagem}.\n"
        "Se quiser remover a imagem atual, envie /imagem remover.\n"
        "Se quiser sair, envie /cancelar."
    )
    return AGUARDANDO_IMAGEM_BOT


async def _baixar_imagem_enviada(update: Update) -> tuple[bytes, str]:
    """Baixa a imagem enviada como foto ou documento."""
    if update.message.photo:
        arquivo = await update.message.photo[-1].get_file()
        conteudo = await arquivo.download_as_bytearray()
        return bytes(conteudo), "imagem.jpg"

    documento = update.message.document
    nome_arquivo = documento.file_name if documento else None
    mime_type = documento.mime_type if documento else None

    if documento and imagem_suportada(nome_arquivo, mime_type):
        arquivo = await documento.get_file()
        conteudo = await arquivo.download_as_bytearray()
        return bytes(conteudo), nome_arquivo or "imagem"

    raise ValueError(
        f"Envie uma foto do Telegram ou um arquivo de imagem em um destes formatos: {listar_formatos_imagem_suportados()}."
    )


async def receber_imagem_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe a imagem do agente e salva a configuração do usuário."""
    empresa = await obter_empresa_por_usuario(update.effective_user.id)
    if not empresa:
        await update.message.reply_text("❌ Seu agente ainda não foi configurado. Use /start primeiro.")
        return ConversationHandler.END

    try:
        conteudo_bytes, _ = await _baixar_imagem_enviada(update)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return AGUARDANDO_IMAGEM_BOT

    await update.message.reply_text("⏳ Atualizando a imagem do seu agente...")

    try:
        salvar_imagem_empresa(empresa["id"], conteudo_bytes)
        await update.message.reply_text(
            "✅ A imagem do seu agente foi atualizada com sucesso."
        )
        await _enviar_preview_imagem_empresa(
            update.message,
            empresa["id"],
            "Preview da imagem atual do seu agente.",
        )
        return ConversationHandler.END
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return AGUARDANDO_IMAGEM_BOT
    except Exception as e:
        logger.error(f"Erro ao atualizar imagem do agente: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Não foi possível atualizar a imagem do seu agente agora. Tente novamente."
        )
        return AGUARDANDO_IMAGEM_BOT


async def painel_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Atualiza o painel principal pelo botão inline."""
    await update.callback_query.answer()
    await cmd_painel(update, context)


async def painel_documentos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abre a listagem de documentos a partir do painel."""
    await update.callback_query.answer()
    await cmd_documentos(update, context)


async def painel_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abre o status a partir do painel."""
    await update.callback_query.answer()
    await cmd_status(update, context)


async def painel_ajuda_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abre a ajuda a partir do painel."""
    await update.callback_query.answer()
    await cmd_ajuda(update, context)


async def painel_upload_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o upload a partir do painel."""
    await update.callback_query.answer()
    return await cmd_upload(update, context)


async def painel_imagem_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia a troca de imagem a partir do painel."""
    await update.callback_query.answer()
    return await cmd_imagem(update, context)


async def painel_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o reset a partir do painel."""
    await update.callback_query.answer()
    return await cmd_reset(update, context)


async def painel_editar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia a edição a partir do painel."""
    await update.callback_query.answer()
    return await cmd_editar(update, context)


# ═══════════════════════════════════════════════════
#  PAINEL E STATUS
# ═══════════════════════════════════════════════════

async def cmd_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra o painel de gerenciamento."""
    mensagem = update.effective_message
    user_id = update.effective_user.id
    empresa = await obter_empresa_por_usuario(user_id)
    if not empresa:
        await mensagem.reply_text("❌ Seu agente ainda não foi configurado. Use /start primeiro.")
        return

    docs = await listar_documentos(empresa["id"])
    tem_docs = empresa_tem_documentos(empresa["id"])
    tem_imagem = empresa_tem_imagem(empresa["id"])

    status_emoji = "🟢" if tem_docs else "🔴"
    status_texto = "Pronto para teste" if tem_docs else "Sem documentos — envie arquivos no chat ou use /upload"
    imagem_texto = "Configurada" if tem_imagem else "Não configurada"

    texto = (
        f"📊 Painel — {empresa['nome']}\n\n"
        f"🤖 Assistente: {empresa['nome_bot']}\n"
        f"👋 Saudação: {empresa['saudacao']}\n"
        f"🖼️ Imagem: {imagem_texto}\n"
        f"📄 Documentos: {len(docs)}\n"
        f"{status_emoji} Status: {status_texto}\n\n"
        f"Use os botões abaixo ou o Menu do Telegram para navegar.\n\n"
        f"Você pode enviar documentos diretamente neste chat e testar o agente com perguntas."
    )
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(texto, reply_markup=_teclado_painel())
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        return

    await mensagem.reply_text(texto, reply_markup=_teclado_painel())


async def cmd_documentos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra a gestão da base de conhecimento da empresa."""
    user_id = update.effective_user.id
    empresa = await obter_empresa_por_usuario(user_id)
    if not empresa:
        await update.effective_message.reply_text("❌ Seu agente ainda não foi configurado. Use /start primeiro.")
        return

    docs = await listar_documentos(empresa["id"])
    if not docs:
        await _editar_ou_responder(
            update,
            (
                f"📭 Base de conhecimento — {empresa['nome']}\n\n"
                "Nenhum documento enviado ainda.\n"
                "Use /upload ou envie arquivos diretamente neste chat para começar."
            ),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("📄 Upload", callback_data="painel_upload"),
                        InlineKeyboardButton("⬅️ Painel", callback_data="docs_painel"),
                    ]
                ]
            ),
        )
        return

    linhas = [
        f"📚 Base de conhecimento — {empresa['nome']}\n",
        "Use os botões abaixo para reprocessar, excluir ou reindexar a base.\n",
    ]
    for i, doc in enumerate(docs, 1):
        linhas.append(f"{i}. {doc['nome_arquivo']} — {doc['carregado_em']}")

    await _editar_ou_responder(
        update,
        "\n".join(linhas),
        reply_markup=_teclado_documentos(docs),
    )


def _resumo_reindexacao(quantidade_processada: int, avisos: list[str]) -> str:
    """Formata o resumo de uma reindexação para o usuário."""
    linhas = [f"📊 Base atualizada com {quantidade_processada} documento(s) válido(s)."]
    if avisos:
        linhas.append("")
        linhas.append("⚠️ Avisos:")
        for aviso in avisos[:3]:
            linhas.append(f"- {aviso}")
        if len(avisos) > 3:
            linhas.append(f"- ... e mais {len(avisos) - 3} aviso(s).")
    return "\n".join(linhas)


async def docs_painel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Volta para o painel principal a partir da gestão da base."""
    await update.callback_query.answer()
    await cmd_painel(update, context)


async def docs_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Atualiza a visão da base de conhecimento."""
    await update.callback_query.answer()
    await cmd_documentos(update, context)


async def docs_reindexar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reconstrói toda a base de conhecimento da empresa."""
    query = update.callback_query
    await query.answer()

    empresa = await obter_empresa_por_usuario(update.effective_user.id)
    if not empresa:
        await query.message.reply_text("❌ Seu agente ainda não foi configurado. Use /start primeiro.")
        return

    try:
        quantidade_processada, avisos = await _reindexar_base_empresa(empresa["id"])
        await query.message.reply_text(
            "✅ Base reindexada com sucesso.\n"
            f"{_resumo_reindexacao(quantidade_processada, avisos)}"
        )
        await cmd_documentos(update, context)
    except Exception as e:
        logger.error(f"Erro ao reindexar base da empresa {empresa['id']}: {e}", exc_info=True)
        await query.message.reply_text("❌ Não foi possível reindexar a base agora. Tente novamente.")


async def docs_reprocessar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reprocessa um documento e reconstrói a base da empresa."""
    query = update.callback_query
    await query.answer()

    empresa = await obter_empresa_por_usuario(update.effective_user.id)
    if not empresa:
        await query.message.reply_text("❌ Seu agente ainda não foi configurado. Use /start primeiro.")
        return

    documento_id = int(query.data.split(":", 1)[1])
    documento = await obter_documento_por_id(empresa["id"], documento_id)
    if not documento:
        await query.message.reply_text("⚠️ Documento não encontrado.")
        await cmd_documentos(update, context)
        return

    caminho = _caminho_documento(empresa["id"], documento["nome_arquivo"])
    if not os.path.exists(caminho):
        await query.message.reply_text("⚠️ O arquivo não foi encontrado no disco.")
        await cmd_documentos(update, context)
        return

    try:
        quantidade_processada, avisos = await _reindexar_base_empresa(empresa["id"])
        await query.message.reply_text(
            f"✅ Documento reprocessado: {documento['nome_arquivo']}\n"
            f"{_resumo_reindexacao(quantidade_processada, avisos)}"
        )
        await cmd_documentos(update, context)
    except Exception as e:
        logger.error(f"Erro ao reprocessar documento {documento_id}: {e}", exc_info=True)
        await query.message.reply_text("❌ Não foi possível reprocessar esse documento agora. Tente novamente.")


async def docs_excluir_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exclui um documento da base e reconstrói o índice da empresa."""
    query = update.callback_query
    await query.answer()

    empresa = await obter_empresa_por_usuario(update.effective_user.id)
    if not empresa:
        await query.message.reply_text("❌ Seu agente ainda não foi configurado. Use /start primeiro.")
        return

    documento_id = int(query.data.split(":", 1)[1])
    documento = await obter_documento_por_id(empresa["id"], documento_id)
    if not documento:
        await query.message.reply_text("⚠️ Documento não encontrado.")
        await cmd_documentos(update, context)
        return

    caminho = _caminho_documento(empresa["id"], documento["nome_arquivo"])

    try:
        if os.path.exists(caminho):
            os.remove(caminho)

        removido = await excluir_documento(empresa["id"], documento_id)
        if not removido:
            await query.message.reply_text("⚠️ Documento não encontrado.")
            await cmd_documentos(update, context)
            return

        quantidade_processada, avisos = await _reindexar_base_empresa(empresa["id"])
        await query.message.reply_text(
            f"🗑 Documento excluído: {documento['nome_arquivo']}\n"
            f"{_resumo_reindexacao(quantidade_processada, avisos)}"
        )
        await cmd_documentos(update, context)
    except Exception as e:
        logger.error(f"Erro ao excluir documento {documento_id}: {e}", exc_info=True)
        await query.message.reply_text("❌ Não foi possível excluir esse documento agora. Tente novamente.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra o status atual do bot."""
    mensagem = update.effective_message
    user_id = update.effective_user.id
    empresa = await obter_empresa_por_usuario(user_id)
    if not empresa:
        await mensagem.reply_text("❌ Seu agente ainda não foi configurado. Use /start primeiro.")
        return

    tem_docs = empresa_tem_documentos(empresa["id"])
    docs = await listar_documentos(empresa["id"])
    tem_imagem = empresa_tem_imagem(empresa["id"])
    imagem_texto = "Configurada" if tem_imagem else "Não configurada"

    if tem_docs:
        texto = (
            f"🟢 Agente CONFIGURADO\n\n"
            f"Empresa: {empresa['nome']}\n"
            f"Assistente: {empresa['nome_bot']}\n"
            f"Imagem: {imagem_texto}\n"
            f"Documentos indexados: {len(docs)}\n\n"
            f"Seu agente já pode ser testado neste chat."
        )
    else:
        texto = (
            f"🟡 Agente INCOMPLETO\n\n"
            f"Empresa: {empresa['nome']}\n"
            f"Imagem: {imagem_texto}\n"
            f"Nenhum documento carregado.\n\n"
            f"Envie documentos neste chat ou use /upload para concluir a configuração."
        )
    await mensagem.reply_text(texto)
    if tem_imagem:
        await _enviar_preview_imagem_empresa(
            mensagem,
            empresa["id"],
            "Imagem atual do seu agente.",
        )


# ═══════════════════════════════════════════════════
#  EDIÇÃO DE CONFIGURAÇÕES
# ═══════════════════════════════════════════════════

async def cmd_editar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra opções de edição."""
    mensagem = update.effective_message
    user_id = update.effective_user.id
    empresa = await obter_empresa_por_usuario(user_id)
    if not empresa:
        await mensagem.reply_text("❌ Seu agente ainda não foi configurado. Use /start primeiro.")
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


CAMPOS_EDITAVEIS = {
    "editar_nome": ("nome", "nome da empresa"),
    "editar_nome_bot": ("nome_bot", "nome do assistente"),
    "editar_saudacao": ("saudacao", "mensagem de saudação"),
    "editar_instrucoes": ("instrucoes", "instruções do bot"),
}


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

    # Limpa dados
    for k in ["empresa_editar_id", "campo_editando", "campo_editando_nome"]:
        context.user_data.pop(k, None)

    return ConversationHandler.END


# ═══════════════════════════════════════════════════
#  INTERAÇÃO COM O AGENTE (mensagens de texto)
# ═══════════════════════════════════════════════════

async def interagir_com_agente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens do próprio usuário e responde com RAG."""
    user_id = update.effective_user.id
    pergunta = update.message.text.strip()

    empresa = await obter_empresa_por_usuario(user_id)
    if not empresa:
        await update.message.reply_text(
            "👋 Seu agente ainda não foi configurado.\n"
            "Envie /start para iniciar a configuração inicial."
        )
        return

    if not empresa_tem_documentos(empresa["id"]):
        await update.message.reply_text(
            "📄 Seu agente ainda não tem base de conhecimento.\n"
            "Envie documentos neste chat ou use /upload para concluir a configuração."
        )
        return

    # Envia indicador de "digitando"
    await update.message.chat.send_action("typing")

    try:
        resposta = await gerar_resposta(
            empresa_id=empresa["id"],
            nome_empresa=empresa["nome"],
            nome_bot=empresa["nome_bot"],
            instrucoes=empresa["instrucoes"],
            pergunta=pergunta,
        )

        await update.message.reply_text(resposta)

        # Registra conversa de teste do usuário
        await registrar_conversa(empresa["id"], user_id, pergunta, resposta)

    except Exception as e:
        logger.error(f"Erro ao gerar resposta: {e}", exc_info=True)
        await update.message.reply_text(
            "Desculpe, ocorreu um erro ao processar sua pergunta. Tente novamente em alguns instantes."
        )


# ═══════════════════════════════════════════════════
#  CONSTRUÇÃO DOS HANDLERS
# ═══════════════════════════════════════════════════

def get_handlers() -> list:
    """Retorna todos os handlers do bot."""

    # ConversationHandler para onboarding da empresa do usuário
    registro_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("registrar", cmd_registrar),
            CommandHandler("reset", cmd_reset),
            CallbackQueryHandler(painel_reset_callback, pattern="^painel_reset$"),
        ],
        states={
            AGUARDANDO_NOME_EMPRESA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome_empresa)],
            AGUARDANDO_NOME_BOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome_bot)],
            AGUARDANDO_SAUDACAO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_saudacao)],
            AGUARDANDO_INSTRUCOES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_instrucoes),
                CommandHandler("pular", pular_instrucoes),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_registro)],
        allow_reentry=True,
    )

    # ConversationHandler para upload de documentos
    upload_handler = ConversationHandler(
        entry_points=[
            CommandHandler("upload", cmd_upload),
            CallbackQueryHandler(painel_upload_callback, pattern="^painel_upload$"),
        ],
        states={
            AGUARDANDO_DOCUMENTO: [
                MessageHandler(filters.Document.ALL, receber_documento),
                CommandHandler("pronto", finalizar_upload),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_registro)],
        allow_reentry=True,
    )

    # ConversationHandler para a imagem própria do agente
    imagem_handler = ConversationHandler(
        entry_points=[
            CommandHandler("imagem", cmd_imagem),
            CallbackQueryHandler(painel_imagem_callback, pattern="^painel_imagem$"),
        ],
        states={
            AGUARDANDO_IMAGEM_BOT: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receber_imagem_bot),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_registro)],
        allow_reentry=True,
    )

    # ConversationHandler para edição
    editar_handler = ConversationHandler(
        entry_points=[
            CommandHandler("editar", cmd_editar),
            CallbackQueryHandler(painel_editar_callback, pattern="^painel_editar$"),
        ],
        states={
            EDITANDO_CAMPO: [
                CallbackQueryHandler(editar_campo_callback, pattern="^editar_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor_editado),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_registro)],
    )

    return [
        CommandHandler("ajuda", cmd_ajuda),
        CommandHandler("painel", cmd_painel),
        CommandHandler("documentos", cmd_documentos),
        CommandHandler("status", cmd_status),
        CallbackQueryHandler(
            painel_refresh_callback,
            pattern="^painel_refresh$",
        ),
        CallbackQueryHandler(
            painel_documentos_callback,
            pattern="^painel_documentos$",
        ),
        CallbackQueryHandler(
            painel_status_callback,
            pattern="^painel_status$",
        ),
        CallbackQueryHandler(
            painel_ajuda_callback,
            pattern="^painel_ajuda$",
        ),
        CallbackQueryHandler(
            docs_painel_callback,
            pattern="^docs_painel$",
        ),
        CallbackQueryHandler(
            docs_refresh_callback,
            pattern="^docs_refresh$",
        ),
        CallbackQueryHandler(
            docs_reindexar_callback,
            pattern="^docs_reindexar$",
        ),
        CallbackQueryHandler(
            docs_reprocessar_callback,
            pattern=r"^docs_reprocessar:\d+$",
        ),
        CallbackQueryHandler(
            docs_excluir_callback,
            pattern=r"^docs_excluir:\d+$",
        ),
        registro_handler,
        upload_handler,
        imagem_handler,
        editar_handler,
        MessageHandler(filters.Document.ALL, receber_documento_direto),
        # Handler de interação com o agente — deve ser o último
        MessageHandler(filters.TEXT & ~filters.COMMAND, interagir_com_agente),
    ]
