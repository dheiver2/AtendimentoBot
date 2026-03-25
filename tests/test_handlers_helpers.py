import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import handlers.common as handlers_common
from agent_service import (
    _buscar_resposta_faq,
    _formatar_resposta_pausado,
    _formatar_resposta_sem_base,
    _instrucoes_operacionais_empresa,
    _normalizar_texto,
)
from handlers.common import (
    _limpar_estado_usuario,
    _montar_link_atendimento,
    _remover_arquivos_empresa,
    _teclado_painel,
)
from handlers.documents import _reindexar_base_empresa, _teclado_documentos
from handlers.faq import _teclado_faqs
from response_intelligence import detectar_pedido_humano, detectar_pergunta_horario


class HandlersHelperTests(unittest.IsolatedAsyncioTestCase):
    def test_limpar_estado_usuario_remove_chaves_temporarias(self):
        context = SimpleNamespace(
            user_data={
                "nome_empresa": "Acme",
                "nome_bot": "Ana",
                "saudacao": "Oi",
                "instrucoes": "Seja objetiva",
                "empresa_upload_id": 1,
                "empresa_editar_id": 2,
                "aguardando_imagem_bot": True,
                "campo_editando": "nome",
                "campo_editando_nome": "Nome",
                "persistir": "sim",
            }
        )

        _limpar_estado_usuario(context)

        self.assertEqual(context.user_data, {"persistir": "sim"})

    def test_teclado_painel_expoe_doze_acoes(self):
        teclado = _teclado_painel({"ativo": 1})
        textos = [botao.text for linha in teclado.inline_keyboard for botao in linha]

        self.assertEqual(len(textos), 12)
        self.assertIn("📄 Upload", textos)
        self.assertIn("❔ FAQ", textos)
        self.assertIn("🕒 Horário", textos)
        self.assertIn("🆘 Fallback", textos)
        self.assertIn("⏸️ Pausar", textos)
        self.assertIn("♻️ Reset", textos)

    def test_teclado_painel_muda_botao_quando_agente_esta_pausado(self):
        teclado = _teclado_painel({"ativo": 0})
        textos = [botao.text for linha in teclado.inline_keyboard for botao in linha]

        self.assertIn("▶️ Ativar", textos)

    def test_monta_link_atendimento(self):
        link = _montar_link_atendimento("@meu_bot_teste", "abc123")

        self.assertEqual(link, "https://t.me/meu_bot_teste?start=abc123")

    def test_monta_link_atendimento_sem_username_gera_erro(self):
        with self.assertRaises(ValueError):
            _montar_link_atendimento("", "abc123")

    def test_resposta_sem_base_muda_para_cliente(self):
        empresa = {
            "horario_atendimento": "Seg a Sex",
            "fallback_contato": "WhatsApp",
        }

        resposta_admin = _formatar_resposta_sem_base(empresa, usuario_admin=True)
        resposta_cliente = _formatar_resposta_sem_base(empresa, usuario_admin=False)

        self.assertIn("/upload", resposta_admin)
        self.assertNotIn("/upload", resposta_cliente)
        self.assertIn("sendo preparado", resposta_cliente)

    def test_teclado_faqs_renderiza_acoes_por_item(self):
        teclado = _teclado_faqs(
            [
                {"id": 10, "pergunta": "Qual é o horário de atendimento?"},
                {"id": 20, "pergunta": "Vocês atendem via WhatsApp?"},
            ]
        )
        textos = [botao.text for linha in teclado.inline_keyboard for botao in linha]
        callbacks = [botao.callback_data for linha in teclado.inline_keyboard for botao in linha]

        self.assertIn("➕ Nova FAQ", textos)
        self.assertIn("🧹 Limpar FAQs", textos)
        self.assertIn("faq_excluir:10", callbacks)
        self.assertIn("faq_excluir:20", callbacks)

    def test_busca_resposta_faq_aceita_variacao_simples(self):
        resposta = _buscar_resposta_faq(
            "qual o horario de atendimento",
            [
                {"pergunta": "Qual é o horário de atendimento?", "resposta": "Seg a Sex"},
                {"pergunta": "Tem WhatsApp?", "resposta": "Sim"},
            ],
        )

        self.assertEqual(resposta, "Seg a Sex")

    def test_busca_resposta_faq_retorna_none_sem_match(self):
        resposta = _buscar_resposta_faq(
            "qual o preço do produto X",
            [
                {"pergunta": "Qual é o horário de atendimento?", "resposta": "Seg a Sex"},
            ],
        )

        self.assertIsNone(resposta)

    def test_teclado_documentos_renderiza_acoes_por_arquivo(self):
        teclado = _teclado_documentos(
            [
                {"id": 10, "nome_arquivo": "manual_extremamente_longo.pdf"},
                {"id": 20, "nome_arquivo": "faq.txt"},
            ]
        )
        textos = [botao.text for linha in teclado.inline_keyboard for botao in linha]
        callbacks = [botao.callback_data for linha in teclado.inline_keyboard for botao in linha]

        self.assertIn("🔁 Reindexar Base", textos)
        self.assertIn("docs_reprocessar:10", callbacks)
        self.assertIn("docs_excluir:20", callbacks)

    def test_remove_arquivos_empresa_limpa_pastas(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_pdfs_dir = handlers_common.PDFS_DIR
            original_vector_stores_dir = handlers_common.VECTOR_STORES_DIR
            original_images_dir = handlers_common.IMAGES_DIR
            handlers_common.PDFS_DIR = os.path.join(temp_dir, "pdfs")
            handlers_common.VECTOR_STORES_DIR = os.path.join(temp_dir, "vector_stores")
            handlers_common.IMAGES_DIR = os.path.join(temp_dir, "images")

            os.makedirs(os.path.join(handlers_common.PDFS_DIR, "7"), exist_ok=True)
            os.makedirs(os.path.join(handlers_common.VECTOR_STORES_DIR, "7"), exist_ok=True)
            os.makedirs(os.path.join(handlers_common.IMAGES_DIR, "7"), exist_ok=True)

            try:
                _remover_arquivos_empresa(7)
                self.assertFalse(os.path.exists(os.path.join(handlers_common.PDFS_DIR, "7")))
                self.assertFalse(os.path.exists(os.path.join(handlers_common.VECTOR_STORES_DIR, "7")))
                self.assertFalse(os.path.exists(os.path.join(handlers_common.IMAGES_DIR, "7")))
            finally:
                handlers_common.PDFS_DIR = original_pdfs_dir
                handlers_common.VECTOR_STORES_DIR = original_vector_stores_dir
                handlers_common.IMAGES_DIR = original_images_dir

    def test_detectar_pedido_humano(self):
        self.assertTrue(detectar_pedido_humano("Quero falar com atendente"))
        self.assertTrue(detectar_pedido_humano("Tem WhatsApp?"))
        self.assertFalse(detectar_pedido_humano("Qual o preço do produto?"))

    def test_detectar_pergunta_horario(self):
        self.assertTrue(detectar_pergunta_horario("Qual o horário de atendimento?"))
        self.assertTrue(detectar_pergunta_horario("Vocês estão aberto agora?"))
        self.assertFalse(detectar_pergunta_horario("Qual o preço?"))

    def test_formatar_resposta_pausado(self):
        empresa = {
            "horario_atendimento": "Seg a Sex",
            "fallback_contato": "suporte@test.com",
        }
        resposta = _formatar_resposta_pausado(empresa)
        self.assertIn("pausado", resposta)
        self.assertIn("Seg a Sex", resposta)
        self.assertIn("suporte@test.com", resposta)

    def test_instrucoes_operacionais_empresa_sem_extras(self):
        empresa = {"instrucoes": "Seja educado", "horario_atendimento": "", "fallback_contato": ""}
        resultado = _instrucoes_operacionais_empresa(empresa)
        self.assertEqual(resultado, "Seja educado")

    def test_instrucoes_operacionais_empresa_com_extras(self):
        empresa = {
            "instrucoes": "Seja educado",
            "horario_atendimento": "Seg a Sex",
            "fallback_contato": "suporte@test.com",
        }
        resultado = _instrucoes_operacionais_empresa(empresa)
        self.assertIn("INFORMAÇÕES OPERACIONAIS", resultado)
        self.assertIn("Seg a Sex", resultado)
        self.assertIn("suporte@test.com", resultado)

    def test_normalizar_texto(self):
        self.assertEqual(_normalizar_texto("  Ação  com   espaços  "), "acao com espacos")
        self.assertEqual(_normalizar_texto("Café"), "cafe")

    async def test_reindexar_base_empresa_reconstroi_documentos_validos(self):
        import handlers.documents as handlers_documents

        with tempfile.TemporaryDirectory() as temp_dir:
            original_pdfs_dir = handlers_documents.PDFS_DIR
            handlers_documents.PDFS_DIR = temp_dir
            empresa_dir = os.path.join(temp_dir, "9")
            os.makedirs(empresa_dir, exist_ok=True)

            caminho_ok = os.path.join(empresa_dir, "ok.txt")
            caminho_erro = os.path.join(empresa_dir, "erro.txt")
            with open(caminho_ok, "w", encoding="utf-8") as arquivo:
                arquivo.write("conteudo valido")
            with open(caminho_erro, "w", encoding="utf-8") as arquivo:
                arquivo.write("conteudo invalido")

            try:
                with (
                    patch(
                        "handlers.documents.listar_documentos",
                        return_value=[
                            {"id": 1, "nome_arquivo": "ok.txt"},
                            {"id": 2, "nome_arquivo": "faltando.txt"},
                            {"id": 3, "nome_arquivo": "erro.txt"},
                        ],
                    ),
                    patch(
                        "handlers.documents.processar_documento_salvo",
                        side_effect=lambda caminho: ["chunk"] if caminho == caminho_ok else (_ for _ in ()).throw(ValueError("falhou")),
                    ),
                    patch("handlers.documents.substituir_documentos") as mock_substituir,
                ):
                    quantidade, avisos = await _reindexar_base_empresa(9)

                self.assertEqual(quantidade, 1)
                self.assertEqual(len(avisos), 2)
                self.assertTrue(any("arquivo não encontrado" in aviso for aviso in avisos))
                self.assertTrue(any("falhou" in aviso for aviso in avisos))
                mock_substituir.assert_called_once_with(
                    9,
                    [(["chunk"], {"arquivo": "ok.txt", "documento_id": 1})],
                )
            finally:
                handlers_documents.PDFS_DIR = original_pdfs_dir
