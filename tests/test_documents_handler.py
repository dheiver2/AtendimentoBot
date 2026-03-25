"""Testes para handlers/documents.py — upload e gestão de documentos."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.ext import ConversationHandler

from tests.helpers import make_context, make_empresa, make_update


class CaminhoDocumentoTests(unittest.TestCase):
    def test_caminho(self):
        from handlers.documents import _caminho_documento
        caminho = _caminho_documento(1, "manual.pdf")
        self.assertIn("1", caminho)
        self.assertTrue(caminho.endswith("manual.pdf"))


class RotuloDocumentoTests(unittest.TestCase):
    def test_nome_curto(self):
        from handlers.documents import _rotulo_documento
        self.assertEqual(_rotulo_documento("faq.txt", 1), "1. faq.txt")

    def test_nome_longo_trunca(self):
        from handlers.documents import _rotulo_documento
        resultado = _rotulo_documento("manual_extremamente_longo_demais.pdf", 2)
        self.assertIn("...", resultado)
        self.assertTrue(resultado.startswith("2. "))


class ResumoReindexacaoTests(unittest.TestCase):
    def test_sem_avisos(self):
        from handlers.documents import _resumo_reindexacao
        resultado = _resumo_reindexacao(3, [])
        self.assertIn("3", resultado)
        self.assertNotIn("Aviso", resultado)

    def test_com_avisos(self):
        from handlers.documents import _resumo_reindexacao
        resultado = _resumo_reindexacao(1, ["aviso1", "aviso2"])
        self.assertIn("Aviso", resultado)
        self.assertIn("aviso1", resultado)

    def test_avisos_truncados(self):
        from handlers.documents import _resumo_reindexacao
        avisos = [f"aviso{i}" for i in range(10)]
        resultado = _resumo_reindexacao(1, avisos)
        self.assertIn("mais 7 aviso", resultado)


class CmdUploadTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.documents._obter_empresa_admin_ou_responder", return_value=None)
    async def test_sem_empresa(self, mock_admin):
        from handlers.documents import cmd_upload
        update = make_update()
        ctx = make_context()
        result = await cmd_upload(update, ctx)
        self.assertEqual(result, ConversationHandler.END)

    @patch("handlers.documents._obter_empresa_admin_ou_responder")
    async def test_inicia_upload(self, mock_admin):
        from handlers.common import AGUARDANDO_DOCUMENTO
        from handlers.documents import cmd_upload

        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context()
        result = await cmd_upload(update, ctx)
        self.assertEqual(result, AGUARDANDO_DOCUMENTO)
        self.assertEqual(ctx.user_data["empresa_upload_id"], 1)


class FinalizarUploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_finaliza(self):
        from handlers.documents import finalizar_upload
        update = make_update()
        ctx = make_context(user_data={"empresa_upload_id": 1})
        result = await finalizar_upload(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        self.assertNotIn("empresa_upload_id", ctx.user_data)


class ReceberDocumentoTests(unittest.IsolatedAsyncioTestCase):
    async def test_sem_estado_retorna_erro(self):
        from handlers.documents import receber_documento
        update = make_update()
        ctx = make_context(user_data={})
        result = await receber_documento(update, ctx)
        self.assertEqual(result, ConversationHandler.END)

    @patch("handlers.documents._processar_documento_enviado", new_callable=AsyncMock, return_value=5)
    async def test_com_estado_processa(self, mock_proc):
        from handlers.documents import receber_documento
        update = make_update()
        ctx = make_context(user_data={"empresa_upload_id": 1})
        await receber_documento(update, ctx)
        mock_proc.assert_called_once_with(update, 1, modo_upload=True)


class ReceberDocumentoDiretoTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.documents._obter_empresa_admin_ou_responder", return_value=None)
    async def test_sem_empresa(self, mock_admin):
        from handlers.documents import receber_documento_direto
        update = make_update()
        ctx = make_context()
        await receber_documento_direto(update, ctx)

    @patch("handlers.documents._obter_empresa_admin_ou_responder")
    @patch("handlers.documents._processar_documento_enviado", new_callable=AsyncMock)
    async def test_com_empresa_processa(self, mock_proc, mock_admin):
        from handlers.documents import receber_documento_direto
        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context()
        await receber_documento_direto(update, ctx)
        mock_proc.assert_called_once_with(update, 1, modo_upload=False)


class ProcessarDocumentoEnviadoTests(unittest.IsolatedAsyncioTestCase):
    def _make_doc_update(self, file_name="manual.pdf"):
        update = make_update()
        doc = MagicMock()
        doc.file_name = file_name
        doc.mime_type = "application/pdf"
        doc.get_file = AsyncMock(return_value=MagicMock(
            download_as_bytearray=AsyncMock(return_value=bytearray(b"conteudo"))
        ))
        update.message.document = doc
        return update

    @patch("handlers.documents.arquivo_suportado", return_value=False)
    async def test_formato_nao_suportado(self, mock_sup):
        from handlers.common import AGUARDANDO_DOCUMENTO
        from handlers.documents import _processar_documento_enviado

        update = self._make_doc_update("arquivo.xyz")
        result = await _processar_documento_enviado(update, 1, modo_upload=True)
        self.assertEqual(result, AGUARDANDO_DOCUMENTO)

    @patch("handlers.documents.arquivo_suportado", return_value=True)
    @patch("handlers.documents.verificar_rate_limit", return_value="⏳ muito rápido")
    async def test_rate_limit(self, mock_rate, mock_sup):
        from handlers.documents import _processar_documento_enviado

        update = self._make_doc_update()
        result = await _processar_documento_enviado(update, 1, modo_upload=False)
        self.assertIsNone(result)

    @patch("handlers.documents.arquivo_suportado", return_value=True)
    @patch("handlers.documents.verificar_rate_limit", return_value=None)
    @patch("handlers.documents.listar_documentos", new_callable=AsyncMock)
    async def test_limite_documentos_atingido(self, mock_docs, mock_rate, mock_sup):
        from handlers.documents import _processar_documento_enviado
        from validators import MAX_DOCUMENTOS_POR_EMPRESA

        mock_docs.return_value = [{"id": i} for i in range(MAX_DOCUMENTOS_POR_EMPRESA)]
        update = self._make_doc_update()
        result = await _processar_documento_enviado(update, 1, modo_upload=False)
        self.assertIsNone(result)
        self.assertIn("Limite", update.message.reply_text.call_args[0][0])

    @patch("handlers.documents.arquivo_suportado", return_value=True)
    @patch("handlers.documents.verificar_rate_limit", return_value=None)
    @patch("handlers.documents.listar_documentos", new_callable=AsyncMock, return_value=[])
    @patch("handlers.documents.processar_documento", return_value=["chunk1", "chunk2"])
    @patch("handlers.documents.registrar_documento", new_callable=AsyncMock)
    @patch("handlers.documents.adicionar_documentos")
    @patch("handlers.documents.os.path.exists", return_value=False)
    async def test_processa_novo_documento(self, mock_exists, mock_add, mock_reg, mock_proc, mock_docs, mock_rate, mock_sup):
        from handlers.documents import _processar_documento_enviado

        update = self._make_doc_update()
        result = await _processar_documento_enviado(update, 1, modo_upload=False)
        self.assertIsNone(result)
        mock_proc.assert_called_once()
        mock_add.assert_called_once()
        # Verifica se a mensagem de sucesso contém o nome do arquivo
        texto_sucesso = update.message.reply_text.call_args_list[-1][0][0]
        self.assertIn("manual.pdf", texto_sucesso)

    @patch("handlers.documents.arquivo_suportado", return_value=True)
    @patch("handlers.documents.verificar_rate_limit", return_value=None)
    @patch("handlers.documents.listar_documentos", new_callable=AsyncMock, return_value=[])
    @patch("handlers.documents.processar_documento", side_effect=ValueError("Arquivo vazio"))
    async def test_erro_validacao(self, mock_proc, mock_docs, mock_rate, mock_sup):
        from handlers.documents import _processar_documento_enviado

        update = self._make_doc_update()
        result = await _processar_documento_enviado(update, 1, modo_upload=False)
        self.assertIsNone(result)
        texto = update.message.reply_text.call_args[0][0]
        self.assertIn("Arquivo vazio", texto)


class CmdDocumentosTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.documents._obter_empresa_admin_ou_responder", return_value=None)
    async def test_sem_empresa(self, mock_admin):
        from handlers.documents import cmd_documentos
        update = make_update()
        ctx = make_context()
        await cmd_documentos(update, ctx)

    @patch("handlers.documents._obter_empresa_admin_ou_responder")
    @patch("handlers.documents.listar_documentos", new_callable=AsyncMock, return_value=[])
    @patch("handlers.documents._editar_ou_responder", new_callable=AsyncMock)
    async def test_sem_documentos(self, mock_edit, mock_docs, mock_admin):
        from handlers.documents import cmd_documentos
        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context()
        await cmd_documentos(update, ctx)
        mock_edit.assert_called_once()
        texto = mock_edit.call_args[0][1]
        self.assertIn("Nenhum documento", texto)

    @patch("handlers.documents._obter_empresa_admin_ou_responder")
    @patch("handlers.documents.listar_documentos", new_callable=AsyncMock)
    @patch("handlers.documents._editar_ou_responder", new_callable=AsyncMock)
    async def test_com_documentos(self, mock_edit, mock_docs, mock_admin):
        from handlers.documents import cmd_documentos
        mock_admin.return_value = make_empresa()
        mock_docs.return_value = [{"id": 1, "nome_arquivo": "doc.pdf", "carregado_em": "2024-01-01"}]
        update = make_update()
        ctx = make_context()
        await cmd_documentos(update, ctx)
        mock_edit.assert_called_once()
        texto = mock_edit.call_args[0][1]
        self.assertIn("doc.pdf", texto)


class DocsCallbackTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.documents._obter_empresa_admin_ou_responder")
    @patch("handlers.documents._reindexar_base_empresa", new_callable=AsyncMock, return_value=(2, []))
    @patch("handlers.documents.cmd_documentos", new_callable=AsyncMock)
    async def test_reindexar_callback(self, mock_cmd, mock_reindex, mock_admin):
        from handlers.documents import docs_reindexar_callback
        mock_admin.return_value = make_empresa()
        update = make_update(callback_data="docs_reindexar")
        ctx = make_context()
        await docs_reindexar_callback(update, ctx)
        mock_reindex.assert_called_once_with(1)

    @patch("handlers.documents._obter_empresa_admin_ou_responder")
    @patch("handlers.documents.obter_documento_por_id", new_callable=AsyncMock, return_value=None)
    @patch("handlers.documents.cmd_documentos", new_callable=AsyncMock)
    async def test_reprocessar_doc_nao_encontrado(self, mock_cmd, mock_doc, mock_admin):
        from handlers.documents import docs_reprocessar_callback
        mock_admin.return_value = make_empresa()
        update = make_update(callback_data="docs_reprocessar:99")
        ctx = make_context()
        await docs_reprocessar_callback(update, ctx)
        texto = update.callback_query.message.reply_text.call_args[0][0]
        self.assertIn("não encontrado", texto)

    @patch("handlers.documents._obter_empresa_admin_ou_responder")
    @patch("handlers.documents.obter_documento_por_id", new_callable=AsyncMock, return_value=None)
    @patch("handlers.documents.cmd_documentos", new_callable=AsyncMock)
    async def test_excluir_doc_nao_encontrado(self, mock_cmd, mock_doc, mock_admin):
        from handlers.documents import docs_excluir_callback
        mock_admin.return_value = make_empresa()
        update = make_update(callback_data="docs_excluir:99")
        ctx = make_context()
        await docs_excluir_callback(update, ctx)
        texto = update.callback_query.message.reply_text.call_args[0][0]
        self.assertIn("não encontrado", texto)
