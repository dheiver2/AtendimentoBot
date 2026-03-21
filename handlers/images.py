"""Handlers de gestão de imagem do agente."""
import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot_profile_photo import (
    empresa_tem_imagem,
    excluir_imagem_empresa,
    imagem_suportada,
    listar_formatos_imagem_suportados,
    salvar_imagem_empresa,
)
from validators import InputValidationError

from .common import (
    AGUARDANDO_IMAGEM_BOT,
    _enviar_preview_imagem_empresa,
    _obter_empresa_admin_ou_responder,
)

logger = logging.getLogger(__name__)


async def cmd_imagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o fluxo para atualizar a imagem própria do agente."""
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
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
            logger.error("Erro ao remover imagem do agente: %s", e, exc_info=True)
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
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
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
    except (ValueError, InputValidationError) as e:
        await update.message.reply_text(f"⚠️ {e}")
        return AGUARDANDO_IMAGEM_BOT
    except Exception as e:
        logger.error("Erro ao atualizar imagem do agente: %s", e, exc_info=True)
        await update.message.reply_text(
            "❌ Não foi possível atualizar a imagem do seu agente agora. Tente novamente."
        )
        return AGUARDANDO_IMAGEM_BOT
