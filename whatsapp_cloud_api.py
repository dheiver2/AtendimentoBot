"""Webhook HTTP para integrar o projeto com o WhatsApp Cloud API da Meta."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import monotonic
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from agent_service import processar_pergunta
from database import listar_empresas, obter_empresa_por_id, obter_empresa_por_link_token

logger = logging.getLogger(__name__)

_DEFAULT_API_VERSION = "v23.0"
_DEFAULT_WEBHOOK_HOST = "0.0.0.0"
_DEFAULT_WEBHOOK_PATH = "/webhook/whatsapp"
_DEFAULT_WEBHOOK_PORT = 8080
_MESSAGE_CACHE_TTL_SECONDS = 600
_MAX_TEXT_MESSAGE_LENGTH = 4096
_UNSUPPORTED_MESSAGE_TYPES = {
    "audio",
    "contacts",
    "document",
    "image",
    "interactive",
    "location",
    "order",
    "sticker",
    "system",
    "video",
}


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_webhook_path(value: str | None) -> str:
    path = (value or _DEFAULT_WEBHOOK_PATH).strip() or _DEFAULT_WEBHOOK_PATH
    if not path.startswith("/"):
        path = f"/{path}"
    return path.rstrip("/") or "/"


def _truncate_text_message(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= _MAX_TEXT_MESSAGE_LENGTH:
        return text
    return text[: _MAX_TEXT_MESSAGE_LENGTH - 3].rstrip() + "..."


def _coerce_user_id(raw_value: str) -> int:
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return abs(hash(raw_value))


def _iter_incoming_messages(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Extrai mensagens recebidas do payload de webhook da Meta."""
    mensagens: list[tuple[str, dict[str, Any]]] = []
    for entry in payload.get("entry", []):
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", []):
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata")
            phone_number_id = ""
            if isinstance(metadata, dict):
                phone_number_id = str(metadata.get("phone_number_id") or "").strip()
            for message in value.get("messages", []):
                if isinstance(message, dict):
                    mensagens.append((phone_number_id, message))
    return mensagens


@dataclass(frozen=True)
class WhatsAppCloudSettings:
    enabled: bool
    access_token: str = ""
    phone_number_id: str = ""
    business_account_id: str = ""
    api_version: str = _DEFAULT_API_VERSION
    verify_token: str = ""
    webhook_host: str = _DEFAULT_WEBHOOK_HOST
    webhook_port: int = _DEFAULT_WEBHOOK_PORT
    webhook_path: str = _DEFAULT_WEBHOOK_PATH
    default_company_id: int | None = None
    default_company_link_token: str = ""
    app_secret: str = ""

    @classmethod
    def from_env(cls) -> "WhatsAppCloudSettings":
        """Carrega configuracao do WhatsApp a partir do ambiente."""
        enabled = _is_truthy(os.getenv("WHATSAPP_CLOUD_API_ENABLED"))
        company_id_raw = (os.getenv("WHATSAPP_DEFAULT_COMPANY_ID") or "").strip()

        settings = cls(
            enabled=enabled,
            access_token=(os.getenv("WHATSAPP_CLOUD_API_ACCESS_TOKEN") or "").strip(),
            phone_number_id=(os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip(),
            business_account_id=(os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID") or "").strip(),
            api_version=(os.getenv("WHATSAPP_CLOUD_API_VERSION") or _DEFAULT_API_VERSION).strip(),
            verify_token=(os.getenv("WHATSAPP_VERIFY_TOKEN") or "").strip(),
            webhook_host=(os.getenv("WHATSAPP_WEBHOOK_HOST") or _DEFAULT_WEBHOOK_HOST).strip(),
            webhook_port=int(
                (os.getenv("WHATSAPP_WEBHOOK_PORT") or str(_DEFAULT_WEBHOOK_PORT)).strip()
            ),
            webhook_path=_normalize_webhook_path(os.getenv("WHATSAPP_WEBHOOK_PATH")),
            default_company_id=int(company_id_raw) if company_id_raw else None,
            default_company_link_token=(
                os.getenv("WHATSAPP_DEFAULT_COMPANY_LINK_TOKEN") or ""
            ).strip(),
            app_secret=(os.getenv("WHATSAPP_APP_SECRET") or "").strip(),
        )

        if not settings.enabled:
            return settings

        missing: list[str] = []
        if not settings.access_token:
            missing.append("WHATSAPP_CLOUD_API_ACCESS_TOKEN")
        if not settings.phone_number_id:
            missing.append("WHATSAPP_PHONE_NUMBER_ID")
        if not settings.verify_token:
            missing.append("WHATSAPP_VERIFY_TOKEN")
        if missing:
            raise ValueError(
                "Configuração incompleta do WhatsApp Cloud API. "
                f"Defina: {', '.join(missing)}"
            )

        return settings


class WhatsAppCloudClient:
    """Cliente minimo para envio de mensagens de texto pela Cloud API."""

    def __init__(self, settings: WhatsAppCloudSettings):
        self._settings = settings

    async def send_text(self, *, to: str, body: str, reply_to_message_id: str | None = None) -> None:
        """Envia uma mensagem de texto para um numero do WhatsApp."""
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": _truncate_text_message(body),
            },
        }
        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}

        headers = {
            "Authorization": f"Bearer {self._settings.access_token}",
            "Content-Type": "application/json",
        }
        url = (
            f"https://graph.facebook.com/{self._settings.api_version}/"
            f"{self._settings.phone_number_id}/messages"
        )

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.is_error:
            logger.error(
                "Falha ao enviar mensagem via WhatsApp status=%s body=%s",
                response.status_code,
                response.text[:1000],
            )
            response.raise_for_status()


