"""Tests for PDF2HTML API endpoints."""

import tempfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from src.pdf2html_api.main import app
from src.pdf2html_api.services.conversion_pipeline import (
    ConversionArtifacts,
    ConversionResult,
)

client = TestClient(app)

_MERGED_HTML = "<!DOCTYPE html><html><body><p>Test content</p></body></html>"


def _make_result(css_mode: str = "grid", pages: int = 1) -> ConversionResult:
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(b"%PDF stub")
    tmp.close()
    return ConversionResult(
        html=_MERGED_HTML,
        pages_processed=pages,
        model_used="gpt-4o-mini",
        css_mode=css_mode,
        artifacts=ConversionArtifacts(
            pdf_path=Path(tmp.name),
            image_paths=[],
            temp_dir=MagicMock(),
        ),
    )


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "PDF2HTML API"
    assert data["version"] == "0.1.0"
    assert "convert" in data["endpoints"]


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "pdf2html-api"


def test_convert_endpoint_invalid_url():
    response = client.post("/convert", json={"pdf_url": "not-a-valid-url"})
    assert response.status_code == 422


def test_convert_endpoint_missing_url():
    response = client.post("/convert", json={})
    assert response.status_code == 422


def test_convert_endpoint_invalid_css_mode():
    """ValueError from pipeline is wrapped as 500 by the route handler."""
    with (
        patch(
            "src.pdf2html_api.main.ConversionPipeline.execute",
            new=AsyncMock(side_effect=ValueError("CSS mode ... got invalid_mode")),
        ),
        patch("src.pdf2html_api.main._cleanup_files"),
    ):
        response = client.post(
            "/convert",
            json={"pdf_url": "https://example.com/test.pdf", "css_mode": "invalid_mode"},
        )
    assert response.status_code == 500


def test_convert_endpoint_success():
    result = _make_result()
    with (
        patch(
            "src.pdf2html_api.main.ConversionPipeline.execute",
            new=AsyncMock(return_value=result),
        ),
        patch("src.pdf2html_api.main._cleanup_files"),
    ):
        response = client.post(
            "/convert",
            json={"pdf_url": "https://example.com/test.pdf", "css_mode": "grid"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "html" in data
    assert data["pages_processed"] == 1
    assert data["model_used"] == "gpt-4o-mini"
    assert data["css_mode"] == "grid"


def test_convert_html_endpoint_success():
    result = _make_result()
    with (
        patch(
            "src.pdf2html_api.main.ConversionPipeline.execute",
            new=AsyncMock(return_value=result),
        ),
        patch("src.pdf2html_api.main._cleanup_files"),
    ):
        response = client.post(
            "/convert/html",
            json={"pdf_url": "https://example.com/test.pdf", "css_mode": "grid"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "<!DOCTYPE html>" in response.text
