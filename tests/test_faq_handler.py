"""Testes para handlers/faq.py — gestão de perguntas frequentes."""
import unittest
from unittest.mock import AsyncMock, patch
from telegram.ext import ConversationHandler

from tests.helpers import make_update, make_context, make_empresa


class RotuloFaqTests(unittest.TestCase):
    def test_texto_curto(self):
        from handlers.faq import _rotulo_faq
        self.assertEqual(_rotulo_faq("Qual o prazo?", 1), "1. Qual o prazo?")

    def test_texto_longo_trunca(self):
        from handlers.faq import _rotulo_faq
        resultado = _rotulo_faq("Uma pergunta extremamente longa que excede o limite de caracteres", 2)
        self.assertTrue(resultado.endswith("..."))
        self.assertTrue(len(resultado) <= 35)


class CmdFaqTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.faq._obter_empresa_admin_ou_responder", return_value=None)
    async def test_sem_empresa(self, mock_admin):
        from handlers.faq import cmd_faq
        update = make_update()
        ctx = make_context()
        result = await cmd_faq(update, ctx)
        self.assertEqual(result, ConversationHandler.END)

    @patch("handlers.faq._obter_empresa_admin_ou_responder")
    @patch("handlers.faq._mostrar_faqs", new_callable=AsyncMock)
    async def test_sem_args_mostra_lista(self, mock_mostrar, mock_admin):
        from handlers.faq import cmd_faq
        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context(args=None)
        ctx.args = None
        result = await cmd_faq(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        mock_mostrar.assert_called_once()

    @patch("handlers.faq._obter_empresa_admin_ou_responder")
    @patch("handlers.faq._iniciar_cadastro_faq", new_callable=AsyncMock, return_value=10)
    async def test_arg_adicionar(self, mock_iniciar, mock_admin):
        from handlers.faq import cmd_faq
        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context(args=["adicionar"])
        ctx.args = ["adicionar"]
        result = await cmd_faq(update, ctx)
        mock_iniciar.assert_called_once()

    @patch("handlers.faq._obter_empresa_admin_ou_responder")
    @patch("handlers.faq.limpar_faqs", new_callable=AsyncMock, return_value=5)
    async def test_arg_limpar(self, mock_limpar, mock_admin):
        from handlers.faq import cmd_faq
        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context(args=["limpar"])
        ctx.args = ["limpar"]
        result = await cmd_faq(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        self.assertIn("5", update.effective_message.reply_text.call_args[0][0])

    @patch("handlers.faq._obter_empresa_admin_ou_responder")
    @patch("handlers.faq.excluir_faq", new_callable=AsyncMock, return_value=True)
    async def test_arg_remover_com_id(self, mock_excluir, mock_admin):
        from handlers.faq import cmd_faq
        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context(args=["remover", "42"])
        ctx.args = ["remover", "42"]
        result = await cmd_faq(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        mock_excluir.assert_called_once_with(1, 42)

    @patch("handlers.faq._obter_empresa_admin_ou_responder")
    async def test_arg_remover_sem_id(self, mock_admin):
        from handlers.faq import cmd_faq
        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context(args=["remover"])
        ctx.args = ["remover"]
        result = await cmd_faq(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        self.assertIn("id", update.effective_message.reply_text.call_args[0][0].lower())


class IniciarCadastroFaqTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.faq._obter_empresa_admin_ou_responder")
    @patch("handlers.faq.listar_faqs", new_callable=AsyncMock, return_value=[])
    async def test_inicia_fluxo(self, mock_faqs, mock_admin):
        from handlers.faq import _iniciar_cadastro_faq
        from handlers.common import AGUARDANDO_FAQ_PERGUNTA

        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context()
        result = await _iniciar_cadastro_faq(update, ctx)
        self.assertEqual(result, AGUARDANDO_FAQ_PERGUNTA)
        self.assertEqual(ctx.user_data["empresa_faq_id"], 1)

    @patch("handlers.faq._obter_empresa_admin_ou_responder")
    @patch("handlers.faq.listar_faqs", new_callable=AsyncMock)
    async def test_limite_atingido(self, mock_faqs, mock_admin):
        from handlers.faq import _iniciar_cadastro_faq
        from validators import MAX_FAQS_POR_EMPRESA

        mock_admin.return_value = make_empresa()
        mock_faqs.return_value = [{"id": i} for i in range(MAX_FAQS_POR_EMPRESA)]
        update = make_update()
        ctx = make_context()
        result = await _iniciar_cadastro_faq(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        self.assertIn("Limite", update.effective_message.reply_text.call_args[0][0])


class ReceberFaqPerguntaTests(unittest.IsolatedAsyncioTestCase):
    async def test_sem_estado_retorna_erro(self):
        from handlers.faq import receber_faq_pergunta
        update = make_update("pergunta")
        ctx = make_context(user_data={})
        result = await receber_faq_pergunta(update, ctx)
        self.assertEqual(result, ConversationHandler.END)

    @patch("handlers.faq.verificar_rate_limit", return_value="⏳ muito rápido")
    async def test_rate_limit(self, mock_rate):
        from handlers.faq import receber_faq_pergunta
        update = make_update("pergunta")
        ctx = make_context(user_data={"empresa_faq_id": 1})
        result = await receber_faq_pergunta(update, ctx)
        self.assertEqual(result, ConversationHandler.END)

    @patch("handlers.faq.verificar_rate_limit", return_value=None)
    async def test_pergunta_valida(self, mock_rate):
        from handlers.faq import receber_faq_pergunta
        from handlers.common import AGUARDANDO_FAQ_RESPOSTA

        update = make_update("Qual o prazo de entrega?")
        ctx = make_context(user_data={"empresa_faq_id": 1})
        result = await receber_faq_pergunta(update, ctx)
        self.assertEqual(result, AGUARDANDO_FAQ_RESPOSTA)
        self.assertEqual(ctx.user_data["faq_pergunta"], "Qual o prazo de entrega?")


class ReceberFaqRespostaTests(unittest.IsolatedAsyncioTestCase):
    async def test_sem_estado_retorna_erro(self):
        from handlers.faq import receber_faq_resposta
        update = make_update("resposta")
        ctx = make_context(user_data={})
        result = await receber_faq_resposta(update, ctx)
        self.assertEqual(result, ConversationHandler.END)

    @patch("handlers.faq.criar_faq", new_callable=AsyncMock)
    @patch("handlers.faq.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None)
    async def test_resposta_valida_salva(self, mock_admin, mock_criar):
        from handlers.faq import receber_faq_resposta
        update = make_update("3 dias úteis")
        ctx = make_context(user_data={"empresa_faq_id": 1, "faq_pergunta": "Prazo?"})
        result = await receber_faq_resposta(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        mock_criar.assert_called_once_with(1, "Prazo?", "3 dias úteis")
        self.assertNotIn("empresa_faq_id", ctx.user_data)


class FaqCallbacksTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.faq._obter_empresa_admin_ou_responder")
    @patch("handlers.faq.excluir_faq", new_callable=AsyncMock, return_value=True)
    @patch("handlers.faq._mostrar_faqs", new_callable=AsyncMock)
    async def test_excluir_callback(self, mock_mostrar, mock_excl, mock_admin):
        from handlers.faq import faq_excluir_callback
        mock_admin.return_value = make_empresa()
        update = make_update(callback_data="faq_excluir:42")
        ctx = make_context()
        await faq_excluir_callback(update, ctx)
        mock_excl.assert_called_once_with(1, 42)

    @patch("handlers.faq._obter_empresa_admin_ou_responder")
    @patch("handlers.faq.limpar_faqs", new_callable=AsyncMock, return_value=3)
    @patch("handlers.faq._mostrar_faqs", new_callable=AsyncMock)
    async def test_limpar_callback(self, mock_mostrar, mock_limpar, mock_admin):
        from handlers.faq import faq_limpar_callback
        mock_admin.return_value = make_empresa()
        update = make_update(callback_data="faq_limpar")
        ctx = make_context()
        await faq_limpar_callback(update, ctx)
        mock_limpar.assert_called_once()
