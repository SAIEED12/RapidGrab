"""SQLite persistence for downloads and history."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ..constants import app_data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT DEFAULT '',
    site TEXT DEFAULT '',
    media_kind TEXT DEFAULT 'video',
    format_id TEXT DEFAULT '',
    quality_label TEXT DEFAULT '',
    container TEXT DEFAULT '',
    status TEXT DEFAULT 'queued',
    progress REAL DEFAULT 0,
    downloaded_bytes INTEGER DEFAULT 0,
    total_bytes INTEGER DEFAULT 0,
    speed REAL DEFAULT 0,
    eta INTEGER DEFAULT 0,
    filepath TEXT DEFAULT '',
    error TEXT DEFAULT '',
    thumbnail TEXT DEFAULT '',
    audio_format TEXT DEFAULT '',
    audio_bitrate INTEGER DEFAULT 0,
    has_audio INTEGER DEFAULT 0,
    max_height INTEGER DEFAULT 0,
    download_dir TEXT DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_completed ON jobs(completed_at);
"""

JOB_COLUMNS = [
    "id",
    "url",
    "title",
    "site",
    "media_kind",
    "format_id",
    "quality_label",
    "container",
    "status",
    "progress",
    "downloaded_bytes",
    "total_bytes",
    "speed",
    "eta",
    "filepath",
    "error",
    "thumbnail",
    "audio_format",
    "audio_bitrate",
    "has_audio",
    "max_height",
    "download_dir",
    "created_at",
    "updated_at",
    "completed_at",
]


class Store:
    """Thread-safe wrapper around one SQLite database."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_data_dir() / "rapidgrab.db")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def new_job(**fields: Any) -> dict[str, Any]:
        now = time.time()
        job = {col: (0 if col in _NUMERIC else "") for col in JOB_COLUMNS}
        job.update(
            {
                "id": uuid.uuid4().hex,
                "created_at": now,
                "updated_at": now,
                "status": "queued",
                "media_kind": "video",
            }
        )
        job.update(fields)
        job["updated_at"] = time.time()
        return job

    # ------------------------------------------------------------------
    def insert_job(self, job: dict[str, Any]) -> dict[str, Any]:
        values = [job.get(col) for col in JOB_COLUMNS]
        placeholders = ",".join("?" for _ in JOB_COLUMNS)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO jobs ({','.join(JOB_COLUMNS)}) VALUES ({placeholders})",
                values,
            )
            self._conn.commit()
        return job

    def update_job(self, job_id: str, patch: dict[str, Any]) -> None:
        patch = dict(patch)
        patch["updated_at"] = time.time()
        allowed = {k: v for k, v in patch.items() if k in JOB_COLUMNS}
        if not allowed:
            return
        assignments = ",".join(f"{key}=?" for key in allowed)
        with self._lock:
            self._conn.execute(
                f"UPDATE jobs SET {assignments} WHERE id=?",
                [*allowed.values(), job_id],
            )
            self._conn.commit()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_jobs(self, statuses: list[str] | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM jobs"
        params: list[Any] = []
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            query += f" WHERE status IN ({placeholders})"
            params.extend(statuses)
        query += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def list_history(self, search: str = "", limit: int = 1000) -> list[dict[str, Any]]:
        query = "SELECT * FROM jobs WHERE status='completed'"
        params: list[Any] = []
        if search:
            query += " AND (title LIKE ? OR site LIKE ? OR filepath LIKE ?)"
            token = f"%{search}%"
            params.extend([token, token, token])
        query += " ORDER BY completed_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def delete_job(self, job_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            self._conn.commit()

    def clear_completed(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM jobs WHERE status='completed'")
            self._conn.commit()

    def reset_unfinished(self) -> None:
        """Mark jobs interrupted by an app restart as paused."""
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET status='paused', speed=0, eta=0 "
                "WHERE status IN ('queued','starting','downloading','processing')"
            )
            self._conn.commit()


_NUMERIC = {
    "progress",
    "downloaded_bytes",
    "total_bytes",
    "speed",
    "eta",
    "audio_bitrate",
    "has_audio",
    "max_height",
    "created_at",
    "updated_at",
    "completed_at",
}
