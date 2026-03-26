"""Testes para handlers/agent.py — interação com o agente RAG."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.helpers import make_context, make_empresa, make_update


class InteragirComAgenteTests(unittest.IsolatedAsyncioTestCase):
    """Testes para o handler principal interagir_com_agente."""

    def _empresa(self, **kw):
        return make_empresa(**kw)

    @patch("handlers.agent.verificar_rate_limit", return_value="⏳ muito rápido")
    async def test_rate_limit_bloqueia(self, mock_rate):
        from handlers.agent import interagir_com_agente

        update = make_update("Olá")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        update.message.reply_text.assert_called_once_with("⏳ muito rápido")

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", side_effect=__import__("validators").InputValidationError("Campo vazio"))
    async def test_validacao_mensagem_falha(self, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        update = make_update("")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        update.message.reply_text.assert_called_once()
        self.assertIn("Campo vazio", update.message.reply_text.call_args[0][0])

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="Qual o preço?")
    @patch("handlers.agent.listar_empresas", new_callable=AsyncMock, return_value=[])
    @patch("handlers.agent.obter_empresa_do_usuario", return_value=None)
    async def test_usuario_sem_empresa(self, mock_emp, mock_empresas, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        update = make_update("Qual o preço?")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        texto = update.message.reply_text.call_args[0][0]
        self.assertIn("não está configurado", texto)
        self.assertIn("/start", texto)
        self.assertIn("/empresas", texto)

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="Qual o preço?")
    @patch("handlers.agent.listar_empresas", new_callable=AsyncMock, return_value=[])
    @patch("handlers.agent.obter_empresa_do_usuario", return_value=None)
    async def test_usuario_sem_empresa_com_allowlist_exige_link_admin(self, mock_emp, mock_empresas, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        update = make_update("Qual o preço?", user_id=100)
        ctx = make_context()
        with patch.dict(os.environ, {"TELEGRAM_ADMIN_IDS": "999"}, clear=False):
            await interagir_com_agente(update, ctx)

        texto = update.message.reply_text.call_args[0][0]
        self.assertIn("link de admin", texto.lower())
        self.assertIn("/empresas", texto.lower())

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="Oi")
    @patch("handlers.agent._mostrar_seletor_empresas", new_callable=AsyncMock)
    @patch("handlers.agent.listar_empresas", new_callable=AsyncMock)
    @patch("handlers.agent.obter_empresa_do_usuario", return_value=None)
    async def test_usuario_sem_empresa_com_empresas_recebe_seletor_automatico(
        self,
        mock_emp,
        mock_empresas,
        mock_seletor,
        mock_val,
        mock_rate,
    ):
        from handlers.agent import interagir_com_agente

        mock_empresas.return_value = [
            self._empresa(empresa_id=1, nome="Acme"),
            self._empresa(empresa_id=2, nome="Beta"),
        ]
        update = make_update("Oi")
        ctx = make_context()

        await interagir_com_agente(update, ctx)

        mock_seletor.assert_awaited_once_with(update, ctx, mock_empresas.return_value)
        update.message.reply_text.assert_not_called()

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="Oi")
    @patch("handlers.agent._mostrar_seletor_empresas", new_callable=AsyncMock)
    @patch("handlers.agent.listar_empresas", new_callable=AsyncMock)
    @patch("handlers.agent.obter_empresa_do_usuario", return_value=None)
    async def test_usuario_allowlist_sem_empresa_com_empresas_recebe_seletor_automatico(
        self,
        mock_emp,
        mock_empresas,
        mock_seletor,
        mock_val,
        mock_rate,
    ):
        from handlers.agent import interagir_com_agente

        mock_empresas.return_value = [
            self._empresa(empresa_id=1, nome="Acme"),
        ]
        update = make_update("Oi", user_id=999)
        ctx = make_context()

        with patch.dict(os.environ, {"TELEGRAM_ADMIN_IDS": "999"}, clear=False):
            await interagir_com_agente(update, ctx)

        mock_seletor.assert_awaited_once_with(update, ctx, mock_empresas.return_value)
        update.message.reply_text.assert_not_called()

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="Oi")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_agente_pausado_retorna_mensagem(self, mock_reg, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa(ativo=0, horario_atendimento="Seg a Sex")
        update = make_update("Oi")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertIn("pausado", resposta)

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="preço do produto?")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.empresa_tem_documentos", return_value=True)
    @patch("handlers.agent.gerar_resposta", new_callable=AsyncMock, return_value="O produto custa R$50")
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_primeira_interacao_cliente_nao_envia_identidade_visual(self, mock_reg, mock_rag, mock_docs, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa(telegram_user_id=999)
        update = make_update("preço do produto?")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        update.message.reply_photo.assert_not_called()

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="preço do produto?")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.empresa_tem_documentos", return_value=True)
    @patch("handlers.agent.gerar_resposta", new_callable=AsyncMock, return_value="O produto custa R$50")
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_admin_nao_reenvia_identidade_visual(self, mock_reg, mock_rag, mock_docs, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa()
        update = make_update("preço do produto?")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        update.message.reply_photo.assert_not_called()

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="quero falar com atendente")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_pedido_humano_retorna_fallback(self, mock_reg, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa(fallback_contato="suporte@test.com")
        update = make_update("quero falar com atendente")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertIn("suporte@test.com", resposta)

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="qual o horario")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_pergunta_horario_retorna_horario(self, mock_reg, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa(horario_atendimento="Seg a Sex 9h-18h")
        update = make_update("qual o horario")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertIn("Seg a Sex 9h-18h", resposta)

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="prazo de entrega?")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs")
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_faq_match_retorna_resposta(self, mock_reg, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa()
        mock_faqs.return_value = [{"pergunta": "Qual é o prazo de entrega?", "resposta": "3 dias úteis"}]
        update = make_update("prazo de entrega?")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertEqual(resposta, "3 dias úteis")

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="oi")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.gerar_resposta", new_callable=AsyncMock)
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_mensagem_trivial_nao_usa_rag(self, mock_reg, mock_rag, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa(saudacao="Olá! Como posso ajudar?")
        update = make_update("oi")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertIn("Como posso ajudar", resposta)
        mock_rag.assert_not_called()

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="como vai")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.gerar_resposta", new_callable=AsyncMock)
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_smalltalk_como_vai_nao_usa_rag(self, mock_reg, mock_rag, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa()
        update = make_update("como vai")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertIn("pronto para ajudar", resposta)
        mock_rag.assert_not_called()

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="queria tirar duvidas")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.empresa_tem_documentos", return_value=True)
    @patch("handlers.agent.gerar_resposta", new_callable=AsyncMock)
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_mensagem_vaga_nao_usa_rag(self, mock_reg, mock_rag, mock_docs, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa(fallback_contato="suporte@x.com")
        update = make_update("queria tirar duvidas")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertIn("Quais dúvidas você tem sobre a empresa", resposta)
        self.assertIn("suporte@x.com", resposta)
        mock_rag.assert_not_called()

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="o que e a clinica")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.empresa_tem_documentos", return_value=True)
    @patch("handlers.agent.gerar_resposta", new_callable=AsyncMock, return_value="A clínica é especializada em odontologia estética.")
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_pergunta_institucional_usa_rag(self, mock_reg, mock_rag, mock_docs, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa()
        update = make_update("o que e a clinica")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertIn("especializada", resposta)
        mock_rag.assert_called_once()

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="qual o preço?")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.empresa_tem_documentos", return_value=False)
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_sem_documentos_cliente_ve_mensagem_preparando(self, mock_reg, mock_docs, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa(telegram_user_id=999)
        update = make_update("qual o preço?")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertIn("sendo preparado", resposta)

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="preço do produto?")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.empresa_tem_documentos", return_value=True)
    @patch("handlers.agent.gerar_resposta", new_callable=AsyncMock, return_value="O produto custa R$50")
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_rag_responde_com_sucesso(self, mock_reg, mock_rag, mock_docs, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa()
        update = make_update("preço do produto?")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertIn("R$50", resposta)

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="preço do produto?")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.criar_feedback_resposta", new_callable=AsyncMock, return_value=55)
    async def test_resposta_com_contexto_guarda_feedback_pendente_sem_botoes(
        self,
        mock_feedback,
        mock_emp,
        mock_val,
        mock_rate,
    ):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa()
        update = make_update("preço do produto?")
        ctx = make_context()

        with patch(
            "handlers.agent.processar_pergunta",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(text="O produto custa R$50", conversation_id=99, decision="rag"),
        ):
            await interagir_com_agente(update, ctx)

        mock_feedback.assert_awaited_once_with(
            99,
            1,
            100,
            canal="telegram",
            resposta_bot="O produto custa R$50",
        )
        self.assertEqual(ctx.user_data["pending_feedback_id"], 55)
        kwargs = update.message.reply_text.call_args.kwargs
        self.assertIsNone(kwargs.get("reply_markup"))

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="obrigado")
    @patch("handlers.agent.obter_empresa_do_usuario")
    async def test_encerramento_expoe_botoes_de_feedback_pendente(
        self,
        mock_emp,
        mock_val,
        mock_rate,
    ):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa()
        update = make_update("obrigado")
        ctx = make_context(user_data={"pending_feedback_id": 55})

        with patch("handlers.agent.processar_pergunta", new_callable=AsyncMock) as mock_process:
            await interagir_com_agente(update, ctx)

        mock_process.assert_not_awaited()
        self.assertNotIn("pending_feedback_id", ctx.user_data)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertIn("Antes de encerrar", resposta)
        kwargs = update.message.reply_text.call_args.kwargs
        self.assertIsNotNone(kwargs.get("reply_markup"))

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="pergunta qualquer")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.empresa_tem_documentos", return_value=True)
    @patch("handlers.agent.gerar_resposta", new_callable=AsyncMock, side_effect=RuntimeError("API error"))
    async def test_rag_erro_envia_mensagem_generica(self, mock_rag, mock_docs, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa()
        update = make_update("pergunta qualquer")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertIn("erro", resposta.lower())

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="pergunta qualquer")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.empresa_tem_documentos", return_value=True)
    @patch("handlers.agent.gerar_resposta", new_callable=AsyncMock)
    async def test_rag_incompatibilidade_do_indice_envia_orientacao(self, mock_rag, mock_docs, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente
        from vector_store import VectorStoreIncompatibilityError

        mock_emp.return_value = self._empresa()
        mock_rag.side_effect = VectorStoreIncompatibilityError(
            "A base vetorial desta empresa foi criada com outro modelo de embeddings. Reindexe a base em /documentos > Reindexar Base para voltar a responder."
        )
        update = make_update("pergunta qualquer")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertIn("Reindexar Base", resposta)

    @patch("handlers.agent.verificar_rate_limit", return_value=None)
    @patch("handlers.agent.validar_mensagem_usuario", return_value="info")
    @patch("handlers.agent.obter_empresa_do_usuario")
    @patch("handlers.agent.listar_faqs", return_value=[])
    @patch("handlers.agent.empresa_tem_documentos", return_value=True)
    @patch("handlers.agent.gerar_resposta", new_callable=AsyncMock, return_value="nao tenho essa informacao no contexto")
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_fallback_adicionado_quando_resposta_indica_falta_info(self, mock_reg, mock_rag, mock_docs, mock_faqs, mock_emp, mock_val, mock_rate):
        from handlers.agent import interagir_com_agente

        mock_emp.return_value = self._empresa(fallback_contato="suporte@x.com")
        update = make_update("info")
        ctx = make_context()
        await interagir_com_agente(update, ctx)
        resposta = update.message.reply_text.call_args[0][0]
        self.assertIn("suporte@x.com", resposta)


class ResponderERegistrarTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.agent.registrar_conversa", new_callable=AsyncMock)
    async def test_responde_e_registra(self, mock_reg):
        from handlers.agent import _responder_e_registrar

        update = make_update("Oi")
        empresa = make_empresa()
        await _responder_e_registrar(update, empresa, "Oi", "Olá!")
        update.message.reply_text.assert_called_once_with("Olá!")
        mock_reg.assert_called_once_with(empresa["id"], update.effective_user.id, "Oi", "Olá!")


class FeedbackRespostaCallbackTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.agent.registrar_feedback_resposta", new_callable=AsyncMock, return_value=True)
    async def test_registra_feedback_e_remove_botoes(self, mock_feedback):
        from handlers.agent import feedback_resposta_callback

        update = make_update(callback_data="feedback:up:42")
        ctx = make_context()
        await feedback_resposta_callback(update, ctx)

        mock_feedback.assert_awaited_once_with(42, 1)
        update.callback_query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
        update.callback_query.answer.assert_awaited_once()