class WhatsAppWebhookServer:
    """Servidor HTTP simples para receber webhooks da Meta."""

    def __init__(self, settings: WhatsAppCloudSettings):
        if not settings.enabled:
            raise ValueError("WhatsApp Cloud API desabilitado.")

        self.settings = settings
        self._client = WhatsAppCloudClient(settings)
        self._message_lock = threading.Lock()
        self._processed_message_ids: dict[str, float] = {}
        self._event_loop = asyncio.new_event_loop()
        self._event_thread = threading.Thread(
            target=self._run_event_loop,
            name="whatsapp-event-loop",
            daemon=True,
        )
        self._http_server = ThreadingHTTPServer(
            (settings.webhook_host, settings.webhook_port),
            self._build_request_handler(),
        )
        self._http_thread: threading.Thread | None = None

    @property
    def url_path(self) -> str:
        return self.settings.webhook_path

    def _run_event_loop(self) -> None:
        asyncio.set_event_loop(self._event_loop)
        self._event_loop.run_forever()

    def _build_request_handler(self):
        outer = self

        class RequestHandler(BaseHTTPRequestHandler):
            server_version = "AtendimentoBotWhatsApp/1.0"

            def log_message(self, fmt: str, *args: object) -> None:
                logger.info("WhatsApp webhook %s - %s", self.address_string(), fmt % args)

            def do_GET(self) -> None:
                outer._handle_get(self)

            def do_POST(self) -> None:
                outer._handle_post(self)

        return RequestHandler

    def start_background(self) -> None:
        """Inicia o loop async e o servidor HTTP em threads daemon."""
        if not self._event_thread.is_alive():
            self._event_thread.start()

        if self._http_thread is None or not self._http_thread.is_alive():
            self._http_thread = threading.Thread(
                target=self._http_server.serve_forever,
                name="whatsapp-webhook-http",
                daemon=True,
            )
            self._http_thread.start()

    def serve_forever(self) -> None:
        """Executa o webhook em foreground."""
        if not self._event_thread.is_alive():
            self._event_thread.start()

        logger.info(
            "Webhook do WhatsApp ouvindo em http://%s:%s%s",
            self.settings.webhook_host,
            self.settings.webhook_port,
            self.settings.webhook_path,
        )
        self._http_server.serve_forever()

    def shutdown(self) -> None:
        """Encerra o servidor e o loop interno."""
        if self._http_thread is not None and self._http_thread.is_alive():
            self._http_server.shutdown()
        self._http_server.server_close()
        if self._event_thread.is_alive() and self._event_loop.is_running():
            self._event_loop.call_soon_threadsafe(self._event_loop.stop)

    def _handle_get(self, request: BaseHTTPRequestHandler) -> None:
        path = urlparse(request.path)
        if path.path.rstrip("/") != self.settings.webhook_path:
            self._write_response(request, HTTPStatus.NOT_FOUND, "Endpoint nao encontrado.")
            return

        query = parse_qs(path.query)
        mode = (query.get("hub.mode") or [""])[0]
        token = (query.get("hub.verify_token") or [""])[0]
        challenge = (query.get("hub.challenge") or [""])[0]

        if mode != "subscribe" or token != self.settings.verify_token:
            self._write_response(request, HTTPStatus.FORBIDDEN, "Verificacao recusada.")
            return

        self._write_response(request, HTTPStatus.OK, challenge)

    def _handle_post(self, request: BaseHTTPRequestHandler) -> None:
        path = urlparse(request.path)
        if path.path.rstrip("/") != self.settings.webhook_path:
            self._write_response(request, HTTPStatus.NOT_FOUND, "Endpoint nao encontrado.")
            return

        try:
            content_length = int(request.headers.get("Content-Length", "0"))
        except ValueError:
            self._write_response(request, HTTPStatus.BAD_REQUEST, "Content-Length invalido.")
            return

        body = request.rfile.read(content_length)
        if not self._signature_is_valid(body, request.headers.get("X-Hub-Signature-256")):
            self._write_response(request, HTTPStatus.FORBIDDEN, "Assinatura invalida.")
            return

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_response(request, HTTPStatus.BAD_REQUEST, "Payload invalido.")
            return

        if payload.get("object") != "whatsapp_business_account":
            self._write_response(request, HTTPStatus.OK, "EVENT_RECEIVED")
            return

        future = asyncio.run_coroutine_threadsafe(self._process_payload(payload), self._event_loop)
        future.add_done_callback(self._log_future_exception)
        self._write_response(request, HTTPStatus.OK, "EVENT_RECEIVED")

    def _signature_is_valid(self, body: bytes, signature_header: str | None) -> bool:
        if not self.settings.app_secret:
            return True

        if not signature_header or "=" not in signature_header:
            return False

        algo, provided_signature = signature_header.split("=", 1)
        if algo != "sha256" or not provided_signature:
            return False

        expected_signature = hmac.new(
            self.settings.app_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected_signature, provided_signature)

    def _write_response(
        self,
        request: BaseHTTPRequestHandler,
        status: HTTPStatus,
        body: str,
    ) -> None:
        payload = body.encode("utf-8")
        request.send_response(status.value)
        request.send_header("Content-Type", "text/plain; charset=utf-8")
        request.send_header("Content-Length", str(len(payload)))
        request.end_headers()
        request.wfile.write(payload)

    def _log_future_exception(self, future) -> None:
        try:
            future.result()
        except Exception as exc:
            logger.error("Falha ao processar webhook do WhatsApp: %s", exc, exc_info=True)

    def _mark_message_processed(self, message_id: str) -> bool:
        if not message_id:
            return True

        now = monotonic()
        with self._message_lock:
            expiradas = [
                cached_id
                for cached_id, expires_at in self._processed_message_ids.items()
                if expires_at <= now
            ]
            for cached_id in expiradas:
                self._processed_message_ids.pop(cached_id, None)

            if message_id in self._processed_message_ids:
                return False

            self._processed_message_ids[message_id] = now + _MESSAGE_CACHE_TTL_SECONDS
            return True

    async def _resolve_company(self) -> dict | None:
        if self.settings.default_company_id is not None:
            return await obter_empresa_por_id(self.settings.default_company_id)

        if self.settings.default_company_link_token:
            return await obter_empresa_por_link_token(self.settings.default_company_link_token)

        companies = await listar_empresas()
        if len(companies) == 1:
            return companies[0]

        if len(companies) > 1:
            logger.error(
                "Existem %s empresas cadastradas. Defina WHATSAPP_DEFAULT_COMPANY_ID ou "
                "WHATSAPP_DEFAULT_COMPANY_LINK_TOKEN para escolher qual empresa atende no WhatsApp.",
                len(companies),
            )

        return None

    async def _process_payload(self, payload: dict[str, Any]) -> None:
        company = await self._resolve_company()
        if not company:
            logger.error("Nenhuma empresa resolvida para atendimento via WhatsApp.")
            return

        for phone_number_id, message in _iter_incoming_messages(payload):
            if phone_number_id and phone_number_id != self.settings.phone_number_id:
                logger.warning(
                    "Webhook recebido para phone_number_id inesperado=%s esperado=%s",
                    phone_number_id,
                    self.settings.phone_number_id,
                )
                continue

            message_id = str(message.get("id") or "").strip()
            if not self._mark_message_processed(message_id):
                continue

            from_number = str(message.get("from") or "").strip()
            message_type = str(message.get("type") or "").strip()
            if not from_number:
                continue

            if message_type != "text":
                if message_type in _UNSUPPORTED_MESSAGE_TYPES:
                    await self._client.send_text(
                        to=from_number,
                        body="No momento eu consigo responder apenas mensagens de texto.",
                        reply_to_message_id=message_id or None,
                    )
                continue

            text_payload = message.get("text")
            if not isinstance(text_payload, dict):
                continue

            question = str(text_payload.get("body") or "").strip()
            if not question:
                continue

            response = await processar_pergunta(
                empresa=company,
                pergunta_bruta=question,
                usuario_id=_coerce_user_id(from_number),
                usuario_admin=False,
            )
            await self._client.send_text(
                to=from_number,
                body=response,
                reply_to_message_id=message_id or None,
            )
