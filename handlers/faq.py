"""Handlers de gestão de FAQs."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from database import (
    criar_faq,
    excluir_faq,
    limpar_faqs,
    listar_faqs,
    obter_empresa_por_admin,
)
from rate_limiter import limiter_faq, verificar_rate_limit
from validators import (
    MAX_FAQS_POR_EMPRESA,
    InputValidationError,
    validar_faq_pergunta,
    validar_faq_resposta,
)

from .agent import invalidar_cache_faq
from .common import (
    AGUARDANDO_FAQ_PERGUNTA,
    AGUARDANDO_FAQ_RESPOSTA,
    _editar_ou_responder,
    _obter_empresa_admin_ou_responder,
)

logger = logging.getLogger(__name__)


def _rotulo_faq(pergunta: str, indice: int) -> str:
    """Gera um rótulo curto para uma FAQ na interface."""
    pergunta = pergunta.strip()
    if len(pergunta) > 30:
        pergunta = f"{pergunta[:27]}..."
    return f"{indice}. {pergunta}"


def _teclado_faqs(faqs: list[dict]) -> InlineKeyboardMarkup:
    """Retorna o teclado inline de gestão das FAQs."""
    botoes = [
        [
            InlineKeyboardButton("➕ Nova FAQ", callback_data="faq_add"),
            InlineKeyboardButton("🔄 Atualizar", callback_data="faq_refresh"),
        ],
        [
            InlineKeyboardButton("🧹 Limpar FAQs", callback_data="faq_limpar"),
            InlineKeyboardButton("⬅️ Painel", callback_data="faq_painel"),
        ],
    ]

    for indice, faq in enumerate(faqs, 1):
        botoes.append(
            [
                InlineKeyboardButton(_rotulo_faq(faq["pergunta"], indice), callback_data="faq_refresh"),
                InlineKeyboardButton(f"🗑 {indice}", callback_data=f"faq_excluir:{faq['id']}"),
            ]
        )

    return InlineKeyboardMarkup(botoes)


async def _mostrar_faqs(update: Update, empresa: dict):
    """Mostra a lista de FAQs da empresa com ações de gestão."""
    faqs = await listar_faqs(empresa["id"])
    if not faqs:
        await _editar_ou_responder(
            update,
            (
                f"❔ FAQs — {empresa['nome']}\n\n"
                "Nenhuma FAQ cadastrada ainda.\n"
                "Use /faq adicionar ou o botão abaixo para cadastrar respostas rápidas."
            ),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("➕ Nova FAQ", callback_data="faq_add"),
                        InlineKeyboardButton("⬅️ Painel", callback_data="faq_painel"),
                    ]
                ]
            ),
        )
        return

    linhas = [
        f"❔ FAQs — {empresa['nome']}\n",
        "Use o botão abaixo para cadastrar mais respostas rápidas ou excluir FAQs existentes.\n",
    ]
    for indice, faq in enumerate(faqs, 1):
        linhas.append(f"{indice}. {faq['pergunta']}")

    await _editar_ou_responder(
        update,
        "\n".join(linhas),
        reply_markup=_teclado_faqs(faqs),
    )


async def _iniciar_cadastro_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia a conversa de cadastro de uma nova FAQ."""
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return ConversationHandler.END

    # Verificar limite de FAQs
    faqs = await listar_faqs(empresa["id"])
    if len(faqs) >= MAX_FAQS_POR_EMPRESA:
        await mensagem.reply_text(
            f"⚠️ Limite de {MAX_FAQS_POR_EMPRESA} FAQs por empresa atingido.\n"
            "Exclua FAQs antigas com /faq antes de cadastrar novas."
        )
        return ConversationHandler.END

    context.user_data["empresa_faq_id"] = empresa["id"]
    context.user_data.pop("faq_pergunta", None)
    await mensagem.reply_text(
        "➕ Nova FAQ\n\n"
        "Envie agora a pergunta que deve virar uma FAQ.\n"
        "Exemplo: Qual é o prazo de entrega?"
    )
    return AGUARDANDO_FAQ_PERGUNTA


