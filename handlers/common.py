"""Utilitários compartilhados entre os handlers do bot."""
import logging
import os
import shutil
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageOps
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot_profile_photo import obter_caminho_imagem_empresa
from config import IMAGES_DIR, PDFS_DIR, VECTOR_STORES_DIR
from database import (
    obter_empresa_do_cliente,
    obter_empresa_por_admin,
)
from telegram_commands import PerfilComando, sincronizar_comandos_chat

logger = logging.getLogger(__name__)
IDENTIDADE_VISUAL_ENVIADA_KEY = "identidade_visual_enviada"

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
    AGUARDANDO_CONFIRMACAO_RESET,
    AGUARDANDO_CONFIRMACAO_REGISTRO,
) = range(13)


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
    perfil: PerfilComando,
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
    from vector_store import empresa_tem_documentos

    tem_docs = empresa_tem_documentos(empresa["id"])

    texto = _montar_texto_boas_vindas_cliente(empresa, tem_docs)
    imagem_enviada = await _enviar_identidade_visual_empresa(
        mensagem,
        empresa,
        caption=texto,
    )
    if not imagem_enviada:
        await mensagem.reply_text(texto)


def _montar_texto_boas_vindas_cliente(empresa: dict, tem_docs: bool) -> str:
    """Monta o texto de boas-vindas do cliente conforme o estado da empresa."""
    if tem_docs:
        return (
            f"👋 Você está conectado ao atendimento de {empresa['nome']}.\n\n"
            f"{empresa['saudacao']}\n\n"
            "Envie sua mensagem normalmente para conversar."
        )

    texto = (
        f"👋 Você está conectado ao atendimento de {empresa['nome']}.\n\n"
        f"{empresa['saudacao']}\n\n"
        "⚠️ Este atendimento ainda está sendo preparado pelo administrador. "
        "Tente novamente em alguns instantes."
    )
    if empresa.get("fallback_contato"):
        texto += f"\n\nSe precisar de ajuda imediata, entre em contato: {empresa['fallback_contato']}"
    return texto


def _obter_fonte(tamanho: int, negrito: bool = False):
    """Carrega uma fonte legível quando disponível, com fallback seguro."""
    caminhos = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if negrito else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf" if negrito else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if negrito else "C:/Windows/Fonts/arial.ttf",
    ]
    for caminho in caminhos:
        if os.path.exists(caminho):
            try:
                return ImageFont.truetype(caminho, tamanho)
            except OSError:
                continue
    return ImageFont.load_default()


def _quebrar_texto(draw: ImageDraw.ImageDraw, texto: str, fonte, largura_maxima: int) -> str:
    """Quebra o texto em múltiplas linhas dentro da largura disponível."""
    palavras = (texto or "").split()
    if not palavras:
        return ""

    linhas: list[str] = []
    atual = palavras[0]
    for palavra in palavras[1:]:
        candidato = f"{atual} {palavra}"
        bbox = draw.textbbox((0, 0), candidato, font=fonte)
        if bbox[2] - bbox[0] <= largura_maxima:
            atual = candidato
        else:
            linhas.append(atual)
            atual = palavra
    linhas.append(atual)
    return "\n".join(linhas)


def _gerar_capa_empresa(empresa: dict) -> BytesIO:
    """Gera uma capa visual da empresa com imagem, nome e saudação."""
    largura, altura = 1080, 1350
    caminho_imagem = obter_caminho_imagem_empresa(empresa["id"])

    if os.path.exists(caminho_imagem):
        with Image.open(caminho_imagem) as imagem:
            base = ImageOps.fit(imagem.convert("RGB"), (largura, altura))
    else:
        base = Image.new("RGB", (largura, altura), color=(17, 38, 59))

    capa = base.convert("RGBA")
    overlay = Image.new("RGBA", capa.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    draw_overlay.rectangle((0, 0, largura, altura), fill=(8, 16, 28, 110))
    draw_overlay.rounded_rectangle((60, 780, largura - 60, altura - 80), radius=36, fill=(10, 18, 30, 190))
    capa = Image.alpha_composite(capa, overlay)

    draw = ImageDraw.Draw(capa)
    fonte_titulo = _obter_fonte(64, negrito=True)
    fonte_subtitulo = _obter_fonte(30, negrito=False)
    fonte_saudacao = _obter_fonte(40, negrito=False)

    titulo = _quebrar_texto(draw, empresa["nome"], fonte_titulo, largura - 180)
    saudacao = _quebrar_texto(draw, empresa.get("saudacao", ""), fonte_saudacao, largura - 180)
    assistente = empresa.get("nome_bot", "Assistente")

    draw.text((90, 830), "ATENDIMENTO", font=fonte_subtitulo, fill=(161, 199, 255))
    draw.multiline_text((90, 885), titulo, font=fonte_titulo, fill=(255, 255, 255), spacing=12)
    draw.text((90, 1060), f"Com {assistente}", font=fonte_subtitulo, fill=(196, 214, 232))
    draw.multiline_text((90, 1115), saudacao, font=fonte_saudacao, fill=(235, 241, 247), spacing=10)

    saida = BytesIO()
    capa.convert("RGB").save(saida, format="JPEG", quality=92, optimize=True)
    saida.seek(0)
    return saida


async def _enviar_identidade_visual_empresa(
    mensagem,
    empresa: dict,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    caption: str | None = None,
    force: bool = False,
) -> bool:
    """Envia a identidade visual da empresa uma vez por sessão do cliente."""
    if context and context.user_data.get(IDENTIDADE_VISUAL_ENVIADA_KEY) and not force:
        return False

    legenda = caption or (
        f"🏢 {empresa['nome']}\n\n"
        f"{empresa['saudacao']}\n\n"
        "Envie sua mensagem normalmente para continuar o atendimento."
    )
    try:
        capa = _gerar_capa_empresa(empresa)
        await mensagem.reply_photo(photo=capa, caption=legenda)
        if context is not None:
            context.user_data[IDENTIDADE_VISUAL_ENVIADA_KEY] = True
        return True
    except Exception as e:
        logger.warning(
            "Falha ao gerar/enviar identidade visual da empresa %s: %s",
            empresa["id"],
            e,
        )
        return False


async def _enviar_preview_imagem_empresa(
    mensagem,
    empresa_id: int,
    legenda: str,
 ) -> bool:
    """Envia a imagem atual da empresa como preview, quando existir."""
    caminho = obter_caminho_imagem_empresa(empresa_id)
    if not os.path.exists(caminho):
        return False

    with open(caminho, "rb") as arquivo:
        await mensagem.reply_photo(photo=arquivo, caption=legenda)
    return True


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
