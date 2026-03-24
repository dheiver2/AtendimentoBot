"""Testes para main.py — error_handler e configuração."""
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
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
