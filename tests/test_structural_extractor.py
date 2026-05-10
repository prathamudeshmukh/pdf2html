"""Unit tests for StructuralExtractor — all fitz calls are mocked."""

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from pdf2html_api.services.structural_extractor import (
    ExtractedImage,
    PageMetadata,
    StructuralExtractor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_rect(x0, y0, x1, y1):
    """Return a mock fitz.Rect with x0/y0/x1/y1 attributes."""
    rect = MagicMock()
    rect.x0 = x0
    rect.y0 = y0
    rect.x1 = x1
    rect.y1 = y1
    return rect


def _make_mock_page(
    drawings=None,
    images=None,
    text_dict=None,
    image_rects=None,
):
    """Return a mock fitz.Page with controllable outputs.

    image_rects: dict mapping xref -> list[Rect], defaults to a single rect at (0,0,100,80)
    """
    page = MagicMock()
    page.get_drawings.return_value = drawings or []
    page.get_images.return_value = images or []
    page.get_text.return_value = text_dict or {"blocks": []}

    if image_rects is not None:
        page.get_image_rects.side_effect = lambda xref: image_rects.get(xref, [])
    else:
        # Default: one rect per image at (0, 0, 100, 80)
        page.get_image_rects.return_value = [_make_mock_rect(0, 0, 100, 80)]

    return page


def _make_mock_doc(pages, image_data=None):
    """Return a mock fitz.Document that yields the given pages."""
    doc = MagicMock()
    doc.page_count = len(pages)
    doc.load_page.side_effect = pages
    # extract_image returns a dict with 'image' bytes and 'ext' string
    doc.extract_image.return_value = image_data or {
        "image": b"\x89PNG\r\n",
        "ext": "png",
    }
    doc.__enter__ = lambda s: s
    doc.__exit__ = MagicMock(return_value=False)
    return doc


# ---------------------------------------------------------------------------
# PageMetadata.to_context_dict
# ---------------------------------------------------------------------------

class TestPageMetadataToContextDict:
    def test_excludes_data_url_from_images(self):
        img = ExtractedImage(
            id="img_0",
            bbox=(0, 0, 80, 80),
            data_url="data:image/png;base64,AAAA",
            width=80,
            height=80,
        )
        meta = PageMetadata(
            page_index=0,
            colored_regions=[],
            text_colors=[],
            images=[img],
        )
        ctx = meta.to_context_dict()
        img_entry = ctx["images"][0]
        assert "data_url" not in img_entry
        assert img_entry["id"] == "img_0"
        assert img_entry["bbox"] == (0, 0, 80, 80)
        assert img_entry["width"] == 80
        assert img_entry["height"] == 80

    def test_colored_regions_and_text_colors_preserved(self):
        meta = PageMetadata(
            page_index=1,
            colored_regions=[{"bbox": (0, 0, 100, 20), "fill": "#1a237e", "stroke": None}],
            text_colors=["#ffffff", "#000000"],
            images=[],
        )
        ctx = meta.to_context_dict()
        assert ctx["colored_regions"] == [{"bbox": (0, 0, 100, 20), "fill": "#1a237e", "stroke": None}]
        assert ctx["text_colors"] == ["#ffffff", "#000000"]

    def test_empty_metadata_produces_empty_lists(self):
        meta = PageMetadata(page_index=0, colored_regions=[], text_colors=[], images=[])
        ctx = meta.to_context_dict()
        assert ctx["colored_regions"] == []
        assert ctx["text_colors"] == []
        assert ctx["images"] == []


# ---------------------------------------------------------------------------
# Color extraction helpers (hex formatting)
# ---------------------------------------------------------------------------

class TestColorFormatting:
    def test_extract_all_returns_lowercase_hex(self):
        """Colors must be #rrggbb lowercase."""
        drawing = {
            "fill": (0.10196078431372549, 0.13725490196078433, 0.49411764705882355),
            "stroke": None,
            "rect": (0, 0, 200, 30),
            "type": "f",
        }
        page = _make_mock_page(drawings=[drawing])
        doc = _make_mock_doc([page])

        with patch("fitz.open", return_value=doc):
            result = StructuralExtractor.extract_all(Path("fake.pdf"))

        assert len(result) == 1
        region = result[0].colored_regions[0]
        assert region["fill"] == "#1a237e"
        assert region["fill"] == region["fill"].lower()

    def test_white_fill_is_excluded(self):
        """Pure white (#ffffff) backgrounds are not worth sending to the LLM."""
        drawing = {
            "fill": (1.0, 1.0, 1.0),
            "stroke": None,
            "rect": (0, 0, 500, 700),
            "type": "f",
        }
        page = _make_mock_page(drawings=[drawing])
        doc = _make_mock_doc([page])

        with patch("fitz.open", return_value=doc):
            result = StructuralExtractor.extract_all(Path("fake.pdf"))

        assert result[0].colored_regions == []


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------

class TestImageExtraction:
    def test_embedded_image_becomes_extracted_image(self):
        raw_bytes = b"\x89PNG\r\n\x1a\n"
        page = _make_mock_page(
            images=[(1, 0, 100, 80, 8, "DeviceRGB", "", "", "png", "")],
            image_rects={1: [_make_mock_rect(10, 20, 110, 100)]},
        )
        doc = _make_mock_doc([page], image_data={"image": raw_bytes, "ext": "png"})

        with patch("fitz.open", return_value=doc):
            result = StructuralExtractor.extract_all(Path("fake.pdf"))

        assert len(result[0].images) == 1
        img = result[0].images[0]
        assert img.id == "img_0"
        assert img.bbox == (10, 20, 110, 100)
        assert img.data_url.startswith("data:image/png;base64,")
        expected_b64 = base64.b64encode(raw_bytes).decode()
        assert img.data_url == f"data:image/png;base64,{expected_b64}"

    def test_multiple_images_get_sequential_ids(self):
        raw = b"FAKE"
        page = _make_mock_page(
            images=[
                (1, 0, 100, 80, 8, "DeviceRGB", "", "", "png", ""),
                (2, 0, 50, 50, 8, "DeviceRGB", "", "", "jpeg", ""),
            ],
            image_rects={
                1: [_make_mock_rect(0, 0, 100, 80)],
                2: [_make_mock_rect(0, 100, 50, 150)],
            },
        )
        doc = _make_mock_doc([page], image_data={"image": raw, "ext": "png"})

        with patch("fitz.open", return_value=doc):
            result = StructuralExtractor.extract_all(Path("fake.pdf"))

        ids = [img.id for img in result[0].images]
        assert ids == ["img_0", "img_1"]

    def test_images_ordered_by_visual_reading_order(self):
        """img_0 must be the topmost image on the page (smallest y0), not the first xref."""
        raw = b"FAKE"
        # xref 1 appears second in the list but is lower on the page (y=200)
        # xref 2 appears first in the list but is higher on the page (y=50)
        page = _make_mock_page(
            images=[
                (1, 0, 100, 80, 8, "DeviceRGB", "", "", "png", ""),  # xref=1, lower on page
                (2, 0, 50, 50, 8, "DeviceRGB", "", "", "png", ""),  # xref=2, higher on page
            ],
            image_rects={
                1: [_make_mock_rect(10, 200, 110, 280)],  # y0=200 → appears second
                2: [_make_mock_rect(10, 50, 60, 100)],    # y0=50 → appears first
            },
        )
        doc = _make_mock_doc([page], image_data={"image": raw, "ext": "png"})

        with patch("fitz.open", return_value=doc):
            result = StructuralExtractor.extract_all(Path("fake.pdf"))

        images = result[0].images
        assert len(images) == 2
        assert images[0].bbox == (10, 50, 60, 100)   # topmost image gets img_0
        assert images[0].id == "img_0"
        assert images[1].bbox == (10, 200, 110, 280)  # lower image gets img_1
        assert images[1].id == "img_1"

    def test_image_bbox_reflects_page_position_not_dimensions(self):
        """bbox must come from get_image_rects, not image pixel dimensions."""
        raw = b"FAKE"
        page = _make_mock_page(
            images=[(1, 0, 400, 300, 8, "DeviceRGB", "", "", "png", "")],  # 400x300 image
            image_rects={1: [_make_mock_rect(50, 75, 250, 225)]},           # placed at (50,75)
        )
        doc = _make_mock_doc([page], image_data={"image": raw, "ext": "png"})

        with patch("fitz.open", return_value=doc):
            result = StructuralExtractor.extract_all(Path("fake.pdf"))

        img = result[0].images[0]
        assert img.bbox == (50, 75, 250, 225)   # page position, not (0, 0, 400, 300)
        assert img.width == 400                  # pixel dimensions preserved
        assert img.height == 300

    def test_image_without_rects_is_skipped_gracefully(self):
        """An image with no page rects (e.g. form XObject) should be skipped."""
        raw = b"FAKE"
        page = _make_mock_page(
            images=[(1, 0, 100, 80, 8, "DeviceRGB", "", "", "png", "")],
            image_rects={1: []},  # no rects — image not placed on page
        )
        doc = _make_mock_doc([page], image_data={"image": raw, "ext": "png"})

        with patch("fitz.open", return_value=doc):
            result = StructuralExtractor.extract_all(Path("fake.pdf"))

        assert result[0].images == []

    def test_image_extraction_failure_skips_image_gracefully(self):
        page = _make_mock_page(
            images=[(1, 0, 100, 80, 8, "DeviceRGB", "", "", "png", "")],
            image_rects={1: [_make_mock_rect(0, 0, 100, 80)]},
        )
        doc = _make_mock_doc([page])
        doc.extract_image.side_effect = Exception("xref error")

        with patch("fitz.open", return_value=doc):
            result = StructuralExtractor.extract_all(Path("fake.pdf"))

        assert result[0].images == []


# ---------------------------------------------------------------------------
# Text color extraction
# ---------------------------------------------------------------------------

class TestTextColorExtraction:
    def test_text_colors_extracted_and_deduplicated(self):
        text_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {"spans": [{"color": 0xFFFFFF, "text": "white"}]},
                        {"spans": [{"color": 0x1A237E, "text": "blue"}, {"color": 0xFFFFFF, "text": "white again"}]},
                    ],
                }
            ]
        }
        page = _make_mock_page(text_dict=text_dict)
        doc = _make_mock_doc([page])

        with patch("fitz.open", return_value=doc):
            result = StructuralExtractor.extract_all(Path("fake.pdf"))

        colors = result[0].text_colors
        assert "#ffffff" in colors
        assert "#1a237e" in colors
        assert colors.count("#ffffff") == 1  # deduplicated


