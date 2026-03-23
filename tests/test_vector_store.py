"""Testes para vector_store.py — operações com FAISS."""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import vector_store as vs


class CaminhoStoreTests(unittest.TestCase):
    def test_retorna_caminho_correto(self):
        caminho = vs._caminho_store(42)
        self.assertIn("42", caminho)


class EmpresaTemDocumentosTests(unittest.TestCase):
    def test_retorna_false_quando_nao_existe(self):
        with patch("vector_store.os.path.exists", return_value=False):
            self.assertFalse(vs.empresa_tem_documentos(999))

    def test_retorna_true_quando_existe(self):
        with patch("vector_store.os.path.exists", return_value=True):
            self.assertTrue(vs.empresa_tem_documentos(1))


class AdicionarDocumentosTests(unittest.TestCase):
    @patch("vector_store._get_embeddings")
    @patch("vector_store.os.path.exists", return_value=False)
    @patch("vector_store.FAISS")
    def test_cria_novo_store(self, mock_faiss, mock_exists, mock_emb):
        mock_store = MagicMock()
        mock_faiss.from_texts.return_value = mock_store
        vs.adicionar_documentos(1, ["chunk1", "chunk2"], {"arquivo": "doc.pdf"})
        mock_faiss.from_texts.assert_called_once()
        mock_store.save_local.assert_called_once()

    @patch("vector_store._get_embeddings")
    @patch("vector_store.os.path.exists", return_value=True)
    @patch("vector_store.FAISS")
    def test_adiciona_ao_store_existente(self, mock_faiss, mock_exists, mock_emb):
        mock_store = MagicMock()
        mock_faiss.load_local.return_value = mock_store
        vs.adicionar_documentos(1, ["chunk3"], {"arquivo": "novo.pdf"})
        mock_faiss.load_local.assert_called_once()
        mock_store.add_texts.assert_called_once()
        mock_store.save_local.assert_called_once()


class SubstituirDocumentosTests(unittest.TestCase):
    @patch("vector_store._get_embeddings")
    @patch("vector_store.os.path.exists", return_value=True)
    @patch("vector_store.shutil.rmtree")
    @patch("vector_store.FAISS")
    def test_reconstroi_store(self, mock_faiss, mock_rm, mock_exists, mock_emb):
        mock_store = MagicMock()
        mock_faiss.from_texts.return_value = mock_store
        vs.substituir_documentos(1, [(["chunk1"], {"arquivo": "a.pdf"})])
        mock_rm.assert_called_once()
        mock_faiss.from_texts.assert_called_once()
        mock_store.save_local.assert_called_once()

    @patch("vector_store.os.path.exists", return_value=True)
    @patch("vector_store.shutil.rmtree")
    def test_lista_vazia_apenas_remove(self, mock_rm, mock_exists):
        vs.substituir_documentos(1, [])
        mock_rm.assert_called_once()

    @patch("vector_store.os.path.exists", return_value=False)
    def test_sem_store_e_sem_docs(self, mock_exists):
        # Não deve lançar erro
        vs.substituir_documentos(999, [])

    @patch("vector_store._get_embeddings")
    @patch("vector_store.os.path.exists", return_value=False)
    @patch("vector_store.FAISS")
    def test_chunks_vazios_ignorados(self, mock_faiss, mock_exists, mock_emb):
        vs.substituir_documentos(1, [([], {"arquivo": "vazio.pdf"})])
        mock_faiss.from_texts.assert_not_called()


class BuscarContextoTests(unittest.TestCase):
    def setUp(self):
        vs._carregar_store_cache.cache_clear()
        vs._get_embeddings.cache_clear()

    @patch("vector_store.os.path.exists", return_value=False)
    def test_sem_store_retorna_lista_vazia(self, mock_exists):
        resultado = vs.buscar_contexto(999, "pergunta")
        self.assertEqual(resultado, [])

    @patch("vector_store._get_embeddings")
    @patch("vector_store.os.path.exists", return_value=True)
    @patch("vector_store.FAISS")
    def test_retorna_conteudo_documentos(self, mock_faiss, mock_exists, mock_emb):
        mock_doc1 = MagicMock()
        mock_doc1.page_content = "Resposta 1"
        mock_doc2 = MagicMock()
        mock_doc2.page_content = "Resposta 2"
        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1, 0.2]
        mock_emb.return_value = mock_embeddings
        mock_store = MagicMock()
        mock_store.index.d = 2
        mock_store.similarity_search.return_value = [mock_doc1, mock_doc2]
        mock_faiss.load_local.return_value = mock_store
        resultado = vs.buscar_contexto(1, "pergunta")
        self.assertEqual(resultado, ["Resposta 1", "Resposta 2"])

    @patch("vector_store._get_embeddings")
    @patch("vector_store.os.path.exists", return_value=True)
    @patch("vector_store.FAISS")
    def test_mismatch_de_dimensao_gera_erro_claro(self, mock_faiss, mock_exists, mock_emb):
        mock_embeddings = MagicMock()
        mock_emb.return_value = mock_embeddings

        mock_store = MagicMock()
        mock_store.similarity_search.side_effect = AssertionError("dimensao invalida")
        mock_faiss.load_local.return_value = mock_store

        with self.assertRaises(vs.VectorStoreIncompatibilityError) as ctx:
            vs.buscar_contexto(1, "pergunta")

        self.assertIn("Reindexar Base", str(ctx.exception))
