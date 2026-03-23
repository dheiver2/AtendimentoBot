import unittest

import rag_chain


class RagChainTests(unittest.TestCase):
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
