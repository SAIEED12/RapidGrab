"""Headless GUI + queue end-to-end check.

Usage: .venv\\Scripts\\python.exe build\\smoke_gui.py [url]
Runs the full app offscreen, queues a download through the real UI path and
waits for completion.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rapidgrab.core.db import Store  # noqa: E402
from rapidgrab.core.engine import Engine  # noqa: E402
from rapidgrab.core.queue import DownloadManager  # noqa: E402
from rapidgrab.core.server import LocalServer  # noqa: E402
from rapidgrab.core.settings import Settings  # noqa: E402
from rapidgrab.ui.main_window import MainWindow  # noqa: E402
from rapidgrab.ui.theme import apply_theme  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.w3schools.com/html/mov_bbb.mp4"


def main() -> int:
    workdir = pathlib.Path(tempfile.mkdtemp(prefix="rapidgrab-gui-"))
    app = QApplication([])
    settings = Settings(workdir / "settings.json")
    settings.set("download_dir", str(workdir))
    apply_theme(app, "dark")

    store = Store(workdir / "db.sqlite")
    engine = Engine(settings)
    manager = DownloadManager(engine, store, settings)
    server = LocalServer(settings)
    window = MainWindow(settings, store, engine, manager, server)
    window.show()

    outcome: dict[str, object] = {}

    def completed(job: dict) -> None:
        outcome["job"] = job
        QTimer.singleShot(50, app.quit)

    manager.jobCompleted.connect(completed)
    window._on_quick_download(
        {"url": URL, "title": "GUI smoke", "kind": "video", "quality": "720"}
    )
    QTimer.singleShot(120_000, app.quit)
    app.exec()

    job = outcome.get("job") or {}
    path = pathlib.Path(str(job.get("filepath") or ""))
    print(f"status={job.get('status')} path={path}")
    print(f"library rows={len(store.list_history())}")
    ok = job.get("status") == "completed" and path.is_file() and path.stat().st_size > 0
    print("GUI SMOKE:", "PASS" if ok else "FAIL")

    manager.shutdown()
    server.stop()
    store.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
