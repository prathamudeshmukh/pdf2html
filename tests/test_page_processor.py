"""
Tests for src/pdf2html_api/services/page_processor.py

Coverage
--------
- PageProcessor.process_pages  (happy path + per-page error handling)
- Page-failure graceful degradation (via HTTP body inspection)
"""

import asyncio
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.pdf2html_api.main import app
from src.pdf2html_api.services.conversion_pipeline import (
    ConversionArtifacts,
    ConversionResult,
)
from src.pdf2html_api.services.page_processor import PageProcessor

client = TestClient(app)

_MERGED_HTML = "<!DOCTYPE html><html><body><p>Merged</p></body></html>"


def _make_result(
    *,
    html: str = _MERGED_HTML,
    pages_processed: int = 1,
    model_used: str = "gpt-4o-mini",
    css_mode: str = "grid",
) -> ConversionResult:
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(b"%PDF stub")
    tmp.close()
    return ConversionResult(
        html=html,
        pages_processed=pages_processed,
        model_used=model_used,
        css_mode=css_mode,
        artifacts=ConversionArtifacts(
            pdf_path=Path(tmp.name),
            image_paths=[],
            temp_dir=MagicMock(),
        ),
    )


def _patch_pipeline(result=None, exc=None):
    stack = ExitStack()
    resolved = result or _make_result()

    if exc is not None:
        stack.enter_context(
            patch(
                "src.pdf2html_api.main.ConversionPipeline.execute",
                new=AsyncMock(side_effect=exc),
            )
        )
    else:
        stack.enter_context(
            patch(
                "src.pdf2html_api.main.ConversionPipeline.execute",
                new=AsyncMock(return_value=resolved),
            )
        )
    stack.enter_context(patch("src.pdf2html_api.main._cleanup_files"))
    return stack, resolved


class TestPageProcessor:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _gen(self, *page_htmls):
        g = MagicMock()
        g.image_page_to_html.side_effect = list(page_htmls)
        return g

    def test_single_page_returns_list_of_one(self):
        g = self._gen('<section class="page">P1</section>')
        result = self._run(PageProcessor().process_pages(g, ["img1.png"], "grid", "r", 1))
        assert len(result) == 1

    def test_multi_page_returns_correct_count(self):
        pages = [f'<section class="page">P{i}</section>' for i in range(4)]
        g = self._gen(*pages)
        result = self._run(
            PageProcessor().process_pages(g, ["i1.png", "i2.png", "i3.png", "i4.png"], "grid", "r", 2)
        )
        assert len(result) == 4

    def test_page_order_preserved(self):
        def side(path, css_mode):
            idx = int(path.replace("img", "").replace(".png", ""))
            return f'<section class="page">Page{idx}</section>'
        g = MagicMock()
        g.image_page_to_html.side_effect = side
        result = self._run(
            PageProcessor().process_pages(g, ["img0.png", "img1.png", "img2.png"], "grid", "r", 3)
        )
        assert result[0] == '<section class="page">Page0</section>'
        assert result[1] == '<section class="page">Page1</section>'
        assert result[2] == '<section class="page">Page2</section>'

    def test_css_mode_forwarded_to_generator(self):
        g = self._gen('<section class="page">x</section>')
        self._run(PageProcessor().process_pages(g, ["img1.png"], "columns", "r", 1))
        g.image_page_to_html.assert_called_once_with("img1.png", "columns")

    def test_exception_replaced_with_placeholder(self):
        g = MagicMock()
        g.image_page_to_html.side_effect = RuntimeError("llm failed")
        result = self._run(PageProcessor().process_pages(g, ["img1.png"], "grid", "r", 1))
        assert len(result) == 1
        assert "ocr-uncertain" in result[0]
        assert "Error processing page 1" in result[0]

    def test_partial_failure_does_not_drop_successful_pages(self):
        def side(path, css_mode):
            if "img1" in path:
                return '<section class="page">OK</section>'
            raise RuntimeError("page 2 failed")
        g = MagicMock()
        g.image_page_to_html.side_effect = side
        result = self._run(
            PageProcessor().process_pages(g, ["img1.png", "img2.png"], "grid", "r", 2)
        )
        assert len(result) == 2
        assert result[0] == '<section class="page">OK</section>'
        assert "ocr-uncertain" in result[1]

    def test_page_failure_endpoint_returns_200(self):
        result_with_error = _make_result(
            html='<!DOCTYPE html><html><body><p class="ocr-uncertain">[Error processing page 1: oops]</p></body></html>'
        )
        stack, _ = _patch_pipeline(result_with_error)
        with stack:
            response = client.post("/convert", json={"pdf_url": "https://example.com/test.pdf"})
        assert response.status_code == 200
        assert "ocr-uncertain" in response.json()["html"]
