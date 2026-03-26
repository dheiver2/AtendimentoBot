"""Testes para agent_service.py — integração entre decisão, histórico e RAG."""
import unittest
from unittest.mock import AsyncMock

from agent_service import processar_pergunta
from tests.helpers import make_empresa


class ProcessarPerguntaTests(unittest.IsolatedAsyncioTestCase):
    async def test_continuacao_curta_usa_historico_e_chama_rag(self):
        rag_responder = AsyncMock(return_value="Detalhes do plano Premium.")
        registrar_conversa = AsyncMock(return_value=41)
        conversation_loader = AsyncMock(
            return_value=[
                {
                    "mensagem_usuario": "Quais planos vocês têm?",
                    "resposta_bot": "Temos Básico e Premium. Quer que eu detalhe o Premium?",
                }
            ]
        )

        resultado = await processar_pergunta(
            empresa=make_empresa(),
            pergunta_bruta="sim",
            usuario_id=123,
            usuario_admin=False,
            faq_loader=AsyncMock(return_value=[]),
            conversation_loader=conversation_loader,
            registrar_conversa_fn=registrar_conversa,
            document_checker=lambda _empresa_id: True,
            rag_responder=rag_responder,
            skip_rate_limit=True,
            skip_validation=True,
            return_context=True,
        )

        self.assertEqual(resultado.text, "Detalhes do plano Premium.")
        self.assertEqual(resultado.decision, "rag")
        rag_responder.assert_awaited_once()
        self.assertEqual(rag_responder.await_args.args[4], "sim")
        self.assertEqual(rag_responder.await_args.args[5], conversation_loader.return_value)

    async def test_continuacao_curta_sem_documentos_retorna_orientacao_de_base(self):
        rag_responder = AsyncMock(return_value="não deveria chamar")
        registrar_conversa = AsyncMock(return_value=52)

        resultado = await processar_pergunta(
            empresa=make_empresa(telegram_user_id=999),
            pergunta_bruta="sim",
            usuario_id=123,
            usuario_admin=False,
            faq_loader=AsyncMock(return_value=[]),
            conversation_loader=AsyncMock(
                return_value=[
                    {
                        "mensagem_usuario": "Quais planos vocês têm?",
                        "resposta_bot": "Temos Básico e Premium. Quer que eu detalhe o Premium?",
                    }
                ]
            ),
            registrar_conversa_fn=registrar_conversa,
            document_checker=lambda _empresa_id: False,
            rag_responder=rag_responder,
            skip_rate_limit=True,
            skip_validation=True,
            return_context=True,
        )

        self.assertIn("sendo preparado", resultado.text)
        self.assertEqual(resultado.decision, "no_documents")
        rag_responder.assert_not_awaited()
