"""Tests for structural_context flowing through LLM + PageProcessor."""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pdf2html_api.services.page_processor import PageProcessor
from pdf2html_api.services.structural_extractor import ExtractedImage, PageMetadata


def _make_metadata(page_index=0, fill="#1a237e", img_id="img_0"):
    return PageMetadata(
        page_index=page_index,
        colored_regions=[{"bbox": (0, 0, 100, 30), "fill": fill, "stroke": None}],
        text_colors=["#ffffff"],
        images=[
            ExtractedImage(
                id=img_id,
                bbox=(10, 10, 90, 90),
                data_url="data:image/png;base64,ABC",
                width=80,
                height=80,
            )
        ],
    )


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# PageProcessor passes structural_context to the generator
# ---------------------------------------------------------------------------

class TestPageProcessorStructuralContext:
    def test_structural_context_passed_to_single_page_generator(self):
        gen = MagicMock()
        gen.image_page_to_html.return_value = '<section class="page">ok</section>'
        meta = [_make_metadata()]

        _run(
            PageProcessor().process_pages(
                gen, ["img1.png"], "grid", "req1", page_metadata=meta
            )
        )

        _, kwargs = gen.image_page_to_html.call_args
        ctx = kwargs.get("structural_context")
        assert ctx is not None
        assert ctx["colored_regions"][0]["fill"] == "#1a237e"
        assert ctx["text_colors"] == ["#ffffff"]

    def test_structural_context_none_when_no_metadata_provided(self):
        gen = MagicMock()
        gen.image_page_to_html.return_value = '<section class="page">ok</section>'

        _run(
            PageProcessor().process_pages(gen, ["img1.png"], "grid", "req1")
        )

        _, kwargs = gen.image_page_to_html.call_args
        assert kwargs.get("structural_context") is None

    def test_structural_context_none_when_metadata_list_empty(self):
        gen = MagicMock()
        gen.image_page_to_html.return_value = '<section class="page">ok</section>'

        _run(
            PageProcessor().process_pages(
                gen, ["img1.png"], "grid", "req1", page_metadata=[]
            )
        )

        _, kwargs = gen.image_page_to_html.call_args
        assert kwargs.get("structural_context") is None

    def test_each_page_gets_its_own_context(self):
        gen = MagicMock()
        gen.image_page_to_html.return_value = '<section class="page">ok</section>'
        meta = [_make_metadata(0, fill="#111111"), _make_metadata(1, fill="#222222")]

        _run(
            PageProcessor().process_pages(
                gen,
                ["img0.png", "img1.png"],
                "grid",
                "req1",
                max_workers=1,
                page_metadata=meta,
            )
        )

        calls = gen.image_page_to_html.call_args_list
        ctx0 = calls[0][1].get("structural_context") or calls[0][0][2] if len(calls[0][0]) > 2 else calls[0][1].get("structural_context")
        ctx1 = calls[1][1].get("structural_context") or calls[1][0][2] if len(calls[1][0]) > 2 else calls[1][1].get("structural_context")
        fills = {c["colored_regions"][0]["fill"] for c in [ctx0, ctx1] if c}
        assert "#111111" in fills
        assert "#222222" in fills

    def test_extra_metadata_pages_beyond_image_count_ignored(self):
        gen = MagicMock()
        gen.image_page_to_html.return_value = '<section class="page">ok</section>'
        meta = [_make_metadata(i) for i in range(5)]  # more metadata than images

        result = _run(
            PageProcessor().process_pages(
                gen, ["img0.png"], "grid", "req1", page_metadata=meta
            )
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# HTMLGenerator accepts structural_context
# ---------------------------------------------------------------------------

class TestHTMLGeneratorStructuralContext:
    def test_image_page_to_html_accepts_structural_context(self):
        from pdf2html_api.llm import HTMLGenerator
        import inspect
        sig = inspect.signature(HTMLGenerator.image_page_to_html)
        assert "structural_context" in sig.parameters

    def test_structural_context_none_by_default(self):
        from pdf2html_api.llm import HTMLGenerator
        import inspect
        sig = inspect.signature(HTMLGenerator.image_page_to_html)
        assert sig.parameters["structural_context"].default is None

    def test_structural_context_appended_to_system_prompt(self):
        """When structural_context is provided it should appear in the API call."""
        from pdf2html_api.llm import HTMLGenerator

        gen = HTMLGenerator.__new__(HTMLGenerator)
        gen.model = "gpt-4o-mini"
        gen.max_tokens = 8000
        gen.temperature = 0.0
        gen.prompt_template = "Base prompt."

        ctx = {"colored_regions": [{"bbox": (0, 0, 10, 10), "fill": "#ff0000"}], "text_colors": [], "images": []}

        captured = {}

        def fake_call(image_path, css_mode, structural_context=None):
            captured["system"] = gen.prompt_template
            if structural_context:
                captured["context"] = structural_context
            return '<section class="page">ok</section>'

        gen._call_openai_vision = fake_call

        image_path = Path("/tmp/fake.png")
        with patch.object(Path, "exists", return_value=True):
            gen.image_page_to_html(image_path, "grid", structural_context=ctx)

        assert "context" in captured
        assert captured["context"]["colored_regions"][0]["fill"] == "#ff0000"
