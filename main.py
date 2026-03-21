"""Ponto de entrada principal do bot de atendimento ao cliente."""
import logging
import os

from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder

from config import BUNDLED_ENV_PATH, ENV_PATH
from database import init_db, listar_ids_admins, listar_ids_clientes
from handlers import get_handlers
from telegram_commands import configurar_menu_nativo_padrao, sincronizar_comandos_existentes

load_dotenv(BUNDLED_ENV_PATH)
if ENV_PATH != BUNDLED_ENV_PATH:
    load_dotenv(ENV_PATH, override=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application):
    """Callback executado após a inicialização do bot."""
    await init_db()
    logger.info("Banco de dados inicializado.")
    try:
        await configurar_menu_nativo_padrao(application.bot)

        admins = await listar_ids_admins()
        clientes = await listar_ids_clientes()
        await sincronizar_comandos_existentes(application.bot, admins, clientes)

        logger.info(
            "Menu nativo do Telegram configurado. Admins sincronizados: %s. Clientes sincronizados: %s.",
            len(admins),
            len(clientes),
        )
    except Exception as e:
        logger.warning("Falha ao configurar o menu nativo do Telegram: %s", e, exc_info=True)


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
