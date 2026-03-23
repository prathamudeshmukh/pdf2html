"""Tests for src/pdf2html_api/services/markdown_page_processor.py"""

import asyncio
from unittest.mock import MagicMock

import pytest

from src.pdf2html_api.services.markdown_page_processor import MarkdownPageProcessor


def _run(coro):
    return asyncio.run(coro)


def _gen(*page_markdowns):
    g = MagicMock()
    g.image_page_to_markdown.side_effect = list(page_markdowns)
    return g


class TestMarkdownPageProcessor:
    def test_single_page_returns_list_of_one(self):
        g = _gen("# Page 1")
        result = _run(MarkdownPageProcessor().process_pages(g, ["img1.png"], "r", 1))
        assert len(result) == 1
        assert result[0] == "# Page 1"

    def test_multi_page_returns_correct_count(self):
        pages = [f"# Page {i}" for i in range(4)]
        g = _gen(*pages)
        result = _run(
            MarkdownPageProcessor().process_pages(
                g, ["i1.png", "i2.png", "i3.png", "i4.png"], "r", 2
            )
        )
        assert len(result) == 4

    def test_page_order_preserved(self):
        def side(path):
            idx = int(path.replace("img", "").replace(".png", ""))
            return f"# Page {idx}"

        g = MagicMock()
        g.image_page_to_markdown.side_effect = side
        result = _run(
            MarkdownPageProcessor().process_pages(
                g, ["img0.png", "img1.png", "img2.png"], "r", 3
            )
        )
        assert result[0] == "# Page 0"
        assert result[1] == "# Page 1"
        assert result[2] == "# Page 2"

    def test_exception_replaced_with_placeholder(self):
        g = MagicMock()
        g.image_page_to_markdown.side_effect = RuntimeError("llm failed")
        result = _run(MarkdownPageProcessor().process_pages(g, ["img1.png"], "r", 1))
        assert len(result) == 1
        assert "<!-- Page conversion error" in result[0]
        assert "1" in result[0]

    def test_partial_failure_does_not_drop_successful_pages(self):
        def side(path):
            if "img1" in path:
                return "# OK"
            raise RuntimeError("page 2 failed")

        g = MagicMock()
        g.image_page_to_markdown.side_effect = side
        result = _run(
            MarkdownPageProcessor().process_pages(g, ["img1.png", "img2.png"], "r", 2)
        )
        assert len(result) == 2
        assert result[0] == "# OK"
        assert "<!-- Page conversion error" in result[1]
