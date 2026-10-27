"""Localhost HTTP API used by the RapidGrab browser extension."""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from PySide6.QtCore import QObject, Signal

from ..constants import APP_NAME, VERSION
from .settings import Settings

log = logging.getLogger(__name__)

MAX_BODY = 64 * 1024


class LocalServer(QObject):
    """Small token-authenticated API on 127.0.0.1 for browser hand-off."""

    detectRequested = Signal(dict)
    downloadRequested = Signal(dict)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.port = int(settings.get("server_port") or 0)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self, port: int | None = None) -> tuple[bool, str]:
        if self._httpd is not None:
            return True, f"Already listening on 127.0.0.1:{self.port}"
        desired = int(port or self.port or 47653)
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", desired), _make_handler())
        except OSError as exc:
            return False, f"Could not listen on port {desired}: {exc}"
        httpd.daemon_threads = True
        httpd.rapidgrab = self  # type: ignore[attr-defined]
        self._httpd = httpd
        self.port = desired
        self._thread = threading.Thread(target=httpd.serve_forever, name="rapidgrab-api", daemon=True)
        self._thread.start()
        log.info("Local API listening on http://127.0.0.1:%s", desired)
        return True, f"Listening on 127.0.0.1:{desired}"

    def stop(self) -> None:
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        self._thread = None

    def restart(self, port: int | None = None) -> tuple[bool, str]:
        self.stop()
        return self.start(port)

    # ------------------------------------------------------------------
    def auth_ok(self, token: str | None) -> bool:
        return bool(token) and token == self.settings.server_token


class _Handler(BaseHTTPRequestHandler):
    server_version = f"RapidGrab/{VERSION}"
    protocol_version = "HTTP/1.1"

    # Silence default stderr logging.
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        log.debug("api: " + fmt, *args)

    @property
    def app(self) -> LocalServer:
        return self.server.rapidgrab  # type: ignore[attr-defined]

    # -- helpers --------------------------------------------------------
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-RapidGrab-Token, Authorization",
        )
        self.send_header("Access-Control-Max-Age", "86400")

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _token(self) -> str | None:
        token = self.headers.get("X-RapidGrab-Token")
        if token:
            return token.strip()
        auth = self.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return None

    def _drain_body(self) -> None:
        """Consume an unread request body so keep-alive connections stay in sync."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            # Unknown or oversized body: the socket cannot be safely reused.
            self.close_connection = True
            return
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                self.close_connection = True
                return
            remaining -= len(chunk)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if length <= 0 or length > MAX_BODY:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _reject(self, code: int, message: str) -> None:
        self._json(code, {"ok": False, "error": message})

    def _require_auth(self) -> bool:
        if self.app.auth_ok(self._token()):
            return True
        # Drain first so the connection can be reused after the refusal.
        self._drain_body()
        self._reject(401, "Invalid or missing RapidGrab token.")
        return False

    # -- verbs ----------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/ping":
            self._json(
                200,
                {
                    "ok": True,
                    "app": APP_NAME,
                    "version": VERSION,
                    "port": self.app.port,
                },
            )
            return
        self._reject(404, "Unknown endpoint.")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path not in ("/api/detect", "/api/download"):
            self._drain_body()
            self._reject(404, "Unknown endpoint.")
            return
        if not self._require_auth():
            return
        data = self._read_json()
        url = str(data.get("url") or "").strip()
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            self._reject(400, "A valid http(s) URL is required.")
            return
        if path == "/api/detect":
            self.app.detectRequested.emit(
                {"url": url, "title": str(data.get("title") or "")}
            )
            self._json(200, {"ok": True, "action": "detect"})
            return
        kind = str(data.get("kind") or "video").lower()
        if kind not in ("video", "audio"):
            kind = "video"
        quality = data.get("quality")
        self.app.downloadRequested.emit(
            {
                "url": url,
                "title": str(data.get("title") or ""),
                "kind": kind,
                "quality": quality,
            }
        )
        self._json(200, {"ok": True, "action": "download", "kind": kind})


def _make_handler() -> type[_Handler]:
    return _Handler
