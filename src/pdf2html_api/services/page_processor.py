"""Service for converting PDF page images to HTML."""

import asyncio
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List

logger = logging.getLogger(__name__)

_ERROR_PLACEHOLDER = (
    '<section class="page">'
    '<p class="ocr-uncertain">[Error processing page {index}: {error}]</p>'
    "</section>"
)


class PageProcessor:
    """
    Converts a list of page-image paths to HTML strings.

    For a single page the conversion runs inline in the event loop.
    For multiple pages a ThreadPoolExecutor is used so that blocking
    OpenAI calls run concurrently without blocking the async event loop.
    """

    async def process_pages(
        self,
        html_generator,
        image_paths: List,
        css_mode: str,
        request_id: str,
        max_workers: int = 3,
    ) -> List[str]:
        """
        Convert every page image to HTML, preserving order.

        Args:
            html_generator: An HTMLGenerator instance.
            image_paths:    Ordered list of image file paths.
            css_mode:       CSS layout mode passed to the generator.
            request_id:     Identifier used for correlated log lines.
            max_workers:    Maximum parallel threads when len(image_paths) > 1.

        Returns:
            Ordered list of HTML strings, one per page.
            A page that raises an exception is replaced with an error placeholder
            instead of aborting the whole conversion.
        """
        total = len(image_paths)

        if total == 1:
            return [
                self._convert_page(
                    html_generator, image_paths[0], 0, total, css_mode, request_id
                )
            ]

        logger.info(
            f"[{request_id}] Starting parallel processing: "
            f"{total} pages, {max_workers} workers"
        )
        return await self._process_parallel(
            html_generator, image_paths, css_mode, request_id, max_workers
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _process_parallel(
        self,
        html_generator,
        image_paths: List,
        css_mode: str,
        request_id: str,
        max_workers: int,
    ) -> List[str]:
        """Submit all pages to a thread pool and gather results in order."""
        loop = asyncio.get_event_loop()
        total = len(image_paths)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                loop.run_in_executor(
                    executor,
                    self._convert_page,
                    html_generator,
                    path,
                    index,
                    total,
                    css_mode,
                    request_id,
                )
                for index, path in enumerate(image_paths)
            ]
            results = await asyncio.gather(*futures, return_exceptions=True)

        page_html_list: List[str] = []
        for index, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"[{request_id}] Page {index + 1} raised exception: {result}"
                )
                page_html_list.append(
                    _ERROR_PLACEHOLDER.format(index=index + 1, error=result)
                )
            else:
                page_html_list.append(result)

        logger.info(f"[{request_id}] Parallel processing complete for {total} pages")
        return page_html_list

    def _convert_page(
        self,
        html_generator,
        image_path,
        page_index: int,
        total_pages: int,
        css_mode: str,
        request_id: str,
    ) -> str:
        """Convert a single page; return an error placeholder on failure."""
        page_num = page_index + 1
        start = time.time()
        logger.info(f"[{request_id}] Processing page {page_num}/{total_pages}…")

        try:
            html = html_generator.image_page_to_html(image_path, css_mode)
            elapsed = time.time() - start
            logger.info(
                f"[{request_id}] Page {page_num} done in {elapsed:.3f}s "
                f"({len(html)} chars)"
            )
            return html
        except Exception as exc:
            elapsed = time.time() - start
            logger.error(
                f"[{request_id}] Page {page_num} failed after {elapsed:.3f}s: {exc}"
            )
            return _ERROR_PLACEHOLDER.format(index=page_num, error=exc)
