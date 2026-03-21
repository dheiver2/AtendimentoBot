"""Utilitários compartilhados entre os handlers do bot."""
import logging
import os
import shutil

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import IMAGES_DIR, PDFS_DIR, VECTOR_STORES_DIR
from database import (
    obter_empresa_do_cliente,
    obter_empresa_por_admin,
)
from bot_profile_photo import empresa_tem_imagem, obter_caminho_imagem_empresa
from telegram_commands import sincronizar_comandos_chat

logger = logging.getLogger(__name__)

# ── Estados do ConversationHandler ──
(
    AGUARDANDO_NOME_EMPRESA,
    AGUARDANDO_NOME_BOT,
    AGUARDANDO_SAUDACAO,
    AGUARDANDO_INSTRUCOES,
    AGUARDANDO_DOCUMENTO,
    EDITANDO_CAMPO,
    AGUARDANDO_IMAGEM_BOT,
    AGUARDANDO_HORARIO,
    AGUARDANDO_FALLBACK,
    AGUARDANDO_FAQ_PERGUNTA,
    AGUARDANDO_FAQ_RESPOSTA,
) = range(11)


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
        "empresa_faq_id",
        "faq_pergunta",
    ]:
        context.user_data.pop(key, None)


def _obter_payload_start(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """Extrai o payload do /start quando o usuário veio por deep link."""
    if not context.args:
        return None
    payload = context.args[0].strip()
    return payload or None


def _remover_arquivos_empresa(empresa_id: int):
    """Apaga documentos e vector store da empresa resetada."""
    for diretorio_base in [PDFS_DIR, VECTOR_STORES_DIR, IMAGES_DIR]:
        caminho = os.path.join(diretorio_base, str(empresa_id))
        if os.path.isdir(caminho):
            shutil.rmtree(caminho, ignore_errors=True)


def _mensagem_somente_admin() -> str:
    """Texto padrão para comandos de gestão restritos ao admin."""
    return (
        "🔒 Este comando é exclusivo do admin que configurou o bot.\n"
        "Se você recebeu um link de atendimento, use este chat apenas para conversar."
    )


async def _sincronizar_comandos_do_chat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    perfil: str,
):
    """Atualiza o menu de comandos do chat conforme o perfil atual."""
    chat = update.effective_chat
    if not chat:
        return
    try:
        await sincronizar_comandos_chat(context.bot, chat.id, perfil)
    except Exception as e:
        logger.warning(
            "Falha ao sincronizar comandos do chat %s para o perfil %s: %s",
            chat.id,
            perfil,
            e,
        )


def _montar_link_atendimento(bot_username: str, link_token: str) -> str:
    """Monta o deep link do Telegram para clientes do admin."""
    username = (bot_username or "").strip().lstrip("@")
    if not username:
        raise ValueError("O bot precisa ter um username público no Telegram para gerar links.")
    return f"https://t.me/{username}?start={link_token}"


async def _obter_empresa_admin_ou_responder(
    update: Update,
    mensagem_nao_configurado: str | None = None,
) -> dict | None:
    """Retorna a empresa do admin ou responde com a mensagem adequada."""
    empresa = await obter_empresa_por_admin(update.effective_user.id)
    if empresa:
        return empresa

    empresa_cliente = await obter_empresa_do_cliente(update.effective_user.id)
    if empresa_cliente:
        await update.effective_message.reply_text(_mensagem_somente_admin())
        return None

    await update.effective_message.reply_text(
        mensagem_nao_configurado or "❌ Seu agente ainda não foi configurado. Use /start primeiro."
    )
    return None


async def _enviar_boas_vindas_cliente(mensagem, empresa: dict):
    """Envia a mensagem inicial para um cliente vinculado via link."""
    texto = (
        f"👋 Você está conectado ao atendimento de {empresa['nome']}.\n\n"
        f"{empresa['saudacao']}\n\n"
        "Envie sua mensagem normalmente para conversar."
    )
    await mensagem.reply_text(texto)


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


def _teclado_painel(empresa: dict | None = None) -> InlineKeyboardMarkup:
    """Retorna o teclado inline principal do painel."""
    botao_ativo = "⏸️ Pausar" if (empresa or {}).get("ativo", 1) else "▶️ Ativar"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📄 Upload", callback_data="painel_upload"),
                InlineKeyboardButton("📚 Documentos", callback_data="painel_documentos"),
            ],
            [
                InlineKeyboardButton("🖼️ Imagem", callback_data="painel_imagem"),
                InlineKeyboardButton("❔ FAQ", callback_data="painel_faq"),
            ],
            [
                InlineKeyboardButton("🕒 Horário", callback_data="painel_horario"),
                InlineKeyboardButton("🆘 Fallback", callback_data="painel_fallback"),
            ],
            [
                InlineKeyboardButton(botao_ativo, callback_data="painel_ativo_toggle"),
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
