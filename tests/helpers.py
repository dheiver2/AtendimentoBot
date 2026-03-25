"""Helpers compartilhados para testes — mocks de Update, Context e objetos do Telegram."""
from unittest.mock import AsyncMock, MagicMock


def make_message(text="", user_id=100):
    """Cria um mock de Message do Telegram."""
    msg = MagicMock()
    msg.text = text
    msg.reply_text = AsyncMock()
    msg.reply_photo = AsyncMock()
    msg.chat = MagicMock()
    msg.chat.id = user_id
    msg.chat.send_action = AsyncMock()
    return msg


def make_user(user_id=100):
    """Cria um mock de User do Telegram."""
    user = MagicMock()
    user.id = user_id
    return user


def make_update(text="", user_id=100, callback_data=None):
    """Cria um mock de Update do Telegram."""
    update = MagicMock()
    update.effective_user = make_user(user_id)
    update.effective_chat = MagicMock()
    update.effective_chat.id = user_id
    update.effective_message = make_message(text, user_id)
    update.message = update.effective_message

    if callback_data is not None:
        query = MagicMock()
        query.data = callback_data
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.message = make_message(text, user_id)
        update.callback_query = query
    else:
        update.callback_query = None

    return update


def make_context(user_data=None, args=None):
    """Cria um mock de ContextTypes.DEFAULT_TYPE."""
    ctx = MagicMock()
    ctx.user_data = user_data if user_data is not None else {}
    ctx.args = args
    ctx.bot = MagicMock()
    ctx.bot.get_me = AsyncMock(return_value=MagicMock(username="test_bot"))
    ctx.error = None
    return ctx


def make_empresa(empresa_id=1, nome="Acme Corp", ativo=1, **kwargs):
    """Cria um dict de empresa para testes."""
    empresa = {
        "id": empresa_id,
        "nome": nome,
        "nome_bot": kwargs.get("nome_bot", "Ana"),
        "saudacao": kwargs.get("saudacao", "Olá!"),
        "instrucoes": kwargs.get("instrucoes", "Seja educada"),
        "ativo": ativo,
        "link_token": kwargs.get("link_token", "abc123"),
        "admin_link_token": kwargs.get("admin_link_token", "adm123"),
        "horario_atendimento": kwargs.get("horario_atendimento", ""),
        "fallback_contato": kwargs.get("fallback_contato", ""),
    }
    empresa.update(kwargs)
    return empresa
