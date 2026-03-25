"""Testes para handlers/onboarding.py — registro de empresa."""
import os
import unittest
from unittest.mock import AsyncMock, patch

from telegram.ext import ConversationHandler

from tests.helpers import make_context, make_empresa, make_update


class CmdStartTests(unittest.IsolatedAsyncioTestCase):

    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding.obter_empresa_do_cliente", return_value=None)
    @patch("handlers.onboarding.obter_empresa_por_admin")
    @patch("handlers.onboarding._obter_payload_start", return_value=None)
    async def test_admin_existente_ve_mensagem_ativa(self, mock_payload, mock_admin, mock_cliente, mock_sync):
        from handlers.onboarding import cmd_start

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
        with patch("handlers.onboarding._enviar_boas_vindas_cliente", new_callable=AsyncMock):
            result = await cmd_start(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        self.assertTrue(ctx.user_data["identidade_visual_enviada"])

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
    @patch("handlers.onboarding._obter_payload_start", return_value="admin_adm123")
    @patch("handlers.onboarding.obter_empresa_por_admin_link_token", return_value=None)
    async def test_link_admin_invalido_informa_usuario(self, mock_link, mock_payload, mock_admin, mock_cliente, mock_sync):
        from handlers.onboarding import cmd_start

        update = make_update()
        ctx = make_context()
        result = await cmd_start(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("link de admin", texto.lower())
        self.assertIn("inválido", texto.lower())

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
        self.assertTrue(ctx.user_data["identidade_visual_enviada"])

    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding.obter_empresa_do_cliente", return_value=None)
    @patch("handlers.onboarding.obter_empresa_por_admin", return_value=None)
    @patch("handlers.onboarding._obter_payload_start", return_value="admin_adm123")
    @patch("handlers.onboarding.obter_empresa_por_admin_link_token")
    @patch("handlers.onboarding.adicionar_admin_empresa", new_callable=AsyncMock)
    async def test_link_admin_valido_vincula_admin(self, mock_add_admin, mock_link, mock_payload, mock_admin, mock_cliente, mock_sync):
        from handlers.onboarding import cmd_start

        mock_link.return_value = make_empresa(nome="AdminCorp", admin_link_token="adm123")
        update = make_update()
        ctx = make_context()
        result = await cmd_start(update, ctx)

        self.assertEqual(result, ConversationHandler.END)
        mock_add_admin.assert_awaited_once_with(1, 100)
        mock_sync.assert_awaited_once_with(update, ctx, "admin")
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("acesso de admin", texto.lower())
        self.assertIn("AdminCorp", texto)

    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding.obter_empresa_do_cliente", return_value=None)
    @patch("handlers.onboarding.obter_empresa_por_admin", return_value=None)
    @patch("handlers.onboarding._obter_payload_start", return_value=None)
    async def test_novo_usuario_inicia_onboarding(self, mock_payload, mock_admin, mock_cliente, mock_sync):
        from handlers.common import AGUARDANDO_NOME_EMPRESA
        from handlers.onboarding import cmd_start

        update = make_update()
        ctx = make_context()
        result = await cmd_start(update, ctx)
        self.assertEqual(result, AGUARDANDO_NOME_EMPRESA)

    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding.obter_empresa_do_cliente", return_value=None)
    @patch("handlers.onboarding.obter_empresa_por_admin", return_value=None)
    @patch("handlers.onboarding._obter_payload_start", return_value=None)
    async def test_usuario_nao_autorizado_nao_inicia_onboarding_sem_link(self, mock_payload, mock_admin, mock_cliente, mock_sync):
        from handlers.onboarding import cmd_start

        update = make_update(user_id=100)
        ctx = make_context()
        with patch.dict(os.environ, {"TELEGRAM_ADMIN_IDS": "999"}, clear=False):
            result = await cmd_start(update, ctx)

        self.assertEqual(result, ConversationHandler.END)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("link de admin", texto.lower())
        self.assertNotIn("nome da sua empresa", texto.lower())

    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding.obter_empresa_do_cliente", return_value=None)
    @patch("handlers.onboarding.obter_empresa_por_admin", return_value=None)
    @patch("handlers.onboarding._obter_payload_start", return_value=None)
    async def test_usuario_autorizado_por_lista_inicia_onboarding(self, mock_payload, mock_admin, mock_cliente, mock_sync):
        from handlers.common import AGUARDANDO_NOME_EMPRESA
        from handlers.onboarding import cmd_start

        update = make_update(user_id=999)
        ctx = make_context()
        with patch.dict(os.environ, {"TELEGRAM_ADMIN_IDS": "999"}, clear=False):
            result = await cmd_start(update, ctx)

        self.assertEqual(result, AGUARDANDO_NOME_EMPRESA)


class CmdRegistrarTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.onboarding.obter_empresa_do_cliente")
    @patch("handlers.onboarding.obter_empresa_por_admin", return_value=None)
    async def test_cliente_vinculado_nao_inicia_onboarding(self, mock_admin, mock_cliente):
        from handlers.onboarding import cmd_registrar

        mock_cliente.return_value = make_empresa(nome="Acme")
        update = make_update("/registrar")
        ctx = make_context()

        result = await cmd_registrar(update, ctx)

        self.assertEqual(result, ConversationHandler.END)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("exclusivo do admin", texto.lower())
        self.assertIn("apenas para conversar", texto.lower())

    @patch("handlers.onboarding.obter_empresa_do_cliente", return_value=None)
    @patch("handlers.onboarding.obter_empresa_por_admin", return_value=None)
    async def test_usuario_nao_autorizado_nao_inicia_registro_admin(self, mock_admin, mock_cliente):
        from handlers.onboarding import cmd_registrar

        update = make_update("/registrar", user_id=100)
        ctx = make_context()
        with patch.dict(os.environ, {"TELEGRAM_ADMIN_IDS": "999"}, clear=False):
            result = await cmd_registrar(update, ctx)

        self.assertEqual(result, ConversationHandler.END)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("usuário autorizado como admin", texto)
        self.assertNotIn("nome da sua empresa", texto.lower())


class ReceberNomeEmpresaTests(unittest.IsolatedAsyncioTestCase):
    async def test_nome_valido_avanca(self):
        from handlers.common import AGUARDANDO_NOME_BOT
        from handlers.onboarding import receber_nome_empresa

        update = make_update("Minha Empresa")
        ctx = make_context()
        result = await receber_nome_empresa(update, ctx)
        self.assertEqual(result, AGUARDANDO_NOME_BOT)
        self.assertEqual(ctx.user_data["nome_empresa"], "Minha Empresa")

    async def test_nome_vazio_repete(self):
        from handlers.common import AGUARDANDO_NOME_EMPRESA
        from handlers.onboarding import receber_nome_empresa

        update = make_update("   ")
        ctx = make_context()
        result = await receber_nome_empresa(update, ctx)
        self.assertEqual(result, AGUARDANDO_NOME_EMPRESA)


class ReceberNomeBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_nome_bot_valido(self):
        from handlers.common import AGUARDANDO_SAUDACAO
        from handlers.onboarding import receber_nome_bot

        update = make_update("Ana")
        ctx = make_context()
        result = await receber_nome_bot(update, ctx)
        self.assertEqual(result, AGUARDANDO_SAUDACAO)
        self.assertEqual(ctx.user_data["nome_bot"], "Ana")


class ReceberSaudacaoTests(unittest.IsolatedAsyncioTestCase):
    async def test_saudacao_valida(self):
        from handlers.common import AGUARDANDO_INSTRUCOES
        from handlers.onboarding import receber_saudacao

        update = make_update("Olá, bem-vindo!")
        ctx = make_context()
        result = await receber_saudacao(update, ctx)
        self.assertEqual(result, AGUARDANDO_INSTRUCOES)


class ReceberInstrucoesTests(unittest.IsolatedAsyncioTestCase):
    async def test_instrucoes_validas_mostra_resumo(self):
        from handlers.common import AGUARDANDO_CONFIRMACAO_REGISTRO
        from handlers.onboarding import receber_instrucoes

        update = make_update("Responda sempre de forma educada")
        ctx = make_context(user_data={
            "nome_empresa": "Nova Corp",
            "nome_bot": "Bot",
            "saudacao": "Olá",
        })
        result = await receber_instrucoes(update, ctx)
        self.assertEqual(result, AGUARDANDO_CONFIRMACAO_REGISTRO)
        self.assertEqual(ctx.user_data["instrucoes"], "Responda sempre de forma educada")
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Revise sua configuração", texto)
        self.assertIn("Nova Corp", texto)


class PularInstrucoesTests(unittest.IsolatedAsyncioTestCase):
    async def test_pular_define_instrucoes_padrao_e_mostra_resumo(self):
        from handlers.common import AGUARDANDO_CONFIRMACAO_REGISTRO
        from handlers.onboarding import pular_instrucoes

        update = make_update("/pular")
        ctx = make_context(user_data={
            "nome_empresa": "Nova Corp",
            "nome_bot": "Bot",
            "saudacao": "Olá",
        })
        result = await pular_instrucoes(update, ctx)
        self.assertEqual(result, AGUARDANDO_CONFIRMACAO_REGISTRO)
        self.assertIn("assistente de atendimento", ctx.user_data["instrucoes"])
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Confirma estas informações?", texto)


class CancelarRegistroTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancela_e_limpa_estado(self):
        from handlers.onboarding import cancelar_registro

        update = make_update("/cancelar")
        ctx = make_context(user_data={"nome_empresa": "Teste"})
        result = await cancelar_registro(update, ctx)
        self.assertEqual(result, ConversationHandler.END)


class CmdResetTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.onboarding._obter_empresa_admin_ou_responder")
    async def test_reset_pede_confirmacao(self, mock_admin):
        from handlers.common import AGUARDANDO_CONFIRMACAO_RESET
        from handlers.onboarding import cmd_reset

        mock_admin.return_value = make_empresa(nome="Old Corp")
        update = make_update("/reset")
        ctx = make_context()
        result = await cmd_reset(update, ctx)
        self.assertEqual(result, AGUARDANDO_CONFIRMACAO_RESET)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Tem certeza", texto)
        self.assertIn("Old Corp", texto)

    @patch("handlers.onboarding._obter_empresa_admin_ou_responder", return_value=None)
    async def test_reset_sem_empresa_retorna_end(self, mock_admin):
        from handlers.onboarding import cmd_reset

        update = make_update("/reset")
        ctx = make_context()
        result = await cmd_reset(update, ctx)
        self.assertEqual(result, ConversationHandler.END)


class ResetCallbacksTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding._obter_empresa_admin_ou_responder")
    @patch("handlers.onboarding.excluir_empresa_com_dados", new_callable=AsyncMock)
    @patch("handlers.onboarding._remover_arquivos_empresa")
    async def test_reset_confirmado_apaga_e_reinicia(self, mock_rm, mock_excl, mock_admin, mock_sync):
        from handlers.common import AGUARDANDO_NOME_EMPRESA
        from handlers.onboarding import reset_confirmar_callback

        mock_admin.return_value = make_empresa(nome="Old Corp")
        update = make_update("/reset", callback_data="reset_confirmar")
        ctx = make_context()
        result = await reset_confirmar_callback(update, ctx)
        self.assertEqual(result, AGUARDANDO_NOME_EMPRESA)
        update.callback_query.answer.assert_awaited_once()
        mock_excl.assert_awaited_once_with(1)
        mock_rm.assert_called_once_with(1)
        mock_sync.assert_awaited_once()
        self.assertEqual(update.effective_message.reply_text.await_count, 2)
        self.assertIn("foi apagada", update.effective_message.reply_text.await_args_list[0].args[0])
        self.assertIn("nome da sua empresa", update.effective_message.reply_text.await_args_list[1].args[0])

    async def test_reset_cancelado_retorna_end(self):
        from handlers.onboarding import reset_cancelar_callback

        update = make_update("/reset", callback_data="reset_cancelar")
        ctx = make_context()
        result = await reset_cancelar_callback(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        update.callback_query.answer.assert_awaited_once()
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Reset cancelado", texto)


class ConfirmarRegistroTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding.criar_empresa", new_callable=AsyncMock, return_value=1)
    @patch("handlers.onboarding.atualizar_empresa", new_callable=AsyncMock)
    async def test_confirma_registro_com_sucesso(self, mock_att, mock_criar, mock_sync):
        from handlers.onboarding import confirmar_registro_callback

        update = make_update("instrucoes", callback_data="registro_confirmar")
        ctx = make_context(user_data={
            "nome_empresa": "Nova Corp",
            "nome_bot": "Bot",
            "saudacao": "Olá",
            "instrucoes": "Seja educado",
        })
        result = await confirmar_registro_callback(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        update.callback_query.answer.assert_awaited_once()
        mock_criar.assert_awaited_once_with("Nova Corp", 100)
        mock_att.assert_awaited_once_with(
            1,
            nome_bot="Bot",
            saudacao="Olá",
            instrucoes="Seja educado",
        )
        # Deve limpar dados temporários
        self.assertNotIn("nome_empresa", ctx.user_data)
        self.assertNotIn("nome_bot", ctx.user_data)
        self.assertNotIn("saudacao", ctx.user_data)
        self.assertNotIn("instrucoes", ctx.user_data)


class CmdSairTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.onboarding.obter_empresa_por_admin")
    async def test_admin_nao_pode_sair(self, mock_admin):
        from handlers.onboarding import cmd_sair

        mock_admin.return_value = make_empresa(nome="Acme")
        update = make_update("/sair")
        ctx = make_context()
        await cmd_sair(update, ctx)
        texto = update.message.reply_text.call_args[0][0]
        self.assertIn("Admins não podem usar /sair", texto)

    @patch("handlers.onboarding.obter_empresa_do_cliente", return_value=None)
    @patch("handlers.onboarding.obter_empresa_por_admin", return_value=None)
    async def test_cliente_sem_vinculo_recebe_aviso(self, mock_admin, mock_cliente):
        from handlers.onboarding import cmd_sair

        update = make_update("/sair")
        ctx = make_context()
        await cmd_sair(update, ctx)
        texto = update.message.reply_text.call_args[0][0]
        self.assertIn("não está vinculado", texto)

    @patch("handlers.onboarding._sincronizar_comandos_do_chat", new_callable=AsyncMock)
    @patch("handlers.onboarding.desvincular_cliente", new_callable=AsyncMock, return_value=True)
    @patch("handlers.onboarding.obter_empresa_do_cliente")
    @patch("handlers.onboarding.obter_empresa_por_admin", return_value=None)
    async def test_cliente_pode_sair_do_atendimento(self, mock_admin, mock_cliente, mock_desvincular, mock_sync):
        from handlers.onboarding import cmd_sair

        mock_cliente.return_value = make_empresa(nome="Acme")
        update = make_update("/sair")
        ctx = make_context()
        await cmd_sair(update, ctx)
        mock_desvincular.assert_awaited_once_with(100)
        mock_sync.assert_awaited_once()
        texto = update.message.reply_text.call_args[0][0]
        self.assertIn("Você saiu do atendimento de *Acme*", texto)
