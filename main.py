"""Ponto de entrada principal do bot de atendimento ao cliente."""
import logging
import os

from dotenv import load_dotenv
from telegram import BotCommand, BotCommandScopeAllPrivateChats, MenuButtonCommands
from telegram.ext import ApplicationBuilder

from config import BUNDLED_ENV_PATH, ENV_PATH
from database import init_db
from handlers import get_handlers

load_dotenv(BUNDLED_ENV_PATH)
if ENV_PATH != BUNDLED_ENV_PATH:
    load_dotenv(ENV_PATH, override=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def obter_comandos_nativos() -> list[BotCommand]:
    """Retorna a lista de comandos nativos exibidos pelo Telegram."""
    return [
        BotCommand("start", "Iniciar ou abrir seu agente"),
        BotCommand("painel", "Abrir o painel principal"),
        BotCommand("upload", "Enviar novos documentos"),
        BotCommand("imagem", "Atualizar a imagem do agente"),
        BotCommand("pausar", "Pausar o agente"),
        BotCommand("ativar", "Ativar o agente"),
        BotCommand("horario", "Definir horário de atendimento"),
        BotCommand("fallback", "Definir contato humano"),
        BotCommand("faq", "Gerenciar perguntas frequentes"),
        BotCommand("documentos", "Gerenciar a base de conhecimento"),
        BotCommand("editar", "Editar a configuração do agente"),
        BotCommand("status", "Ver o status atual"),
        BotCommand("reset", "Reconfigurar do zero"),
        BotCommand("ajuda", "Ver ajuda rápida"),
    ]


async def post_init(application):
    """Callback executado após a inicialização do bot."""
    await init_db()
    logger.info("Banco de dados inicializado.")
    await application.bot.set_my_commands(
        obter_comandos_nativos(),
        scope=BotCommandScopeAllPrivateChats(),
    )
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    logger.info("Menu nativo do Telegram configurado.")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN não configurado no .env")

    google_key = os.getenv("GOOGLE_API_KEY")
    if not google_key:
        raise ValueError("GOOGLE_API_KEY não configurado no .env")

    app = ApplicationBuilder().token(token).post_init(post_init).build()

    for handler in get_handlers():
        app.add_handler(handler)

    logger.info("Bot iniciado! Pressione Ctrl+C para parar.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
