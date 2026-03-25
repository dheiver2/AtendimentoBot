"""Ponto de entrada principal do bot de atendimento ao cliente."""
import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.error import Conflict
from telegram.ext import ApplicationBuilder, ContextTypes

from config import BOT_VERSION, BUNDLED_ENV_PATH, ENV_PATH
from database import init_db, listar_ids_admins, listar_ids_clientes
from handlers import get_handlers
from telegram_commands import configurar_menu_nativo_padrao, sincronizar_comandos_existentes
from whatsapp_cloud_api import WhatsAppCloudSettings, WhatsAppWebhookServer

load_dotenv(BUNDLED_ENV_PATH)
if ENV_PATH != BUNDLED_ENV_PATH:
    load_dotenv(ENV_PATH, override=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Trata erros globais não capturados pelos handlers."""
    error = context.error

    if isinstance(error, Conflict):
        logger.critical(
            "Outra instância do bot já está rodando com o mesmo token. "
            "Encerre a outra instância antes de iniciar esta. Encerrando esta instância. Erro: %s",
            error,
        )
        context.application.stop_running()
        return

    logger.error("Erro não tratado: %s", error, exc_info=error)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Desculpe, ocorreu um erro inesperado. Tente novamente em instantes."
            )
        except Exception:
            pass


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
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        raise ValueError("OPENROUTER_API_KEY não configurado no .env")

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    whatsapp_settings = WhatsAppCloudSettings.from_env()

    if not token and not whatsapp_settings.enabled:
        raise ValueError(
            "Configure TELEGRAM_BOT_TOKEN no .env ou habilite WHATSAPP_CLOUD_API_ENABLED=1."
        )

    asyncio.run(init_db())
    whatsapp_server: WhatsAppWebhookServer | None = None

    if whatsapp_settings.enabled:
        whatsapp_server = WhatsAppWebhookServer(whatsapp_settings)

    if not token:
        if whatsapp_server is None:
            raise ValueError("Nenhum canal de atendimento foi configurado.")

        logger.info(
            "AtendimentoBot v%s iniciado apenas com WhatsApp Cloud API. Pressione Ctrl+C para parar.",
            BOT_VERSION,
        )
        try:
            whatsapp_server.serve_forever()
        finally:
            whatsapp_server.shutdown()
        return

    app = ApplicationBuilder().token(token).post_init(post_init).build()
    app.add_error_handler(error_handler)

    for handler in get_handlers():
        app.add_handler(handler)

    if whatsapp_server is not None:
        whatsapp_server.start_background()
        logger.info(
            "Webhook do WhatsApp habilitado em http://%s:%s%s",
            whatsapp_settings.webhook_host,
            whatsapp_settings.webhook_port,
            whatsapp_settings.webhook_path,
        )

    logger.info("AtendimentoBot v%s iniciado! Pressione Ctrl+C para parar.", BOT_VERSION)
    try:
        app.run_polling(drop_pending_updates=True)
    finally:
        if whatsapp_server is not None:
            whatsapp_server.shutdown()


if __name__ == "__main__":
    main()
