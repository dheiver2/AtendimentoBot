"""Testes do fluxo conversacional do WhatsApp."""
import unittest
from unittest.mock import AsyncMock, patch

from tests.helpers import make_empresa


class WhatsAppFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from whatsapp_flow import _sessions

        _sessions.clear()

    async def test_start_novo_usuario_inicia_onboarding(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                actions = await processar_mensagem_whatsapp(
                    sender="5511999999999@c.us",
                    text="/start",
                    message_type="chat",
                    resolve_default_company=AsyncMock(return_value=None),
                )

        self.assertEqual(len(actions), 1)
        self.assertIn("nome da sua empresa", actions[0]["text"].lower())

    async def test_onboarding_completo_cria_empresa(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                with patch("whatsapp_flow.criar_empresa", new_callable=AsyncMock, return_value=7) as mock_create:
                    with patch("whatsapp_flow.atualizar_empresa", new_callable=AsyncMock) as mock_update:
                        await processar_mensagem_whatsapp(
                            sender="5511999999999@c.us",
                            text="/start",
                            message_type="chat",
                            resolve_default_company=AsyncMock(return_value=None),
                        )
                        await processar_mensagem_whatsapp(
                            sender="5511999999999@c.us",
                            text="Acme",
                            message_type="chat",
                            resolve_default_company=AsyncMock(return_value=None),
                        )
                        await processar_mensagem_whatsapp(
                            sender="5511999999999@c.us",
                            text="Ana",
                            message_type="chat",
                            resolve_default_company=AsyncMock(return_value=None),
                        )
                        await processar_mensagem_whatsapp(
                            sender="5511999999999@c.us",
                            text="Ola! Como posso ajudar?",
                            message_type="chat",
                            resolve_default_company=AsyncMock(return_value=None),
                        )
                        await processar_mensagem_whatsapp(
                            sender="5511999999999@c.us",
                            text="/pular",
                            message_type="chat",
                            resolve_default_company=AsyncMock(return_value=None),
                        )
                        actions = await processar_mensagem_whatsapp(
                            sender="5511999999999@c.us",
                            text="/confirmar",
                            message_type="chat",
                            resolve_default_company=AsyncMock(return_value=None),
                        )

        mock_create.assert_awaited_once_with("Acme", -5511999999999)
        mock_update.assert_awaited_once_with(
            7,
            nome_bot="Ana",
            saudacao="Ola! Como posso ajudar?",
            instrucoes=(
                "Você é um assistente de atendimento ao cliente. "
                "Responda de forma educada e profissional."
            ),
        )
        self.assertIn("empresa cadastrada com sucesso", actions[0]["text"].lower())

    async def test_start_com_token_vincula_cliente(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                with patch(
                    "whatsapp_flow.obter_empresa_por_link_token",
                    new_callable=AsyncMock,
                    return_value=make_empresa(link_token="abc123"),
                ):
                    with patch("whatsapp_flow.vincular_cliente_empresa", new_callable=AsyncMock) as mock_bind:
                        with patch(
                            "whatsapp_flow._make_welcome_actions",
                            return_value=[{"type": "text", "text": "bem-vindo"}],
                        ) as mock_welcome:
                            actions = await processar_mensagem_whatsapp(
                                sender="5511999999999@c.us",
                                text="/start abc123",
                                message_type="chat",
                                resolve_default_company=AsyncMock(return_value=None),
                            )

        mock_bind.assert_awaited_once_with(1, -5511999999999)
        mock_welcome.assert_called_once()
        self.assertEqual(actions, [{"type": "text", "text": "bem-vindo"}])

    async def test_documento_direto_admin_processa_upload(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresa = make_empresa()
        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=empresa):
            with patch("whatsapp_flow.listar_documentos", new_callable=AsyncMock, return_value=[]):
                with patch("whatsapp_flow.processar_documento", return_value=["c1", "c2"]) as mock_process:
                    with patch("whatsapp_flow.registrar_documento", new_callable=AsyncMock) as mock_register:
                        with patch("whatsapp_flow.adicionar_documentos") as mock_add:
                            actions = await processar_mensagem_whatsapp(
                                sender="5511999999999@c.us",
                                text="",
                                message_type="document",
                                file_name="manual.pdf",
                                mime_type="application/pdf",
                                media_bytes=b"pdf-data",
                                resolve_default_company=AsyncMock(return_value=None),
                            )

        mock_process.assert_called_once_with(1, "manual.pdf", b"pdf-data")
        mock_register.assert_awaited_once_with(1, "manual.pdf")
        mock_add.assert_called_once_with(1, ["c1", "c2"], {"arquivo": "manual.pdf"})
        self.assertIn("processado com sucesso", actions[0]["text"].lower())

    async def test_link_admin_retorna_instrucao_com_share_link(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresa = make_empresa(link_token="abc123")
        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=empresa):
            actions = await processar_mensagem_whatsapp(
                sender="5511999999999@c.us",
                text="/link",
                message_type="chat",
                resolve_default_company=AsyncMock(return_value=None),
                share_link_builder=lambda token: f"https://wa.me/5511999999999?text=%2Fstart%20{token}",
            )

        self.assertIn("/start abc123", actions[0]["text"])
        self.assertIn("https://wa.me/5511999999999", actions[0]["text"])
