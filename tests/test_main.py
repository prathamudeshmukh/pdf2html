"""
Characterization tests for src/pdf2html_api/main.py.

These tests document the *actual* observable behaviour of every public
endpoint and every significant private helper in main.py.  They serve as a
safety-net: if any refactoring silently changes the contract, at least one
test here will fail.

Coverage areas
--------------
- GET /
- GET /health
- POST /convert          (JSON response endpoint)
- POST /convert/html     (raw HTML response endpoint)
- _download_pdf_from_url (all success and failure branches)
- _convert_pages_parallel (happy path + per-page exception handling)
- _cleanup_files         (normal cleanup + resistant to missing files)
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import httpx
import pytest
from fastapi.testclient import TestClient

from src.pdf2html_api.main import (
    app,
    _cleanup_files,
    _convert_pages_parallel,
    _download_pdf_from_url,
)

# ---------------------------------------------------------------------------
# Shared test client (synchronous – handles async routes transparently)
# ---------------------------------------------------------------------------

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(
    *,
    model: str = "gpt-4o-mini",
    dpi: int = 200,
    max_tokens: int = 4000,
    temperature: float = 0.0,
    css_mode: str = "grid",
    max_parallel_workers: int = 3,
    openai_api_key: str = "test-key",
) -> MagicMock:
    """Return a pre-configured settings mock."""
    mock = MagicMock()
    mock.model = model
    mock.dpi = dpi
    mock.max_tokens = max_tokens
    mock.temperature = temperature
    mock.css_mode = css_mode
    mock.max_parallel_workers = max_parallel_workers
    mock.openai_api_key = openai_api_key
    return mock


def _patch_happy_path(css_mode: str = "grid", num_pages: int = 1):
    """
    Return a context-manager stack that patches all I/O collaborators so that
    the /convert endpoint succeeds without touching the network or filesystem.
    """
    from contextlib import ExitStack
    import tempfile as _tf
    stack = ExitStack()

    # Create a real temp file so pdf_path.stat() doesn't raise
    _tmp = _tf.NamedTemporaryFile(suffix=".pdf", delete=False)
    _tmp.write(b"%PDF-1.4 stub")
    _tmp.close()
    _real_pdf_path = Path(_tmp.name)
    stack.callback(_real_pdf_path.unlink, missing_ok=True)

    mock_settings = _make_settings(css_mode=css_mode)
    stack.enter_context(
        patch("src.pdf2html_api.main.get_settings", return_value=mock_settings)
    )

    image_paths = [f"/tmp/page{i}.png" for i in range(1, num_pages + 1)]
    stack.enter_context(
        patch(
            "src.pdf2html_api.main._download_pdf_from_url",
            new=AsyncMock(return_value=_real_pdf_path),
        )
    )

    mock_temp_dir = MagicMock()
    stack.enter_context(
        patch(
            "src.pdf2html_api.main.render_pdf_to_images",
            return_value=(image_paths, mock_temp_dir),
        )
    )

    mock_generator = MagicMock()
    mock_generator.image_page_to_html.side_effect = [
        f'<section class="page"><p>Page {i}</p></section>'
        for i in range(1, num_pages + 1)
    ]
    stack.enter_context(
        patch("src.pdf2html_api.main.HTMLGenerator", return_value=mock_generator)
    )

    merged_html = "<!DOCTYPE html><html><body><p>Merged</p></body></html>"
    stack.enter_context(
        patch("src.pdf2html_api.main.merge_pages", return_value=merged_html)
    )

    return stack, mock_settings, mock_generator, merged_html


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
# POST /convert – request validation (no mocking needed)
# ===========================================================================

class TestConvertRequestValidation:
    def test_missing_pdf_url_returns_422(self):
        assert client.post("/convert", json={}).status_code == 422

    def test_invalid_url_string_returns_422(self):
        assert (
            client.post("/convert", json={"pdf_url": "not-a-valid-url"}).status_code
            == 422
        )

    def test_plain_string_without_scheme_returns_422(self):
        assert (
            client.post("/convert", json={"pdf_url": "example.com/file.pdf"}).status_code
            == 422
        )

    def test_ftp_url_returns_422(self):
        # Pydantic HttpUrl only accepts http/https
        assert (
            client.post("/convert", json={"pdf_url": "ftp://example.com/file.pdf"}).status_code
            == 422
        )


# ===========================================================================
# POST /convert – successful single-page conversion
# ===========================================================================

class TestConvertSinglePageSuccess:
    def setup_method(self):
        self.stack, self.mock_settings, self.mock_generator, self.merged_html = (
            _patch_happy_path(num_pages=1)
        )
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

    def test_html_content_is_merged_output(self):
        assert self.data["html"] == self.merged_html

    def test_pages_processed_is_1(self):
        assert self.data["pages_processed"] == 1

    def test_model_used_reflects_settings(self):
        assert self.data["model_used"] == self.mock_settings.model

    def test_css_mode_reflects_settings(self):
        assert self.data["css_mode"] == self.mock_settings.css_mode

    def test_html_generator_called_once(self):
        self.mock_generator.image_page_to_html.assert_called_once()


# ===========================================================================
# POST /convert – successful multi-page conversion (parallel path)
# ===========================================================================

class TestConvertMultiPageSuccess:
    def setup_method(self):
        self.stack, _, self.mock_generator, _ = _patch_happy_path(num_pages=3)
        self.stack.__enter__()
        self.response = client.post(
            "/convert", json={"pdf_url": "https://example.com/test.pdf"}
        )
        self.data = self.response.json()

    def teardown_method(self):
        self.stack.__exit__(None, None, None)

    def test_status_code_is_200(self):
        assert self.response.status_code == 200

    def test_pages_processed_is_3(self):
        assert self.data["pages_processed"] == 3


# ===========================================================================
# POST /convert – request parameters are applied to settings
# ===========================================================================

class TestConvertRequestParametersApplied:
    def test_model_parameter_overrides_default(self):
        stack, mock_settings, _, _ = _patch_happy_path()
        with stack:
            client.post(
                "/convert",
                json={
                    "pdf_url": "https://example.com/test.pdf",
                    "model": "gpt-4o",
                },
            )
        assert mock_settings.model == "gpt-4o"

    def test_dpi_parameter_overrides_default(self):
        stack, mock_settings, _, _ = _patch_happy_path()
        with stack:
            client.post(
                "/convert",
                json={"pdf_url": "https://example.com/test.pdf", "dpi": 300},
            )
        assert mock_settings.dpi == 300

    def test_max_tokens_parameter_overrides_default(self):
        stack, mock_settings, _, _ = _patch_happy_path()
        with stack:
            client.post(
                "/convert",
                json={"pdf_url": "https://example.com/test.pdf", "max_tokens": 2000},
            )
        assert mock_settings.max_tokens == 2000

    def test_temperature_parameter_overrides_default(self):
        stack, mock_settings, _, _ = _patch_happy_path()
        with stack:
            client.post(
                "/convert",
                json={"pdf_url": "https://example.com/test.pdf", "temperature": 0.7},
            )
        assert mock_settings.temperature == 0.7

    def test_max_parallel_workers_parameter_overrides_default(self):
        stack, mock_settings, _, _ = _patch_happy_path()
        with stack:
            client.post(
                "/convert",
                json={
                    "pdf_url": "https://example.com/test.pdf",
                    "max_parallel_workers": 5,
                },
            )
        assert mock_settings.max_parallel_workers == 5

    def test_css_mode_columns_accepted(self):
        stack, _, _, _ = _patch_happy_path(css_mode="columns")
        with stack:
            response = client.post(
                "/convert",
                json={"pdf_url": "https://example.com/test.pdf", "css_mode": "columns"},
            )
        assert response.status_code == 200
        assert response.json()["css_mode"] == "columns"

    def test_css_mode_single_accepted(self):
        stack, _, _, _ = _patch_happy_path(css_mode="single")
        with stack:
            response = client.post(
                "/convert",
                json={"pdf_url": "https://example.com/test.pdf", "css_mode": "single"},
            )
        assert response.status_code == 200
        assert response.json()["css_mode"] == "single"


# ===========================================================================
# POST /convert – invalid CSS mode (validated after settings, returns 400)
# ===========================================================================

class TestConvertInvalidCssMode:
    """
    Characterization note: the endpoint wraps its own business logic inside a
    broad ``except Exception`` handler, so an HTTPException(400) raised for
    an invalid CSS mode is caught and re-raised as HTTPException(500).  That
    is the *actual* observable behaviour we document here.
    """

    def _post_invalid_css(self):
        import tempfile as _tf
        tmp = _tf.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(b"%PDF stub")
        tmp.close()
        real_path = Path(tmp.name)
        try:
            mock_settings = _make_settings()
            with (
                patch("src.pdf2html_api.main.get_settings", return_value=mock_settings),
                patch(
                    "src.pdf2html_api.main._download_pdf_from_url",
                    new=AsyncMock(return_value=real_path),
                ),
            ):
                return client.post(
                    "/convert",
                    json={"pdf_url": "https://example.com/test.pdf", "css_mode": "invalid"},
                )
        finally:
            real_path.unlink(missing_ok=True)

    def test_invalid_css_mode_returns_500(self):
        # HTTPException(400) is caught by the outer except-Exception and
        # re-raised as HTTPException(500)
        assert self._post_invalid_css().status_code == 500

    def test_invalid_css_mode_error_detail_mentions_mode(self):
        assert "invalid" in self._post_invalid_css().json()["detail"]


# ===========================================================================
# POST /convert – download failure propagation
# ===========================================================================

class TestConvertDownloadFailure:
    """
    Characterization: the endpoint's outer ``except Exception`` catches
    *everything*, including HTTPException raised by collaborators.  A
    HTTPException(400) from the downloader therefore surfaces as 500.
    """

    def _post_with_download_error(self, exc):
        mock_settings = _make_settings()
        with (
            patch("src.pdf2html_api.main.get_settings", return_value=mock_settings),
            patch(
                "src.pdf2html_api.main._download_pdf_from_url",
                new=AsyncMock(side_effect=exc),
            ),
        ):
            return client.post(
                "/convert", json={"pdf_url": "https://example.com/test.pdf"}
            )

    def test_http_exception_from_download_wrapped_as_500(self):
        # HTTPException raised inside the try block is caught and rewrapped
        from fastapi import HTTPException
        response = self._post_with_download_error(HTTPException(status_code=400, detail="bad"))
        assert response.status_code == 500

    def test_http_exception_detail_preserved_in_500_message(self):
        from fastapi import HTTPException
        response = self._post_with_download_error(HTTPException(status_code=400, detail="bad"))
        assert "bad" in response.json()["detail"]

    def test_unexpected_download_error_returns_500(self):
        response = self._post_with_download_error(RuntimeError("unexpected"))
        assert response.status_code == 500

    def test_500_detail_contains_conversion_failed(self):
        response = self._post_with_download_error(RuntimeError("boom"))
        assert "Conversion failed" in response.json()["detail"]


# ===========================================================================
# POST /convert – graceful degradation when a page fails
# ===========================================================================

class TestConvertPageProcessingDegradation:
    """
    When image_page_to_html raises for one page the endpoint should still
    return 200 and include an error placeholder in the HTML rather than
    crashing the whole request.
    """

    def _make_pdf_path(self):
        import tempfile as _tf
        tmp = _tf.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(b"%PDF stub")
        tmp.close()
        return Path(tmp.name)

    def test_page_failure_still_returns_200(self):
        mock_settings = _make_settings()
        mock_generator = MagicMock()
        mock_generator.image_page_to_html.side_effect = RuntimeError("LLM error")
        real_path = self._make_pdf_path()

        try:
            with (
                patch("src.pdf2html_api.main.get_settings", return_value=mock_settings),
                patch(
                    "src.pdf2html_api.main._download_pdf_from_url",
                    new=AsyncMock(return_value=real_path),
                ),
                patch(
                    "src.pdf2html_api.main.render_pdf_to_images",
                    return_value=(["page1.png"], MagicMock()),
                ),
                patch("src.pdf2html_api.main.HTMLGenerator", return_value=mock_generator),
                patch(
                    "src.pdf2html_api.main.merge_pages",
                    return_value="<!DOCTYPE html><html><body></body></html>",
                ),
            ):
                response = client.post(
                    "/convert", json={"pdf_url": "https://example.com/test.pdf"}
                )
        finally:
            real_path.unlink(missing_ok=True)

        assert response.status_code == 200

    def test_page_failure_placeholder_passed_to_merge(self):
        mock_settings = _make_settings()
        mock_generator = MagicMock()
        mock_generator.image_page_to_html.side_effect = RuntimeError("LLM error")
        captured_pages = []
        real_path = self._make_pdf_path()

        def capture_merge(pages, mode):
            captured_pages.extend(pages)
            return "<!DOCTYPE html><html><body></body></html>"

        try:
            with (
                patch("src.pdf2html_api.main.get_settings", return_value=mock_settings),
                patch(
                    "src.pdf2html_api.main._download_pdf_from_url",
                    new=AsyncMock(return_value=real_path),
                ),
                patch(
                    "src.pdf2html_api.main.render_pdf_to_images",
                    return_value=(["page1.png"], MagicMock()),
                ),
                patch("src.pdf2html_api.main.HTMLGenerator", return_value=mock_generator),
                patch("src.pdf2html_api.main.merge_pages", side_effect=capture_merge),
            ):
                client.post("/convert", json={"pdf_url": "https://example.com/test.pdf"})
        finally:
            real_path.unlink(missing_ok=True)

        assert len(captured_pages) == 1
        assert "ocr-uncertain" in captured_pages[0]
        assert "Error processing page 1" in captured_pages[0]


# ===========================================================================
# POST /convert/html – raw HTML response variant
# ===========================================================================

class TestConvertHtmlEndpoint:
    def test_status_code_is_200(self):
        stack, _, _, _ = _patch_happy_path()
        with stack:
            response = client.post(
                "/convert/html", json={"pdf_url": "https://example.com/test.pdf"}
            )
        assert response.status_code == 200

    def test_content_type_is_text_html(self):
        stack, _, _, _ = _patch_happy_path()
        with stack:
            response = client.post(
                "/convert/html", json={"pdf_url": "https://example.com/test.pdf"}
            )
        assert "text/html" in response.headers["content-type"]

    def test_response_body_contains_doctype(self):
        stack, _, _, _ = _patch_happy_path()
        with stack:
            response = client.post(
                "/convert/html", json={"pdf_url": "https://example.com/test.pdf"}
            )
        assert "<!DOCTYPE html>" in response.text

    def test_invalid_css_mode_returns_500(self):
        # Same characterization as /convert: HTTPException(400) is caught by
        # the outer except-Exception and re-raised as HTTPException(500)
        import tempfile as _tf
        tmp = _tf.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(b"%PDF stub")
        tmp.close()
        real_path = Path(tmp.name)
        try:
            mock_settings = _make_settings()
            with (
                patch("src.pdf2html_api.main.get_settings", return_value=mock_settings),
                patch(
                    "src.pdf2html_api.main._download_pdf_from_url",
                    new=AsyncMock(return_value=real_path),
                ),
            ):
                response = client.post(
                    "/convert/html",
                    json={"pdf_url": "https://example.com/test.pdf", "css_mode": "nope"},
                )
        finally:
            real_path.unlink(missing_ok=True)
        assert response.status_code == 500

    def test_missing_url_returns_422(self):
        assert client.post("/convert/html", json={}).status_code == 422

    def test_download_failure_returns_500(self):
        mock_settings = _make_settings()
        with (
            patch("src.pdf2html_api.main.get_settings", return_value=mock_settings),
            patch(
                "src.pdf2html_api.main._download_pdf_from_url",
                new=AsyncMock(side_effect=RuntimeError("network error")),
            ),
        ):
            response = client.post(
                "/convert/html", json={"pdf_url": "https://example.com/test.pdf"}
            )
        assert response.status_code == 500

    def test_multi_page_returns_200(self):
        stack, _, _, _ = _patch_happy_path(num_pages=2)
        with stack:
            response = client.post(
                "/convert/html", json={"pdf_url": "https://example.com/test.pdf"}
            )
        assert response.status_code == 200

    def test_html_endpoint_parameters_applied(self):
        stack, mock_settings, _, _ = _patch_happy_path()
        with stack:
            client.post(
                "/convert/html",
                json={"pdf_url": "https://example.com/test.pdf", "dpi": 150},
            )
        assert mock_settings.dpi == 150


# ===========================================================================
# _download_pdf_from_url – unit tests (async)
# ===========================================================================

class TestDownloadPdfFromUrl:
    """
    Tests for the private helper that downloads a PDF from a URL to a
    temporary file.  Uses httpx's MockTransport to simulate HTTP responses.
    """

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_success_returns_path(self):
        pdf_bytes = b"%PDF-1.4 fake pdf content"
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=pdf_bytes,
                headers={"content-type": "application/pdf"},
            )
        )
        with patch("src.pdf2html_api.main.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = pdf_bytes
            mock_response.headers = {"content-type": "application/pdf"}
            mock_response.raise_for_status = MagicMock()
            mock_async_client.__aenter__.return_value = mock_async_client
            mock_async_client.__aexit__.return_value = False
            mock_async_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_async_client

            result = self._run(_download_pdf_from_url("https://example.com/doc.pdf"))

        assert isinstance(result, Path)
        assert result.suffix == ".pdf"
        assert result.exists()
        result.unlink()  # cleanup

    def test_success_file_contains_pdf_content(self):
        pdf_bytes = b"%PDF-1.4 fake pdf content"
        with patch("src.pdf2html_api.main.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = pdf_bytes
            mock_response.headers = {"content-type": "application/pdf"}
            mock_response.raise_for_status = MagicMock()
            mock_async_client.__aenter__.return_value = mock_async_client
            mock_async_client.__aexit__.return_value = False
            mock_async_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_async_client

            result = self._run(_download_pdf_from_url("https://example.com/doc.pdf"))

        assert result.read_bytes() == pdf_bytes
        result.unlink()

    def test_non_pdf_content_type_raises_500(self):
        """
        Characterization: the HTTPException(400) raised for non-PDF content is
        caught by the outer `except Exception` handler inside
        _download_pdf_from_url and re-raised as HTTPException(500).
        """
        from fastapi import HTTPException

        with patch("src.pdf2html_api.main.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = b"<html>not a pdf</html>"
            mock_response.headers = {"content-type": "text/html"}
            mock_response.raise_for_status = MagicMock()
            mock_async_client.__aenter__.return_value = mock_async_client
            mock_async_client.__aexit__.return_value = False
            mock_async_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_async_client

            with pytest.raises(HTTPException) as exc_info:
                self._run(_download_pdf_from_url("https://example.com/page"))

        assert exc_info.value.status_code == 500
        assert "URL does not point to a PDF file" in exc_info.value.detail

    def test_url_ending_in_pdf_bypasses_content_type_check(self):
        """A .pdf URL suffix is accepted even if Content-Type is octet-stream."""
        pdf_bytes = b"%PDF-1.4 content"
        with patch("src.pdf2html_api.main.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = pdf_bytes
            mock_response.headers = {"content-type": "application/octet-stream"}
            mock_response.raise_for_status = MagicMock()
            mock_async_client.__aenter__.return_value = mock_async_client
            mock_async_client.__aexit__.return_value = False
            mock_async_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_async_client

            result = self._run(
                _download_pdf_from_url("https://example.com/document.pdf")
            )

        assert result.exists()
        result.unlink()

    def test_http_status_error_raises_400(self):
        from fastapi import HTTPException

        with patch("src.pdf2html_api.main.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            error_response = MagicMock()
            error_response.status_code = 404
            http_error = httpx.HTTPStatusError(
                "Not found", request=MagicMock(), response=error_response
            )
            mock_async_client.__aenter__.return_value = mock_async_client
            mock_async_client.__aexit__.return_value = False
            mock_async_client.get = AsyncMock(side_effect=http_error)
            mock_client_cls.return_value = mock_async_client

            with pytest.raises(HTTPException) as exc_info:
                self._run(_download_pdf_from_url("https://example.com/missing.pdf"))

        assert exc_info.value.status_code == 400
        assert "404" in exc_info.value.detail

    def test_request_error_raises_400(self):
        from fastapi import HTTPException

        with patch("src.pdf2html_api.main.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            mock_async_client.__aenter__.return_value = mock_async_client
            mock_async_client.__aexit__.return_value = False
            mock_async_client.get = AsyncMock(
                side_effect=httpx.ConnectError("connection refused")
            )
            mock_client_cls.return_value = mock_async_client

            with pytest.raises(HTTPException) as exc_info:
                self._run(_download_pdf_from_url("https://example.com/test.pdf"))

        assert exc_info.value.status_code == 400

    def test_unexpected_error_raises_500(self):
        from fastapi import HTTPException

        with patch("src.pdf2html_api.main.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            mock_async_client.__aenter__.return_value = mock_async_client
            mock_async_client.__aexit__.return_value = False
            mock_async_client.get = AsyncMock(side_effect=MemoryError("oom"))
            mock_client_cls.return_value = mock_async_client

            with pytest.raises(HTTPException) as exc_info:
                self._run(_download_pdf_from_url("https://example.com/test.pdf"))

        assert exc_info.value.status_code == 500

    def test_raise_for_status_is_called(self):
        pdf_bytes = b"%PDF-1.4 content"
        with patch("src.pdf2html_api.main.httpx.AsyncClient") as mock_client_cls:
            mock_async_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = pdf_bytes
            mock_response.headers = {"content-type": "application/pdf"}
            mock_response.raise_for_status = MagicMock()
            mock_async_client.__aenter__.return_value = mock_async_client
            mock_async_client.__aexit__.return_value = False
            mock_async_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_async_client

            result = self._run(
                _download_pdf_from_url("https://example.com/document.pdf")
            )

        mock_response.raise_for_status.assert_called_once()
        result.unlink()


# ===========================================================================
# _convert_pages_parallel – unit tests (async)
# ===========================================================================

class TestConvertPagesParallel:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _make_generator(self, *pages):
        gen = MagicMock()
        gen.image_page_to_html.side_effect = list(pages)
        return gen

    def test_single_page_returns_list_of_one(self):
        gen = self._make_generator('<section class="page">P1</section>')
        result = self._run(
            _convert_pages_parallel(gen, ["img1.png"], "grid", "req_test", 1)
        )
        assert len(result) == 1

    def test_multi_page_returns_correct_count(self):
        pages = [f'<section class="page">P{i}</section>' for i in range(4)]
        gen = self._make_generator(*pages)
        result = self._run(
            _convert_pages_parallel(gen, ["img1.png", "img2.png", "img3.png", "img4.png"], "grid", "req_test", 2)
        )
        assert len(result) == 4

    def test_page_order_preserved(self):
        pages = [f'<section class="page">Page{i}</section>' for i in range(3)]
        gen = MagicMock()
        # Return pages in order, thread-safe via side_effect list
        call_count = [0]
        lock_results = pages[:]

        def side_effect(image_path, css_mode):
            # Identify page by index from path
            idx = int(image_path.replace("img", "").replace(".png", ""))
            return f'<section class="page">Page{idx}</section>'

        gen.image_page_to_html.side_effect = side_effect
        result = self._run(
            _convert_pages_parallel(
                gen,
                ["img0.png", "img1.png", "img2.png"],
                "grid",
                "req_test",
                3,
            )
        )
        assert result[0] == '<section class="page">Page0</section>'
        assert result[1] == '<section class="page">Page1</section>'
        assert result[2] == '<section class="page">Page2</section>'

    def test_exception_in_page_replaced_with_placeholder(self):
        gen = MagicMock()
        gen.image_page_to_html.side_effect = RuntimeError("llm failed")
        result = self._run(
            _convert_pages_parallel(gen, ["img1.png"], "grid", "req_test", 1)
        )
        assert len(result) == 1
        assert "ocr-uncertain" in result[0]
        assert "Error processing page 1" in result[0]

    def test_partial_page_failure_does_not_drop_successful_pages(self):
        """Two pages: first succeeds, second fails. Both entries survive."""

        def side_effect(path, css_mode):
            if "img1" in path:
                return '<section class="page">OK</section>'
            raise RuntimeError("page 2 failed")

        gen = MagicMock()
        gen.image_page_to_html.side_effect = side_effect
        result = self._run(
            _convert_pages_parallel(
                gen, ["img1.png", "img2.png"], "grid", "req_test", 2
            )
        )
        assert len(result) == 2
        assert result[0] == '<section class="page">OK</section>'
        assert "ocr-uncertain" in result[1]

    def test_css_mode_forwarded_to_generator(self):
        gen = MagicMock()
        gen.image_page_to_html.return_value = '<section class="page">x</section>'
        self._run(
            _convert_pages_parallel(gen, ["img1.png"], "columns", "req_test", 1)
        )
        gen.image_page_to_html.assert_called_once_with("img1.png", "columns")


# ===========================================================================
# _cleanup_files – unit tests
# ===========================================================================

class TestCleanupFiles:
    def test_pdf_file_is_deleted(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = Path(f.name)

        assert pdf_path.exists()
        _cleanup_files(pdf_path, [], MagicMock())
        assert not pdf_path.exists()

    def test_cleanup_temp_images_is_called(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = Path(f.name)

        image_paths = ["/tmp/img1.png", "/tmp/img2.png"]
        mock_temp_dir = MagicMock()

        with patch("src.pdf2html_api.main.cleanup_temp_images") as mock_cleanup:
            _cleanup_files(pdf_path, image_paths, mock_temp_dir)
            mock_cleanup.assert_called_once_with(image_paths, mock_temp_dir)

    def test_missing_pdf_does_not_raise(self):
        """Cleanup should be idempotent if PDF was already removed."""
        phantom = Path("/tmp/does_not_exist_xyz.pdf")
        assert not phantom.exists()
        # Should not raise
        _cleanup_files(phantom, [], MagicMock())

    def test_cleanup_temp_images_exception_is_swallowed(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = Path(f.name)

        with patch(
            "src.pdf2html_api.main.cleanup_temp_images",
            side_effect=RuntimeError("disk error"),
        ):
            # Must not raise
            _cleanup_files(pdf_path, [], MagicMock())


# ===========================================================================
# PDFRequest model validation
# ===========================================================================

class TestPDFRequestModel:
    """
    Characterize the default values and validation of the PDFRequest Pydantic
    model – these are visible in the API contract.
    """

    def test_default_model_is_gpt_4o_mini(self):
        from src.pdf2html_api.main import PDFRequest
        req = PDFRequest(pdf_url="https://example.com/test.pdf")
        assert req.model == "gpt-4o-mini"

    def test_default_dpi_is_200(self):
        from src.pdf2html_api.main import PDFRequest
        req = PDFRequest(pdf_url="https://example.com/test.pdf")
        assert req.dpi == 200

    def test_default_max_tokens_is_4000(self):
        from src.pdf2html_api.main import PDFRequest
        req = PDFRequest(pdf_url="https://example.com/test.pdf")
        assert req.max_tokens == 4000

    def test_default_temperature_is_0(self):
        from src.pdf2html_api.main import PDFRequest
        req = PDFRequest(pdf_url="https://example.com/test.pdf")
        assert req.temperature == 0.0

    def test_default_css_mode_is_grid(self):
        from src.pdf2html_api.main import PDFRequest
        req = PDFRequest(pdf_url="https://example.com/test.pdf")
        assert req.css_mode == "grid"

    def test_default_max_parallel_workers_is_3(self):
        from src.pdf2html_api.main import PDFRequest
        req = PDFRequest(pdf_url="https://example.com/test.pdf")
        assert req.max_parallel_workers == 3


# ===========================================================================
# PDFResponse model validation
# ===========================================================================

class TestPDFResponseModel:
    def test_response_schema_fields(self):
        from src.pdf2html_api.main import PDFResponse
        resp = PDFResponse(
            html="<html/>",
            pages_processed=2,
            model_used="gpt-4o-mini",
            css_mode="grid",
        )
        assert resp.html == "<html/>"
        assert resp.pages_processed == 2
        assert resp.model_used == "gpt-4o-mini"
        assert resp.css_mode == "grid"


# ===========================================================================
# App metadata characterization
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
