"""Merge page HTML fragments into a complete HTML document."""

import time
import logging
from enum import Enum
from typing import List

from pdf2html_api.css_styles import BASE_CSS, COLUMNS_CSS, GRID_CSS

logger = logging.getLogger(__name__)


class CSSMode(str, Enum):
    """Supported CSS layout modes for the merged HTML document."""

    GRID = "grid"
    COLUMNS = "columns"
    SINGLE = "single"


def merge_pages(page_html_list: List[str], css_mode: CSSMode) -> str:
    """
    Merge page HTML fragments into a complete HTML document.
    
    Args:
        page_html_list: List of HTML strings for each page
        css_mode: CSS mode for layout styling
        
    Returns:
        Complete HTML document string
    """
    merge_start = time.time()
    logger.info(f"Starting HTML merge for {len(page_html_list)} pages, CSS mode: {css_mode}")
    
    # Generate CSS based on mode
    css_start = time.time()
    css = _generate_css(css_mode)
    css_time = time.time() - css_start
    logger.info(f"CSS generated in {css_time:.3f}s, length: {len(css)} chars")
    
    # Combine all page HTML
    combine_start = time.time()
    pages_html = "\n".join(page_html_list)
    combine_time = time.time() - combine_start
    logger.info(f"Pages combined in {combine_time:.3f}s, total HTML length: {len(pages_html)} chars")
    
    # Create complete HTML document
    document_start = time.time()
    html_document = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PDF to HTML Conversion</title>
    <style>
{css}
    </style>
</head>
<body>
    <main class="document">
{pages_html}
    </main>
</body>
</html>"""
    
    document_time = time.time() - document_start
    total_time = time.time() - merge_start
    
    logger.info(f"HTML document created in {document_time:.3f}s")
    logger.info(f"HTML merge completed in {total_time:.3f}s")
    logger.info(f"Final document size: {len(html_document)} chars")
    
    return html_document


def _generate_css(css_mode: CSSMode) -> str:
    """
    Generate CSS styles based on the selected mode.
    
    Args:
        css_mode: CSS mode for layout styling
        
    Returns:
        CSS string
    """
    base_css = BASE_CSS
    
    if css_mode == CSSMode.GRID:
        return base_css + GRID_CSS

    if css_mode == CSSMode.COLUMNS:
        return base_css + COLUMNS_CSS

    return base_css  # CSSMode.SINGLE 