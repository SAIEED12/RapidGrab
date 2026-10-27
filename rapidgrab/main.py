"""RapidGrab application entry point."""

from __future__ import annotations

import argparse
import ctypes
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .constants import APP_NAME, APP_SLUG, VERSION, app_data_dir, assets_dir
from .core.db import Store
from .core.engine import Engine, find_ffmpeg, find_js_runtimes, ytdlp_version
from .core.queue import DownloadManager
from .core.server import LocalServer
from .core.settings import Settings
from .ui.main_window import MainWindow
from .ui.theme import apply_theme

log = logging.getLogger("rapidgrab")


def setup_logging() -> None:
    log_dir = app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    file_handler = RotatingFileHandler(
        log_dir / "rapidgrab.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    if sys.stderr is not None:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)


def _excepthook(exc_type, exc, tb) -> None:
    log.error("Unhandled exception", exc_info=(exc_type, exc, tb))
    sys.__excepthook__(exc_type, exc, tb)


def run_diagnostics() -> int:
    """Write environment details to a file (and stdout) for troubleshooting."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        extension = base / "extension"
        ffmpeg_glob = sorted(str(path) for path in (base / "bin").glob("ffmpeg*")) if (base / "bin").is_dir() else []
    else:
        extension = Path(__file__).resolve().parents[1] / "extension"
        ffmpeg_glob = []

    settings = Settings()
    lines = [
        f"{APP_NAME} {VERSION}",
        f"frozen: {getattr(sys, 'frozen', False)}",
        f"python: {sys.version.split()[0]}",
        f"data dir: {app_data_dir()}",
        f"ffmpeg: {find_ffmpeg(settings) or 'MISSING'}",
        f"ffmpeg bundled: {ffmpeg_glob or 'n/a'}",
        f"js runtimes: {find_js_runtimes(settings) or 'MISSING'}",
        f"yt-dlp: {ytdlp_version()}",
        f"extension dir: {extension if extension.is_dir() else 'MISSING'}",
        f"api port: {settings.get('server_port')}",
        f"api token set: {bool(settings.get('server_token'))}",
    ]
    text = "\n".join(lines)
    try:
        (app_data_dir() / "diagnostics.txt").write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rapidgrab",
        description=f"{APP_NAME} - download video and audio from the web.",
    )
    parser.add_argument("--version", action="store_true", help="Show the version and exit.")
    parser.add_argument("--diagnose", action="store_true", help="Write environment diagnostics and exit.")
    parser.add_argument("--no-server", action="store_true", help="Do not start the browser API.")
    parser.add_argument("url", nargs="?", help="Optional URL to analyze on startup.")
    args = parser.parse_args(argv)

    if args.version:
        print(f"{APP_NAME} {VERSION}")
        return 0
    if args.diagnose:
        return run_diagnostics()

    setup_logging()
    sys.excepthook = _excepthook

    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                f"{APP_SLUG}.App.{VERSION}"
            )
        except Exception:  # pragma: no cover - cosmetic only
            pass

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_SLUG)
    app.setApplicationVersion(VERSION)
    app.setDesktopFileName(APP_SLUG)

    settings = Settings()
    apply_theme(app, str(settings.get("theme") or "dark"))
    icon_path = assets_dir() / "app_icon.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    store = Store()
    engine = Engine(settings)
    manager = DownloadManager(engine, store, settings)
    server = LocalServer(settings)
    server_ok, server_message = (True, "Local API disabled.")
    if not args.no_server:
        server_ok, server_message = server.start()
        if not server_ok:
            log.warning("Local API failed to start: %s", server_message)

    window = MainWindow(settings, store, engine, manager, server)
    app.setQuitOnLastWindowClosed(False)

    def cleanup() -> None:
        log.info("Shutting down")
        try:
            manager.shutdown()
        finally:
            server.stop()
            store.close()

    app.aboutToQuit.connect(cleanup)
    window.show()

    if not server_ok:
        window._set_status(server_message)
    if args.url:
        window.url_input.setText(args.url)
        QTimer.singleShot(400, lambda: window._analyze(args.url))

    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
