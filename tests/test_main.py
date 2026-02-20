"""
Tests for src/pdf2html_api/main.py and the services it delegates to.

Coverage
--------
- GET /  and  GET /health
- POST /convert  and  POST /convert/html  (HTTP contract)
- ConversionPipeline._configure_settings  (request → Settings wiring)
- Invalid CSS mode  (ValueError → 500 characterisation)
- Pipeline failures  (propagation as 500)
- Page-failure graceful degradation (via HTML body inspection)
- PDFDownloader.download  (all success / error branches)
- PageProcessor.process_pages  (happy path + per-page error handling)
- _cleanup_files  (idempotency + collaborator calls)
- PDFRequest / PDFResponse  (model defaults and schema)
- App metadata
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.pdf2html_api.main import PDFRequest, PDFResponse, _cleanup_files, app
from src.pdf2html_api.services.conversion_pipeline import (
    ConversionArtifacts,
    ConversionPipeline,
    ConversionResult,
)
from src.pdf2html_api.services.page_processor import PageProcessor
from src.pdf2html_api.services.pdf_downloader import PDFDownloader

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


def _make_settings_mock(**kw):
    m = MagicMock()
    m.model = kw.get("model", "gpt-4o-mini")
    m.dpi = kw.get("dpi", 200)
    m.max_tokens = kw.get("max_tokens", 4000)
    m.temperature = kw.get("temperature", 0.0)
    m.css_mode = kw.get("css_mode", "grid")
    m.max_parallel_workers = kw.get("max_parallel_workers", 3)
    m.openai_api_key = kw.get("openai_api_key", "test-key")
    return m


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
# ConversionPipeline configuration: request params → Settings
# ===========================================================================


class TestConversionPipelineConfiguration:
    _SETTINGS_PATH = "src.pdf2html_api.services.settings_configurator.SettingsConfigurator.configure"

    def _make_pipeline(self, **request_kwargs):
        pipeline = ConversionPipeline(
            PDFRequest(pdf_url="https://example.com/test.pdf", **request_kwargs)
        )
        return pipeline, pipeline._settings

    def test_model_override(self):
        _, s = self._make_pipeline(model="gpt-4o")
        assert s.model == "gpt-4o"

    def test_dpi_override(self):
        _, s = self._make_pipeline(dpi=300)
        assert s.dpi == 300

    def test_max_tokens_override(self):
        _, s = self._make_pipeline(max_tokens=2000)
        assert s.max_tokens == 2000

    def test_temperature_override(self):
        _, s = self._make_pipeline(temperature=0.7)
        assert s.temperature == 0.7

    def test_max_parallel_workers_override(self):
        _, s = self._make_pipeline(max_parallel_workers=5)
        assert s.max_parallel_workers == 5

    def test_css_mode_columns_accepted(self):
        _, s = self._make_pipeline(css_mode="columns")
        assert s.css_mode == "columns"

    def test_css_mode_single_accepted(self):
        _, s = self._make_pipeline(css_mode="single")
        assert s.css_mode == "single"

    def test_default_css_mode_is_grid(self):
        _, s = self._make_pipeline()
        assert s.css_mode == "grid"


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
# POST /convert/html
# ===========================================================================


class TestConvertHtmlEndpoint:
    def test_status_200(self):
        stack, _ = _patch_pipeline()
        with stack:
            r = client.post("/convert/html", json={"pdf_url": "https://example.com/test.pdf"})
        assert r.status_code == 200

    def test_content_type_is_text_html(self):
        stack, _ = _patch_pipeline()
        with stack:
            r = client.post("/convert/html", json={"pdf_url": "https://example.com/test.pdf"})
        assert "text/html" in r.headers["content-type"]

    def test_response_body_contains_doctype(self):
        stack, _ = _patch_pipeline()
        with stack:
            r = client.post("/convert/html", json={"pdf_url": "https://example.com/test.pdf"})
        assert "<!DOCTYPE html>" in r.text

    def test_invalid_css_mode_returns_500(self):
        stack, _ = _patch_pipeline(exc=ValueError("CSS mode ... got nope"))
        with stack:
            r = client.post(
                "/convert/html",
                json={"pdf_url": "https://example.com/test.pdf", "css_mode": "nope"},
            )
        assert r.status_code == 500

    def test_missing_url_returns_422(self):
        assert client.post("/convert/html", json={}).status_code == 422

    def test_pipeline_failure_returns_500(self):
        stack, _ = _patch_pipeline(exc=RuntimeError("network error"))
        with stack:
            r = client.post("/convert/html", json={"pdf_url": "https://example.com/test.pdf"})
        assert r.status_code == 500

    def test_multi_page_returns_200(self):
        stack, _ = _patch_pipeline(_make_result(pages_processed=2))
        with stack:
            r = client.post("/convert/html", json={"pdf_url": "https://example.com/test.pdf"})
        assert r.status_code == 200


# ===========================================================================
# PDFDownloader – unit tests
# ===========================================================================


class TestPDFDownloader:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _mock_httpx_client(self, content: bytes, content_type: str, *, raise_error=None):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = content
        mock_response.headers = {"content-type": content_type}
        mock_response.raise_for_status = MagicMock()
        if raise_error is not None:
            mock_client.get = AsyncMock(side_effect=raise_error)
        else:
            mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return mock_client

    def _patch(self, mock_client):
        return patch(
            "src.pdf2html_api.services.pdf_downloader.httpx.AsyncClient",
            return_value=mock_client,
        )

    # happy path

    def test_success_returns_path(self):
        pdf_bytes = b"%PDF-1.4 fake"
        mc = self._mock_httpx_client(pdf_bytes, "application/pdf")
        with self._patch(mc):
            result = self._run(PDFDownloader().download("https://example.com/doc.pdf"))
        assert isinstance(result, Path)
        assert result.suffix == ".pdf"
        assert result.exists()
        result.unlink()

    def test_success_file_contains_pdf_content(self):
        pdf_bytes = b"%PDF-1.4 fake"
        mc = self._mock_httpx_client(pdf_bytes, "application/pdf")
        with self._patch(mc):
            result = self._run(PDFDownloader().download("https://example.com/doc.pdf"))
        assert result.read_bytes() == pdf_bytes
        result.unlink()

    def test_url_ending_in_pdf_bypasses_content_type_check(self):
        pdf_bytes = b"%PDF-1.4 content"
        mc = self._mock_httpx_client(pdf_bytes, "application/octet-stream")
        with self._patch(mc):
            result = self._run(PDFDownloader().download("https://example.com/document.pdf"))
        assert result.exists()
        result.unlink()

    def test_raise_for_status_is_called(self):
        pdf_bytes = b"%PDF-1.4 content"
        mc = self._mock_httpx_client(pdf_bytes, "application/pdf")
        with self._patch(mc):
            result = self._run(PDFDownloader().download("https://example.com/document.pdf"))
        mc.get.return_value.raise_for_status.assert_called_once()
        result.unlink()

    # error branches

    def test_non_pdf_content_type_raises_http_exception(self):
        from fastapi import HTTPException
        mc = self._mock_httpx_client(b"<html/>", "text/html")
        with self._patch(mc):
            with pytest.raises(HTTPException) as exc_info:
                self._run(PDFDownloader().download("https://example.com/page"))
        assert "URL does not point to a PDF file" in exc_info.value.detail

    def test_http_status_error_raises_400(self):
        from fastapi import HTTPException
        err_resp = MagicMock()
        err_resp.status_code = 404
        http_err = httpx.HTTPStatusError("Not found", request=MagicMock(), response=err_resp)
        mc = self._mock_httpx_client(b"", "application/pdf", raise_error=http_err)
        with self._patch(mc):
            with pytest.raises(HTTPException) as exc_info:
                self._run(PDFDownloader().download("https://example.com/missing.pdf"))
        assert exc_info.value.status_code == 400
        assert "404" in exc_info.value.detail

    def test_request_error_raises_400(self):
        from fastapi import HTTPException
        mc = self._mock_httpx_client(b"", "application/pdf", raise_error=httpx.ConnectError("refused"))
        with self._patch(mc):
            with pytest.raises(HTTPException) as exc_info:
                self._run(PDFDownloader().download("https://example.com/test.pdf"))
        assert exc_info.value.status_code == 400

    def test_unexpected_error_raises_500(self):
        from fastapi import HTTPException
        mc = self._mock_httpx_client(b"", "application/pdf", raise_error=MemoryError("oom"))
        with self._patch(mc):
            with pytest.raises(HTTPException) as exc_info:
                self._run(PDFDownloader().download("https://example.com/test.pdf"))
        assert exc_info.value.status_code == 500


# ===========================================================================
# PageProcessor – unit tests
# ===========================================================================


class TestPageProcessor:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _gen(self, *page_htmls):
        g = MagicMock()
        g.image_page_to_html.side_effect = list(page_htmls)
        return g

    def test_single_page_returns_list_of_one(self):
        g = self._gen('<section class="page">P1</section>')
        result = self._run(PageProcessor().process_pages(g, ["img1.png"], "grid", "r", 1))
        assert len(result) == 1

    def test_multi_page_returns_correct_count(self):
        pages = [f'<section class="page">P{i}</section>' for i in range(4)]
        g = self._gen(*pages)
        result = self._run(
            PageProcessor().process_pages(g, ["i1.png", "i2.png", "i3.png", "i4.png"], "grid", "r", 2)
        )
        assert len(result) == 4

    def test_page_order_preserved(self):
        def side(path, css_mode):
            idx = int(path.replace("img", "").replace(".png", ""))
            return f'<section class="page">Page{idx}</section>'
        g = MagicMock()
        g.image_page_to_html.side_effect = side
        result = self._run(
            PageProcessor().process_pages(g, ["img0.png", "img1.png", "img2.png"], "grid", "r", 3)
        )
        assert result[0] == '<section class="page">Page0</section>'
        assert result[1] == '<section class="page">Page1</section>'
        assert result[2] == '<section class="page">Page2</section>'

    def test_css_mode_forwarded_to_generator(self):
        g = self._gen('<section class="page">x</section>')
        self._run(PageProcessor().process_pages(g, ["img1.png"], "columns", "r", 1))
        g.image_page_to_html.assert_called_once_with("img1.png", "columns")

    def test_exception_replaced_with_placeholder(self):
        g = MagicMock()
        g.image_page_to_html.side_effect = RuntimeError("llm failed")
        result = self._run(PageProcessor().process_pages(g, ["img1.png"], "grid", "r", 1))
        assert len(result) == 1
        assert "ocr-uncertain" in result[0]
        assert "Error processing page 1" in result[0]

    def test_partial_failure_does_not_drop_successful_pages(self):
        def side(path, css_mode):
            if "img1" in path:
                return '<section class="page">OK</section>'
            raise RuntimeError("page 2 failed")
        g = MagicMock()
        g.image_page_to_html.side_effect = side
        result = self._run(
            PageProcessor().process_pages(g, ["img1.png", "img2.png"], "grid", "r", 2)
        )
        assert len(result) == 2
        assert result[0] == '<section class="page">OK</section>'
        assert "ocr-uncertain" in result[1]

    def test_page_failure_endpoint_returns_200(self):
        result_with_error = _make_result(
            html='<!DOCTYPE html><html><body><p class="ocr-uncertain">[Error processing page 1: oops]</p></body></html>'
        )
        stack, _ = _patch_pipeline(result_with_error)
        with stack:
            response = client.post("/convert", json={"pdf_url": "https://example.com/test.pdf"})
        assert response.status_code == 200
        assert "ocr-uncertain" in response.json()["html"]


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
