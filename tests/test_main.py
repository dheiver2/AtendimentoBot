"""Testes para main.py — error_handler e configuração."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update
from telegram.error import Conflict


class ErrorHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_conflict_error_para_aplicacao(self):
        from main import error_handler

        ctx = MagicMock()
        ctx.error = Conflict("Conflict: terminated by other getUpdates request")
        ctx.application = MagicMock()
        await error_handler(MagicMock(), ctx)
        ctx.application.stop_running.assert_called_once()

    async def test_erro_generico_responde_usuario(self):
        from main import error_handler

        update = MagicMock(spec=Update)
        update.effective_message = AsyncMock()
        ctx = MagicMock()
        ctx.error = RuntimeError("unexpected")
        await error_handler(update, ctx)
        update.effective_message.reply_text.assert_called_once()
        self.assertIn("erro", update.effective_message.reply_text.call_args[0][0].lower())

    async def test_erro_generico_sem_mensagem(self):
        from main import error_handler

        update = MagicMock(spec=Update)
        update.effective_message = None
        ctx = MagicMock()
        ctx.error = RuntimeError("unexpected")
        # Não deve lançar exceção
        await error_handler(update, ctx)

    async def test_erro_generico_update_nao_e_update(self):
        from main import error_handler

        ctx = MagicMock()
        ctx.error = RuntimeError("unexpected")
        # update é object, não Update — não deve tentar reply_text
        await error_handler(object(), ctx)


class MainFunctionTests(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_sem_token_gera_erro(self):
        from main import main

        with self.assertRaises(ValueError) as ctx:
            main()
        self.assertIn("TELEGRAM_BOT_TOKEN", str(ctx.exception))

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "fake_token"}, clear=False)
    @patch("os.getenv", side_effect=lambda k, d=None: {"TELEGRAM_BOT_TOKEN": "fake_token"}.get(k, d))
    def test_sem_google_key_gera_erro(self, mock_env):
        from main import main

        with self.assertRaises(ValueError) as ctx:
            main()
        self.assertIn("OPENROUTER_API_KEY", str(ctx.exception))


class PostInitTests(unittest.IsolatedAsyncioTestCase):
    async def test_configura_menu_e_sincroniza_chats_existentes(self):
        from main import post_init

        application = MagicMock()
        application.bot = MagicMock()

        with patch("main.init_db", new_callable=AsyncMock) as mock_init:
            with patch("main.configurar_menu_nativo_padrao", new_callable=AsyncMock) as mock_menu:
                with patch("main.listar_ids_admins", new_callable=AsyncMock, return_value=[10, 20]) as mock_admins:
                    with patch("main.listar_ids_clientes", new_callable=AsyncMock, return_value=[30]) as mock_clientes:
                        with patch("main.sincronizar_comandos_existentes", new_callable=AsyncMock) as mock_sync:
                            await post_init(application)

        mock_init.assert_awaited_once()
        mock_menu.assert_awaited_once_with(application.bot)
        mock_admins.assert_awaited_once()
        mock_clientes.assert_awaited_once()
        mock_sync.assert_awaited_once_with(application.bot, [10, 20], [30])

    async def test_falha_ao_configurar_menu_nao_interrompe_inicializacao(self):
        from main import post_init

        application = MagicMock()
        application.bot = MagicMock()

        with patch("main.init_db", new_callable=AsyncMock) as mock_init:
            with patch(
                "main.configurar_menu_nativo_padrao",
                new_callable=AsyncMock,
                side_effect=RuntimeError("falha"),
            ) as mock_menu:
                with patch("main.listar_ids_admins", new_callable=AsyncMock) as mock_admins:
                    with patch("main.listar_ids_clientes", new_callable=AsyncMock) as mock_clientes:
                        with patch("main.sincronizar_comandos_existentes", new_callable=AsyncMock) as mock_sync:
                            with patch("main.logger.warning") as mock_warning:
                                await post_init(application)

        mock_init.assert_awaited_once()
        mock_menu.assert_awaited_once_with(application.bot)
        mock_admins.assert_not_awaited()
        mock_clientes.assert_not_awaited()
        mock_sync.assert_not_awaited()
        mock_warning.assert_called_once()
