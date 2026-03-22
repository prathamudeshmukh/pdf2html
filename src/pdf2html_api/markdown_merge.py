"""Merge per-page Markdown fragments into a single document."""

import logging
from typing import List

logger = logging.getLogger(__name__)

_PAGE_SEPARATOR = "\n\n---\n\n"


def merge_markdown_pages(page_md_list: List[str]) -> str:
    """Merge a list of per-page Markdown strings into one document.

    Pages are joined with a horizontal-rule separator (``---``) so that
    page boundaries are visible in the output.

    Args:
        page_md_list: Ordered list of Markdown strings, one per page.

    Returns:
        A single Markdown string representing the full document, or an
        empty string when ``page_md_list`` is empty.
    """
    if not page_md_list:
        return ""

    stripped = [page.strip() for page in page_md_list]
    merged = _PAGE_SEPARATOR.join(stripped)

    logger.info(
        f"Merged {len(page_md_list)} page(s) into {len(merged)} chars of Markdown"
    )
    return merged
