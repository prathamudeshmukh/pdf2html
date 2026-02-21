"""Orchestrates the full PDF-to-HTML conversion pipeline."""

import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List



from ..config import Settings
from ..html_merge import merge_pages
from ..pdf_to_images import render_pdf_to_images
from .pdf_downloader import PDFDownloader
from .page_processor import PageProcessor
from .settings_configurator import SettingsConfigurator
from .css_mode_validator import CSSModeValidator
from .html_generator_factory import HTMLGeneratorFactory

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
    Coordinates the PDF-to-HTML conversion process using injected helpers.
    """
    def __init__(self, request) -> None:
        self._request = request
        self._settings: Settings = SettingsConfigurator.configure(request)
        self._downloader = PDFDownloader()
        self._page_processor = PageProcessor()

    async def execute(self, request_id: str) -> ConversionResult:
        CSSModeValidator.validate(self._settings.css_mode)

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

        html_generator = HTMLGeneratorFactory.build(self._settings)
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
