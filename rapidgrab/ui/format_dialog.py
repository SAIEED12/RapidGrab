"""Format picker and playlist selection dialogs."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..constants import AUDIO_PRESETS, VIDEO_QUALITY_CAPS, format_bytes, format_duration
from ..core.models import FormatOption, MediaInfo
from ..core.settings import Settings
from .theme import muted


class FormatDialog(QDialog):
    """Pick a video quality or an audio format for one media item."""

    def __init__(self, media: MediaInfo, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.media = media
        self.settings = settings
        self.result_fields: dict[str, Any] | None = None
        self._video_options: list[FormatOption | None] = [None, *media.video_formats]
        self._audio_rows: list[dict[str, Any]] = []

        self.setWindowTitle("Choose format")
        self.setMinimumWidth(660)
        self._build()
        self._populate()
        if not self.media.video_formats and self.media.audio_formats:
            self.tabs.setCurrentIndex(1)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        title = QLabel(self.media.title or "Untitled")
        title.setObjectName("H2")
        title.setWordWrap(True)
        root.addWidget(title)

        meta_bits = [self.media.site]
        if self.media.uploader:
            meta_bits.append(self.media.uploader)
        if self.media.duration:
            meta_bits.append(format_duration(self.media.duration))
        root.addWidget(muted("  -  ".join(bit for bit in meta_bits if bit)))

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_video_tab(), "Video")
        self.tabs.addTab(self._build_audio_tab(), "Audio")
        self.tabs.currentChanged.connect(self._sync_button)
        root.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        self.download_btn = QPushButton("Download video")
        self.download_btn.setObjectName("Primary")
        self.download_btn.setDefault(True)
        self.download_btn.clicked.connect(self._accept)
        row.addWidget(self.download_btn)
        root.addLayout(row)

        self._sync_button()

    def _build_video_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        self.video_table = QTableWidget(0, 3)
        self.video_table.setHorizontalHeaderLabels(["Quality", "Format", "Size"])
        self.video_table.verticalHeader().setVisible(False)
        self.video_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.video_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.video_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.video_table.setAlternatingRowColors(True)
        header = self.video_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.video_table.doubleClicked.connect(self._accept)
        layout.addWidget(self.video_table)
        if not self.media.video_formats:
            note = muted("This link only provides audio streams. Use the Audio tab.")
            note.setWordWrap(True)
            layout.addWidget(note)
        return page

    def _build_audio_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        self.audio_table = QTableWidget(0, 3)
        self.audio_table.setHorizontalHeaderLabels(["Format", "Type", "Size"])
        self.audio_table.verticalHeader().setVisible(False)
        self.audio_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.audio_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.audio_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.audio_table.setAlternatingRowColors(True)
        header = self.audio_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.audio_table.doubleClicked.connect(self._accept)
        layout.addWidget(self.audio_table)
        return page

    # ------------------------------------------------------------------
    def _populate(self) -> None:
        # Video: auto option first, then every resolution.
        rows: list[FormatOption | None] = [None, *self.media.video_formats]
        self.video_table.setRowCount(len(rows))
        for index, fmt in enumerate(rows):
            if fmt is None:
                label = "Best available"
                detail = "Video + best audio"
                size = "-"
            else:
                label = fmt.label
                detail = f"{fmt.ext.upper()} - {_codec(fmt)}"
                size = format_bytes(fmt.filesize) if fmt.filesize else "-"
            self._fill_row(self.video_table, index, label, detail, size)
        if self.video_table.rowCount():
            default_quality = str(self.settings.get("default_video_quality") or "best")
            selected = 0
            if default_quality.isdigit():
                for index, fmt in enumerate(self._video_options):
                    if fmt is not None and fmt.height == int(default_quality):
                        selected = index
                        break
            self.video_table.selectRow(selected)

        # Audio: original streams first, then conversion presets.
        self._audio_rows = []
        for fmt in self.media.audio_formats:
            self._audio_rows.append(
                {
                    "label": fmt.label,
                    "type": "Original",
                    "size": format_bytes(fmt.filesize) if fmt.filesize else "-",
                    "format_id": fmt.format_id,
                    "preset": {"format": "best", "bitrate": 0},
                    "ext": fmt.ext,
                    "kind": "audio",
                }
            )
        for fmt, bitrate, label in AUDIO_PRESETS:
            self._audio_rows.append(
                {
                    "label": label,
                    "type": "Convert" if fmt != "best" else "Original",
                    "size": "-",
                    "format_id": "__best__",
                    "preset": {"format": fmt, "bitrate": bitrate},
                    "ext": fmt if fmt != "best" else "",
                    "kind": "audio",
                }
            )
        self.audio_table.setRowCount(len(self._audio_rows))
        for index, row in enumerate(self._audio_rows):
            self._fill_row(
                self.audio_table, index, row["label"], row["type"], row["size"]
            )
        default_row = self._default_audio_row()
        if default_row is not None:
            self.audio_table.selectRow(default_row)
        elif self.audio_table.rowCount():
            self.audio_table.selectRow(0)

    def _default_audio_row(self) -> int | None:
        fmt = str(self.settings.get("default_audio_format") or "mp3")
        bitrate = int(self.settings.get("default_audio_bitrate") or 192)
        for index, row in enumerate(self._audio_rows):
            if row["preset"].get("format") == fmt and row["preset"].get("bitrate") == bitrate:
                return index
        return None

    @staticmethod
    def _fill_row(table: QTableWidget, row: int, *values: str) -> None:
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, column, item)

    def _sync_button(self) -> None:
        is_audio = self.tabs.currentIndex() == 1
        self.download_btn.setText("Download audio" if is_audio else "Download video")
        self.download_btn.setEnabled(
            bool(self._audio_rows) if is_audio else bool(self.media.video_formats)
        )

    # ------------------------------------------------------------------
    def _accept(self) -> None:
        if self.tabs.currentIndex() == 1:
            self._accept_audio()
        else:
            self._accept_video()

    def _accept_video(self) -> None:
        row = self.video_table.currentRow()
        options = self._video_options
        if row < 0 or row >= len(options):
            return
        fmt = options[row]
        if fmt is None:
            self.result_fields = {
                "media_kind": "video",
                "format_id": "__auto__",
                "quality_label": "Best available",
                "container": "auto",
                "has_audio": False,
                "max_height": 0,
            }
        else:
            self.result_fields = {
                "media_kind": "video",
                "format_id": fmt.format_id,
                "quality_label": fmt.label,
                "container": fmt.ext,
                "has_audio": fmt.has_audio,
                "max_height": fmt.height or 0,
            }
        self.accept()

    def _accept_audio(self) -> None:
        row = self.audio_table.currentRow()
        if row < 0 or row >= len(self._audio_rows):
            return
        data = self._audio_rows[row]
        preset = data.get("preset") or {}
        fmt = str(preset.get("format") or "best")
        bitrate = int(preset.get("bitrate") or 0)
        label = f"{fmt.upper()} {bitrate} kbps" if fmt != "best" and bitrate else data["label"]
        self.result_fields = {
            "media_kind": "audio",
            "format_id": data.get("format_id") or "__best__",
            "audio_preset": preset,
            "audio_format": fmt,
            "audio_bitrate": bitrate,
            "quality_label": label,
            "container": data.get("ext") or fmt,
            "has_audio": True,
            "max_height": 0,
        }
        self.accept()


class PlaylistDialog(QDialog):
    """Select which entries of a playlist/channel to queue."""

    def __init__(self, media: MediaInfo, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.media = media
        self.settings = settings
        self.result_jobs: list[tuple[str, dict[str, Any]]] = []
        self.setWindowTitle("Add playlist")
        self.resize(700, 560)
        self._build()
        self._populate()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        title = QLabel(self.media.title or "Playlist")
        title.setObjectName("H2")
        title.setWordWrap(True)
        root.addWidget(title)
        count = self.media.playlist_count or len(self.media.entries)
        root.addWidget(
            muted(
                f"{self.media.site} - {count} entries detected"
                + (f" (showing first {len(self.media.entries)})" if len(self.media.entries) < count else "")
            )
        )

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Download as"))
        self.mode = QComboBox()
        self.mode.addItem("Video - best quality", ("video", 0))
        for cap in VIDEO_QUALITY_CAPS[:5]:
            self.mode.addItem(f"Video - up to {cap}p", ("video", cap))
        self.mode.addItem("Audio - default format", ("audio", 0))
        controls.addWidget(self.mode, 1)
        self.select_all_btn = QPushButton("Select all")
        self.select_all_btn.setObjectName("Flat")
        self.select_all_btn.clicked.connect(lambda: self._set_all(True))
        controls.addWidget(self.select_all_btn)
        self.select_none_btn = QPushButton("Select none")
        self.select_none_btn.setObjectName("Flat")
        self.select_none_btn.clicked.connect(lambda: self._set_all(False))
        controls.addWidget(self.select_none_btn)
        root.addLayout(controls)

        self.list = QListWidget()
        self.list.itemChanged.connect(self._sync_count)
        root.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.count_label = muted("0 selected")
        row.addWidget(self.count_label)
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        self.add_btn = QPushButton("Add downloads")
        self.add_btn.setObjectName("Primary")
        self.add_btn.clicked.connect(self._accept)
        row.addWidget(self.add_btn)
        root.addLayout(row)

    def _populate(self) -> None:
        for entry in self.media.entries:
            item = QListWidgetItem(entry.label())
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setToolTip(entry.url)
            self.list.addItem(item)
        self._sync_count()

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in range(self.list.count()):
            self.list.item(index).setCheckState(state)

    def _sync_count(self) -> None:
        selected = len(self._selected_entries())
        self.count_label.setText(f"{selected} of {self.list.count()} selected")
        self.add_btn.setEnabled(selected > 0)

    def _selected_entries(self) -> list[Any]:
        entries = []
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                entries.append(self.media.entries[index])
        return entries

    def _accept(self) -> None:
        mode, cap = self.mode.currentData()
        fields: dict[str, Any]
        if mode == "audio":
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
                "max_height": 0,
            }
        else:
            fields = {
                "media_kind": "video",
                "format_id": "__auto__",
                "quality_label": f"Up to {cap}p" if cap else "Best available",
                "container": "auto",
                "has_audio": False,
                "max_height": int(cap or 0),
            }
        self.result_jobs = [
            (entry.url, {**fields, "title": entry.title, "site": self.media.site, "thumbnail": self.media.thumbnail or ""})
            for entry in self._selected_entries()
        ]
        self.accept()


def _codec(fmt: FormatOption) -> str:
    codec = (fmt.vcodec or "").split(".")[0] or "video"
    return codec.upper()
