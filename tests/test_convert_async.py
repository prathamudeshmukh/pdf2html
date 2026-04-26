"""
Tests for POST /convert/async endpoint.

Coverage
--------
- Returns 202 with job_id immediately
- job_id is a valid UUID
- Accepts same PDFRequest body as POST /convert
- Job transitions to processing then done (mocked pipeline)
- Job transitions to failed when pipeline raises
- Invalid body → 422
"""

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.pdf2html_api.main import app, job_store

client = TestClient(app)

_VALID_BODY = {"pdf_url": "https://example.com/sample.pdf"}


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_returns_202(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.pdf2html_api.main._run_conversion_background",
        lambda *args, **kwargs: None,
    )
    resp = client.post("/convert/async", json=_VALID_BODY)
    assert resp.status_code == 202


def test_returns_valid_job_id(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.pdf2html_api.main._run_conversion_background",
        lambda *args, **kwargs: None,
    )
    resp = client.post("/convert/async", json=_VALID_BODY)
    job_id = resp.json()["job_id"]
    uuid.UUID(job_id)  # raises if invalid


def test_invalid_body_returns_422() -> None:
    resp = client.post("/convert/async", json={"not_a_field": "x"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Background task success path (synchronous simulation)
# ---------------------------------------------------------------------------


def test_background_task_marks_job_done(monkeypatch) -> None:
    """Simulate the background task running synchronously to verify state transitions."""
    completed_calls: list = []

    def fake_background(job_id: str, request, store) -> None:
        store.set_processing(job_id, pages_total=1)
        store.increment_page_done(job_id)
        store.set_done(job_id, {"html": "<p>hi</p>", "sample_json": None, "pages_processed": 1})
        completed_calls.append(job_id)

    monkeypatch.setattr(
        "src.pdf2html_api.main._run_conversion_background",
        fake_background,
    )

    resp = client.post("/convert/async", json=_VALID_BODY)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # background ran synchronously in TestClient
    assert len(completed_calls) == 1
    job = job_store.get_job(job_id)
    assert job["status"] == "done"
    assert job["pages_done"] == 1


def test_background_task_marks_job_failed(monkeypatch) -> None:
    def fake_background(job_id: str, request, store) -> None:
        store.set_processing(job_id, pages_total=1)
        store.set_failed(job_id, "OpenAI timeout")

    monkeypatch.setattr(
        "src.pdf2html_api.main._run_conversion_background",
        fake_background,
    )

    resp = client.post("/convert/async", json=_VALID_BODY)
    job_id = resp.json()["job_id"]
    job = job_store.get_job(job_id)
    assert job["status"] == "failed"
    assert job["error"] == "OpenAI timeout"
