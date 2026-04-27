"""Tests for src/pdf2html_api/markdown_merge.py"""

import pytest

from src.pdf2html_api.markdown_merge import merge_markdown_pages


class TestMergeMarkdownPages:
    def test_single_page_returns_content_as_is(self):
        result = merge_markdown_pages(["# Hello\n\nSome text."])
        assert result == "# Hello\n\nSome text."

    def test_multiple_pages_joined_with_separator(self):
        result = merge_markdown_pages(["# Page 1", "# Page 2"])
        assert result == "# Page 1\n\n---\n\n# Page 2"

    def test_three_pages_two_separators(self):
        result = merge_markdown_pages(["Page 1", "Page 2", "Page 3"])
        assert result.count("---") == 2

    def test_empty_list_returns_empty_string(self):
        result = merge_markdown_pages([])
        assert result == ""

    def test_whitespace_stripped_per_page(self):
        result = merge_markdown_pages(["  # Page 1  ", "  # Page 2  "])
        assert result == "# Page 1\n\n---\n\n# Page 2"

    def test_order_preserved(self):
        pages = [f"# Page {i}" for i in range(5)]
        result = merge_markdown_pages(pages)
        parts = result.split("\n\n---\n\n")
        assert parts == pages
