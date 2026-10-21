"""Main application window."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..constants import APP_NAME, VERSION, assets_dir
from ..core.db import Store
from ..core.engine import Engine, find_ffmpeg, ytdlp_version
from ..core.models import MediaInfo
from ..core.queue import DownloadManager
from ..core.server import LocalServer
from ..core.settings import Settings
from .downloads_page import DownloadsPage
from .format_dialog import FormatDialog, PlaylistDialog
from .library_page import LibraryPage
from .settings_page import SettingsPage
from .theme import apply_theme, muted


class ProbeThread(QThread):
    success = Signal(object)
    failed = Signal(str)

    def __init__(self, engine: Engine, url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.url = url

    def run(self) -> None:
        try:
            info = self.engine.probe(self.url)
            self.success.emit(info)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: Settings,
        store: Store,
        engine: Engine,
        manager: DownloadManager,
        server: LocalServer,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.store = store
        self.engine = engine
        self.manager = manager
        self.server = server
        self._probe_thread: ProbeThread | None = None
        self._allow_close = False
        self._tray_hint_shown = False

        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1060, 720)
        self.setMinimumSize(860, 560)
        icon = QIcon(str(assets_dir() / "app_icon.svg"))
        self.setWindowIcon(icon)

        self._build()
        self._wire()
        self._build_tray(icon)
        self._refresh_engine_status()
        self.downloads.load_jobs(self.manager.jobs)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 10)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(self.windowIcon().pixmap(38, 38))
        header.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        app_title = QLabel(APP_NAME)
        app_title.setObjectName("H1")
        titles.addWidget(app_title)
        subtitle = muted("Download video and audio from YouTube, Facebook, X and many more sites")
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        self.api_pill = QLabel("API off")
        self.api_pill.setObjectName("StatusPill")
        header.addWidget(self.api_pill)
        root.addLayout(header)

        url_row = QHBoxLayout()
        url_row.setSpacing(10)
        self.url_input = QLineEdit()
        self.url_input.setObjectName("UrlInput")
        self.url_input.setPlaceholderText(
            "Paste a video, playlist or channel link  (Ctrl+V works anywhere)"
        )
        self.url_input.setClearButtonEnabled(True)
        url_row.addWidget(self.url_input, 1)
        self.analyze_btn = QPushButton("Analyze")
        self.analyze_btn.setObjectName("Primary")
        self.analyze_btn.setMinimumWidth(120)
        self.analyze_btn.setMinimumHeight(38)
        url_row.addWidget(self.analyze_btn)
        root.addLayout(url_row)

        self.tabs = QTabWidget()
        self.downloads = DownloadsPage(self.manager)
        self.library = LibraryPage(self.store, self.manager)
        self.settings_page = SettingsPage(self.settings)
        self.tabs.addTab(self.downloads, "Downloads")
        self.tabs.addTab(self.library, "Library")
        self.tabs.addTab(self.settings_page, "Settings")
        root.addWidget(self.tabs, 1)

        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.status_label, 1)
        self.engine_label = QLabel()
        self.statusBar().addPermanentWidget(self.engine_label)
        self.ffmpeg_label = QLabel()
        self.statusBar().addPermanentWidget(self.ffmpeg_label)
        self.server_label = QLabel()
        self.statusBar().addPermanentWidget(self.server_label)

    def _wire(self) -> None:
        self.analyze_btn.clicked.connect(lambda: self._analyze())
        self.url_input.returnPressed.connect(lambda: self._analyze())
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.manager.jobCompleted.connect(self._on_job_completed)
        self.manager.jobsChanged.connect(self._refresh_tray_tooltip)
        self.server.detectRequested.connect(self._on_detect_request)
        self.server.downloadRequested.connect(self._on_quick_download)
        self.settings_page.settingsSaved.connect(self._on_settings_saved)
        self.settings_page.serverRestartRequested.connect(self._restart_server)

    def _build_tray(self, icon: QIcon) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        show_action = QAction("Open Rapid Grab", menu)
        show_action.triggered.connect(self.show_window)
        menu.addAction(show_action)
        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.setToolTip(APP_NAME)
        tray.activated.connect(self._tray_activated)
        tray.messageClicked.connect(self.show_window)
        tray.show()
        self.tray = tray

    # ------------------------------------------------------------------
    def show_window(self) -> None:
        if self.isMinimized():
            self.showNormal()
        if not self.isVisible():
            self.show()
        self.setWindowState(
            self.windowState() & ~Qt.WindowState.WindowMinimized
            | Qt.WindowState.WindowActive
        )
        self.raise_()
        self.activateWindow()
        if sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            except Exception:
                pass

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def _quit_app(self) -> None:
        self._allow_close = True
        QApplication.instance().quit()

    # ------------------------------------------------------------------
    def _default_url(self) -> str:
        url = self.url_input.text().strip()
        if not url:
            clipboard = QApplication.clipboard().text().strip()
            if clipboard.startswith(("http://", "https://")):
                url = clipboard
                self.url_input.setText(url)
        if url and "://" not in url and "." in url:
            url = "https://" + url
            self.url_input.setText(url)
        return url

    def _analyze(self, url: str | None = None) -> None:
        if self._probe_thread is not None:
            return
        target = (url or self._default_url()).strip()
        if not target:
            self._set_status("Paste a link first, then press Analyze.")
            return
        if not target.startswith(("http://", "https://")):
            QMessageBox.information(
                self, "Unsupported link", "Please paste a full http:// or https:// link."
            )
            return
        self.url_input.setText(target)
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("Analyzing...")
        self._set_status("Fetching available formats...")
        thread = ProbeThread(self.engine, target, self)
        thread.success.connect(self._on_probe_success)
        thread.failed.connect(self._on_probe_failed)
        thread.finished.connect(self._on_probe_finished)
        self._probe_thread = thread
        thread.start()

    def _on_probe_finished(self) -> None:
        thread = self._probe_thread
        self._probe_thread = None
        if thread is not None:
            thread.deleteLater()
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("Analyze")

    def _on_probe_failed(self, message: str) -> None:
        self._set_status("Could not analyze that link.")
        QMessageBox.warning(self, "Could not analyze link", message)

    def _on_probe_success(self, media: MediaInfo) -> None:
        self._set_status("Formats loaded. Choose what to download.")
        if media.is_playlist and media.entries:
            dialog = PlaylistDialog(media, self.settings, self)
            if dialog.exec() and dialog.result_jobs:
                count = self.manager.add_jobs(dialog.result_jobs)
                self.tabs.setCurrentWidget(self.downloads)
                self._set_status(f"Added {count} playlist item{'s' if count != 1 else ''} to the queue.")
            return

        dialog = FormatDialog(media, self.settings, self)
        if not dialog.exec() or not dialog.result_fields:
            return
        fields = dict(dialog.result_fields)
        fields.update(
            {
                "title": media.title,
                "site": media.site,
                "thumbnail": media.thumbnail or "",
            }
        )
        self.manager.add_job(media.url or media.webpage_url, **fields)
        self.tabs.setCurrentWidget(self.downloads)
        self._set_status(f"Added \"{media.title}\" to the queue.")

    # ------------------------------------------------------------------
    def _on_detect_request(self, payload: dict) -> None:
        self.show_window()
        url = str(payload.get("url") or "")
        self.url_input.setText(url)
        self._set_status("Link received from the browser extension.")
        self._analyze(url)

    def _on_quick_download(self, payload: dict) -> None:
        url = str(payload.get("url") or "")
        if not url:
            return
        kind = str(payload.get("kind") or "video")
        title = str(payload.get("title") or url)
        if kind == "audio":
            fmt = str(self.settings.get("default_audio_format") or "mp3")
            bitrate = int(self.settings.get("default_audio_bitrate") or 192)
            fields = {
                "media_kind": "audio",
                "format_id": "__best__",
                "audio_preset": {"format": fmt, "bitrate": bitrate},
                "audio_format": fmt,
                "audio_bitrate": bitrate,
                "quality_label": f"{fmt.upper()} {bitrate} kbps" if fmt != "best" else "Original audio",
                "container": fmt,
                "has_audio": True,
            }
        else:
            quality = payload.get("quality")
            cap = 0
            if isinstance(quality, (int, float)) and quality:
                cap = int(quality)
            elif isinstance(quality, str) and quality.isdigit():
                cap = int(quality)
            else:
                default_quality = str(self.settings.get("default_video_quality") or "best")
                cap = int(default_quality) if default_quality.isdigit() else 0
            fields = {
                "media_kind": "video",
                "format_id": "__auto__",
                "quality_label": f"Up to {cap}p" if cap else "Best available",
                "container": "auto",
                "has_audio": False,
                "max_height": cap,
            }
        fields.update({"title": title, "site": "Browser", "thumbnail": ""})
        self.manager.add_job(url, **fields)
        self.tabs.setCurrentWidget(self.downloads)
        self._set_status(f"Queued \"{title}\".")
        if self.tray and self.settings.get("notify_on_finish"):
            self.tray.showMessage(
                APP_NAME, f"Added to downloads: {title[:80]}", QSystemTrayIcon.MessageIcon.Information, 3000
            )

    def _on_job_completed(self, job: dict) -> None:
        self._set_status(f"Finished: {job.get('title') or 'download'}")
        if self.tray and self.settings.get("notify_on_finish"):
            title = str(job.get("title") or "Download complete")
            self.tray.showMessage(
                "Download complete", title[:120], QSystemTrayIcon.MessageIcon.Information, 4000
            )

    # ------------------------------------------------------------------
    def _on_tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is self.library:
            self.library.refresh(self.library.search.text())

    def _on_settings_saved(self, patch: dict) -> None:
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, str(self.settings.get("theme") or "dark"))
        self.manager.pump()
        self._refresh_engine_status()
        self._refresh_server_status()
        if self.settings.get("server_port") and self.server.port != int(self.settings.get("server_port")):
            self._restart_server(int(self.settings.get("server_port")))
        self._set_status("Settings saved.")

    def _restart_server(self, port: int) -> None:
        self.settings.set("server_port", int(port))
        self.settings.save()
        ok, message = self.server.restart(int(port))
        self._refresh_server_status()
        self.settings_page.set_server_status(ok, message)
        if not ok:
            QMessageBox.warning(self, "Local API", message)
        else:
            self._set_status(message)

    # ------------------------------------------------------------------
    def _refresh_engine_status(self) -> None:
        self.engine_label.setText(f"yt-dlp {ytdlp_version()}")
        ffmpeg = find_ffmpeg(self.settings)
        if ffmpeg:
            self.ffmpeg_label.setText("FFmpeg ready")
            self.ffmpeg_label.setToolTip(ffmpeg)
            self.ffmpeg_label.setStyleSheet("color: #8b93a7;")
        else:
            self.ffmpeg_label.setText("FFmpeg missing")
            self.ffmpeg_label.setToolTip("Merging and audio conversion need FFmpeg.")
            self.ffmpeg_label.setStyleSheet("color: #ff5c72;")
        self._refresh_server_status()

    def _refresh_server_status(self) -> None:
        running = self.server.running
        if running:
            text = f"API :{self.server.port}"
            self.server_label.setText(text)
            self.server_label.setStyleSheet("color: #3ddc84;")
            self.api_pill.setText(f"Browser API :{self.server.port}")
            self.api_pill.setStyleSheet("color: #3ddc84;")
        else:
            self.server_label.setText("API off")
            self.server_label.setStyleSheet("color: #ff5c72;")
            self.api_pill.setText("Browser API off")
            self.api_pill.setStyleSheet("color: #8b93a7;")
        self.settings_page.set_server_status(running, f"Listening on 127.0.0.1:{self.server.port}" if running else "API stopped")

    def _refresh_tray_tooltip(self) -> None:
        if not self.tray:
            return
        active = sum(
            1
            for job in self.manager.jobs
            if job["status"] in ("downloading", "starting", "processing", "queued")
        )
        self.tray.setToolTip(f"{APP_NAME} - {active} active" if active else APP_NAME)

    def _set_status(self, text: str, timeout: int = 6000) -> None:
        self.status_label.setText(text)
        self.statusBar().showMessage(text, timeout)

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        if (
            self._allow_close
            or not self.settings.get("close_to_tray")
            or self.tray is None
        ):
            event.accept()
            QApplication.instance().quit()
            return
        event.ignore()
        self.hide()
        if self.tray and not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.showMessage(
                APP_NAME,
                "Still running in the tray. Right-click the icon to quit.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
