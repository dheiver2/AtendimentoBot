"""Testes para handlers/onboarding.py — registro de empresa."""
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from telegram.ext import ConversationHandler

from tests.helpers import make_update, make_context, make_empresa


class CmdStartTests(unittest.IsolatedAsyncioTestCase):

    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding.obter_empresa_do_cliente", return_value=None)
    @patch("handlers.onboarding.obter_empresa_por_admin")
    @patch("handlers.onboarding._obter_payload_start", return_value=None)
    async def test_admin_existente_ve_mensagem_ativa(self, mock_payload, mock_admin, mock_cliente, mock_sync):
        from handlers.onboarding import cmd_start
        from handlers.common import AGUARDANDO_NOME_EMPRESA

        empresa = make_empresa(nome="Acme")
        mock_admin.return_value = empresa
        with patch("handlers.onboarding.empresa_tem_documentos", return_value=True):
            update = make_update()
            ctx = make_context()
            result = await cmd_start(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Acme", texto)

    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding.obter_empresa_do_cliente")
    @patch("handlers.onboarding.obter_empresa_por_admin", return_value=None)
    @patch("handlers.onboarding._obter_payload_start", return_value=None)
    async def test_cliente_existente_recebe_boas_vindas(self, mock_payload, mock_admin, mock_cliente, mock_sync):
        from handlers.onboarding import cmd_start

        mock_cliente.return_value = make_empresa(nome="TestCorp")
        update = make_update()
        ctx = make_context()
        with patch("handlers.onboarding._enviar_boas_vindas_cliente", new_callable=AsyncMock) as mock_bv:
            result = await cmd_start(update, ctx)
        self.assertEqual(result, ConversationHandler.END)

    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding.obter_empresa_do_cliente", return_value=None)
    @patch("handlers.onboarding.obter_empresa_por_admin", return_value=None)
    @patch("handlers.onboarding._obter_payload_start", return_value="valid_token")
    @patch("handlers.onboarding.obter_empresa_por_link_token", return_value=None)
    async def test_link_invalido_informa_usuario(self, mock_link, mock_payload, mock_admin, mock_cliente, mock_sync):
        from handlers.onboarding import cmd_start

        update = make_update()
        ctx = make_context()
        result = await cmd_start(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("inválido", texto)

    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding.obter_empresa_do_cliente", return_value=None)
    @patch("handlers.onboarding.obter_empresa_por_admin", return_value=None)
    @patch("handlers.onboarding._obter_payload_start", return_value="valid_token")
    @patch("handlers.onboarding.obter_empresa_por_link_token")
    @patch("handlers.onboarding.vincular_cliente_empresa", new_callable=AsyncMock)
    @patch("handlers.onboarding._enviar_boas_vindas_cliente", new_callable=AsyncMock)
    async def test_link_valido_vincula_cliente(self, mock_bv, mock_vincular, mock_link, mock_payload, mock_admin, mock_cliente, mock_sync):
        from handlers.onboarding import cmd_start

        mock_link.return_value = make_empresa(nome="ClientCorp")
        update = make_update()
        ctx = make_context()
        result = await cmd_start(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        mock_vincular.assert_called_once()

    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding.obter_empresa_do_cliente", return_value=None)
    @patch("handlers.onboarding.obter_empresa_por_admin", return_value=None)
    @patch("handlers.onboarding._obter_payload_start", return_value=None)
    async def test_novo_usuario_inicia_onboarding(self, mock_payload, mock_admin, mock_cliente, mock_sync):
        from handlers.onboarding import cmd_start
        from handlers.common import AGUARDANDO_NOME_EMPRESA

        update = make_update()
        ctx = make_context()
        result = await cmd_start(update, ctx)
        self.assertEqual(result, AGUARDANDO_NOME_EMPRESA)


class ReceberNomeEmpresaTests(unittest.IsolatedAsyncioTestCase):
    async def test_nome_valido_avanca(self):
        from handlers.onboarding import receber_nome_empresa
        from handlers.common import AGUARDANDO_NOME_BOT

        update = make_update("Minha Empresa")
        ctx = make_context()
        result = await receber_nome_empresa(update, ctx)
        self.assertEqual(result, AGUARDANDO_NOME_BOT)
        self.assertEqual(ctx.user_data["nome_empresa"], "Minha Empresa")

    async def test_nome_vazio_repete(self):
        from handlers.onboarding import receber_nome_empresa
        from handlers.common import AGUARDANDO_NOME_EMPRESA

        update = make_update("   ")
        ctx = make_context()
        result = await receber_nome_empresa(update, ctx)
        self.assertEqual(result, AGUARDANDO_NOME_EMPRESA)


class ReceberNomeBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_nome_bot_valido(self):
        from handlers.onboarding import receber_nome_bot
        from handlers.common import AGUARDANDO_SAUDACAO

        update = make_update("Ana")
        ctx = make_context()
        result = await receber_nome_bot(update, ctx)
        self.assertEqual(result, AGUARDANDO_SAUDACAO)
        self.assertEqual(ctx.user_data["nome_bot"], "Ana")


class ReceberSaudacaoTests(unittest.IsolatedAsyncioTestCase):
    async def test_saudacao_valida(self):
        from handlers.onboarding import receber_saudacao
        from handlers.common import AGUARDANDO_INSTRUCOES

        update = make_update("Olá, bem-vindo!")
        ctx = make_context()
        result = await receber_saudacao(update, ctx)
        self.assertEqual(result, AGUARDANDO_INSTRUCOES)


class ReceberInstrucoesTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.onboarding._finalizar_registro", new_callable=AsyncMock, return_value=ConversationHandler.END)
    async def test_instrucoes_validas(self, mock_fin):
        from handlers.onboarding import receber_instrucoes

        update = make_update("Responda sempre de forma educada")
        ctx = make_context()
        result = await receber_instrucoes(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        self.assertEqual(ctx.user_data["instrucoes"], "Responda sempre de forma educada")


class PularInstrucoesTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.onboarding._finalizar_registro", new_callable=AsyncMock, return_value=ConversationHandler.END)
    async def test_pular_define_instrucoes_padrao(self, mock_fin):
        from handlers.onboarding import pular_instrucoes

        update = make_update("/pular")
        ctx = make_context()
        result = await pular_instrucoes(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        self.assertIn("assistente de atendimento", ctx.user_data["instrucoes"])


class CancelarRegistroTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancela_e_limpa_estado(self):
        from handlers.onboarding import cancelar_registro

        update = make_update("/cancelar")
        ctx = make_context(user_data={"nome_empresa": "Teste"})
        result = await cancelar_registro(update, ctx)
        self.assertEqual(result, ConversationHandler.END)


class CmdResetTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding._obter_empresa_admin_ou_responder")
    @patch("handlers.onboarding.excluir_empresa_com_dados", new_callable=AsyncMock)
    @patch("handlers.onboarding._remover_arquivos_empresa")
    async def test_reset_apaga_e_reinicia(self, mock_rm, mock_excl, mock_admin, mock_sync):
        from handlers.onboarding import cmd_reset
        from handlers.common import AGUARDANDO_NOME_EMPRESA

        mock_admin.return_value = make_empresa(nome="Old Corp")
        update = make_update("/reset")
        ctx = make_context()
        result = await cmd_reset(update, ctx)
        self.assertEqual(result, AGUARDANDO_NOME_EMPRESA)
        mock_excl.assert_called_once()

    @patch("handlers.onboarding._obter_empresa_admin_ou_responder", return_value=None)
    async def test_reset_sem_empresa_retorna_end(self, mock_admin):
        from handlers.onboarding import cmd_reset

        update = make_update("/reset")
        ctx = make_context()
        result = await cmd_reset(update, ctx)
        self.assertEqual(result, ConversationHandler.END)


class FinalizarRegistroTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding.criar_empresa", new_callable=AsyncMock, return_value=1)
    @patch("handlers.onboarding.atualizar_empresa", new_callable=AsyncMock)
    async def test_finaliza_registro_com_sucesso(self, mock_att, mock_criar, mock_sync):
        from handlers.onboarding import _finalizar_registro

        update = make_update("instrucoes")
        ctx = make_context(user_data={
            "nome_empresa": "Nova Corp",
            "nome_bot": "Bot",
            "saudacao": "Olá",
            "instrucoes": "Seja educado",
        })
        result = await _finalizar_registro(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        mock_criar.assert_called_once()
        mock_att.assert_called_once()
        # Deve limpar dados temporários
        self.assertNotIn("nome_empresa", ctx.user_data)
