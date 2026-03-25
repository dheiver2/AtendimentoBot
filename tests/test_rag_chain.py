import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import rag_chain


class RagChainTests(unittest.TestCase):
    def setUp(self):
        rag_chain._response_cache.clear()

    def test_classifica_pergunta_curta(self):
        instrucoes, quantidade_chunks, max_tokens = rag_chain._classificar_dosagem_resposta(
            "Qual o horário?"
        )

        self.assertIn("curta e direta", instrucoes)
        self.assertEqual(quantidade_chunks, 1)
        self.assertEqual(max_tokens, 180)

    def test_classifica_pergunta_media(self):
        instrucoes, quantidade_chunks, max_tokens = rag_chain._classificar_dosagem_resposta(
            "Quais documentos preciso enviar para começar o atendimento?"
        )

        self.assertIn("tamanho médio", instrucoes)
        self.assertEqual(quantidade_chunks, 2)
        self.assertEqual(max_tokens, 260)

    def test_classifica_pergunta_detalhada(self):
        instrucoes, quantidade_chunks, max_tokens = rag_chain._classificar_dosagem_resposta(
            "Explique como funciona o processo de troca e quais condições precisam ser atendidas."
        )

        self.assertIn("explicação objetiva", instrucoes)
        self.assertEqual(quantidade_chunks, 3)
        self.assertEqual(max_tokens, 420)

    def test_extrai_texto_de_resposta_estruturada(self):
        resposta = SimpleNamespace(content=[{"text": "Linha 1"}, "Linha 2"])

        self.assertEqual(rag_chain._extrair_texto_resposta(resposta), "Linha 1\nLinha 2")


class _FakePrompt:
    def __init__(self, chain):
        self.chain = chain

    def __or__(self, _llm):
        return self.chain


class _FakeChain:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def ainvoke(self, payload):
        self.calls.append(payload)
        if self.error is not None:
            raise self.error
        return self.response


class GerarRespostaTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        rag_chain._response_cache.clear()

    async def test_sem_chunks_retorna_mensagem_padrao(self):
        with patch("rag_chain.buscar_contexto", return_value=[]):
            resposta = await rag_chain.gerar_resposta(
                empresa_id=1,
                nome_empresa="Acme",
                nome_bot="Ana",
                instrucoes="Seja objetiva",
                pergunta="Qual o prazo?",
            )

        self.assertIn("ainda não tenho documentos", resposta)

    async def test_normaliza_resposta_estruturada_e_reaproveita_cache(self):
        chain = _FakeChain(response=SimpleNamespace(content=[{"text": "Primeira linha"}, "Segunda linha"]))

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            with patch("rag_chain.buscar_contexto", return_value=["Trecho relevante"]):
                with patch("rag_chain.ChatPromptTemplate.from_template", return_value=_FakePrompt(chain)):
                    with patch("rag_chain.ChatOpenAI", return_value=MagicMock()):
                        with patch("rag_chain.registrar_metrica_rag") as mock_metricas:
                            resposta_1 = await rag_chain.gerar_resposta(
                                empresa_id=7,
                                nome_empresa="Acme",
                                nome_bot="Ana",
                                instrucoes="Seja objetiva",
                                pergunta="Explique a política de troca",
                            )
                            resposta_2 = await rag_chain.gerar_resposta(
                                empresa_id=7,
                                nome_empresa="Acme",
                                nome_bot="Ana",
                                instrucoes="Seja objetiva",
                                pergunta="Explique a política de troca",
                            )

        self.assertEqual(resposta_1, "Primeira linha\nSegunda linha")
        self.assertEqual(resposta_2, resposta_1)
        self.assertEqual(len(chain.calls), 1)
        self.assertEqual(mock_metricas.call_count, 2)
        self.assertTrue(mock_metricas.call_args.kwargs["cache_hit"])

    async def test_erro_do_modelo_registra_falha(self):
        chain = _FakeChain(error=RuntimeError("boom"))

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            with patch("rag_chain.buscar_contexto", return_value=["Trecho relevante"]):
                with patch("rag_chain.ChatPromptTemplate.from_template", return_value=_FakePrompt(chain)):
                    with patch("rag_chain.ChatOpenAI", return_value=MagicMock()):
                        with patch("rag_chain.registrar_metrica_rag") as mock_metricas:
                            with self.assertRaises(RuntimeError):
                                await rag_chain.gerar_resposta(
                                    empresa_id=9,
                                    nome_empresa="Acme",
                                    nome_bot="Ana",
                                    instrucoes="Seja objetiva",
                                    pergunta="Explique a política de troca",
                                )

        self.assertFalse(mock_metricas.call_args.kwargs["sucesso"])
