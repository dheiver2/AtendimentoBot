"""Testes para handlers/images.py — gestão de imagem do agente."""
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from telegram.ext import ConversationHandler

from tests.helpers import make_update, make_context, make_empresa


class CmdImagemTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.images._obter_empresa_admin_ou_responder", return_value=None)
    async def test_sem_empresa(self, mock_admin):
        from handlers.images import cmd_imagem
        update = make_update()
        ctx = make_context()
        result = await cmd_imagem(update, ctx)
        self.assertEqual(result, ConversationHandler.END)

    @patch("handlers.images._obter_empresa_admin_ou_responder")
    @patch("handlers.images.excluir_imagem_empresa", return_value=True)
    async def test_remover_imagem(self, mock_excl, mock_admin):
        from handlers.images import cmd_imagem
        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context(args=["remover"])
        ctx.args = ["remover"]
        result = await cmd_imagem(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        self.assertIn("removida", update.effective_message.reply_text.call_args[0][0])

    @patch("handlers.images._obter_empresa_admin_ou_responder")
    @patch("handlers.images.excluir_imagem_empresa", return_value=False)
    async def test_remover_imagem_inexistente(self, mock_excl, mock_admin):
        from handlers.images import cmd_imagem
        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context(args=["remover"])
        ctx.args = ["remover"]
        result = await cmd_imagem(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        self.assertIn("não tinha", update.effective_message.reply_text.call_args[0][0])

    @patch("handlers.images._obter_empresa_admin_ou_responder")
    @patch("handlers.images.empresa_tem_imagem", return_value=False)
    async def test_inicia_fluxo_imagem(self, mock_tem, mock_admin):
        from handlers.images import cmd_imagem
        from handlers.common import AGUARDANDO_IMAGEM_BOT

        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context(args=None)
        ctx.args = None
        result = await cmd_imagem(update, ctx)
        self.assertEqual(result, AGUARDANDO_IMAGEM_BOT)


class BaixarImagemEnviadaTests(unittest.IsolatedAsyncioTestCase):
    async def test_foto_telegram(self):
        from handlers.images import _baixar_imagem_enviada
        update = make_update()
        photo = MagicMock()
        photo.get_file = AsyncMock(return_value=MagicMock(
            download_as_bytearray=AsyncMock(return_value=bytearray(b"\xff\xd8\xff"))
        ))
        update.message.photo = [photo]
        conteudo, nome = await _baixar_imagem_enviada(update)
        self.assertEqual(nome, "imagem.jpg")
        self.assertIsInstance(conteudo, bytes)

    async def test_documento_imagem(self):
        from handlers.images import _baixar_imagem_enviada
        update = make_update()
        update.message.photo = []
        doc = MagicMock()
        doc.file_name = "logo.png"
        doc.mime_type = "image/png"
        doc.get_file = AsyncMock(return_value=MagicMock(
            download_as_bytearray=AsyncMock(return_value=bytearray(b"\x89PNG"))
        ))
        update.message.document = doc
        with patch("handlers.images.imagem_suportada", return_value=True):
            conteudo, nome = await _baixar_imagem_enviada(update)
        self.assertEqual(nome, "logo.png")

    async def test_documento_nao_suportado(self):
        from handlers.images import _baixar_imagem_enviada
        update = make_update()
        update.message.photo = []
        doc = MagicMock()
        doc.file_name = "planilha.xlsx"
        doc.mime_type = "application/xlsx"
        update.message.document = doc
        with patch("handlers.images.imagem_suportada", return_value=False):
            with self.assertRaises(ValueError):
                await _baixar_imagem_enviada(update)


class ReceberImagemBotTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.images._obter_empresa_admin_ou_responder", return_value=None)
    async def test_sem_empresa(self, mock_admin):
        from handlers.images import receber_imagem_bot
        update = make_update()
        ctx = make_context()
        result = await receber_imagem_bot(update, ctx)
        self.assertEqual(result, ConversationHandler.END)

    @patch("handlers.images._obter_empresa_admin_ou_responder")
    @patch("handlers.images._baixar_imagem_enviada", new_callable=AsyncMock, side_effect=ValueError("Formato inválido"))
    async def test_formato_invalido(self, mock_baixar, mock_admin):
        from handlers.images import receber_imagem_bot
        from handlers.common import AGUARDANDO_IMAGEM_BOT

        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context()
        result = await receber_imagem_bot(update, ctx)
        self.assertEqual(result, AGUARDANDO_IMAGEM_BOT)

    @patch("handlers.images._obter_empresa_admin_ou_responder")
    @patch("handlers.images._baixar_imagem_enviada", new_callable=AsyncMock, return_value=(b"\xff\xd8", "img.jpg"))
    @patch("handlers.images.salvar_imagem_empresa")
    @patch("handlers.images._enviar_preview_imagem_empresa", new_callable=AsyncMock)
    async def test_salva_com_sucesso(self, mock_preview, mock_salvar, mock_baixar, mock_admin):
        from handlers.images import receber_imagem_bot

        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context()
        result = await receber_imagem_bot(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        mock_salvar.assert_called_once()

    @patch("handlers.images._obter_empresa_admin_ou_responder")
    @patch("handlers.images._baixar_imagem_enviada", new_callable=AsyncMock, return_value=(b"\xff\xd8", "img.jpg"))
    @patch("handlers.images.salvar_imagem_empresa", side_effect=RuntimeError("disk full"))
    async def test_erro_salvar(self, mock_salvar, mock_baixar, mock_admin):
        from handlers.images import receber_imagem_bot
        from handlers.common import AGUARDANDO_IMAGEM_BOT

        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context()
        result = await receber_imagem_bot(update, ctx)
        self.assertEqual(result, AGUARDANDO_IMAGEM_BOT)
        self.assertIn("Não foi possível", update.message.reply_text.call_args[0][0])
