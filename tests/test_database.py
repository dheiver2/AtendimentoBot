import asyncio
import os
import sqlite3
import tempfile
import unittest

import database


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.original_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.temp_dir.name, "bot.db")
        await database.init_db()

    async def asyncTearDown(self):
        database.DB_PATH = self.original_db_path
        await asyncio.sleep(0.1)
        self.temp_dir.cleanup()

    async def test_cria_atualiza_e_busca_empresa(self):
        empresa_id = await database.criar_empresa("Acme", 12345)
        await database.atualizar_empresa(
            empresa_id,
            nome_bot="Ana",
            saudacao="Oi",
            instrucoes="Seja objetiva",
            ativo=0,
            horario_atendimento="Seg a Sex, 08h às 18h",
            fallback_contato="WhatsApp (11) 99999-9999",
        )

        empresa = await database.obter_empresa_por_usuario(12345)

        self.assertIsNotNone(empresa)
        self.assertEqual(empresa["id"], empresa_id)
        self.assertEqual(empresa["nome"], "Acme")
        self.assertEqual(empresa["nome_bot"], "Ana")
        self.assertEqual(empresa["saudacao"], "Oi")
        self.assertEqual(empresa["instrucoes"], "Seja objetiva")
        self.assertEqual(empresa["ativo"], 0)
        self.assertEqual(empresa["horario_atendimento"], "Seg a Sex, 08h às 18h")
        self.assertEqual(empresa["fallback_contato"], "WhatsApp (11) 99999-9999")
        self.assertTrue(empresa["link_token"])

    async def test_vincula_cliente_e_resolve_empresa_por_link(self):
        empresa_id = await database.criar_empresa("Acme", 12345)
        empresa_admin = await database.obter_empresa_por_admin(12345)

        self.assertIsNotNone(empresa_admin)
        self.assertEqual(empresa_admin["id"], empresa_id)
        self.assertTrue(empresa_admin["link_token"])

        empresa_por_token = await database.obter_empresa_por_link_token(empresa_admin["link_token"])
        self.assertIsNotNone(empresa_por_token)
        self.assertEqual(empresa_por_token["id"], empresa_id)

        await database.vincular_cliente_empresa(empresa_id, 99999)

        empresa_cliente = await database.obter_empresa_do_cliente(99999)
        empresa_usuario = await database.obter_empresa_do_usuario(99999)
        total_clientes = await database.contar_clientes_empresa(empresa_id)
        admins = await database.listar_ids_admins()
        clientes = await database.listar_ids_clientes()

        self.assertIsNotNone(empresa_cliente)
        self.assertEqual(empresa_cliente["id"], empresa_id)
        self.assertEqual(empresa_usuario["id"], empresa_id)
        self.assertEqual(total_clientes, 1)
        self.assertEqual(admins, [12345])
        self.assertEqual(clientes, [99999])

    async def test_migra_tabela_legada_clientes_empresa(self):
        empresa_id = await database.criar_empresa("Acme", 12345)

        with sqlite3.connect(database.DB_PATH) as conn:
            conn.execute("DROP TABLE clientes_empresa")
            conn.execute("""
                CREATE TABLE clientes_empresa (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empresa_id INTEGER NOT NULL,
                    telegram_user_id INTEGER NOT NULL UNIQUE,
                    vinculado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (empresa_id) REFERENCES empresas(id)
                )
            """)
            conn.execute(
                "INSERT INTO clientes_empresa (empresa_id, telegram_user_id) VALUES (?, ?)",
                (empresa_id, 777),
            )
            conn.commit()

        await database.init_db()
        await asyncio.sleep(0.05)

        empresa_cliente = await database.obter_empresa_do_cliente(777)
        total_clientes = await database.contar_clientes_empresa(empresa_id)

        self.assertIsNotNone(empresa_cliente)
        self.assertEqual(empresa_cliente["id"], empresa_id)
        self.assertEqual(total_clientes, 1)

        with sqlite3.connect(database.DB_PATH) as conn:
            colunas = {
                row[1]
                for row in conn.execute("PRAGMA table_info(clientes_empresa)").fetchall()
            }

        self.assertIn("cliente_telegram_user_id", colunas)
        self.assertIn("criado_em", colunas)
        self.assertNotIn("telegram_user_id", colunas)
        self.assertNotIn("vinculado_em", colunas)

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
        await database.criar_faq(empresa_id, "Qual o horário?", "Seg a Sex")
        await database.vincular_cliente_empresa(empresa_id, 777)

        excluido = await database.excluir_documento(empresa_id, documento_id)
        documento = await database.obter_documento_por_id(empresa_id, documento_id)

        self.assertTrue(excluido)
        self.assertIsNone(documento)

        await database.registrar_documento(empresa_id, "novo.txt")
        await database.excluir_empresa_com_dados(empresa_id)

        empresa = await database.obter_empresa_por_usuario(12345)
        empresa_cliente = await database.obter_empresa_do_cliente(777)
        documentos = await database.listar_documentos(empresa_id)

        self.assertIsNone(empresa)
        self.assertIsNone(empresa_cliente)
        self.assertEqual(documentos, [])

    async def test_cria_lista_e_limpa_faqs(self):
        empresa_id = await database.criar_empresa("Acme", 12345)

        faq_id = await database.criar_faq(empresa_id, "Qual o horário?", "Seg a Sex")
        await database.criar_faq(empresa_id, "Tem WhatsApp?", "Sim")
        faqs = await database.listar_faqs(empresa_id)

        self.assertEqual(len(faqs), 2)
        self.assertEqual(faqs[0]["id"], faq_id)
        self.assertEqual(faqs[0]["pergunta"], "Qual o horário?")

        removida = await database.excluir_faq(empresa_id, faq_id)
        restantes = await database.listar_faqs(empresa_id)

        self.assertTrue(removida)
        self.assertEqual(len(restantes), 1)

        removidas = await database.limpar_faqs(empresa_id)

        self.assertEqual(removidas, 1)
        self.assertEqual(await database.listar_faqs(empresa_id), [])

    async def test_persiste_e_lista_metricas_recentes(self):
        empresa_id = await database.criar_empresa("Acme", 12345)

        await database.registrar_metrica_atendimento_db(
            empresa_id=empresa_id,
            decisao="faq",
            total_segundos=0.42,
            usou_rag=False,
            sucesso=True,
        )
        await database.registrar_metrica_rag_db(
            empresa_id=empresa_id,
            total_segundos=1.75,
            cache_hit=True,
            sucesso=True,
        )

        metricas = await database.listar_metricas_empresa(empresa_id)

        self.assertEqual(len(metricas), 2)
        self.assertEqual(metricas[0]["tipo"], "rag")
        self.assertEqual(metricas[1]["tipo"], "atendimento")
        self.assertEqual(metricas[1]["decisao"], "faq")
