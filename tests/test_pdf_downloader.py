"""
Tests for src/pdf2html_api/services/pdf_downloader.py

Coverage
--------
- PDFDownloader.download  (all success / error branches)
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.pdf2html_api.services.pdf_downloader import PDFDownloader


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
