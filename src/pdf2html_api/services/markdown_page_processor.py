"""Service for converting PDF page images to Markdown."""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

logger = logging.getLogger(__name__)

_ERROR_PLACEHOLDER = "<!-- Page conversion error: Page {index}: {error} -->"


class MarkdownPageProcessor:
    """Convert a list of page-image paths to Markdown strings.

    Single-page PDFs are converted inline to avoid threading overhead.
    Multi-page PDFs use a ThreadPoolExecutor so that blocking OpenAI
    calls run concurrently without stalling the async event loop.
    """

    async def process_pages(
        self,
        markdown_generator,
        image_paths: List,
        request_id: str,
        max_workers: int = 3,
    ) -> List[str]:
        """Convert every page image to Markdown, preserving order.

        Args:
            markdown_generator: A MarkdownGenerator instance.
            image_paths:        Ordered list of image file paths.
            request_id:         Identifier used for correlated log lines.
            max_workers:        Maximum parallel threads when len > 1.

        Returns:
            Ordered list of Markdown strings, one per page.
            A page that raises an exception is replaced with an error
            placeholder instead of aborting the whole conversion.
        """
        total = len(image_paths)

        if total == 1:
            return [self._convert_page(markdown_generator, image_paths[0], 0, total, request_id)]

        logger.info(
            f"[{request_id}] Starting parallel Markdown processing: "
            f"{total} pages, {max_workers} workers"
        )
        return await self._process_parallel(
            markdown_generator, image_paths, request_id, max_workers
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _process_parallel(
        self,
        markdown_generator,
        image_paths: List,
        request_id: str,
        max_workers: int,
    ) -> List[str]:
        loop = asyncio.get_event_loop()
        total = len(image_paths)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                loop.run_in_executor(
                    executor,
                    self._convert_page,
                    markdown_generator,
                    path,
                    index,
                    total,
                    request_id,
                )
                for index, path in enumerate(image_paths)
            ]
            results = await asyncio.gather(*futures, return_exceptions=True)

        page_md_list: List[str] = []
        for index, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[{request_id}] Page {index + 1} raised exception: {result}")
                page_md_list.append(
                    _ERROR_PLACEHOLDER.format(index=index + 1, error=result)
                )
            else:
                page_md_list.append(result)

        logger.info(f"[{request_id}] Parallel Markdown processing complete for {total} pages")
        return page_md_list

    def _convert_page(
        self,
        markdown_generator,
        image_path,
        page_index: int,
        total_pages: int,
        request_id: str,
    ) -> str:
        page_num = page_index + 1
        start = time.time()
        logger.info(f"[{request_id}] Processing page {page_num}/{total_pages} (Markdown)…")

        try:
            md = markdown_generator.image_page_to_markdown(image_path)
            elapsed = time.time() - start
            logger.info(
                f"[{request_id}] Page {page_num} done in {elapsed:.3f}s ({len(md)} chars)"
            )
            return md
        except Exception as exc:
            elapsed = time.time() - start
            logger.error(
                f"[{request_id}] Page {page_num} failed after {elapsed:.3f}s: {exc}"
            )
            return _ERROR_PLACEHOLDER.format(index=page_num, error=exc)
