"""
Tests for the on_page_done progress callback added to PageProcessor.

Coverage
--------
- Callback called once per page (single-page path)
- Callback called once per page (parallel multi-page path)
- Callback receives correct (pages_done_so_far, total_pages) values
- Error-placeholder pages still trigger the callback
- Callers that omit the callback are unaffected (no TypeError)
"""

import asyncio
import threading
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.pdf2html_api.services.page_processor import PageProcessor


def _make_image_paths(count: int):
    """Return a list of `count` real temp files (PageProcessor reads from disk via the generator)."""
    paths = []
    for _ in range(count):
        f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        f.close()
        paths.append(Path(f.name))
    return paths


def _mock_generator(html: str = "<p>page</p>"):
    gen = MagicMock()
    gen.image_page_to_html.return_value = html
    return gen


# ---------------------------------------------------------------------------
# Single-page path
# ---------------------------------------------------------------------------


def test_single_page_callback_called_once() -> None:
    calls: list = []

    def on_page_done(done: int, total: int) -> None:
        calls.append((done, total))

    processor = PageProcessor()
    paths = _make_image_paths(1)
    asyncio.run(
        processor.process_pages(
            _mock_generator(),
            paths,
            css_mode="grid",
            request_id="req_test",
            on_page_done=on_page_done,
        )
    )

    assert len(calls) == 1
    assert calls[0] == (1, 1)


# ---------------------------------------------------------------------------
# Multi-page parallel path
# ---------------------------------------------------------------------------


def test_multi_page_callback_called_for_each_page() -> None:
    calls: list = []
    lock = threading.Lock()

    def on_page_done(done: int, total: int) -> None:
        with lock:
            calls.append((done, total))

    processor = PageProcessor()
    paths = _make_image_paths(4)
    asyncio.run(
        processor.process_pages(
            _mock_generator(),
            paths,
            css_mode="grid",
            request_id="req_test",
            on_page_done=on_page_done,
        )
    )

    assert len(calls) == 4
    totals = {total for _, total in calls}
    assert totals == {4}
    dones = sorted(done for done, _ in calls)
    assert dones == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Error-placeholder pages still trigger callback
# ---------------------------------------------------------------------------


def test_failing_page_still_triggers_callback() -> None:
    calls: list = []

    def on_page_done(done: int, total: int) -> None:
        calls.append((done, total))

    gen = MagicMock()
    gen.image_page_to_html.side_effect = RuntimeError("OpenAI timeout")

    processor = PageProcessor()
    paths = _make_image_paths(2)
    results = asyncio.run(
        processor.process_pages(
            gen,
            paths,
            css_mode="grid",
            request_id="req_test",
            on_page_done=on_page_done,
        )
    )

    assert len(calls) == 2
    for html in results:
        assert "Error processing page" in html


# ---------------------------------------------------------------------------
# Omitting callback does not raise
# ---------------------------------------------------------------------------


def test_no_callback_does_not_raise() -> None:
    processor = PageProcessor()
    paths = _make_image_paths(2)
    results = asyncio.run(
        processor.process_pages(
            _mock_generator(),
            paths,
            css_mode="grid",
            request_id="req_test",
        )
    )
    assert len(results) == 2
