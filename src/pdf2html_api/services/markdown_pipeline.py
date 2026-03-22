"""Orchestrates the full PDF-to-Markdown conversion pipeline."""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from ..config import get_settings, Settings
from ..markdown_merge import merge_markdown_pages
from ..pdf_to_images import render_pdf_to_images
from .pdf_downloader import PDFDownloader
from .markdown_page_processor import MarkdownPageProcessor
from .markdown_generator_factory import MarkdownGeneratorFactory

logger = logging.getLogger(__name__)


@dataclass
class MarkdownConversionArtifacts:
    """Temporary resources created during conversion that require cleanup."""

    pdf_path: Path
    image_paths: List
    temp_dir: object  # tempfile.TemporaryDirectory


@dataclass
class MarkdownConversionResult:
    """Output of the Markdown conversion pipeline."""

    markdown: str
    pages_processed: int
    model_used: str
    artifacts: MarkdownConversionArtifacts = field(repr=False)


def _configure_settings(request) -> Settings:
    """Merge request parameters into a fresh Settings instance."""
    settings = get_settings()
    settings.model = request.model
    settings.dpi = request.dpi
    settings.max_tokens = request.max_tokens
    settings.temperature = request.temperature
    settings.max_parallel_workers = request.max_parallel_workers
    return settings


class MarkdownConversionPipeline:
    """Coordinates the PDF-to-Markdown conversion process."""

    def __init__(self, request) -> None:
        self._request = request
        self._settings: Settings = _configure_settings(request)
        self._downloader = PDFDownloader()
        self._page_processor = MarkdownPageProcessor()

    async def execute(self, request_id: str) -> MarkdownConversionResult:
        total_start = time.time()
        logger.info(
            f"[{request_id}] Markdown pipeline started for: {self._request.pdf_url}"
        )

        pdf_path = await self._downloader.download(str(self._request.pdf_url))
        logger.info(
            f"[{request_id}] PDF downloaded ({pdf_path.stat().st_size / 1024:.1f} KB)"
        )

        image_paths, temp_dir = render_pdf_to_images(pdf_path, self._settings.dpi)
        logger.info(f"[{request_id}] Rendered {len(image_paths)} page image(s)")

        md_generator = MarkdownGeneratorFactory.build(self._settings)
        page_md_list = await self._page_processor.process_pages(
            md_generator,
            image_paths,
            request_id,
            self._settings.max_parallel_workers,
        )

        final_markdown = merge_markdown_pages(page_md_list)

        elapsed = time.time() - total_start
        logger.info(
            f"[{request_id}] Markdown pipeline complete in {elapsed:.3f}s "
            f"({len(page_md_list)} page(s), {len(final_markdown)} chars)"
        )

        return MarkdownConversionResult(
            markdown=final_markdown,
            pages_processed=len(page_md_list),
            model_used=self._settings.model,
            artifacts=MarkdownConversionArtifacts(
                pdf_path=pdf_path,
                image_paths=image_paths,
                temp_dir=temp_dir,
            ),
        )
