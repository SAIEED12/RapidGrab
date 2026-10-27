from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

from PySide6.QtCore import QCoreApplication

from rapidgrab.core.server import LocalServer
from rapidgrab.core.settings import Settings


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(port: int, path: str, payload: dict | None = None, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-RapidGrab-Token"] = token
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers=headers,
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_api_ping_and_authenticated_actions(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    settings = Settings(tmp_path / "settings.json")
    server = LocalServer(settings)
    port = free_port()
    ok, message = server.start(port)
    assert ok, message

    detections: list[dict] = []
    downloads: list[dict] = []
    server.detectRequested.connect(lambda payload: detections.append(payload))
    server.downloadRequested.connect(lambda payload: downloads.append(payload))

    try:
        status, payload = request(port, "/api/ping")
        assert status == 200
        assert payload["app"] == "RapidGrab"

        # Unauthenticated detect is rejected.
        status, payload = request(
            port, "/api/detect", {"url": "https://www.youtube.com/watch?v=abc"}
        )
        assert status == 401

        # With the correct token the app receives the URL.
        status, payload = request(
            port,
            "/api/detect",
            {"url": "https://www.youtube.com/watch?v=abc", "title": "A video"},
            token=settings.server_token,
        )
        assert status == 200
        deadline = time.time() + 2
        while not detections and time.time() < deadline:
            app.processEvents()
            time.sleep(0.02)
        assert detections[0]["url"] == "https://www.youtube.com/watch?v=abc"

        status, payload = request(
            port,
            "/api/download",
            {"url": "https://x.com/user/status/1", "kind": "audio"},
            token=settings.server_token,
        )
        assert status == 200
        deadline = time.time() + 2
        while not downloads and time.time() < deadline:
            app.processEvents()
            time.sleep(0.02)
        assert downloads[0]["kind"] == "audio"

        status, _ = request(
            port, "/api/detect", {"url": "not-a-url"}, token=settings.server_token
        )
        assert status == 400
    finally:
        server.stop()
        assert not server.running


def read_response(stream) -> tuple[int, dict[str, str], bytes]:
    """Read one HTTP response from a raw socket stream."""
    status_line = stream.readline().decode("latin-1")
    status = int(status_line.split(" ")[1])
    headers: dict[str, str] = {}
    while True:
        line = stream.readline().decode("latin-1")
        if line in ("\r\n", "\n", ""):
            break
        key, _, value = line.partition(":")
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length") or 0)
    return status, headers, stream.read(length) if length else b""


def test_rejected_request_keeps_connection_usable(tmp_path):
    """A 401 must not leave the unread body behind to corrupt the next request."""
    QCoreApplication.instance() or QCoreApplication([])
    settings = Settings(tmp_path / "settings.json")
    server = LocalServer(settings)
    port = free_port()
    ok, message = server.start(port)
    assert ok, message

    body = json.dumps({"url": "https://www.youtube.com/watch?v=abc"}).encode("utf-8")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            stream = sock.makefile("rwb")
            stream.write(
                b"POST /api/download HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"Connection: keep-alive\r\n"
                + b"Content-Length: %d\r\n\r\n" % len(body)
                + body
            )
            stream.flush()

            status, headers, payload = read_response(stream)
            assert status == 401
            assert json.loads(payload)["ok"] is False

            # Second request on the same connection must be parsed correctly.
            stream.write(
                b"GET /api/ping HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Connection: close\r\n\r\n"
            )
            stream.flush()
            status, _, payload = read_response(stream)
            assert status == 200
            assert json.loads(payload)["app"] == "RapidGrab"
    finally:
        server.stop()
