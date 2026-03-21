"""Testes para handlers/common.py — utilitários compartilhados."""
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from tests.helpers import make_update, make_context, make_empresa


class ObterPayloadStartTests(unittest.TestCase):
    def test_sem_args(self):
        from handlers.common import _obter_payload_start
        ctx = make_context(args=None)
        ctx.args = None
        self.assertIsNone(_obter_payload_start(ctx))

    def test_args_vazio(self):
        from handlers.common import _obter_payload_start
        ctx = make_context(args=[])
        ctx.args = []
        self.assertIsNone(_obter_payload_start(ctx))

    def test_args_com_payload(self):
        from handlers.common import _obter_payload_start
        ctx = make_context(args=["abc123"])
        ctx.args = ["abc123"]
        self.assertEqual(_obter_payload_start(ctx), "abc123")

    def test_args_com_espaco(self):
        from handlers.common import _obter_payload_start
        ctx = make_context(args=["  token_xyz  "])
        ctx.args = ["  token_xyz  "]
        self.assertEqual(_obter_payload_start(ctx), "token_xyz")


class MensagemSomenteAdminTests(unittest.TestCase):
    def test_retorna_texto(self):
        from handlers.common import _mensagem_somente_admin
        texto = _mensagem_somente_admin()
        self.assertIn("admin", texto.lower())
        self.assertIn("exclusivo", texto.lower())


class ObterEmpresaAdminOuResponderTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.common.obter_empresa_por_admin")
    async def test_retorna_empresa_quando_admin(self, mock_admin):
        from handlers.common import _obter_empresa_admin_ou_responder
        empresa = make_empresa()
        mock_admin.return_value = empresa
        update = make_update()
        resultado = await _obter_empresa_admin_ou_responder(update)
        self.assertEqual(resultado, empresa)

    @patch("handlers.common.obter_empresa_por_admin", return_value=None)
    @patch("handlers.common.obter_empresa_do_cliente")
    async def test_cliente_recebe_mensagem_somente_admin(self, mock_cliente, mock_admin):
        from handlers.common import _obter_empresa_admin_ou_responder
        mock_cliente.return_value = make_empresa()
        update = make_update()
        resultado = await _obter_empresa_admin_ou_responder(update)
        self.assertIsNone(resultado)
        update.effective_message.reply_text.assert_called_once()
        self.assertIn("admin", update.effective_message.reply_text.call_args[0][0].lower())

    @patch("handlers.common.obter_empresa_por_admin", return_value=None)
    @patch("handlers.common.obter_empresa_do_cliente", return_value=None)
    async def test_usuario_desconhecido_recebe_mensagem_padrao(self, mock_cliente, mock_admin):
        from handlers.common import _obter_empresa_admin_ou_responder
        update = make_update()
        resultado = await _obter_empresa_admin_ou_responder(update)
        self.assertIsNone(resultado)
        self.assertIn("/start", update.effective_message.reply_text.call_args[0][0])

    @patch("handlers.common.obter_empresa_por_admin", return_value=None)
    @patch("handlers.common.obter_empresa_do_cliente", return_value=None)
    async def test_mensagem_personalizada(self, mock_cliente, mock_admin):
        from handlers.common import _obter_empresa_admin_ou_responder
        update = make_update()
        resultado = await _obter_empresa_admin_ou_responder(update, "Minha mensagem custom")
        self.assertIsNone(resultado)
        update.effective_message.reply_text.assert_called_once_with("Minha mensagem custom")


class EnviarBoasVindasClienteTests(unittest.IsolatedAsyncioTestCase):
    async def test_envia_texto_com_nome_empresa(self):
        from handlers.common import _enviar_boas_vindas_cliente
        msg = AsyncMock()
        empresa = make_empresa(nome="MinhaEmpresa", saudacao="Bem-vindo!")
        await _enviar_boas_vindas_cliente(msg, empresa)
        msg.reply_text.assert_called_once()
        texto = msg.reply_text.call_args[0][0]
        self.assertIn("MinhaEmpresa", texto)
        self.assertIn("Bem-vindo!", texto)


class SincronizarComandosChatTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.common.sincronizar_comandos_chat", new_callable=AsyncMock)
    async def test_chama_sincronizar(self, mock_sync):
        from handlers.common import _sincronizar_comandos_do_chat
        update = make_update()
        ctx = make_context()
        await _sincronizar_comandos_do_chat(update, ctx, "admin")
        mock_sync.assert_called_once()

    @patch("handlers.common.sincronizar_comandos_chat", new_callable=AsyncMock, side_effect=RuntimeError("fail"))
    async def test_erro_nao_propaga(self, mock_sync):
        from handlers.common import _sincronizar_comandos_do_chat
        update = make_update()
        ctx = make_context()
        # Não deve lançar exceção
        await _sincronizar_comandos_do_chat(update, ctx, "admin")


class MontarLinkAtendimentoTests(unittest.TestCase):
    def test_com_arroba(self):
        from handlers.common import _montar_link_atendimento
        link = _montar_link_atendimento("@meu_bot", "token123")
        self.assertEqual(link, "https://t.me/meu_bot?start=token123")

    def test_sem_arroba(self):
        from handlers.common import _montar_link_atendimento
        link = _montar_link_atendimento("meu_bot", "token123")
        self.assertEqual(link, "https://t.me/meu_bot?start=token123")


class EditarOuResponderTests(unittest.IsolatedAsyncioTestCase):
    async def test_sem_callback_responde_normalmente(self):
        from handlers.common import _editar_ou_responder
        update = make_update("x")
        update.callback_query = None
        await _editar_ou_responder(update, "Texto")
        update.effective_message.reply_text.assert_called_once()

    async def test_com_callback_edita_mensagem(self):
        from handlers.common import _editar_ou_responder
        update = make_update("x", callback_data="test")
        await _editar_ou_responder(update, "Texto editado")
        update.callback_query.edit_message_text.assert_called_once()
