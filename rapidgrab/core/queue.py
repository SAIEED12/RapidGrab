"""Download queue: worker threads, cancellation, persistence."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from .db import Store
from .engine import DownloadCancelled, Engine
from .settings import Settings

log = logging.getLogger(__name__)


class DownloadWorker(QThread):
    """Runs one yt-dlp download and reports its progress."""

    progressed = Signal(str, dict)
    succeeded = Signal(str, str, float)
    cancelled = Signal(str)
    failed = Signal(str, str)

    def __init__(self, engine: Engine, job: dict[str, Any], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.job = dict(job)
        self.job_id = str(job["id"])
        self.stop_event = threading.Event()

    def request_stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            path = self.engine.download(
                self.job,
                lambda patch: self.progressed.emit(self.job_id, patch),
                self.stop_event,
            )
            size = 0.0
            try:
                size = Path(path).stat().st_size
            except OSError:
                pass
            self.succeeded.emit(self.job_id, path, size)
        except DownloadCancelled:
            self.cancelled.emit(self.job_id)
        except Exception as exc:  # EngineError or unexpected
            log.warning("Download failed for %s: %s", self.job_id, exc)
            self.failed.emit(self.job_id, str(exc))


class DownloadManager(QObject):
    """Owns queue state and schedules worker threads."""

    jobAdded = Signal(dict)
    jobUpdated = Signal(str, dict)
    jobRemoved = Signal(str)
    jobsChanged = Signal()
    jobCompleted = Signal(dict)

    def __init__(self, engine: Engine, store: Store, settings: Settings) -> None:
        super().__init__()
        self.engine = engine
        self.store = store
        self.settings = settings
        self._jobs: dict[str, dict[str, Any]] = {}
        self._workers: dict[str, DownloadWorker] = {}
        self._intents: dict[str, str] = {}
        self._last_db_write: dict[str, float] = {}
        self._shutting_down = False
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        self.store.reset_unfinished()
        for job in self.store.list_jobs():
            if job["status"] in ("queued", "starting", "downloading", "processing", "paused", "error"):
                # Completed jobs are history; they are loaded from the DB by
                # the library page instead of cluttering the download list.
                job["status"] = "paused" if job["status"] in (
                    "starting",
                    "downloading",
                    "processing",
                ) else job["status"]
                self._jobs[job["id"]] = job

    # ------------------------------------------------------------------
    @property
    def jobs(self) -> list[dict[str, Any]]:
        return sorted(self._jobs.values(), key=lambda j: j.get("created_at") or 0, reverse=True)

    def active_count(self) -> int:
        return len(self._workers)

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self._jobs.get(job_id)

    # ------------------------------------------------------------------
    def add_job(self, url: str, **fields: Any) -> dict[str, Any]:
        fields.setdefault("download_dir", str(self.settings.download_dir))
        job = self.store.new_job(url=url, **fields)
        self.store.insert_job(job)
        self._jobs[job["id"]] = job
        self.jobAdded.emit(job)
        self.jobsChanged.emit()
        self._pump()
        return job

    def add_jobs(self, urls_and_fields: list[tuple[str, dict[str, Any]]]) -> int:
        count = 0
        for url, fields in urls_and_fields:
            fields.setdefault("download_dir", str(self.settings.download_dir))
            job = self.store.new_job(url=url, **fields)
            self.store.insert_job(job)
            self._jobs[job["id"]] = job
            self.jobAdded.emit(job)
            count += 1
        if count:
            self.jobsChanged.emit()
            self._pump()
        return count

    # ------------------------------------------------------------------
    def pump(self) -> None:
        """Public hook so settings changes can start queued work immediately."""
        self._pump()

    def _pump(self) -> None:
        if self._shutting_down:
            return
        limit = max(1, int(self.settings.get("max_concurrent") or 1))
        if len(self._workers) >= limit:
            return
        queued = [j for j in self._jobs.values() if j["status"] == "queued"]
        queued.sort(key=lambda j: j.get("created_at") or 0)
        for job in queued:
            if len(self._workers) >= limit:
                break
            self._start(job)

    def _start(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        if job_id in self._workers:
            return
        patch = {"status": "starting", "error": "", "speed": 0, "eta": 0}
        self._apply(job_id, patch)
        worker = DownloadWorker(self.engine, job, self)
        worker.progressed.connect(self._on_progress)
        worker.succeeded.connect(self._on_success)
        worker.cancelled.connect(self._on_cancelled)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(worker.deleteLater)
        self._workers[job_id] = worker
        worker.start()

    # ------------------------------------------------------------------
    def _apply(self, job_id: str, patch: dict[str, Any], persist: bool = True) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        job.update(patch)
        if persist:
            self.store.update_job(job_id, patch)
        self.jobUpdated.emit(job_id, patch)

    # -- worker callbacks ----------------------------------------------
    def _on_progress(self, job_id: str, patch: dict[str, Any]) -> None:
        if job_id not in self._jobs:
            return
        now = time.time()
        last = self._last_db_write.get(job_id, 0.0)
        persist = now - last > 1.0 or patch.get("status") in ("processing",)
        if persist:
            self._last_db_write[job_id] = now
        self._apply(job_id, patch, persist=persist)

    def _release_worker(self, job_id: str) -> None:
        self._workers.pop(job_id, None)
        self._intents.pop(job_id, None)
        self._last_db_write.pop(job_id, None)

    def _on_success(self, job_id: str, filepath: str, filesize: float) -> None:
        self._release_worker(job_id)
        self._apply(
            job_id,
            {
                "status": "completed",
                "progress": 1.0,
                "filepath": filepath,
                "total_bytes": int(filesize or 0),
                "downloaded_bytes": int(filesize or 0),
                "speed": 0,
                "eta": 0,
                "completed_at": time.time(),
                "error": "",
            },
        )
        self.jobsChanged.emit()
        job = self._jobs.get(job_id)
        if job:
            self.jobCompleted.emit(job)
        self._pump()

    def _on_cancelled(self, job_id: str) -> None:
        intent = self._intents.get(job_id, "pause")
        self._release_worker(job_id)
        if intent == "cancel":
            self._apply(job_id, {"status": "canceled", "speed": 0, "eta": 0})
        else:
            self._apply(job_id, {"status": "paused", "speed": 0, "eta": 0})
        self.jobsChanged.emit()
        self._pump()

    def _on_failed(self, job_id: str, error: str) -> None:
        self._release_worker(job_id)
        self._apply(
            job_id,
            {"status": "error", "error": error, "speed": 0, "eta": 0},
        )
        self.jobsChanged.emit()
        self._pump()

    # -- user actions ---------------------------------------------------
    def pause(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        if job_id in self._workers:
            self._intents[job_id] = "pause"
            self._workers[job_id].request_stop()
            self._apply(job_id, {"status": "pausing"}, persist=False)
        elif job["status"] == "queued":
            self._apply(job_id, {"status": "paused"})

    def resume(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        if job_id in self._workers:
            return
        self._apply(job_id, {"status": "queued", "error": "", "speed": 0, "eta": 0})
        self._pump()

    def cancel(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        if job_id in self._workers:
            self._intents[job_id] = "cancel"
            self._workers[job_id].request_stop()
            self._apply(job_id, {"status": "canceling"}, persist=False)
        else:
            self._apply(job_id, {"status": "canceled", "speed": 0, "eta": 0})
            self.jobsChanged.emit()

    def retry(self, job_id: str) -> None:
        self.resume(job_id)

    def remove(self, job_id: str) -> None:
        """Delete a job record entirely (download + history)."""
        if job_id in self._workers:
            return
        self._jobs.pop(job_id, None)
        self.store.delete_job(job_id)
        self.jobRemoved.emit(job_id)
        self.jobsChanged.emit()

    def dismiss(self, job_id: str) -> None:
        """Hide a finished item from the download list, keeping its history."""
        if job_id in self._workers:
            return
        job = self._jobs.pop(job_id, None)
        if job and job.get("status") not in ("completed",):
            self.store.delete_job(job_id)
        self.jobRemoved.emit(job_id)
        self.jobsChanged.emit()

    def clear_completed(self) -> None:
        """Remove finished items from the download list (history is kept)."""
        for job_id, job in list(self._jobs.items()):
            if job["status"] in ("completed", "canceled") and job_id not in self._workers:
                self._jobs.pop(job_id, None)
                self.jobRemoved.emit(job_id)
        self.jobsChanged.emit()

    def open_folder(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            job = self.store.get_job(job_id)
        if not job:
            return
        path = Path(job.get("filepath") or job.get("download_dir") or "")
        folder = path.parent if path.suffix else path
        if folder.exists():
            import os

            os.startfile(str(folder))  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        self._shutting_down = True
        for job_id, worker in list(self._workers.items()):
            self._intents[job_id] = "pause"
            worker.request_stop()
        for worker in list(self._workers.values()):
            if not worker.wait(4000):
                worker.terminate()
                worker.wait(1000)
        self._workers.clear()
