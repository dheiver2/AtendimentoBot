"""Testes para o suporte ao WhatsApp Cloud API."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.helpers import make_empresa


class IterIncomingMessagesTests(unittest.TestCase):
    def test_extracts_phone_number_id_and_message(self):
        from whatsapp_cloud_api import _iter_incoming_messages

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "phone_number_id": "1028026920393619",
                                },
                                "messages": [
                                    {
                                        "from": "5511999999999",
                                        "id": "wamid.123",
                                        "type": "text",
                                        "text": {"body": "Oi"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ],
        }

        messages = _iter_incoming_messages(payload)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0][0], "1028026920393619")
        self.assertEqual(messages[0][1]["id"], "wamid.123")


class WhatsAppCloudSettingsTests(unittest.TestCase):
    @patch.dict("os.environ", {"WHATSAPP_CLOUD_API_ENABLED": "1"}, clear=True)
    def test_enabled_without_required_env_raises_error(self):
        from whatsapp_cloud_api import WhatsAppCloudSettings

        with self.assertRaises(ValueError) as ctx:
            WhatsAppCloudSettings.from_env()

        self.assertIn("WHATSAPP_CLOUD_API_ACCESS_TOKEN", str(ctx.exception))
        self.assertIn("WHATSAPP_PHONE_NUMBER_ID", str(ctx.exception))
        self.assertIn("WHATSAPP_VERIFY_TOKEN", str(ctx.exception))


class WhatsAppCloudClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_text_mounts_graph_api_request(self):
        from whatsapp_cloud_api import WhatsAppCloudClient, WhatsAppCloudSettings

        settings = WhatsAppCloudSettings(
            enabled=True,
            access_token="secret-token",
            phone_number_id="1028026920393619",
            verify_token="verify-me",
        )
        client = WhatsAppCloudClient(settings)
        response = MagicMock()
        response.is_error = False
        response.status_code = 200
        response.text = "{}"

        client_cm = AsyncMock()
        http_client = AsyncMock()
        client_cm.__aenter__.return_value = http_client
        http_client.post.return_value = response

        with patch("whatsapp_cloud_api.httpx.AsyncClient", return_value=client_cm):
            await client.send_text(
                to="5511999999999",
                body="Mensagem teste",
                reply_to_message_id="wamid.123",
            )

        http_client.post.assert_awaited_once()
        args, kwargs = http_client.post.call_args
        self.assertEqual(
            args[0],
            "https://graph.facebook.com/v23.0/1028026920393619/messages",
        )
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret-token")
        self.assertEqual(kwargs["json"]["to"], "5511999999999")
        self.assertEqual(kwargs["json"]["text"]["body"], "Mensagem teste")
        self.assertEqual(kwargs["json"]["context"]["message_id"], "wamid.123")


class WhatsAppWebhookServerTests(unittest.IsolatedAsyncioTestCase):
    def _settings(self, **kwargs):
        from whatsapp_cloud_api import WhatsAppCloudSettings

        base_kwargs = {
            "enabled": True,
            "access_token": "secret-token",
            "phone_number_id": "1028026920393619",
            "verify_token": "verify-me",
            "webhook_port": 0,
        }
        base_kwargs.update(kwargs)
        return WhatsAppCloudSettings(**base_kwargs)

    async def test_process_payload_uses_unique_company_and_replies(self):
        from whatsapp_cloud_api import WhatsAppWebhookServer

        server = WhatsAppWebhookServer(self._settings())
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "phone_number_id": "1028026920393619",
                                },
                                "messages": [
                                    {
                                        "from": "5511999999999",
                                        "id": "wamid.123",
                                        "type": "text",
                                        "text": {"body": "Qual o horario?"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ],
        }

        try:
            with patch(
                "whatsapp_cloud_api.listar_empresas",
                new_callable=AsyncMock,
                return_value=[make_empresa()],
            ):
                with patch(
                    "whatsapp_cloud_api.processar_pergunta",
                    new_callable=AsyncMock,
                    return_value="Atendemos das 9h as 18h.",
                ) as mock_process:
                    server._client.send_text = AsyncMock()
                    await server._process_payload(payload)
        finally:
            server.shutdown()

        mock_process.assert_awaited_once()
        server._client.send_text.assert_awaited_once_with(
            to="5511999999999",
            body="Atendemos das 9h as 18h.",
            reply_to_message_id="wamid.123",
        )

    async def test_resolve_company_by_default_company_id(self):
        from whatsapp_cloud_api import WhatsAppWebhookServer

        server = WhatsAppWebhookServer(self._settings(default_company_id=7))
        try:
            with patch(
                "whatsapp_cloud_api.obter_empresa_por_id",
                new_callable=AsyncMock,
                return_value=make_empresa(empresa_id=7),
            ) as mock_get:
                company = await server._resolve_company()
        finally:
            server.shutdown()

        mock_get.assert_awaited_once_with(7)
        self.assertIsNotNone(company)
        self.assertEqual(company["id"], 7)
