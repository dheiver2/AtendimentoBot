"""Bridge local para integrar o projeto ao WhatsApp Web via QR code."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import monotonic
from typing import Any
from urllib.error import URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from config import BASE_DIR, DATA_DIR
from database import listar_empresas, obter_empresa_por_id, obter_empresa_por_link_token
from whatsapp_flow import processar_mensagem_whatsapp

logger = logging.getLogger(__name__)

_DEFAULT_BRIDGE_HOST = "127.0.0.1"
_DEFAULT_BRIDGE_PATH = "/bridge/whatsapp/message"
_DEFAULT_BRIDGE_PORT = 8010
_DEFAULT_CLIENT_COMMAND = "npm run whatsapp:bridge"
_DEFAULT_CLIENT_HEALTH_PATH = "/health"
_DEFAULT_CLIENT_HOST = "127.0.0.1"
_DEFAULT_CLIENT_ID = "atendimento-bot"
_DEFAULT_CLIENT_PORT = 8011
_DEFAULT_LAUNCH_TIMEOUT_SECONDS = 15
_DEFAULT_SESSION_DIR = os.path.join(DATA_DIR, "whatsapp-web-session")
_MESSAGE_CACHE_TTL_SECONDS = 600
_MAX_TEXT_MESSAGE_LENGTH = 4096


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_path(value: str | None, default: str) -> str:
    path = (value or default).strip() or default
    if not path.startswith("/"):
        path = f"/{path}"
    return path.rstrip("/") or "/"


def _normalize_request_path(path: str) -> str:
    return path.rstrip("/") or "/"


def _normalize_local_host(host: str | None) -> str:
    value = (host or "").strip()
    if value in {"", "0.0.0.0", "::"}:
        return "127.0.0.1"
    return value


def _truncate_text_message(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= _MAX_TEXT_MESSAGE_LENGTH:
        return text
    return text[: _MAX_TEXT_MESSAGE_LENGTH - 3].rstrip() + "..."


def _resolve_path(value: str | None, default: str) -> str:
    path = (value or default).strip() or default
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, path)


@dataclass(frozen=True)
class WhatsAppWebSettings:
    enabled: bool
    bridge_host: str = _DEFAULT_BRIDGE_HOST
    bridge_port: int = _DEFAULT_BRIDGE_PORT
    bridge_path: str = _DEFAULT_BRIDGE_PATH
    bridge_token: str = ""
    client_host: str = _DEFAULT_CLIENT_HOST
    client_port: int = _DEFAULT_CLIENT_PORT
    client_health_path: str = _DEFAULT_CLIENT_HEALTH_PATH
    client_command: str = _DEFAULT_CLIENT_COMMAND
    client_id: str = _DEFAULT_CLIENT_ID
    session_dir: str = _DEFAULT_SESSION_DIR
    auto_launch: bool = True
    launch_timeout_seconds: int = _DEFAULT_LAUNCH_TIMEOUT_SECONDS
    default_company_id: int | None = None
    default_company_link_token: str = ""

    @classmethod
    def from_env(cls) -> "WhatsAppWebSettings":
        enabled = _is_truthy(os.getenv("WHATSAPP_WEB_ENABLED"))
        company_id_raw = (os.getenv("WHATSAPP_DEFAULT_COMPANY_ID") or "").strip()

        return cls(
            enabled=enabled,
            bridge_host=(os.getenv("WHATSAPP_WEB_BRIDGE_HOST") or _DEFAULT_BRIDGE_HOST).strip(),
            bridge_port=int(
                (os.getenv("WHATSAPP_WEB_BRIDGE_PORT") or str(_DEFAULT_BRIDGE_PORT)).strip()
            ),
            bridge_path=_normalize_path(
                os.getenv("WHATSAPP_WEB_BRIDGE_PATH"),
                _DEFAULT_BRIDGE_PATH,
            ),
            bridge_token=(os.getenv("WHATSAPP_WEB_BRIDGE_TOKEN") or "").strip(),
            client_host=(os.getenv("WHATSAPP_WEB_CLIENT_HOST") or _DEFAULT_CLIENT_HOST).strip(),
            client_port=int(
                (os.getenv("WHATSAPP_WEB_CLIENT_PORT") or str(_DEFAULT_CLIENT_PORT)).strip()
            ),
            client_health_path=_normalize_path(
                os.getenv("WHATSAPP_WEB_CLIENT_HEALTH_PATH"),
                _DEFAULT_CLIENT_HEALTH_PATH,
            ),
            client_command=(
                os.getenv("WHATSAPP_WEB_CLIENT_COMMAND") or _DEFAULT_CLIENT_COMMAND
            ).strip(),
            client_id=(os.getenv("WHATSAPP_WEB_CLIENT_ID") or _DEFAULT_CLIENT_ID).strip(),
            session_dir=_resolve_path(
                os.getenv("WHATSAPP_WEB_SESSION_DIR"),
                _DEFAULT_SESSION_DIR,
            ),
            auto_launch=_is_truthy(os.getenv("WHATSAPP_WEB_AUTO_LAUNCH") or "1"),
            launch_timeout_seconds=int(
                (
                    os.getenv("WHATSAPP_WEB_LAUNCH_TIMEOUT_SECONDS")
                    or str(_DEFAULT_LAUNCH_TIMEOUT_SECONDS)
                ).strip()
            ),
            default_company_id=int(company_id_raw) if company_id_raw else None,
            default_company_link_token=(
                os.getenv("WHATSAPP_DEFAULT_COMPANY_LINK_TOKEN") or ""
            ).strip(),
        )

    @property
    def bridge_url(self) -> str:
        host = _normalize_local_host(self.bridge_host)
        return f"http://{host}:{self.bridge_port}{self.bridge_path}"

    @property
    def client_health_url(self) -> str:
        host = _normalize_local_host(self.client_host)
        return f"http://{host}:{self.client_port}{self.client_health_path}"


class WhatsAppWebBridgeServer:
    """Servidor HTTP local consumido pelo bridge do WhatsApp Web."""

    def __init__(self, settings: WhatsAppWebSettings):
        if not settings.enabled:
            raise ValueError("WhatsApp Web desabilitado.")

        self.settings = settings
        self._message_lock = threading.Lock()
        self._processed_message_ids: dict[str, float] = {}
        self._event_loop = asyncio.new_event_loop()
        self._event_thread = threading.Thread(
            target=self._run_event_loop,
            name="whatsapp-web-event-loop",
            daemon=True,
        )
        self._http_server = ThreadingHTTPServer(
            (settings.bridge_host, settings.bridge_port),
            self._build_request_handler(),
        )
        self._http_thread: threading.Thread | None = None

    @property
    def url_path(self) -> str:
        return self.settings.bridge_path

    def _run_event_loop(self) -> None:
        asyncio.set_event_loop(self._event_loop)
        self._event_loop.run_forever()

    def _build_request_handler(self):
        outer = self

        class RequestHandler(BaseHTTPRequestHandler):
            server_version = "AtendimentoBotWhatsAppWeb/1.0"

            def log_message(self, fmt: str, *args: object) -> None:
                logger.info("WhatsApp Web bridge %s - %s", self.address_string(), fmt % args)

            def do_GET(self) -> None:
                outer._handle_get(self)

            def do_POST(self) -> None:
                outer._handle_post(self)

        return RequestHandler

    def start_background(self) -> None:
        if not self._event_thread.is_alive():
            self._event_thread.start()

        if self._http_thread is None or not self._http_thread.is_alive():
            self._http_thread = threading.Thread(
                target=self._http_server.serve_forever,
                name="whatsapp-web-bridge-http",
                daemon=True,
            )
            self._http_thread.start()

    def serve_forever(self) -> None:
        if not self._event_thread.is_alive():
            self._event_thread.start()

        logger.info(
            "Bridge local do WhatsApp ouvindo em http://%s:%s%s",
            self.settings.bridge_host,
            self.settings.bridge_port,
            self.settings.bridge_path,
        )
        self._http_server.serve_forever()

    def shutdown(self) -> None:
        if self._http_thread is not None and self._http_thread.is_alive():
            self._http_server.shutdown()
            self._http_thread.join(timeout=2)

        self._http_server.server_close()

        if self._event_thread.is_alive() and self._event_loop.is_running():
            self._event_loop.call_soon_threadsafe(self._event_loop.stop)
            self._event_thread.join(timeout=2)

        if not self._event_loop.is_closed():
            self._event_loop.close()

    def _handle_get(self, request: BaseHTTPRequestHandler) -> None:
        path = urlparse(request.path)
        if _normalize_request_path(path.path) != "/health":
            self._write_json_response(
                request,
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": "Endpoint nao encontrado."},
            )
            return

        self._write_json_response(
            request,
            HTTPStatus.OK,
            {
                "ok": True,
                "bridge_url": self.settings.bridge_url,
            },
        )

    def _handle_post(self, request: BaseHTTPRequestHandler) -> None:
        path = urlparse(request.path)
        if _normalize_request_path(path.path) != self.settings.bridge_path:
            self._write_json_response(
                request,
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": "Endpoint nao encontrado."},
            )
            return

        if not self._request_is_authorized(request):
            self._write_json_response(
                request,
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": "Token local invalido."},
            )
            return

        try:
            content_length = int(request.headers.get("Content-Length", "0"))
        except ValueError:
            self._write_json_response(
                request,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "Content-Length invalido."},
            )
            return

        try:
            body = request.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_json_response(
                request,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "Payload invalido."},
            )
            return

        future = asyncio.run_coroutine_threadsafe(self._build_actions(payload), self._event_loop)
        try:
            actions = future.result()
        except Exception as exc:
            logger.error("Falha ao processar mensagem do WhatsApp Web: %s", exc, exc_info=True)
            self._write_json_response(
                request,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": "Falha ao processar mensagem."},
            )
            return

        self._write_json_response(
            request,
            HTTPStatus.OK,
            {
                "ok": True,
                "reply": next(
                    (
                        action.get("text", "")
                        for action in actions
                        if action.get("type") == "text" and action.get("text")
                    ),
                    "",
                ),
                "actions": actions,
            },
        )

    def _request_is_authorized(self, request: BaseHTTPRequestHandler) -> bool:
        if not self.settings.bridge_token:
            return True

        authorization = request.headers.get("Authorization") or ""
        forwarded_token = request.headers.get("X-Bridge-Token") or ""
        expected_bearer = f"Bearer {self.settings.bridge_token}"
        return (
            secrets.compare_digest(authorization, expected_bearer)
            or secrets.compare_digest(forwarded_token, self.settings.bridge_token)
        )

    def _write_json_response(
        self,
        request: BaseHTTPRequestHandler,
        status: HTTPStatus,
        payload: dict[str, Any],
    ) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request.send_response(status.value)
        request.send_header("Content-Type", "application/json; charset=utf-8")
        request.send_header("Content-Length", str(len(body)))
        request.end_headers()
        request.wfile.write(body)

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

        return None

    async def _build_actions(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        sender = str(payload.get("sender") or "").strip()
        text = _truncate_text_message(str(payload.get("text") or "").strip())
        message_id = str(payload.get("message_id") or "").strip()
        message_type = str(payload.get("message_type") or "chat").strip() or "chat"
        is_owner_chat = bool(payload.get("is_owner_chat"))
        mime_type = str(payload.get("mime_type") or "").strip()
        file_name = str(payload.get("file_name") or "").strip()
        media_base64 = str(payload.get("media_base64") or "").strip()
        media_bytes = None
        if media_base64:
            media_bytes = base64.b64decode(media_base64, validate=True)

        if not sender or (not text and message_type == "chat"):
            raise ValueError("Mensagem do WhatsApp Web incompleta.")

        if not self._mark_message_processed(message_id):
            return []

        return await processar_mensagem_whatsapp(
            sender=sender,
            text=text,
            message_type=message_type,
            is_owner_chat=is_owner_chat,
            mime_type=mime_type,
            file_name=file_name,
            media_bytes=media_bytes,
            resolve_default_company=self._resolve_company,
            share_link_builder=self._build_share_link,
        )

    def _build_share_link(self, command_text: str) -> str | None:
        status = get_whatsapp_client_status(self.settings)
        own_number = str(status.get("ownNumber") or "").strip() if status else ""
        digits = "".join(char for char in own_number if char.isdigit())
        if not digits:
            return None
        return f"https://wa.me/{digits}?text={quote(command_text)}"


def is_whatsapp_client_running(settings: WhatsAppWebSettings) -> bool:
    request = Request(settings.client_health_url, method="GET")
    try:
        with urlopen(request, timeout=2.0) as response:
            return response.status == HTTPStatus.OK
    except (OSError, URLError):
        return False


def get_whatsapp_client_status(settings: WhatsAppWebSettings) -> dict[str, Any] | None:
    request = Request(settings.client_health_url, method="GET")
    try:
        with urlopen(request, timeout=2.0) as response:
            if response.status != HTTPStatus.OK:
                return None
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else None
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _build_windows_launch_command(command: str) -> list[str]:
    windows_cwd = BASE_DIR.replace("/", "\\")
    shell_command = f'cd /d "{windows_cwd}" && {command}'
    return ["cmd.exe", "/c", "start", "", "cmd.exe", "/k", shell_command]


def _build_wsl_launch_command(command: str) -> list[str]:
    distro = (os.getenv("WSL_DISTRO_NAME") or "").strip()
    shell_command = f"cd {shlex.quote(BASE_DIR)} && {command}"
    cmd = ["cmd.exe", "/c", "start", "", "wsl.exe"]
    if distro:
        cmd.extend(["-d", distro])
    cmd.extend(["bash", "-lc", shell_command])
    return cmd


def _build_macos_launch_command(command: str) -> list[str]:
    shell_command = f"cd {shlex.quote(BASE_DIR)} && {command}"
    apple_script = f'tell application "Terminal" to do script "{shell_command.replace(chr(34), chr(92) + chr(34))}"'
    return ["osascript", "-e", apple_script]


def _build_linux_launch_command(command: str) -> list[str] | None:
    shell_command = f"cd {shlex.quote(BASE_DIR)} && {command}"
    candidates: list[tuple[str, list[str]]] = [
        ("x-terminal-emulator", ["x-terminal-emulator", "-e", "bash", "-lc", shell_command]),
        ("gnome-terminal", ["gnome-terminal", "--", "bash", "-lc", shell_command]),
        ("konsole", ["konsole", "-e", "bash", "-lc", shell_command]),
        ("xfce4-terminal", ["xfce4-terminal", "--command", f"bash -lc {shlex.quote(shell_command)}"]),
        ("mate-terminal", ["mate-terminal", "--", "bash", "-lc", shell_command]),
        ("lxterminal", ["lxterminal", "-e", f"bash -lc {shlex.quote(shell_command)}"]),
        ("xterm", ["xterm", "-e", "bash", "-lc", shell_command]),
    ]

    for executable, launch_command in candidates:
        if shutil.which(executable):
            return launch_command
    return None


def _build_terminal_launch_command(settings: WhatsAppWebSettings) -> list[str] | None:
    command = settings.client_command.strip() or _DEFAULT_CLIENT_COMMAND
    if os.getenv("WSL_DISTRO_NAME"):
        return _build_wsl_launch_command(command)
    if os.name == "nt":
        return _build_windows_launch_command(command)
    if sys.platform == "darwin":
        return _build_macos_launch_command(command)
    return _build_linux_launch_command(command)


def launch_whatsapp_client_in_new_terminal(settings: WhatsAppWebSettings) -> bool:
    if not settings.enabled or not settings.auto_launch:
        return False

    if is_whatsapp_client_running(settings):
        return False

    launch_command = _build_terminal_launch_command(settings)
    if not launch_command:
        logger.warning(
            "Nao foi possivel abrir um novo terminal automaticamente. "
            "Execute manualmente em outro terminal: %s",
            settings.client_command,
        )
        return False

    os.makedirs(settings.session_dir, exist_ok=True)
    subprocess.Popen(launch_command, cwd=BASE_DIR, start_new_session=True)

    deadline = monotonic() + max(settings.launch_timeout_seconds, 0)
    while monotonic() < deadline:
        if is_whatsapp_client_running(settings):
            return True
        time.sleep(0.5)

    logger.warning(
        "O terminal do WhatsApp foi iniciado, mas o bridge ainda nao respondeu em %ss. "
        "Se precisar, execute manualmente em outro terminal: %s",
        settings.launch_timeout_seconds,
        settings.client_command,
    )
    return True
