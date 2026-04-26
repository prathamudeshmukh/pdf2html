"""
Tests for src/pdf2html_api/services/job_store.py

Coverage
--------
- create_job: returns UUID, sets pending status with zero progress
- get_job: returns None for unknown IDs
- set_processing: updates status and records pages_total
- increment_page_done: atomically increments pages_done
- set_done: stores result payload and marks done
- set_failed: stores error string and marks failed
- thread safety: concurrent increments reach the correct total
"""

import threading
import uuid

import pytest

from src.pdf2html_api.services.job_store import JobStore


@pytest.fixture()
def store() -> JobStore:
    return JobStore()


# ---------------------------------------------------------------------------
# create_job
# ---------------------------------------------------------------------------


def test_create_job_returns_valid_uuid(store: JobStore) -> None:
    job_id = store.create_job()
    uuid.UUID(job_id)  # raises ValueError if not a valid UUID


def test_create_job_sets_pending_status(store: JobStore) -> None:
    job_id = store.create_job()
    job = store.get_job(job_id)
    assert job is not None
    assert job["status"] == "pending"


def test_create_job_sets_zero_progress(store: JobStore) -> None:
    job_id = store.create_job()
    job = store.get_job(job_id)
    assert job["pages_done"] == 0
    assert job["pages_total"] == 0


# ---------------------------------------------------------------------------
# get_job
# ---------------------------------------------------------------------------


def test_get_job_returns_none_for_unknown_id(store: JobStore) -> None:
    assert store.get_job("nonexistent-id") is None


# ---------------------------------------------------------------------------
# set_processing
# ---------------------------------------------------------------------------


def test_set_processing_updates_status_and_total(store: JobStore) -> None:
    job_id = store.create_job()
    store.set_processing(job_id, pages_total=5)
    job = store.get_job(job_id)
    assert job["status"] == "processing"
    assert job["pages_total"] == 5
    assert job["pages_done"] == 0


# ---------------------------------------------------------------------------
# increment_page_done
# ---------------------------------------------------------------------------


def test_increment_page_done_increases_count(store: JobStore) -> None:
    job_id = store.create_job()
    store.set_processing(job_id, pages_total=3)
    store.increment_page_done(job_id)
    store.increment_page_done(job_id)
    job = store.get_job(job_id)
    assert job["pages_done"] == 2


def test_increment_page_done_thread_safe(store: JobStore) -> None:
    job_id = store.create_job()
    total = 50
    store.set_processing(job_id, pages_total=total)

    threads = [
        threading.Thread(target=store.increment_page_done, args=(job_id,))
        for _ in range(total)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert store.get_job(job_id)["pages_done"] == total


# ---------------------------------------------------------------------------
# set_done
# ---------------------------------------------------------------------------


def test_set_done_stores_result_and_marks_done(store: JobStore) -> None:
    job_id = store.create_job()
    result = {"html": "<p>hi</p>", "sample_json": None, "pages_processed": 2}
    store.set_done(job_id, result)
    job = store.get_job(job_id)
    assert job["status"] == "done"
    assert job["result"] == result


# ---------------------------------------------------------------------------
# set_failed
# ---------------------------------------------------------------------------


def test_set_failed_stores_error_and_marks_failed(store: JobStore) -> None:
    job_id = store.create_job()
    store.set_failed(job_id, "OpenAI API timed out")
    job = store.get_job(job_id)
    assert job["status"] == "failed"
    assert job["error"] == "OpenAI API timed out"
