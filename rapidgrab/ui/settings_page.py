"""Settings page."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..constants import AUDIO_BITRATES, AUDIO_FORMATS, VIDEO_QUALITY_CAPS
from ..core.engine import find_ffmpeg, find_js_runtimes, update_ytdlp, ytdlp_version
from ..core.settings import Settings
from .theme import muted


class _UpdateThread(QThread):
    done = Signal(bool, str)

    def run(self) -> None:
        ok, message = update_ytdlp()
        self.done.emit(ok, message)


class SettingsPage(QWidget):
    settingsSaved = Signal(dict)
    serverRestartRequested = Signal(int)

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._update_thread: _UpdateThread | None = None
        self._build()
        self._load()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(14)

        title = QLabel("Settings")
        title.setObjectName("H1")
        layout.addWidget(title)

        # -- downloads --------------------------------------------------
        downloads_box = QGroupBox("Downloads")
        form = QFormLayout(downloads_box)
        form.setContentsMargins(14, 18, 14, 12)
        form.setSpacing(10)

        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit()
        dir_row.addWidget(self.dir_edit, 1)
        browse_dir = QPushButton("Browse...")
        browse_dir.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse_dir)
        form.addRow("Download folder", dir_row)

        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 10)
        self.concurrency.setToolTip("How many downloads can run at the same time.")
        form.addRow("Simultaneous downloads", self.concurrency)

        self.video_quality = QComboBox()
        self.video_quality.addItem("Best available", "best")
        for cap in VIDEO_QUALITY_CAPS:
            label = "2160p (4K)" if cap == 2160 else ("1440p (2K)" if cap == 1440 else f"{cap}p")
            self.video_quality.addItem(label, str(cap))
        form.addRow("Default video quality", self.video_quality)

        audio_row = QHBoxLayout()
        self.audio_format = QComboBox()
        for fmt in AUDIO_FORMATS:
            self.audio_format.addItem(fmt.upper(), fmt)
        audio_row.addWidget(self.audio_format)
        self.audio_bitrate = QComboBox()
        for bitrate in AUDIO_BITRATES:
            self.audio_bitrate.addItem(f"{bitrate} kbps", bitrate)
        audio_row.addWidget(self.audio_bitrate)
        audio_row.addStretch(1)
        form.addRow("Default audio format", audio_row)

        self.thumbnail_check = QCheckBox("Save video thumbnail next to the download")
        form.addRow("", self.thumbnail_check)

        layout.addWidget(downloads_box)

        # -- behavior ---------------------------------------------------
        behavior_box = QGroupBox("Behavior")
        behavior = QFormLayout(behavior_box)
        behavior.setContentsMargins(14, 18, 14, 12)
        behavior.setSpacing(10)
        self.tray_check = QCheckBox("Keep Rapid Grab running in the system tray when closed")
        behavior.addRow("", self.tray_check)
        self.notify_check = QCheckBox("Show a notification when a download finishes")
        behavior.addRow("", self.notify_check)
        self.theme = QComboBox()
        self.theme.addItem("Dark", "dark")
        self.theme.addItem("Light", "light")
        behavior.addRow("Theme", self.theme)
        layout.addWidget(behavior_box)

        # -- sign-in cookies --------------------------------------------
        signin_box = QGroupBox("Sign-in cookies")
        signin = QFormLayout(signin_box)
        signin.setContentsMargins(14, 18, 14, 12)
        signin.setSpacing(10)
        self.cookie_browser = QComboBox()
        for label, value in [
            ("None", ""),
            ("Chrome", "chrome"),
            ("Edge", "edge"),
            ("Firefox", "firefox"),
            ("Brave", "brave"),
            ("Opera", "opera"),
            ("Vivaldi", "vivaldi"),
            ("Chromium", "chromium"),
        ]:
            self.cookie_browser.addItem(label, value)
        signin.addRow("Read cookies from", self.cookie_browser)

        cookie_row = QHBoxLayout()
        self.cookie_file_edit = QLineEdit()
        self.cookie_file_edit.setPlaceholderText("Optional Netscape cookies.txt")
        cookie_row.addWidget(self.cookie_file_edit, 1)
        cookie_browse = QPushButton("Browse...")
        cookie_browse.clicked.connect(self._browse_cookies)
        cookie_row.addWidget(cookie_browse)
        cookie_clear = QPushButton("Clear")
        cookie_clear.clicked.connect(lambda: self.cookie_file_edit.setText(""))
        cookie_row.addWidget(cookie_clear)
        signin.addRow("Cookies file", cookie_row)

        cookie_hint = muted(
            "Sites such as YouTube sometimes require a signed-in browser session "
            "('Sign in to confirm you're not a bot'). Pick your browser here, or "
            "export a cookies.txt file. Close Chrome/Edge completely before reading "
            "their cookies."
        )
        cookie_hint.setWordWrap(True)
        signin.addRow("", cookie_hint)
        layout.addWidget(signin_box)

        # -- browser integration ----------------------------------------
        browser_box = QGroupBox("Browser integration")
        browser = QFormLayout(browser_box)
        browser.setContentsMargins(14, 18, 14, 12)
        browser.setSpacing(10)

        port_row = QHBoxLayout()
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        port_row.addWidget(self.port)
        restart_btn = QPushButton("Restart API")
        restart_btn.clicked.connect(lambda: self.serverRestartRequested.emit(self.port.value()))
        port_row.addWidget(restart_btn)
        port_row.addStretch(1)
        browser.addRow("Local API port", port_row)

        token_row = QHBoxLayout()
        self.token = QLineEdit()
        self.token.setReadOnly(True)
        self.token.setCursorPosition(0)
        token_row.addWidget(self.token, 1)
        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self._copy_token)
        token_row.addWidget(copy_btn)
        browser.addRow("Pairing token", token_row)

        self.server_status = muted("API stopped")
        browser.addRow("Status", self.server_status)

        extension_row = QHBoxLayout()
        self.extension_path = _extension_dir()
        open_ext = QPushButton("Open extension folder")
        open_ext.clicked.connect(self._open_extension_folder)
        extension_row.addWidget(open_ext)
        extension_row.addStretch(1)
        browser.addRow("Extension", extension_row)

        help_label = muted(
            "Load the extension once: open chrome://extensions, enable Developer mode, "
            "click 'Load unpacked' and pick the extension folder. Then open the Rapid Grab "
            "toolbar popup, enter the port and token shown here, and press Test connection."
        )
        help_label.setWordWrap(True)
        browser.addRow("", help_label)
        layout.addWidget(browser_box)

        # -- tools ------------------------------------------------------
        tools_box = QGroupBox("Tools")
        tools = QFormLayout(tools_box)
        tools.setContentsMargins(14, 18, 14, 12)
        tools.setSpacing(10)

        ffmpeg_row = QHBoxLayout()
        self.ffmpeg_edit = QLineEdit()
        self.ffmpeg_edit.setPlaceholderText("Auto-detect (leave empty)")
        ffmpeg_row.addWidget(self.ffmpeg_edit, 1)
        ffmpeg_browse = QPushButton("Browse...")
        ffmpeg_browse.clicked.connect(self._browse_ffmpeg)
        ffmpeg_row.addWidget(ffmpeg_browse)
        ffmpeg_detect = QPushButton("Detect")
        ffmpeg_detect.clicked.connect(self._detect_ffmpeg)
        ffmpeg_row.addWidget(ffmpeg_detect)
        tools.addRow("FFmpeg", ffmpeg_row)
        self.ffmpeg_status = muted("")
        self.ffmpeg_status.setWordWrap(True)
        tools.addRow("", self.ffmpeg_status)

        js_row = QHBoxLayout()
        self.js_runtime = QComboBox()
        for label, value in [
            ("Auto-detect", "auto"),
            ("Deno", "deno"),
            ("Node.js", "node"),
            ("Bun", "bun"),
            ("QuickJS", "quickjs"),
        ]:
            self.js_runtime.addItem(label, value)
        self.js_runtime.setMinimumWidth(130)
        js_row.addWidget(self.js_runtime)
        self.js_path_edit = QLineEdit()
        self.js_path_edit.setPlaceholderText("Optional runtime executable path")
        js_row.addWidget(self.js_path_edit, 1)
        js_browse = QPushButton("Browse...")
        js_browse.clicked.connect(self._browse_js_runtime)
        js_row.addWidget(js_browse)
        tools.addRow("JavaScript runtime", js_row)
        self.js_status = muted("")
        self.js_status.setWordWrap(True)
        tools.addRow("", self.js_status)

        ytdlp_row = QHBoxLayout()
        self.ytdlp_label = QLabel(f"yt-dlp {ytdlp_version()}")
        ytdlp_row.addWidget(self.ytdlp_label)
        ytdlp_row.addStretch(1)
        self.update_btn = QPushButton("Check for updates")
        self.update_btn.clicked.connect(self._update_ytdlp)
        ytdlp_row.addWidget(self.update_btn)
        tools.addRow("Engine", ytdlp_row)
        self.update_status = muted("")
        self.update_status.setWordWrap(True)
        tools.addRow("", self.update_status)
        layout.addWidget(tools_box)

        layout.addStretch(1)

        footer = QHBoxLayout()
        self.saved_label = muted("")
        footer.addWidget(self.saved_label)
        footer.addStretch(1)
        save_btn = QPushButton("Save settings")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self._save)
        footer.addWidget(save_btn)
        layout.addLayout(footer)

        scroll.setWidget(content)
        root.addWidget(scroll)

    # ------------------------------------------------------------------
    def _load(self) -> None:
        s = self.settings
        self.dir_edit.setText(str(s.get("download_dir") or ""))
        self.concurrency.setValue(int(s.get("max_concurrent") or 3))
        quality = str(s.get("default_video_quality") or "best")
        index = self.video_quality.findData(quality)
        self.video_quality.setCurrentIndex(max(0, index))
        index = self.audio_format.findData(str(s.get("default_audio_format") or "mp3"))
        self.audio_format.setCurrentIndex(max(0, index))
        index = self.audio_bitrate.findData(int(s.get("default_audio_bitrate") or 192))
        self.audio_bitrate.setCurrentIndex(max(0, index))
        self.thumbnail_check.setChecked(bool(s.get("write_thumbnail")))
        self.tray_check.setChecked(bool(s.get("close_to_tray")))
        self.notify_check.setChecked(bool(s.get("notify_on_finish")))
        index = self.theme.findData(str(s.get("theme") or "dark"))
        self.theme.setCurrentIndex(max(0, index))
        browser = str(s.get("cookies_from_browser") or "")
        index = self.cookie_browser.findData(browser)
        self.cookie_browser.setCurrentIndex(max(0, index))
        self.cookie_file_edit.setText(str(s.get("cookies_file") or ""))
        self.port.setValue(int(s.get("server_port") or 47653))
        self.token.setText(s.server_token)
        ffmpeg = str(s.get("ffmpeg_path") or "")
        self.ffmpeg_edit.setText(ffmpeg)
        self._refresh_ffmpeg_status()
        index = self.js_runtime.findData(str(s.get("js_runtime") or "auto"))
        self.js_runtime.setCurrentIndex(max(0, index))
        self.js_path_edit.setText(str(s.get("js_runtime_path") or ""))
        self._refresh_js_status()

    # ------------------------------------------------------------------
    def _browse_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose download folder", self.dir_edit.text())
        if folder:
            self.dir_edit.setText(folder)

    def _browse_ffmpeg(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self, "Locate ffmpeg", "", "Executables (*.exe);;All files (*)"
        )
        if file:
            self.ffmpeg_edit.setText(file)
            self._refresh_ffmpeg_status()

    def _browse_cookies(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self, "Choose cookies file", "", "Cookies (*.txt);;All files (*)"
        )
        if file:
            self.cookie_file_edit.setText(file)

    def _detect_ffmpeg(self) -> None:
        self.settings.set("ffmpeg_path", self.ffmpeg_edit.text().strip())
        found = find_ffmpeg(self.settings)
        if found:
            self.ffmpeg_edit.setText(found)
            self.ffmpeg_status.setText(f"Found: {found}")
        else:
            self.ffmpeg_status.setText(
                "No FFmpeg found. Install it, then use Browse or Detect."
            )

    def _refresh_ffmpeg_status(self) -> None:
        found = find_ffmpeg(self.settings)
        if found:
            self.ffmpeg_status.setText(f"Found: {found}")
        else:
            self.ffmpeg_status.setText("Not found - merging and audio conversion will not work.")

    def _browse_js_runtime(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self, "Locate JavaScript runtime", "", "Executables (*.exe);;All files (*)"
        )
        if not file:
            return
        self.js_path_edit.setText(file)
        stem = Path(file).stem.lower()
        for name in ("deno", "node", "bun", "qjs", "quickjs"):
            if stem.startswith(name):
                value = "quickjs" if name in ("qjs", "quickjs") else name
                index = self.js_runtime.findData(value)
                if index >= 0:
                    self.js_runtime.setCurrentIndex(index)
                break
        self.settings.set("js_runtime", str(self.js_runtime.currentData()))
        self.settings.set("js_runtime_path", file)
        self._refresh_js_status()

    def _refresh_js_status(self) -> None:
        found = find_js_runtimes(self.settings)
        if found:
            details = ", ".join(f"{name} ({path})" for name, path in found.items())
            self.js_status.setText(f"Found: {details}")
        else:
            self.js_status.setText(
                "No JavaScript runtime found. YouTube may offer fewer formats - install "
                "Deno (deno.com) or Node.js, or browse to the executable above."
            )

    def _copy_token(self) -> None:
        QApplication.clipboard().setText(self.token.text())
        self.saved_label.setText("Token copied to clipboard")
        QTimer.singleShot(2200, lambda: self.saved_label.setText(""))

    def _open_extension_folder(self) -> None:
        if self.extension_path and Path(self.extension_path).is_dir():
            os.startfile(str(self.extension_path))  # type: ignore[attr-defined]
        else:
            QMessageBox.information(
                self,
                "Extension folder",
                "The extension folder was not found next to the application.",
            )

    # ------------------------------------------------------------------
    def _save(self) -> None:
        folder = self.dir_edit.text().strip()
        if folder:
            try:
                Path(folder).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.warning(self, "Invalid folder", str(exc))
                return
        patch: dict[str, Any] = {
            "download_dir": folder,
            "max_concurrent": int(self.concurrency.value()),
            "default_video_quality": str(self.video_quality.currentData()),
            "default_audio_format": str(self.audio_format.currentData()),
            "default_audio_bitrate": int(self.audio_bitrate.currentData()),
            "write_thumbnail": self.thumbnail_check.isChecked(),
            "close_to_tray": self.tray_check.isChecked(),
            "notify_on_finish": self.notify_check.isChecked(),
            "theme": str(self.theme.currentData()),
            "server_port": int(self.port.value()),
            "ffmpeg_path": self.ffmpeg_edit.text().strip(),
            "js_runtime": str(self.js_runtime.currentData()),
            "js_runtime_path": self.js_path_edit.text().strip(),
            "cookies_from_browser": str(self.cookie_browser.currentData()),
            "cookies_file": self.cookie_file_edit.text().strip(),
        }
        self.settings.update(patch)
        self.settings.save()
        self._refresh_ffmpeg_status()
        self._refresh_js_status()
        self.settingsSaved.emit(patch)
        self.saved_label.setText("Settings saved")
        QTimer.singleShot(2200, lambda: self.saved_label.setText(""))

    # ------------------------------------------------------------------
    def _update_ytdlp(self) -> None:
        if self._update_thread and self._update_thread.isRunning():
            return
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Updating...")
        self.update_status.setText("Downloading the latest yt-dlp...")
        thread = _UpdateThread(self)
        thread.done.connect(self._on_update_done)
        thread.finished.connect(thread.deleteLater)
        self._update_thread = thread
        thread.start()

    def _on_update_done(self, ok: bool, message: str) -> None:
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Check for updates")
        self.update_status.setText(message)
        self.ytdlp_label.setText(f"yt-dlp {ytdlp_version()}")
        if not ok:
            QMessageBox.warning(self, "yt-dlp update", message)

    # ------------------------------------------------------------------
    def set_server_status(self, running: bool, text: str) -> None:
        self.server_status.setText(text)
        self.server_status.setStyleSheet("color: #3ddc84;" if running else "color: #ff5c72;")


def _extension_dir() -> Path | None:
    if getattr(sys, "frozen", False):
        bundled = Path(sys._MEIPASS) / "extension"  # type: ignore[attr-defined]
        return bundled if bundled.is_dir() else None
    root = Path(__file__).resolve().parents[2]
    candidate = root / "extension"
    return candidate if candidate.is_dir() else None
