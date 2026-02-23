"""
Tests for src/pdf2html_api/main.py and its HTTP endpoints.

Coverage
--------
- GET /  and  GET /health
- POST /convert  (HTTP contract)
- Invalid CSS mode  (ValueError → 500 characterisation)
- Pipeline failures  (propagation as 500)
- _cleanup_files  (idempotency + collaborator calls)
- PDFRequest / PDFResponse  (model defaults and schema)
- App metadata

See also
--------
- test_conversion_pipeline.py  – ConversionPipeline._configure_settings
- test_pdf_downloader.py        – PDFDownloader.download
- test_page_processor.py        – PageProcessor.process_pages
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.pdf2html_api.main import PDFRequest, PDFResponse, _cleanup_files, app
from src.pdf2html_api.services.conversion_pipeline import (
    ConversionArtifacts,
    ConversionResult,
)

client = TestClient(app)

_MERGED_HTML = "<!DOCTYPE html><html><body><p>Merged</p></body></html>"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    *,
    html: str = _MERGED_HTML,
    pages_processed: int = 1,
    model_used: str = "gpt-4o-mini",
    css_mode: str = "grid",
) -> ConversionResult:
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(b"%PDF stub")
    tmp.close()
    return ConversionResult(
        html=html,
        pages_processed=pages_processed,
        model_used=model_used,
        css_mode=css_mode,
        artifacts=ConversionArtifacts(
            pdf_path=Path(tmp.name),
            image_paths=[],
            temp_dir=MagicMock(),
        ),
    )


def _patch_pipeline(result=None, exc=None):
    from contextlib import ExitStack

    stack = ExitStack()
    resolved = result or _make_result()

    if exc is not None:
        stack.enter_context(
            patch(
                "src.pdf2html_api.main.ConversionPipeline.execute",
                new=AsyncMock(side_effect=exc),
            )
        )
    else:
        stack.enter_context(
            patch(
                "src.pdf2html_api.main.ConversionPipeline.execute",
                new=AsyncMock(return_value=resolved),
            )
        )
    stack.enter_context(patch("src.pdf2html_api.main._cleanup_files"))
    return stack, resolved


# ===========================================================================
# GET /
# ===========================================================================


class TestRootEndpoint:
    def test_status_code_is_200(self):
        assert client.get("/").status_code == 200

    def test_message_field(self):
        assert client.get("/").json()["message"] == "PDF2HTML API"

    def test_version_field(self):
        assert client.get("/").json()["version"] == "0.1.0"

    def test_endpoints_dict_contains_convert(self):
        assert "convert" in client.get("/").json()["endpoints"]

    def test_endpoints_dict_contains_docs(self):
        assert "docs" in client.get("/").json()["endpoints"]

    def test_endpoints_dict_contains_health(self):
        assert "health" in client.get("/").json()["endpoints"]

    def test_convert_path_value(self):
        assert client.get("/").json()["endpoints"]["convert"] == "/convert"


# ===========================================================================
# GET /health
# ===========================================================================


class TestHealthEndpoint:
    def test_status_code_is_200(self):
        assert client.get("/health").status_code == 200

    def test_status_field_is_healthy(self):
        assert client.get("/health").json()["status"] == "healthy"

    def test_service_field(self):
        assert client.get("/health").json()["service"] == "pdf2html-api"


# ===========================================================================
# POST /convert – request validation
# ===========================================================================


class TestConvertRequestValidation:
    def test_missing_pdf_url_returns_422(self):
        assert client.post("/convert", json={}).status_code == 422

    def test_invalid_url_string_returns_422(self):
        assert client.post("/convert", json={"pdf_url": "not-valid"}).status_code == 422

    def test_plain_string_without_scheme_returns_422(self):
        assert (
            client.post("/convert", json={"pdf_url": "example.com/file.pdf"}).status_code == 422
        )

    def test_ftp_url_returns_422(self):
        assert (
            client.post("/convert", json={"pdf_url": "ftp://example.com/file.pdf"}).status_code
            == 422
        )


# ===========================================================================
# POST /convert – successful (pipeline mocked)
# ===========================================================================


class TestConvertSinglePageSuccess:
    def setup_method(self):
        self.result = _make_result(pages_processed=1)
        self.stack, _ = _patch_pipeline(self.result)
        self.stack.__enter__()
        self.response = client.post(
            "/convert", json={"pdf_url": "https://example.com/test.pdf"}
        )
        self.data = self.response.json()

    def teardown_method(self):
        self.stack.__exit__(None, None, None)

    def test_status_code_is_200(self):
        assert self.response.status_code == 200

    def test_html_field_present(self):
        assert "html" in self.data

    def test_html_content(self):
        assert self.data["html"] == self.result.html

    def test_pages_processed_is_1(self):
        assert self.data["pages_processed"] == 1

    def test_model_used_field(self):
        assert self.data["model_used"] == self.result.model_used

    def test_css_mode_field(self):
        assert self.data["css_mode"] == self.result.css_mode


class TestConvertMultiPageSuccess:
    def setup_method(self):
        self.result = _make_result(pages_processed=3)
        self.stack, _ = _patch_pipeline(self.result)
        self.stack.__enter__()
        self.response = client.post(
            "/convert", json={"pdf_url": "https://example.com/test.pdf"}
        )

    def teardown_method(self):
        self.stack.__exit__(None, None, None)

    def test_status_code_is_200(self):
        assert self.response.status_code == 200

    def test_pages_processed_is_3(self):
        assert self.response.json()["pages_processed"] == 3


# ===========================================================================
# CSS mode variants – accepted end-to-end
# ===========================================================================


class TestConvertCssModeVariants:
    def test_css_mode_columns_returns_200(self):
        stack, _ = _patch_pipeline(_make_result(css_mode="columns"))
        with stack:
            r = client.post(
                "/convert",
                json={"pdf_url": "https://example.com/test.pdf", "css_mode": "columns"},
            )
        assert r.status_code == 200
        assert r.json()["css_mode"] == "columns"

    def test_css_mode_single_returns_200(self):
        stack, _ = _patch_pipeline(_make_result(css_mode="single"))
        with stack:
            r = client.post(
                "/convert",
                json={"pdf_url": "https://example.com/test.pdf", "css_mode": "single"},
            )
        assert r.status_code == 200
        assert r.json()["css_mode"] == "single"


# ===========================================================================
# Invalid CSS mode → 500
# ===========================================================================


class TestConvertInvalidCssMode:
    def _post(self):
        stack, _ = _patch_pipeline(exc=ValueError("CSS mode ... got invalid"))
        with stack:
            return client.post(
                "/convert",
                json={"pdf_url": "https://example.com/test.pdf", "css_mode": "invalid"},
            )

    def test_returns_500(self):
        assert self._post().status_code == 500

    def test_detail_mentions_invalid(self):
        assert "invalid" in self._post().json()["detail"]


# ===========================================================================
# Pipeline failures → 500
# ===========================================================================


class TestConvertPipelineFailure:
    def _post(self, exc):
        stack, _ = _patch_pipeline(exc=exc)
        with stack:
            return client.post("/convert", json={"pdf_url": "https://example.com/test.pdf"})

    def test_http_exception_400_wrapped_as_500(self):
        from fastapi import HTTPException
        assert self._post(HTTPException(status_code=400, detail="bad")).status_code == 500

    def test_http_exception_detail_preserved(self):
        from fastapi import HTTPException
        assert "bad" in self._post(HTTPException(status_code=400, detail="bad")).json()["detail"]

    def test_runtime_error_returns_500(self):
        assert self._post(RuntimeError("unexpected")).status_code == 500

    def test_500_detail_contains_conversion_failed(self):
        assert "Conversion failed" in self._post(RuntimeError("boom")).json()["detail"]


# ===========================================================================
# _cleanup_files
# ===========================================================================


class TestCleanupFiles:
    def _artifacts(self, pdf_path, image_paths=None, temp_dir=None):
        return ConversionArtifacts(
            pdf_path=pdf_path,
            image_paths=image_paths or [],
            temp_dir=temp_dir or MagicMock(),
        )

    def test_pdf_file_is_deleted(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            p = Path(f.name)
        assert p.exists()
        _cleanup_files(self._artifacts(p))
        assert not p.exists()

    def test_cleanup_temp_images_is_called(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            p = Path(f.name)
        image_paths = ["/tmp/img1.png"]
        mock_dir = MagicMock()
        with patch("src.pdf2html_api.main.cleanup_temp_images") as mock_cleanup:
            _cleanup_files(self._artifacts(p, image_paths, mock_dir))
            mock_cleanup.assert_called_once_with(image_paths, mock_dir)

    def test_missing_pdf_does_not_raise(self):
        phantom = Path("/tmp/does_not_exist_xyz.pdf")
        _cleanup_files(self._artifacts(phantom))  # must not raise

    def test_cleanup_exception_is_swallowed(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            p = Path(f.name)
        with patch("src.pdf2html_api.main.cleanup_temp_images", side_effect=RuntimeError("disk")):
            _cleanup_files(self._artifacts(p))  # must not raise


# ===========================================================================
# PDFRequest / PDFResponse models
# ===========================================================================


class TestPDFRequestModel:
    def _req(self):
        return PDFRequest(pdf_url="https://example.com/test.pdf")

    def test_default_model(self):
        assert self._req().model == "gpt-4o-mini"

    def test_default_dpi(self):
        assert self._req().dpi == 200

    def test_default_max_tokens(self):
        assert self._req().max_tokens == 4000

    def test_default_temperature(self):
        assert self._req().temperature == 0.0

    def test_default_css_mode(self):
        assert self._req().css_mode == "grid"

    def test_default_max_parallel_workers(self):
        assert self._req().max_parallel_workers == 3


class TestPDFResponseModel:
    def test_schema_fields(self):
        r = PDFResponse(html="<html/>", pages_processed=2, model_used="gpt-4o-mini", css_mode="grid")
        assert r.html == "<html/>"
        assert r.pages_processed == 2
        assert r.model_used == "gpt-4o-mini"
        assert r.css_mode == "grid"


# ===========================================================================
# App metadata
# ===========================================================================


class TestAppMetadata:
    def test_app_title(self):
        assert app.title == "PDF2HTML API"

    def test_app_version(self):
        assert app.version == "0.1.0"

    def test_docs_url(self):
        assert app.docs_url == "/docs"

    def test_redoc_url(self):
        assert app.redoc_url == "/redoc"
