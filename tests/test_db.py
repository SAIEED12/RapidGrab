from __future__ import annotations

import time

from rapidgrab.core.db import Store


def make_store(tmp_path):
    return Store(tmp_path / "test.db")


def test_job_insert_update_and_history(tmp_path):
    store = make_store(tmp_path)
    job = store.new_job(
        url="https://example.com/video",
        title="Example",
        site="Example",
        media_kind="video",
        quality_label="1080p",
    )
    store.insert_job(job)

    fetched = store.get_job(job["id"])
    assert fetched is not None
    assert fetched["title"] == "Example"
    assert fetched["status"] == "queued"

    store.update_job(job["id"], {"status": "completed", "completed_at": time.time(), "total_bytes": 1234})
    history = store.list_history()
    assert len(history) == 1
    assert history[0]["total_bytes"] == 1234

    assert store.list_history("does-not-exist") == []
    assert len(store.list_history("Example")) == 1

    store.delete_job(job["id"])
    assert store.get_job(job["id"]) is None


def test_reset_unfinished(tmp_path):
    store = make_store(tmp_path)
    running = store.new_job(url="https://example.com/a", status="downloading", progress=0.5)
    store.insert_job(running)
    done = store.new_job(url="https://example.com/b", status="completed", progress=1.0)
    store.insert_job(done)

    store.reset_unfinished()

    assert store.get_job(running["id"])["status"] == "paused"
    assert store.get_job(done["id"])["status"] == "completed"
