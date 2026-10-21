"""Downloads list page."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..constants import format_bytes
from ..core.queue import DownloadManager
from .theme import muted


def _speed_text(speed: float | None) -> str:
    if not speed:
        return ""
    return f"{format_bytes(speed)}/s"


def _eta_text(eta: int | None) -> str:
    if eta is None or eta <= 0:
        return ""
    minutes, seconds = divmod(int(eta), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}:{seconds:02d}"


class DownloadItem(QFrame):
    """One row in the download queue."""

    def __init__(self, job: dict[str, Any], manager: DownloadManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.job_id = job["id"]
        self.manager = manager
        self._build()
        self.update_job(job)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 13, 16, 13)
        outer.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        top.addWidget(self.title_label, 1)
        self.status_label = QLabel()
        self.status_label.setObjectName("Muted")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.status_label, 0)
        outer.addLayout(top)

        self.meta_label = muted("")
        self.meta_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        outer.addWidget(self.meta_label)

        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        bottom.addWidget(self.progress, 1)

        self.pause_btn = self._button("Pause", self.manager.pause)
        self.resume_btn = self._button("Resume", self.manager.resume)
        self.retry_btn = self._button("Retry", self.manager.retry)
        self.open_btn = self._button("Open", self._open_file)
        self.folder_btn = self._button("Folder", self._open_folder)
        self.cancel_btn = self._button("Cancel", self.manager.cancel, danger=True)
        self.remove_btn = self._button("Remove", self.manager.dismiss)
        for button in (
            self.pause_btn,
            self.resume_btn,
            self.retry_btn,
            self.open_btn,
            self.folder_btn,
            self.cancel_btn,
            self.remove_btn,
        ):
            bottom.addWidget(button, 0)
        outer.addLayout(bottom)

    def _button(self, text: str, action, danger: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("Danger" if danger else "Flat")
        button.clicked.connect(lambda: action(self.job_id))
        return button

    # ------------------------------------------------------------------
    def _open_file(self, job_id: str | None = None) -> None:
        job = self.manager.get(job_id or self.job_id) or {}
        path = Path(job.get("filepath") or "")
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_folder(self, job_id: str | None = None) -> None:
        self.manager.open_folder(job_id or self.job_id)

    # ------------------------------------------------------------------
    def update_job(self, job: dict[str, Any]) -> None:
        status = str(job.get("status") or "queued")
        title = str(job.get("title") or job.get("url") or "Untitled")
        self.title_label.setText(title)
        self.title_label.setToolTip(title)

        meta_bits = [str(job.get("site") or "Web")]
        if job.get("quality_label"):
            meta_bits.append(str(job["quality_label"]))
        if job.get("total_bytes"):
            meta_bits.append(format_bytes(job.get("total_bytes")))
        if status == "completed" and job.get("filepath"):
            meta_bits.append(Path(str(job["filepath"])).name)
        self.meta_label.setText("  -  ".join(meta_bits))
        self.meta_label.setToolTip(str(job.get("filepath") or ""))
        self.meta_label.setStyleSheet("")

        progress = float(job.get("progress") or 0.0)
        self.progress.setValue(int(max(0.0, min(1.0, progress)) * 1000))
        self.progress.setVisible(status not in ("error", "canceled"))

        if status == "downloading":
            speed = _speed_text(job.get("speed"))
            eta = _eta_text(job.get("eta"))
            pieces = [f"{progress * 100:.1f}%"]
            if speed:
                pieces.append(speed)
            if eta:
                pieces.append(f"ETA {eta}")
            self.status_label.setText("  -  ".join(pieces))
        elif status == "processing":
            self.status_label.setText("Processing...")
        elif status == "starting":
            self.status_label.setText("Starting...")
        elif status == "queued":
            self.status_label.setText("Queued")
        elif status == "pausing":
            self.status_label.setText("Pausing...")
        elif status == "canceling":
            self.status_label.setText("Canceling...")
        elif status == "paused":
            self.status_label.setText(f"Paused at {progress * 100:.0f}%")
        elif status == "completed":
            self.status_label.setText("Completed")
        elif status == "canceled":
            self.status_label.setText("Canceled")
            self.progress.setValue(0)
        elif status == "error":
            self.status_label.setText("Failed")
            self.meta_label.setText(str(job.get("error") or "Download failed"))
            self.meta_label.setStyleSheet("color: #ff5c72;")
            self.meta_label.setToolTip(str(job.get("error") or ""))
        else:
            self.status_label.setText(status.title())

        active = status in ("downloading", "processing", "starting", "pausing", "canceling")
        error = status in ("error", "canceled")
        completed = status == "completed"
        paused = status == "paused"

        self.pause_btn.setVisible(status in ("downloading", "queued"))
        self.resume_btn.setVisible(paused)
        self.retry_btn.setVisible(error)
        self.cancel_btn.setVisible(status in ("downloading", "queued", "starting", "pausing", "paused"))
        self.open_btn.setVisible(completed)
        self.folder_btn.setVisible(completed)
        self.remove_btn.setVisible(completed or error or paused)
        self.pause_btn.setEnabled(status in ("downloading", "queued"))


class DownloadsPage(QWidget):
    def __init__(self, manager: DownloadManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.items: dict[str, DownloadItem] = {}
        self._build()
        self._connect()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Downloads")
        title.setObjectName("H1")
        header.addWidget(title)
        self.count_label = muted("")
        header.addWidget(self.count_label)
        header.addStretch(1)
        self.clear_btn = QPushButton("Clear completed")
        self.clear_btn.setObjectName("Flat")
        self.clear_btn.clicked.connect(self.manager.clear_completed)
        header.addWidget(self.clear_btn)
        root.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 6, 0)
        self.list_layout.setSpacing(10)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        self.empty_label = muted(
            "No downloads yet.\nPaste a video link above and press Analyze to get started."
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("font-size: 14px; padding: 40px;")
        root.addWidget(self.empty_label, 1)

    def _connect(self) -> None:
        self.manager.jobAdded.connect(self.add_job)
        self.manager.jobUpdated.connect(self.update_job)
        self.manager.jobRemoved.connect(self.remove_job)
        self.manager.jobsChanged.connect(self.refresh_counts)

    # ------------------------------------------------------------------
    def load_jobs(self, jobs: list[dict[str, Any]]) -> None:
        for job in reversed(jobs):  # oldest at the bottom
            self.add_job(job)
        self.refresh_counts()

    def add_job(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        if job_id in self.items:
            return
        item = DownloadItem(job, self.manager, self.container)
        self.items[job_id] = item
        self.list_layout.insertWidget(0, item)
        self._update_empty_state()

    def update_job(self, job_id: str, patch: dict[str, Any] | None = None) -> None:
        item = self.items.get(job_id)
        job = self.manager.get(job_id)
        if item and job:
            item.update_job(job)
        self.refresh_counts()

    def remove_job(self, job_id: str) -> None:
        item = self.items.pop(job_id, None)
        if item is not None:
            self.list_layout.removeWidget(item)
            item.deleteLater()
        self._update_empty_state()
        self.refresh_counts()

    def refresh_counts(self) -> None:
        jobs = self.manager.jobs
        active = sum(1 for j in jobs if j["status"] in ("downloading", "starting", "processing"))
        queued = sum(1 for j in jobs if j["status"] == "queued")
        if not jobs:
            self.count_label.setText("")
        else:
            self.count_label.setText(f"{active} active  -  {queued} queued")
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        has_items = bool(self.items)
        self.scroll.setVisible(has_items)
        self.empty_label.setVisible(not has_items)
