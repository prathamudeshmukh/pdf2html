"""Orchestrates the full PDF-to-HTML conversion pipeline."""

import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from ..config import get_settings, Settings
from ..html_merge import merge_pages
from ..llm import HTMLGenerator
from ..pdf_to_images import render_pdf_to_images
from .pdf_downloader import PDFDownloader
from .page_processor import PageProcessor

logger = logging.getLogger(__name__)

_VALID_CSS_MODES = frozenset({"grid", "columns", "single"})


@dataclass
class ConversionArtifacts:
    """Temporary resources created during conversion that require cleanup."""

    pdf_path: Path
    image_paths: List
    temp_dir: object  # tempfile.TemporaryDirectory


@dataclass
class ConversionResult:
    """Output of the conversion pipeline."""

    html: str
    pages_processed: int
    model_used: str
    css_mode: str
    artifacts: ConversionArtifacts = field(repr=False)


class ConversionPipeline:
    """
    Orchestrates all stages of PDF-to-HTML conversion:

    1. Validate + configure settings from the HTTP request.
    2. Download the PDF via PDFDownloader.
    3. Render pages to images via pdf_to_images.
    4. Generate per-page HTML via HTMLGenerator + PageProcessor.
    5. Merge HTML fragments into a complete document.

    The pipeline does *not* schedule cleanup; callers receive
    ConversionArtifacts and decide when to clean up (e.g., as a
    FastAPI background task).
    """

    def __init__(self, request) -> None:
        """Build and configure the pipeline for *request*."""
        self._request = request
        self._settings: Settings = self._configure_settings(request)
        self._downloader = PDFDownloader()
        self._page_processor = PageProcessor()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(self, request_id: str) -> ConversionResult:
        """
        Run the conversion pipeline end-to-end.

        Args:
            request_id: Correlation token used in log messages.

        Returns:
            ConversionResult with HTML content and temporary artifacts.

        Raises:
            ValueError:    Invalid css_mode.
            HTTPException: Raised by PDFDownloader on network failures.
        """
        self._validate_css_mode()

        total_start = time.time()
        logger.info(
            f"[{request_id}] Conversion pipeline started for: {self._request.pdf_url}"
        )

        pdf_path = await self._downloader.download(str(self._request.pdf_url))
        logger.info(
            f"[{request_id}] PDF downloaded "
            f"({pdf_path.stat().st_size / 1024:.1f} KB)"
        )

        image_paths, temp_dir = render_pdf_to_images(pdf_path, self._settings.dpi)
        logger.info(f"[{request_id}] Rendered {len(image_paths)} page image(s)")

        html_generator = self._build_html_generator()
        page_html_list = await self._page_processor.process_pages(
            html_generator,
            image_paths,
            self._settings.css_mode,
            request_id,
            self._settings.max_parallel_workers,
        )

        final_html = merge_pages(page_html_list, self._settings.css_mode)
        elapsed = time.time() - total_start
        logger.info(
            f"[{request_id}] Pipeline complete in {elapsed:.3f}s "
            f"({len(page_html_list)} page(s), {len(final_html)} chars)"
        )

        return ConversionResult(
            html=final_html,
            pages_processed=len(page_html_list),
            model_used=self._settings.model,
            css_mode=self._settings.css_mode,
            artifacts=ConversionArtifacts(
                pdf_path=pdf_path,
                image_paths=image_paths,
                temp_dir=temp_dir,
            ),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _configure_settings(self, request) -> Settings:
        """Load base settings and apply per-request overrides."""
        settings = get_settings()
        settings.model = request.model
        settings.dpi = request.dpi
        settings.max_tokens = request.max_tokens
        settings.temperature = request.temperature
        settings.max_parallel_workers = request.max_parallel_workers
        settings.css_mode = request.css_mode
        return settings

    def _validate_css_mode(self) -> None:
        """Raise ValueError if the configured css_mode is not supported."""
        if self._settings.css_mode not in _VALID_CSS_MODES:
            raise ValueError(
                f"CSS mode must be one of {sorted(_VALID_CSS_MODES)}, "
                f"got '{self._settings.css_mode}'"
            )

    def _build_html_generator(self) -> HTMLGenerator:
        return HTMLGenerator(
            api_key=self._settings.openai_api_key,
            model=self._settings.model,
            max_tokens=self._settings.max_tokens,
            temperature=self._settings.temperature,
        )
