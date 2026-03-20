import os
import tempfile
import unittest

import database


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.temp_dir.name, "bot.db")
        await database.init_db()

    async def asyncTearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    async def test_cria_atualiza_e_busca_empresa(self):
        empresa_id = await database.criar_empresa("Acme", 12345)
        await database.atualizar_empresa(
            empresa_id,
            nome_bot="Ana",
            saudacao="Oi",
            instrucoes="Seja objetiva",
        )

        empresa = await database.obter_empresa_por_usuario(12345)

        self.assertIsNotNone(empresa)
        self.assertEqual(empresa["id"], empresa_id)
        self.assertEqual(empresa["nome"], "Acme")
        self.assertEqual(empresa["nome_bot"], "Ana")
        self.assertEqual(empresa["saudacao"], "Oi")
        self.assertEqual(empresa["instrucoes"], "Seja objetiva")

    async def test_documentos_nao_duplicam_por_nome_arquivo(self):
        empresa_id = await database.criar_empresa("Acme", 12345)

        primeiro_id = await database.registrar_documento(empresa_id, "base.txt")
        segundo_id = await database.registrar_documento(empresa_id, "base.txt")

        documentos = await database.listar_documentos(empresa_id)

        self.assertEqual(primeiro_id, segundo_id)
        self.assertEqual(len(documentos), 1)
        self.assertEqual(documentos[0]["nome_arquivo"], "base.txt")

    async def test_exclui_documento_e_empresa_com_dados(self):
        empresa_id = await database.criar_empresa("Acme", 12345)
        documento_id = await database.registrar_documento(empresa_id, "base.txt")
        await database.registrar_conversa(empresa_id, 999, "Oi", "Olá")

        excluido = await database.excluir_documento(empresa_id, documento_id)
        documento = await database.obter_documento_por_id(empresa_id, documento_id)

        self.assertTrue(excluido)
        self.assertIsNone(documento)

        await database.registrar_documento(empresa_id, "novo.txt")
        await database.excluir_empresa_com_dados(empresa_id)

        empresa = await database.obter_empresa_por_usuario(12345)
        documentos = await database.listar_documentos(empresa_id)

        self.assertIsNone(empresa)
        self.assertEqual(documentos, [])
