"""Download history / library page."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..constants import format_bytes
from ..core.db import Store
from ..core.queue import DownloadManager
from .theme import muted


class LibraryPage(QWidget):
    """Searchable list of completed downloads."""

    COLUMNS = ["Title", "Type", "Quality", "Site", "Size", "Finished", "Folder"]

    def __init__(self, store: Store, manager: DownloadManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.manager = manager
        self._build()
        self.manager.jobCompleted.connect(lambda _job: self.refresh(self.search.text()))
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Library")
        title.setObjectName("H1")
        header.addWidget(title)
        self.count_label = muted("")
        header.addWidget(self.count_label)
        header.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("Flat")
        refresh_btn.clicked.connect(lambda: self.refresh(self.search.text()))
        header.addWidget(refresh_btn)
        root.addLayout(header)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by title, site or file name...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search, 1)
        self.open_btn = QPushButton("Open file")
        self.open_btn.clicked.connect(self.open_selected)
        toolbar.addWidget(self.open_btn)
        self.folder_btn = QPushButton("Open folder")
        self.folder_btn.clicked.connect(self.open_selected_folder)
        toolbar.addWidget(self.folder_btn)
        self.delete_btn = QPushButton("Delete file")
        self.delete_btn.setObjectName("Danger")
        self.delete_btn.clicked.connect(self.delete_selected_file)
        toolbar.addWidget(self.delete_btn)
        self.forget_btn = QPushButton("Remove record")
        self.forget_btn.setObjectName("Flat")
        self.forget_btn.clicked.connect(self.remove_selected_record)
        toolbar.addWidget(self.forget_btn)
        root.addLayout(toolbar)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemDoubleClicked.connect(lambda _item: self.open_selected())
        self.table.itemSelectionChanged.connect(self._sync_buttons)
        root.addWidget(self.table, 1)

        self.empty_label = muted("Nothing here yet. Completed downloads will appear in this list.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_label)
        self._sync_buttons()

    # ------------------------------------------------------------------
    def _on_search_changed(self, text: str) -> None:
        self.refresh(text)

    def refresh(self, search: str | None = None) -> None:
        if search is None:
            search = self.search.text()
        jobs = self.store.list_history(search or "")
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            title = str(job.get("title") or Path(str(job.get("filepath") or "")).name or "Untitled")
            values = [
                title,
                "Audio" if job.get("media_kind") == "audio" else "Video",
                str(job.get("quality_label") or ""),
                str(job.get("site") or ""),
                format_bytes(job.get("total_bytes") or job.get("downloaded_bytes")),
                _format_time(job.get("completed_at")),
                str(Path(str(job.get("filepath") or "")).parent),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, job["id"])
                    item.setToolTip(str(job.get("filepath") or ""))
                if column == 6:
                    item.setToolTip(value)
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(6, header.ResizeMode.Stretch)
        self.table.resizeColumnsToContents()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(6, header.ResizeMode.Stretch)

        self.count_label.setText(f"{len(jobs)} item{'s' if len(jobs) != 1 else ''}")
        self.empty_label.setVisible(not jobs)
        self.table.setVisible(bool(jobs))
        self._sync_buttons()

    # ------------------------------------------------------------------
    def _selected_job(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        job_id = item.data(Qt.ItemDataRole.UserRole)
        return self.store.get_job(str(job_id))

    def _sync_buttons(self) -> None:
        has_selection = self._selected_job() is not None
        for button in (self.open_btn, self.folder_btn, self.delete_btn, self.forget_btn):
            button.setEnabled(has_selection)

    def open_selected(self) -> None:
        job = self._selected_job()
        if not job:
            return
        path = Path(str(job.get("filepath") or ""))
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.warning(self, "File missing", "The downloaded file is no longer at that location.")

    def open_selected_folder(self) -> None:
        job = self._selected_job()
        if not job:
            return
        folder = Path(str(job.get("filepath") or "")).parent
        if folder.exists():
            os.startfile(str(folder))  # type: ignore[attr-defined]

    def delete_selected_file(self) -> None:
        job = self._selected_job()
        if not job:
            return
        path = Path(str(job.get("filepath") or ""))
        answer = QMessageBox.question(
            self,
            "Delete file",
            f"Delete this file from disk?\n\n{path}\n\nThis cannot be undone.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            QMessageBox.warning(self, "Could not delete", str(exc))
            return
        self.remove_selected_record()

    def remove_selected_record(self) -> None:
        job = self._selected_job()
        if not job:
            return
        job_id = str(job["id"])
        if self.manager.get(job_id):
            self.manager.remove(job_id)
        else:
            self.store.delete_job(job_id)
        self.refresh(self.search.text())


def _format_time(timestamp: float | None) -> str:
    if not timestamp:
        return ""
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return ""
