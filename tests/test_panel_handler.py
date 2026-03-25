"""Testes para handlers/panel.py — painel, ajuda, link, status."""
import os
import unittest
from unittest.mock import AsyncMock, patch

from tests.helpers import make_context, make_empresa, make_update


class CmdPainelTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.panel._obter_empresa_admin_ou_responder", return_value=None)
    async def test_sem_empresa(self, mock_admin):
        from handlers.panel import cmd_painel
        update = make_update()
        ctx = make_context()
        await cmd_painel(update, ctx)
        update.effective_message.reply_text.assert_not_called()

    @patch("handlers.panel._obter_empresa_admin_ou_responder")
    @patch("handlers.panel.listar_documentos", new_callable=AsyncMock, return_value=[])
    @patch("handlers.panel.listar_faqs", new_callable=AsyncMock, return_value=[])
    @patch("handlers.panel.contar_clientes_empresa", new_callable=AsyncMock, return_value=5)
    @patch("handlers.panel.empresa_tem_documentos", return_value=True)
    @patch("handlers.panel.empresa_tem_imagem", return_value=False)
    async def test_painel_completo(self, mock_img, mock_docs, mock_clientes, mock_faqs, mock_list_docs, mock_admin):
        from handlers.panel import cmd_painel
        mock_admin.return_value = make_empresa(nome="TestCorp")
        update = make_update()
        update.callback_query = None
        ctx = make_context()
        await cmd_painel(update, ctx)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("TestCorp", texto)
        self.assertIn("5", texto)

    @patch("handlers.panel._obter_empresa_admin_ou_responder")
    @patch("handlers.panel.listar_documentos", new_callable=AsyncMock, return_value=[])
    @patch("handlers.panel.listar_faqs", new_callable=AsyncMock, return_value=[])
    @patch("handlers.panel.contar_clientes_empresa", new_callable=AsyncMock, return_value=0)
    @patch("handlers.panel.empresa_tem_documentos", return_value=False)
    @patch("handlers.panel.empresa_tem_imagem", return_value=False)
    async def test_painel_sem_documentos_mostra_status_incompleto(self, mock_img, mock_docs, mock_clientes, mock_faqs, mock_list_docs, mock_admin):
        from handlers.panel import cmd_painel
        mock_admin.return_value = make_empresa()
        update = make_update()
        update.callback_query = None
        ctx = make_context()
        await cmd_painel(update, ctx)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Sem documentos", texto)


class CmdAjudaTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.panel.obter_empresa_por_admin")
    @patch("handlers.panel.obter_empresa_do_cliente", return_value=None)
    async def test_ajuda_admin(self, mock_cliente, mock_admin):
        from handlers.panel import cmd_ajuda
        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context()
        await cmd_ajuda(update, ctx)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("/painel", texto)
        self.assertIn("/meuid", texto)

    @patch("handlers.panel.obter_empresa_por_admin", return_value=None)
    @patch("handlers.panel.obter_empresa_do_cliente")
    async def test_ajuda_cliente(self, mock_cliente, mock_admin):
        from handlers.panel import cmd_ajuda
        mock_cliente.return_value = make_empresa(nome="EmpCliente")
        update = make_update()
        ctx = make_context()
        await cmd_ajuda(update, ctx)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("EmpCliente", texto)
        self.assertIn("/meuid", texto)

    @patch("handlers.panel.obter_empresa_por_admin", return_value=None)
    @patch("handlers.panel.obter_empresa_do_cliente", return_value=None)
    async def test_ajuda_desconhecido(self, mock_cliente, mock_admin):
        from handlers.panel import cmd_ajuda
        update = make_update()
        ctx = make_context()
        await cmd_ajuda(update, ctx)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("/start", texto)
        self.assertIn("/meuid", texto)

    @patch("handlers.panel.obter_empresa_por_admin", return_value=None)
    @patch("handlers.panel.obter_empresa_do_cliente", return_value=None)
    async def test_ajuda_desconhecido_com_allowlist_exige_link_admin(self, mock_cliente, mock_admin):
        from handlers.panel import cmd_ajuda

        update = make_update(user_id=100)
        ctx = make_context()
        with patch.dict(os.environ, {"TELEGRAM_ADMIN_IDS": "999"}, clear=False):
            await cmd_ajuda(update, ctx)

        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("link de admin", texto.lower())
        self.assertNotIn("envie /start para iniciar a configuração", texto.lower())


class CmdMeuIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_exibe_ids_do_usuario_e_chat(self):
        from handlers.panel import cmd_meuid

        update = make_update(user_id=123456789)
        ctx = make_context()
        await cmd_meuid(update, ctx)
        texto = update.effective_message.reply_text.call_args[0][0]
        kwargs = update.effective_message.reply_text.call_args.kwargs

        self.assertIn("123456789", texto)
        self.assertIn("Chat atual", texto)
        self.assertEqual(kwargs["parse_mode"], "Markdown")


class CmdLinkTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.panel._obter_empresa_admin_ou_responder", return_value=None)
    async def test_sem_empresa(self, mock_admin):
        from handlers.panel import cmd_link
        update = make_update()
        ctx = make_context()
        await cmd_link(update, ctx)

    @patch("handlers.panel._obter_empresa_admin_ou_responder")
    async def test_gera_link(self, mock_admin):
        from handlers.panel import cmd_link
        mock_admin.return_value = make_empresa(link_token="tok123", admin_link_token="adm123")
        update = make_update()
        ctx = make_context()
        await cmd_link(update, ctx)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("t.me/test_bot?start=tok123", texto)
        self.assertIn("t.me/test_bot?start=admin_adm123", texto)
        self.assertIn("cliente", texto.lower())
        self.assertIn("admin", texto.lower())


class CmdStatusTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.panel._obter_empresa_admin_ou_responder")
    @patch("handlers.panel.empresa_tem_documentos", return_value=True)
    @patch("handlers.panel.listar_documentos", new_callable=AsyncMock, return_value=[{"id": 1}])
    @patch("handlers.panel.listar_faqs", new_callable=AsyncMock, return_value=[])
    @patch("handlers.panel.contar_clientes_empresa", new_callable=AsyncMock, return_value=2)
    @patch("handlers.panel.empresa_tem_imagem", return_value=True)
    @patch("handlers.panel.obter_resumo_metricas_empresa", new_callable=AsyncMock)
    @patch("handlers.panel._enviar_preview_imagem_empresa", new_callable=AsyncMock)
    async def test_status_configurado(self, mock_preview, mock_metricas, mock_img, mock_clientes, mock_faqs, mock_docs, mock_tem, mock_admin):
        from handlers.panel import cmd_status
        mock_admin.return_value = make_empresa(nome="Acme")
        mock_metricas.return_value = {
            "janela_horas": 24,
            "atendimentos": {
                "total": 10,
                "media_segundos": 1.25,
                "p95_segundos": 2.4,
                "taxa_rag": 0.4,
                "taxa_sucesso": 0.9,
                "decisoes": {"faq": 4, "rag": 3, "trivial": 2},
            },
            "rag": {
                "total": 4,
                "media_segundos": 1.8,
                "p95_segundos": 3.1,
                "taxa_cache_hit": 0.25,
                "taxa_sucesso": 0.75,
            },
        }
        update = make_update()
        ctx = make_context()
        await cmd_status(update, ctx)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("CONFIGURADO", texto)
        self.assertIn("Métricas recentes", texto)
        self.assertIn("Top decisões", texto)
        mock_preview.assert_called_once()

    @patch("handlers.panel._obter_empresa_admin_ou_responder")
    @patch("handlers.panel.empresa_tem_documentos", return_value=False)
    @patch("handlers.panel.listar_documentos", new_callable=AsyncMock, return_value=[])
    @patch("handlers.panel.listar_faqs", new_callable=AsyncMock, return_value=[])
    @patch("handlers.panel.contar_clientes_empresa", new_callable=AsyncMock, return_value=0)
    @patch("handlers.panel.empresa_tem_imagem", return_value=False)
    @patch("handlers.panel.obter_resumo_metricas_empresa", new_callable=AsyncMock, return_value=None)
    async def test_status_incompleto(self, mock_metricas, mock_img, mock_clientes, mock_faqs, mock_docs, mock_tem, mock_admin):
        from handlers.panel import cmd_status
        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context()
        await cmd_status(update, ctx)
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("INCOMPLETO", texto)
        self.assertIn("ainda sem dados", texto)


class PainelCallbacksTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.panel.cmd_painel", new_callable=AsyncMock)
    async def test_refresh_callback(self, mock_painel):
        from handlers.panel import painel_refresh_callback
        update = make_update(callback_data="painel_refresh")
        ctx = make_context()
        await painel_refresh_callback(update, ctx)
        mock_painel.assert_called_once()

    @patch("handlers.panel.cmd_status", new_callable=AsyncMock)
    async def test_status_callback(self, mock_status):
        from handlers.panel import painel_status_callback
        update = make_update(callback_data="painel_status")
        ctx = make_context()
        await painel_status_callback(update, ctx)
        mock_status.assert_called_once()

    @patch("handlers.panel.cmd_ajuda", new_callable=AsyncMock)
    async def test_ajuda_callback(self, mock_ajuda):
        from handlers.panel import painel_ajuda_callback
        update = make_update(callback_data="painel_ajuda")
        ctx = make_context()
        await painel_ajuda_callback(update, ctx)
        mock_ajuda.assert_called_once()