# ---------------------------------------------------------------------------
# extract_all error handling
# ---------------------------------------------------------------------------

class TestExtractAllErrorHandling:
    def test_returns_empty_list_when_fitz_open_raises(self):
        with patch("fitz.open", side_effect=Exception("corrupt pdf")):
            result = StructuralExtractor.extract_all(Path("bad.pdf"))

        assert result == []

    def test_returns_empty_list_when_pdf_not_found(self):
        with patch("fitz.open", side_effect=FileNotFoundError("not found")):
            result = StructuralExtractor.extract_all(Path("missing.pdf"))

        assert result == []

    def test_returns_partial_results_when_one_page_fails(self):
        good_page = _make_mock_page()
        bad_page = MagicMock()
        bad_page.get_drawings.side_effect = RuntimeError("page error")
        bad_page.get_images.return_value = []
        bad_page.get_text.return_value = {"blocks": []}

        doc = _make_mock_doc([good_page, bad_page])

        with patch("fitz.open", return_value=doc):
            result = StructuralExtractor.extract_all(Path("fake.pdf"))

        # Two pages extracted; the failing one returns empty metadata
        assert len(result) == 2

    def test_one_page_result_per_pdf_page(self):
        pages = [_make_mock_page() for _ in range(3)]
        doc = _make_mock_doc(pages)

        with patch("fitz.open", return_value=doc):
            result = StructuralExtractor.extract_all(Path("fake.pdf"))

        assert len(result) == 3
        assert [m.page_index for m in result] == [0, 1, 2]