async def cmd_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerencia as FAQs da empresa."""
    mensagem = update.effective_message
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return ConversationHandler.END

    if context.args:
        acao = context.args[0].lower()
        if acao in {"adicionar", "nova", "novo"}:
            return await _iniciar_cadastro_faq(update, context)

        if acao in {"limpar", "apagar"}:
            removidas = await limpar_faqs(empresa["id"])
            invalidar_cache_faq(empresa["id"])
            await mensagem.reply_text(f"🧹 {removidas} FAQ(s) removida(s).")
            return ConversationHandler.END

        if acao in {"remover", "excluir"}:
            if len(context.args) < 2 or not context.args[1].isdigit():
                await mensagem.reply_text("⚠️ Use /faq remover <id> para excluir uma FAQ específica.")
                return ConversationHandler.END

            removida = await excluir_faq(empresa["id"], int(context.args[1]))
            if removida:
                invalidar_cache_faq(empresa["id"])
                await mensagem.reply_text("🗑 FAQ removida com sucesso.")
            else:
                await mensagem.reply_text("⚠️ FAQ não encontrada.")
            return ConversationHandler.END

    await _mostrar_faqs(update, empresa)
    return ConversationHandler.END


async def receber_faq_pergunta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe a pergunta da nova FAQ."""
    if not context.user_data.get("empresa_faq_id"):
        await update.message.reply_text("❌ Erro interno. Use /faq novamente.")
        return ConversationHandler.END

    # Rate limiting
    rate_msg = verificar_rate_limit(limiter_faq, update.effective_user.id)
    if rate_msg:
        await update.message.reply_text(rate_msg)
        return ConversationHandler.END

    try:
        pergunta = validar_faq_pergunta(update.message.text)
    except InputValidationError as e:
        await update.message.reply_text(f"⚠️ {e.message}")
        return AGUARDANDO_FAQ_PERGUNTA

    context.user_data["faq_pergunta"] = pergunta
    await update.message.reply_text(
        "📝 Agora envie a resposta que o agente deve usar para essa pergunta."
    )
    return AGUARDANDO_FAQ_RESPOSTA


async def receber_faq_resposta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe a resposta da nova FAQ e salva no banco."""
    empresa_id = context.user_data.get("empresa_faq_id")
    pergunta = context.user_data.get("faq_pergunta")
    if not empresa_id or not pergunta:
        await update.message.reply_text("❌ Erro interno. Use /faq novamente.")
        return ConversationHandler.END

    try:
        resposta = validar_faq_resposta(update.message.text)
    except InputValidationError as e:
        await update.message.reply_text(f"⚠️ {e.message}")
        return AGUARDANDO_FAQ_RESPOSTA

    await criar_faq(empresa_id, pergunta, resposta)
    invalidar_cache_faq(empresa_id)
    context.user_data.pop("empresa_faq_id", None)
    context.user_data.pop("faq_pergunta", None)

    await update.message.reply_text("✅ FAQ cadastrada com sucesso.")
    empresa = await obter_empresa_por_admin(update.effective_user.id)
    if empresa:
        await _mostrar_faqs(update, empresa)
    return ConversationHandler.END


async def faq_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o cadastro de FAQ a partir do teclado inline."""
    await update.callback_query.answer()
    return await _iniciar_cadastro_faq(update, context)


async def faq_painel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Volta ao painel principal a partir da gestão de FAQ."""
    await update.callback_query.answer()
    from .panel import cmd_painel
    await cmd_painel(update, context)


async def faq_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Atualiza a visão de FAQ da empresa."""
    await update.callback_query.answer()
    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return
    await _mostrar_faqs(update, empresa)


async def faq_excluir_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exclui uma FAQ da empresa."""
    query = update.callback_query
    await query.answer()

    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return

    faq_id = int(query.data.split(":", 1)[1])
    removida = await excluir_faq(empresa["id"], faq_id)
    if removida:
        invalidar_cache_faq(empresa["id"])
        await query.message.reply_text("🗑 FAQ removida com sucesso.")
    else:
        await query.message.reply_text("⚠️ FAQ não encontrada.")
    await _mostrar_faqs(update, empresa)


async def faq_limpar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove todas as FAQs da empresa."""
    query = update.callback_query
    await query.answer()

    empresa = await _obter_empresa_admin_ou_responder(update)
    if not empresa:
        return

    removidas = await limpar_faqs(empresa["id"])
    invalidar_cache_faq(empresa["id"])
    await query.message.reply_text(f"🧹 {removidas} FAQ(s) removida(s).")
    await _mostrar_faqs(update, empresa)
