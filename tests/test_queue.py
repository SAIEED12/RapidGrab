from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from rapidgrab.core.db import Store
from rapidgrab.core.engine import DownloadCancelled
from rapidgrab.core.queue import DownloadManager
from rapidgrab.core.settings import Settings

_APP = QCoreApplication.instance() or QCoreApplication([])


class FakeEngine:
    """Engine stand-in that downloads slowly enough to control."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.started: list[str] = []
        self.lock = threading.Lock()

    def download(self, job, progress, stop_event):
        with self.lock:
            self.started.append(job["url"])
        for step in range(20):
            if stop_event is not None and stop_event.is_set():
                raise DownloadCancelled()
            progress(
                {
                    "status": "downloading",
                    "progress": step / 20,
                    "downloaded_bytes": step * 10,
                    "total_bytes": 200,
                    "speed": 1024,
                    "eta": 1,
                }
            )
            time.sleep(0.03)
        path = self.root / f"{job['id']}.mp4"
        path.write_bytes(b"x" * 100)
        progress({"status": "processing", "progress": 1.0, "filepath": str(path)})
        return str(path)


def wait_for(predicate, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        _APP.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    _APP.processEvents()
    return predicate()


def make_manager(tmp_path: Path, **settings_overrides):
    settings = Settings(tmp_path / "settings.json")
    settings.update(settings_overrides)
    store = Store(tmp_path / "jobs.db")
    engine = FakeEngine(tmp_path)
    manager = DownloadManager(engine, store, settings)
    return manager, store, engine, settings


def test_concurrency_limit_and_completion(tmp_path):
    manager, store, engine, settings = make_manager(tmp_path, max_concurrent=1)
    first = manager.add_job("https://example.com/a", title="A")
    second = manager.add_job("https://example.com/b", title="B")

    assert wait_for(lambda: store.get_job(first["id"])["status"] == "completed")
    assert wait_for(lambda: store.get_job(second["id"])["status"] == "completed")

    # With one worker the second job starts only after the first finishes.
    assert engine.started == ["https://example.com/a", "https://example.com/b"]
    assert len(store.list_history()) == 2
    manager.shutdown()
    store.close()


def test_pause_and_resume(tmp_path):
    manager, store, engine, settings = make_manager(tmp_path, max_concurrent=1)
    job = manager.add_job("https://example.com/slow", title="Slow")

    assert wait_for(lambda: manager.get(job["id"])["status"] == "downloading")
    manager.pause(job["id"])
    assert wait_for(lambda: store.get_job(job["id"])["status"] == "paused")
    assert len(engine.started) == 1

    manager.resume(job["id"])
    assert wait_for(lambda: store.get_job(job["id"])["status"] == "completed")
    assert len(engine.started) == 2

    manager.shutdown()
    store.close()


def test_cancel(tmp_path):
    manager, store, engine, settings = make_manager(tmp_path, max_concurrent=1)
    job = manager.add_job("https://example.com/cancel", title="Cancel me")

    assert wait_for(lambda: manager.get(job["id"])["status"] == "downloading")
    manager.cancel(job["id"])
    assert wait_for(lambda: store.get_job(job["id"])["status"] == "canceled")

    manager.shutdown()
    store.close()


def test_restart_recovers_interrupted_jobs(tmp_path):
    manager, store, engine, settings = make_manager(tmp_path, max_concurrent=1)
    job = manager.add_job("https://example.com/resume", title="Resume me")
    assert wait_for(lambda: manager.get(job["id"])["status"] == "downloading")
    manager.shutdown()
    store.close()

    # A new process should see the interrupted job as paused, not lost.
    store2 = Store(tmp_path / "jobs.db")
    settings2 = Settings(tmp_path / "settings.json")
    engine2 = FakeEngine(tmp_path)
    manager2 = DownloadManager(engine2, store2, settings2)
    recovered = manager2.get(job["id"])
    assert recovered is not None
    assert recovered["status"] == "paused"
    manager2.shutdown()
    store2.close()
