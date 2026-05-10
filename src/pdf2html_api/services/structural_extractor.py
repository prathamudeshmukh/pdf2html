"""Extract structural metadata (colors, images) from PDF pages using PyMuPDF."""

import base64
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

_WHITE = "#ffffff"
_BLACK = "#000000"


@dataclass
class ExtractedImage:
    id: str
    bbox: tuple
    data_url: str
    width: int
    height: int


@dataclass
class PageMetadata:
    page_index: int
    colored_regions: list[dict]
    text_colors: list[str]
    images: list[ExtractedImage] = field(default_factory=list)

    def to_context_dict(self) -> dict:
        """JSON-serialisable dict for the LLM prompt (no base64 data URLs)."""
        return {
            "colored_regions": self.colored_regions,
            "text_colors": self.text_colors,
            "images": [
                {
                    "id": img.id,
                    "bbox": img.bbox,
                    "width": img.width,
                    "height": img.height,
                }
                for img in self.images
            ],
        }


def _fitz_color_to_hex(color: Any) -> str | None:
    """Convert a fitz color value to lowercase #rrggbb hex string.

    fitz colors come in two forms:
    - tuple of floats 0.0–1.0  (from get_drawings)
    - integer packed RGB       (from span["color"])
    Returns None for None/invalid values.
    """
    if color is None:
        return None
    try:
        if isinstance(color, (tuple, list)) and len(color) >= 3:
            r, g, b = (round(c * 255) for c in color[:3])
        elif isinstance(color, int):
            r = (color >> 16) & 0xFF
            g = (color >> 8) & 0xFF
            b = color & 0xFF
        else:
            return None
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return None


def _extract_colored_regions(page: fitz.Page) -> list[dict]:
    regions = []
    try:
        for drawing in page.get_drawings():
            fill = _fitz_color_to_hex(drawing.get("fill"))
            stroke = _fitz_color_to_hex(drawing.get("stroke") or drawing.get("color"))
            # Skip pure white fills — not useful context for the LLM
            if fill == _WHITE:
                fill = None
            if fill is None and stroke is None:
                continue
            rect = drawing.get("rect")
            if rect is None:
                continue
            try:
                # fitz.Rect has x0/y0/x1/y1 attributes; plain tuples are also accepted
                if hasattr(rect, "x0"):
                    bbox = (round(rect.x0), round(rect.y0), round(rect.x1), round(rect.y1))
                else:
                    x0, y0, x1, y1 = rect
                    bbox = (round(x0), round(y0), round(x1), round(y1))
            except Exception:
                continue
            regions.append({"bbox": bbox, "fill": fill, "stroke": stroke})
    except Exception as exc:
        logger.warning("Failed to extract colored regions: %s", exc)
    return regions


def _extract_text_colors(page: fitz.Page) -> list[str]:
    seen: set[str] = set()
    try:
        blocks = page.get_text("dict").get("blocks", [])
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    hex_color = _fitz_color_to_hex(span.get("color"))
                    if hex_color and hex_color != _BLACK:
                        seen.add(hex_color)
    except Exception as exc:
        logger.warning("Failed to extract text colors: %s", exc)
    return sorted(seen)


def _extract_images(page: fitz.Page, doc: fitz.Document, page_index: int) -> list[ExtractedImage]:
    # Collect (y0, x0, bbox, data_url, width, height) then sort by visual reading order.
    candidates: list[tuple] = []
    try:
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            width = img_info[2]
            height = img_info[3]
            try:
                rects = page.get_image_rects(xref)
                if not rects:
                    # Image is not placed on the page (e.g. embedded form XObject) — skip.
                    continue
                rect = rects[0]
                if hasattr(rect, "x0"):
                    bbox = (round(rect.x0), round(rect.y0), round(rect.x1), round(rect.y1))
                else:
                    x0, y0, x1, y1 = rect
                    bbox = (round(x0), round(y0), round(x1), round(y1))

                image_dict = doc.extract_image(xref)
                raw_bytes = image_dict["image"]
                ext = image_dict.get("ext", "png")
                data_url = f"data:image/{ext};base64,{base64.b64encode(raw_bytes).decode()}"
                candidates.append((bbox[1], bbox[0], bbox, data_url, width, height))
            except Exception as exc:
                logger.warning("Skipping image xref=%d on page %d: %s", xref, page_index, exc)
    except Exception as exc:
        logger.warning("Failed to list images on page %d: %s", page_index, exc)

    # Sort top-to-bottom, left-to-right so img_0 is always the topmost image.
    candidates.sort(key=lambda c: (c[0], c[1]))

    return [
        ExtractedImage(
            id=f"img_{i}",
            bbox=c[2],
            data_url=c[3],
            width=c[4],
            height=c[5],
        )
        for i, c in enumerate(candidates)
    ]


class StructuralExtractor:
    @staticmethod
    def extract_page(page: fitz.Page, doc: fitz.Document, page_index: int) -> PageMetadata:
        colored_regions: list[dict] = []
        text_colors: list[str] = []
        images: list[ExtractedImage] = []

        try:
            colored_regions = _extract_colored_regions(page)
        except Exception as exc:
            logger.warning("Color extraction failed for page %d: %s", page_index, exc)

        try:
            text_colors = _extract_text_colors(page)
        except Exception as exc:
            logger.warning("Text color extraction failed for page %d: %s", page_index, exc)

        try:
            images = _extract_images(page, doc, page_index)
        except Exception as exc:
            logger.warning("Image extraction failed for page %d: %s", page_index, exc)

        return PageMetadata(
            page_index=page_index,
            colored_regions=colored_regions,
            text_colors=text_colors,
            images=images,
        )

    @staticmethod
    def extract_all(pdf_path: Path) -> list[PageMetadata]:
        """Open the PDF, extract metadata for all pages, close. Returns [] on failure."""
        try:
            doc = fitz.open(str(pdf_path))
        except Exception as exc:
            logger.warning("StructuralExtractor could not open %s: %s", pdf_path, exc)
            return []

        results: list[PageMetadata] = []
        try:
            for page_index in range(doc.page_count):
                try:
                    page = doc.load_page(page_index)
                    metadata = StructuralExtractor.extract_page(page, doc, page_index)
                except Exception as exc:
                    logger.warning("Extraction failed for page %d: %s", page_index, exc)
                    metadata = PageMetadata(
                        page_index=page_index,
                        colored_regions=[],
                        text_colors=[],
                        images=[],
                    )
                results.append(metadata)
        finally:
            doc.close()

        return results
