"""
Tests for GET /jobs/{job_id} poll endpoint.

Coverage
--------
- pending → 200 with status + zero progress
- processing → 200 with status + pages_done/pages_total
- done → 200 with status + full result
- failed → 200 with status + error
- unknown job_id → 404
"""

import pytest
from fastapi.testclient import TestClient

from src.pdf2html_api.main import app, job_store

client = TestClient(app)


def test_unknown_job_returns_404() -> None:
    resp = client.get("/jobs/nonexistent-id")
    assert resp.status_code == 404


def test_pending_job_returns_status_and_zero_progress() -> None:
    job_id = job_store.create_job()
    resp = client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["pages_done"] == 0
    assert body["pages_total"] == 0


def test_processing_job_returns_progress() -> None:
    job_id = job_store.create_job()
    job_store.set_processing(job_id, pages_total=5)
    job_store.increment_page_done(job_id)
    job_store.increment_page_done(job_id)

    resp = client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "processing"
    assert body["pages_done"] == 2
    assert body["pages_total"] == 5


def test_done_job_returns_full_result() -> None:
    job_id = job_store.create_job()
    job_store.set_processing(job_id, pages_total=2)
    job_store.set_done(job_id, {
        "html": "<p>done</p>",
        "sample_json": {"{{name}}": "Alice"},
        "pages_processed": 2,
    })

    resp = client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["html"] == "<p>done</p>"
    assert body["sample_json"] == {"{{name}}": "Alice"}
    assert body["pages_processed"] == 2
    assert body["pages_total"] == 2


def test_failed_job_returns_error() -> None:
    job_id = job_store.create_job()
    job_store.set_failed(job_id, "OpenAI API quota exceeded")

    resp = client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error"] == "OpenAI API quota exceeded"
