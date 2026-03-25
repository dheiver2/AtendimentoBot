"""Testes para o bridge local do WhatsApp Web."""
import unittest
from unittest.mock import AsyncMock, patch

from tests.helpers import make_empresa


class WhatsAppWebSettingsTests(unittest.TestCase):
    @patch.dict("os.environ", {"WHATSAPP_WEB_ENABLED": "1"}, clear=True)
    def test_enabled_uses_defaults(self):
        from whatsapp_web_bridge import WhatsAppWebSettings

        settings = WhatsAppWebSettings.from_env()

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.bridge_port, 8010)
        self.assertEqual(settings.bridge_path, "/bridge/whatsapp/message")
        self.assertTrue(settings.auto_launch)


class WhatsAppWebBridgeServerTests(unittest.IsolatedAsyncioTestCase):
    def _settings(self, **kwargs):
        from whatsapp_web_bridge import WhatsAppWebSettings

        base_kwargs = {
            "enabled": True,
            "bridge_port": 0,
            "auto_launch": False,
        }
        base_kwargs.update(kwargs)
        return WhatsAppWebSettings(**base_kwargs)

    async def test_build_reply_uses_unique_company(self):
        from whatsapp_web_bridge import WhatsAppWebBridgeServer

        server = WhatsAppWebBridgeServer(self._settings())
        try:
            with patch(
                "whatsapp_web_bridge.processar_mensagem_whatsapp",
                new_callable=AsyncMock,
                return_value=[{"type": "text", "text": "Atendemos das 9h as 18h."}],
            ) as mock_process:
                reply = await server._build_actions(
                    {
                        "sender": "5511999999999@c.us",
                        "message_id": "abc123",
                        "text": "Qual o horario?",
                        "message_type": "chat",
                    }
                )
        finally:
            server.shutdown()

        self.assertEqual(reply, [{"type": "text", "text": "Atendemos das 9h as 18h."}])
        mock_process.assert_awaited_once()

    async def test_duplicate_message_id_returns_empty_reply(self):
        from whatsapp_web_bridge import WhatsAppWebBridgeServer

        server = WhatsAppWebBridgeServer(self._settings())
        try:
            with patch(
                "whatsapp_web_bridge.processar_mensagem_whatsapp",
                new_callable=AsyncMock,
                return_value=[{"type": "text", "text": "Resposta"}],
            ) as mock_process:
                primeira = await server._build_actions(
                    {
                        "sender": "5511999999999@c.us",
                        "message_id": "abc123",
                        "text": "Oi",
                        "message_type": "chat",
                    }
                )
                segunda = await server._build_actions(
                    {
                        "sender": "5511999999999@c.us",
                        "message_id": "abc123",
                        "text": "Oi",
                        "message_type": "chat",
                    }
                )
        finally:
            server.shutdown()

        self.assertEqual(primeira, [{"type": "text", "text": "Resposta"}])
        self.assertEqual(segunda, [])
        mock_process.assert_awaited_once()

    async def test_resolve_company_by_default_company_id(self):
        from whatsapp_web_bridge import WhatsAppWebBridgeServer

        server = WhatsAppWebBridgeServer(self._settings(default_company_id=7))
        try:
            with patch(
                "whatsapp_web_bridge.obter_empresa_por_id",
                new_callable=AsyncMock,
                return_value=make_empresa(empresa_id=7),
            ) as mock_get:
                company = await server._resolve_company()
        finally:
            server.shutdown()

        mock_get.assert_awaited_once_with(7)
        self.assertIsNotNone(company)
        self.assertEqual(company["id"], 7)


class LauncherTests(unittest.TestCase):
    def test_does_not_launch_when_auto_launch_disabled(self):
        from whatsapp_web_bridge import WhatsAppWebSettings, launch_whatsapp_client_in_new_terminal

        settings = WhatsAppWebSettings(enabled=True, auto_launch=False)

        with patch("whatsapp_web_bridge.subprocess.Popen") as mock_popen:
            launched = launch_whatsapp_client_in_new_terminal(settings)

        self.assertFalse(launched)
        mock_popen.assert_not_called()

    @patch.dict("os.environ", {}, clear=True)
    def test_headless_linux_skips_graphical_auto_launch(self):
        import whatsapp_web_bridge
        from whatsapp_web_bridge import WhatsAppWebSettings, launch_whatsapp_client_in_new_terminal

        settings = WhatsAppWebSettings(enabled=True)

        with patch.object(whatsapp_web_bridge.sys, "platform", "linux"):
            with patch.object(whatsapp_web_bridge.os, "name", "posix"):
                with patch("whatsapp_web_bridge.is_whatsapp_client_running", return_value=False):
                    with patch("whatsapp_web_bridge.subprocess.Popen") as mock_popen:
                        with patch("whatsapp_web_bridge.logger.warning") as mock_warning:
                            launched = launch_whatsapp_client_in_new_terminal(settings)

        self.assertFalse(launched)
        mock_popen.assert_not_called()
        mock_warning.assert_called_once()
        self.assertIn("WHATSAPP_WEB_AUTO_LAUNCH=0", mock_warning.call_args[0][0])
