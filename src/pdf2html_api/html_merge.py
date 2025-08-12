"""Merge page HTML fragments into a complete HTML document."""

from typing import List, Literal


def merge_pages(
    page_html_list: List[str], css_mode: Literal["grid", "columns", "single"]
) -> str:
    """
    Merge page HTML fragments into a complete HTML document.

    Args:
        page_html_list: List of HTML strings for each page
        css_mode: CSS mode for layout styling

    Returns:
        Complete HTML document string
    """
    # Generate CSS based on mode
    css = _generate_css(css_mode)

    # Combine all page HTML
    pages_html = "\n".join(page_html_list)

    # Create complete HTML document
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

    return html_document


def _generate_css(css_mode: Literal["grid", "columns", "single"]) -> str:
    """
    Generate CSS styles based on the selected mode.

    Args:
        css_mode: CSS mode for layout styling

    Returns:
        CSS string
    """
    base_css = """/* Base typography and layout */
body {
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI',
                 Roboto, sans-serif;
    line-height: 1.6;
    color: #333;
    margin: 0;
    padding: 0;
    background-color: #fff;
}

.document {
    width: min(900px, 90vw);
    margin: 24px auto;
    padding: 0 16px;
}

.page {
    margin: 0 0 32px;
    page-break-after: always;
    page-break-inside: avoid;
}

/* Section-based layout support */
.page-section {
    margin: 1em 0;
    padding: 0.5em 0;
}

.page-section:first-child {
    margin-top: 0;
}

.page-section:last-child {
    margin-bottom: 0;
}

/* Typography */
h1, h2, h3, h4, h5, h6 {
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    font-weight: 600;
    line-height: 1.3;
}

h1 { font-size: 2em; }
h2 { font-size: 1.5em; }
h3 { font-size: 1.25em; }
h4 { font-size: 1.1em; }
h5 { font-size: 1em; }
h6 { font-size: 0.9em; }

p {
    margin: 0 0 1em;
    text-align: justify;
}

/* Lists */
ul, ol {
    margin: 1em 0;
    padding-left: 2em;
}

li {
    margin: 0.25em 0;
}

/* Tables */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
    font-size: 0.9em;
}

th, td {
    border: 1px solid #ddd;
    padding: 8px 12px;
    text-align: left;
    vertical-align: top;
}

th {
    background-color: #f6f6f6;
    font-weight: 600;
}

/* Images and figures */
img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1em auto;
}

figure {
    margin: 1em 0;
    text-align: center;
}

figcaption {
    font-size: 0.9em;
    color: #666;
    margin-top: 0.5em;
    font-style: italic;
}

/* Special classes */
.ocr-uncertain {
    color: #888;
    font-style: italic;
    background-color: #f9f9f9;
    padding: 2px 4px;
    border-radius: 3px;
}

/* Links */
a {
    color: #0066cc;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

/* Print styles */
@media print {
    .page {
        page-break-after: always;
        margin: 0;
    }
    .document {
        width: 100%;
        margin: 0;
        padding: 0;
    }
}"""

    if css_mode == "grid":
        grid_css = """
/* CSS Grid layout helpers */
.grid-2col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    align-items: start;
}

.grid-3col {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 16px;
    align-items: start;
}

@media (max-width: 768px) {
    .grid-2col,
    .grid-3col {
        grid-template-columns: 1fr;
        gap: 8px;
    }
}"""
        return base_css + grid_css

    elif css_mode == "columns":
        columns_css = """
/* CSS Columns layout helpers */
.columns-2 {
    column-count: 2;
    column-gap: 24px;
    column-fill: balance;
}

.columns-3 {
    column-count: 3;
    column-gap: 24px;
    column-fill: balance;
}

/* Ensure proper breaks in columns */
.columns-2 h1,
.columns-2 h2,
.columns-2 h3,
.columns-3 h1,
.columns-3 h2,
.columns-3 h3 {
    break-inside: avoid;
    page-break-inside: avoid;
}

@media (max-width: 768px) {
    .columns-2,
    .columns-3 {
        column-count: 1;
        column-gap: 0;
    }
}"""
        return base_css + columns_css

    else:  # single mode
        return base_css
