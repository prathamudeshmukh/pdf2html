"""Service for downloading PDF files from remote URLs."""

import tempfile
import time
import logging
from pathlib import Path

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class PDFDownloader:
    """Handles downloading PDF files from remote URLs to temporary files."""

    _TIMEOUT_SECONDS = 120.0

    async def download(self, url: str) -> Path:
        """
        Download a PDF from *url* and write it to a temporary file.

        Args:
            url: HTTP/HTTPS URL pointing to a PDF file.

        Returns:
            Path to the downloaded file (caller is responsible for deletion).

        Raises:
            HTTPException 400: URL returns a non-200 status or non-PDF content.
            HTTPException 500: Unexpected error during download.
        """
        start = time.time()
        logger.info(f"Downloading PDF from: {url}")

        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT_SECONDS) as client:
                response = await client.get(url)
                response.raise_for_status()
                self._validate_pdf_response(response, url)

                content = response.content
                logger.info(
                    f"Received {len(content)} bytes "
                    f"(content-type: {response.headers.get('content-type', 'unknown')}) "
                    f"in {time.time() - start:.3f}s"
                )
                return self._write_to_temp_file(content)

        except httpx.HTTPStatusError as exc:
            logger.error(
                f"HTTP {exc.response.status_code} downloading PDF "
                f"after {time.time() - start:.3f}s"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Failed to download PDF: HTTP {exc.response.status_code}",
            ) from exc

        except httpx.RequestError as exc:
            logger.error(f"Request error after {time.time() - start:.3f}s: {exc}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to download PDF: {exc}",
            ) from exc

        except HTTPException:
            raise

        except Exception as exc:
            logger.error(f"Unexpected download error after {time.time() - start:.3f}s: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error downloading PDF: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_pdf_response(self, response: httpx.Response, url: str) -> None:
        """Raise HTTPException(400) if the response does not appear to be a PDF."""
        content_type = response.headers.get("content-type", "").lower()
        is_pdf_content_type = "pdf" in content_type
        is_pdf_url = url.lower().endswith(".pdf")

        if not is_pdf_content_type and not is_pdf_url:
            raise HTTPException(
                status_code=400,
                detail="URL does not point to a PDF file",
            )

    def _write_to_temp_file(self, content: bytes) -> Path:
        """Persist *content* to a temporary .pdf file and return its path."""
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, mode="wb")
        tmp.write(content)
        tmp.close()
        return Path(tmp.name)
