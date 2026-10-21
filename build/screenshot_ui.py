"""Render the main UI to PNG files for visual inspection.

Set QT_QPA_PLATFORM=offscreen in headless environments; native rendering
is preferred locally because it uses the real system fonts.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

from rapidgrab.core.db import Store  # noqa: E402
from rapidgrab.core.engine import Engine  # noqa: E402
from rapidgrab.core.models import MediaInfo, build_format_options  # noqa: E402
from rapidgrab.core.queue import DownloadManager  # noqa: E402
from rapidgrab.core.server import LocalServer  # noqa: E402
from rapidgrab.core.settings import Settings  # noqa: E402
from rapidgrab.ui.format_dialog import FormatDialog  # noqa: E402
from rapidgrab.ui.main_window import MainWindow  # noqa: E402
from rapidgrab.ui.theme import apply_theme  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "screens"
OUT.mkdir(exist_ok=True)

INFO = {
    "title": "Big Buck Bunny - a short animated film",
    "uploader": "Blender Foundation",
    "duration": 596,
    "extractor_key": "Youtube",
    "webpage_url": "https://www.youtube.com/watch?v=abcd1234",
    "resolution": "1920x1080",
    "formats": [
        {"format_id": "137", "ext": "mp4", "height": 1080, "fps": 30, "vcodec": "avc1", "acodec": "none", "filesize": 84_000_000, "tbr": 2500},
        {"format_id": "136", "ext": "mp4", "height": 720, "fps": 30, "vcodec": "avc1", "acodec": "none", "filesize": 42_000_000, "tbr": 1400},
        {"format_id": "18", "ext": "mp4", "height": 360, "fps": 30, "vcodec": "avc1", "acodec": "mp4a", "filesize": 18_000_000, "tbr": 700},
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a", "abr": 128, "filesize": 9_500_000},
        {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 160, "filesize": 11_000_000},
    ],
}


def main() -> int:
    workdir = pathlib.Path(tempfile.mkdtemp(prefix="rapidgrab-shots-"))
    app = QApplication([])
    settings = Settings(workdir / "settings.json")
    settings.set("download_dir", str(workdir))
    apply_theme(app, "dark")

    store = Store(workdir / "db.sqlite")
    engine = Engine(settings)
    manager = DownloadManager(engine, store, settings)
    server = LocalServer(settings)
    server.start()
    window = MainWindow(settings, store, engine, manager, server)
    window.resize(1080, 740)

    completed_file = workdir / "Nature documentary [abc] .mp4"
    completed_file.write_bytes(b"x" * 2048)

    samples = [
        dict(
            url="https://www.youtube.com/watch?v=abc",
            title="Lofi beats to relax and study to - 3 hour mix",
            site="YouTube",
            media_kind="video",
            quality_label="1080p",
            status="downloading",
            progress=0.42,
            speed=4_300_000,
            eta=37,
            total_bytes=84_000_000,
            downloaded_bytes=35_000_000,
        ),
        dict(
            url="https://x.com/example/status/1",
            title="Launch highlights from the space center",
            site="X",
            media_kind="video",
            quality_label="720p",
            status="paused",
            progress=0.68,
            total_bytes=22_000_000,
        ),
        dict(
            url="https://www.facebook.com/watch?v=9",
            title="Nature documentary - full episode",
            site="Facebook",
            media_kind="audio",
            quality_label="MP3 192 kbps",
            status="completed",
            progress=1.0,
            total_bytes=9_200_000,
            filepath=str(completed_file),
        ),
    ]
    for fields in samples:
        job = store.new_job(**fields)
        store.insert_job(job)
        window.downloads.add_job(job)
    window.downloads.refresh_counts()
    window.show()
    app.processEvents()
    window.grab().save(str(OUT / "main_downloads.png"))

    # Format picker
    videos, audios = build_format_options(INFO)
    media = MediaInfo(
        url=INFO["webpage_url"],
        title=INFO["title"],
        site="YouTube",
        uploader=INFO["uploader"],
        duration=INFO["duration"],
        webpage_url=INFO["webpage_url"],
        video_formats=videos,
        audio_formats=audios,
    )
    dialog = FormatDialog(media, settings)
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(OUT / "format_dialog.png"))
    dialog.tabs.setCurrentIndex(1)
    app.processEvents()
    dialog.grab().save(str(OUT / "format_dialog_audio.png"))
    dialog.close()

    # Library and settings
    window.tabs.setCurrentWidget(window.library)
    app.processEvents()
    print(
        "library debug:",
        "history=", len(store.list_history()),
        "rows=", window.library.table.rowCount(),
        "table_visible=", window.library.table.isVisible(),
        "viewport_h=", window.library.table.viewport().height(),
    )
    window.grab().save(str(OUT / "library.png"))
    window.tabs.setCurrentWidget(window.settings_page)
    app.processEvents()
    window.grab().save(str(OUT / "settings.png"))

    # Scroll to the Tools group so the FFmpeg / JavaScript runtime rows are visible.
    scroll = window.settings_page.findChild(QScrollArea)
    if scroll is not None:
        bar = scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        app.processEvents()
        window.grab().save(str(OUT / "settings_tools.png"))

    QTimer.singleShot(50, app.quit)
    app.exec()
    manager.shutdown()
    server.stop()
    store.close()
    print("screens written to", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
