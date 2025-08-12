"""Smoke tests for PDF2HTML CLI."""

import pytest

from pdf2html_api.html_merge import merge_pages


def test_import_main():
    """Test that the main module can be imported."""
    from pdf2html_api import main

    assert main.app is not None


def test_import_config():
    """Test that the config module can be imported."""
    from pdf2html_api import config

    assert config.get_settings is not None


def test_import_pdf_to_images():
    """Test that the PDF to images module can be imported."""
    from pdf2html_api import pdf_to_images

    assert pdf_to_images.render_pdf_to_images is not None


def test_import_llm():
    """Test that the LLM module can be imported."""
    from pdf2html_api import llm

    assert llm.HTMLGenerator is not None


def test_import_html_merge():
    """Test that the HTML merge module can be imported."""
    from pdf2html_api import html_merge

    assert html_merge.merge_pages is not None


def test_merge_pages_grid_mode():
    """Test HTML merge functionality with grid mode."""
    page_html_list = [
        '<section class="page"><h1>Page 1</h1><p>Content from page 1.</p></section>',
        '<section class="page"><h2>Page 2</h2><p>Content from page 2.</p></section>',
    ]

    result = merge_pages(page_html_list, "grid")

    # Check that the result is a complete HTML document
    assert "<!DOCTYPE html>" in result
    assert "<html" in result
    assert "<head>" in result
    assert "<body>" in result
    assert '<main class="document">' in result

    # Check that page content is included
    assert "Page 1" in result
    assert "Page 2" in result
    assert "Content from page 1" in result
    assert "Content from page 2" in result

    # Check that grid CSS is included
    assert ".grid-2col" in result
    assert "display: grid" in result


def test_merge_pages_columns_mode():
    """Test HTML merge functionality with columns mode."""
    page_html_list = [
        '<section class="page"><h1>Page 1</h1><p>Content from page 1.</p></section>',
    ]

    result = merge_pages(page_html_list, "columns")

    # Check that the result is a complete HTML document
    assert "<!DOCTYPE html>" in result
    assert "<html" in result
    assert "<head>" in result
    assert "<body>" in result

    # Check that page content is included
    assert "Page 1" in result
    assert "Content from page 1" in result

    # Check that columns CSS is included
    assert ".columns-2" in result
    assert "column-count: 2" in result


def test_merge_pages_empty_list():
    """Test HTML merge with empty page list."""
    result = merge_pages([], "grid")

    # Should still produce valid HTML
    assert "<!DOCTYPE html>" in result
    assert "<html" in result
    assert '<main class="document">' in result
    assert "</main>" in result


def test_merge_pages_single_page():
    """Test HTML merge with single page."""
    page_html_list = [
        '<section class="page">'
        "<h1>Single Page</h1>"
        "<p>This is a single page document.</p>"
        "</section>",
    ]

    result = merge_pages(page_html_list, "grid")

    assert "Single Page" in result
    assert "This is a single page document" in result
    assert result.count('<section class="page">') == 1


if __name__ == "__main__":
    pytest.main([__file__])
