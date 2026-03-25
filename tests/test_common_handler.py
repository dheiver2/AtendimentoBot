"""Testes para handlers/common.py — utilitários compartilhados."""
import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import AsyncMock, patch

from tests.helpers import make_context, make_empresa, make_update


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
    async def test_usuario_desconhecido_com_allowlist_exige_link_admin(self, mock_cliente, mock_admin):
        from handlers.common import _obter_empresa_admin_ou_responder

        update = make_update(user_id=100)
        with patch.dict(os.environ, {"TELEGRAM_ADMIN_IDS": "999"}, clear=False):
            resultado = await _obter_empresa_admin_ou_responder(update)

        self.assertIsNone(resultado)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("link de admin", texto.lower())
        self.assertNotIn("/start primeiro", texto.lower())

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
        with patch("handlers.common._enviar_preview_imagem_empresa", new_callable=AsyncMock, return_value=False):
            with patch("handlers.common._enviar_identidade_visual_empresa", new_callable=AsyncMock, return_value=False):
                await _enviar_boas_vindas_cliente(msg, empresa)
        msg.reply_text.assert_called_once()
        texto = msg.reply_text.call_args[0][0]
        self.assertIn("MinhaEmpresa", texto)
        self.assertIn("Bem-vindo!", texto)

    async def test_envia_imagem_quando_empresa_tem_identidade_visual(self):
        from handlers.common import _enviar_boas_vindas_cliente

        msg = AsyncMock()
        empresa = make_empresa(id=7, nome="MinhaEmpresa", saudacao="Bem-vindo!")

        with patch("handlers.common._enviar_identidade_visual_empresa", new_callable=AsyncMock, return_value=True) as mock_preview:
            await _enviar_boas_vindas_cliente(msg, empresa)

        mock_preview.assert_called_once()
        msg.reply_text.assert_not_called()


class TextoBoasVindasClienteTests(unittest.TestCase):
    def test_sem_documentos_inclui_fallback(self):
        from handlers.common import _montar_texto_boas_vindas_cliente

        empresa = make_empresa(nome="MinhaEmpresa", saudacao="Bem-vindo!", fallback_contato="(11) 9999-9999")

        texto = _montar_texto_boas_vindas_cliente(empresa, tem_docs=False)

        self.assertIn("ainda está sendo preparado", texto)
        self.assertIn("(11) 9999-9999", texto)


class IdentidadeVisualEmpresaTests(unittest.IsolatedAsyncioTestCase):
    async def test_nao_reenvia_quando_ja_enviada_na_sessao(self):
        from handlers.common import _enviar_identidade_visual_empresa

        msg = AsyncMock()
        empresa = make_empresa()
        ctx = make_context(user_data={"identidade_visual_enviada": True})

        enviado = await _enviar_identidade_visual_empresa(msg, empresa, context=ctx)

        self.assertFalse(enviado)
        msg.reply_photo.assert_not_called()

    async def test_marca_sessao_quando_envia(self):
        from handlers.common import _enviar_identidade_visual_empresa

        msg = AsyncMock()
        empresa = make_empresa()
        ctx = make_context()

        with patch("handlers.common._gerar_capa_empresa", return_value=BytesIO(b"jpg")):
            enviado = await _enviar_identidade_visual_empresa(msg, empresa, context=ctx)

        self.assertTrue(enviado)
        self.assertTrue(ctx.user_data["identidade_visual_enviada"])
        msg.reply_photo.assert_called_once()


class CapaEmpresaTests(unittest.TestCase):
    @patch("handlers.common.obter_caminho_imagem_empresa", return_value="/tmp/arquivo-inexistente.jpg")
    def test_gera_capa_sem_imagem_personalizada(self, mock_caminho):
        from handlers.common import _gerar_capa_empresa

        capa = _gerar_capa_empresa(make_empresa(nome="MinhaEmpresa", saudacao="Bem-vindo!"))

        self.assertIsInstance(capa, BytesIO)
        self.assertGreater(len(capa.getvalue()), 0)


class PreviewImagemEmpresaTests(unittest.IsolatedAsyncioTestCase):
    async def test_envia_preview_quando_imagem_existe(self):
        from handlers.common import _enviar_preview_imagem_empresa

        mensagem = AsyncMock()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as arquivo:
            arquivo.write(b"conteudo-imagem")
            caminho = arquivo.name

        try:
            with patch("handlers.common.obter_caminho_imagem_empresa", return_value=caminho):
                enviado = await _enviar_preview_imagem_empresa(mensagem, empresa_id=1, legenda="Preview atual")
        finally:
            os.unlink(caminho)

        self.assertTrue(enviado)
        mensagem.reply_photo.assert_called_once()


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

    @patch("handlers.common.sincronizar_comandos_chat", new_callable=AsyncMock)
    async def test_sem_chat_nao_sincroniza(self, mock_sync):
        from handlers.common import _sincronizar_comandos_do_chat

        update = make_update()
        update.effective_chat = None
        ctx = make_context()

        await _sincronizar_comandos_do_chat(update, ctx, "cliente")

        mock_sync.assert_not_called()


class MontarLinkAtendimentoTests(unittest.TestCase):
    def test_com_arroba(self):
        from handlers.common import _montar_link_atendimento
        link = _montar_link_atendimento("@meu_bot", "token123")
        self.assertEqual(link, "https://t.me/meu_bot?start=token123")

    def test_sem_arroba(self):
        from handlers.common import _montar_link_atendimento
        link = _montar_link_atendimento("meu_bot", "token123")
        self.assertEqual(link, "https://t.me/meu_bot?start=token123")

    def test_monta_link_admin(self):
        from handlers.common import _montar_link_admin
        link = _montar_link_admin("@meu_bot", "adm123")
        self.assertEqual(link, "https://t.me/meu_bot?start=admin_adm123")

    def test_extrai_token_link_admin(self):
        from handlers.common import _extrair_token_link_admin
        self.assertEqual(_extrair_token_link_admin("admin_adm123"), "adm123")
        self.assertIsNone(_extrair_token_link_admin("abc123"))


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
