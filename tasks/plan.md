# Plan: Enhanced PDF-to-HTML Conversion

## Goal
Achieve ≥90% visual fidelity on structured, design-heavy PDFs (boarding passes, invoices, certificates) by adding PyMuPDF-based structural extraction and switching from custom CSS classes to Tailwind CSS utilities.

## Current Failure Modes
- Background colors lost (colored headers, section fills render white)
- Embedded images broken (QR codes, logos become empty `<img>` placeholders)
- Bordered/grid layouts flattened (info boxes, side-by-side panels collapse)
- LLM generates CSS classes that don't exist in the output stylesheet

## Approach: Hybrid Extraction
Use PyMuPDF (already in stack) to extract colors and images from the PDF before the LLM call. Pass that context alongside the page image. LLM generates HTML using Tailwind CSS utility classes (via CDN) — Tailwind supports arbitrary values (`bg-[#1a237e]`) so any extracted color can be applied exactly.

## Architecture After Changes
```
POST /convert
  → PDFDownloader.download()
  → render_pdf_to_images()               # DPI 200→300, max_size 1024→2048
  → [NEW] StructuralExtractor.extract_all()  # PyMuPDF → List[PageMetadata]
  → HTMLGeneratorFactory.build()
  → PageProcessor.process_pages()        # + page_metadata per page
      → html_generator.image_page_to_html(path, css_mode, structural_context)
  → [NEW] ImageInjector.inject_all()     # data-img-ref → base64 src
  → merge_pages()                        # + Tailwind CDN in <head>
  → (optional) SampleJSONExtractor
  → PDFResponse  (shape unchanged)
```

## Key Design Decisions
1. All new method parameters are optional with `None` defaults → no existing test breaks
2. `StructuralExtractor` opens the PDF independently after image rendering, closes after extraction
3. `StructuralExtractor.extract_all()` returns `[]` on any failure — pipeline continues gracefully
4. `ImageInjector` uses BeautifulSoup (already installed) to replace `data-img-ref` attributes
5. Tailwind CDN added to `merge_pages()` output; BASE_CSS retained for page/document structure
6. `image_page_to_html` max_tokens raised to 8000 (already in Settings validator range)

---

## Task 1 — Resolution + Model Path
**Files:** `src/pdf2html_api/pdf_to_images.py`

- `render_pdf_to_images(pdf_path, dpi=300)` — DPI default 200→300
- `_optimize_image_for_api(image_path, max_size=2048)` — cap 1024→2048

**Verify:** `pytest tests/ -v` — all existing tests pass.

---

## Task 2 — Tailwind Integration + Prompt Rewrite
**Files:** `src/pdf2html_api/html_merge.py`, `src/pdf2html_api/prompts/image_to_html.md`, `tests/test_smoke.py`

- `merge_pages()`: Add `<script src="https://cdn.tailwindcss.com"></script>` before `</head>`
- Rewrite `image_to_html.md`: Tailwind utility classes, structural metadata context format, anti-hallucination rules
- `test_smoke.py`: Add assertion that Tailwind script tag is in output

**Verify:** `pytest tests/test_smoke.py -v`

---

### ✅ CHECKPOINT A

---

## Task 3 — StructuralExtractor
**Files:** `src/pdf2html_api/services/structural_extractor.py`, `tests/test_structural_extractor.py`

New dataclasses:
```python
@dataclass
class ExtractedImage:
    id: str        # "img_0", "img_1", ...
    bbox: tuple    # (x0, y0, x1, y1)
    data_url: str  # "data:image/png;base64,..."
    width: int
    height: int

@dataclass
class PageMetadata:
    page_index: int
    colored_regions: list[dict]  # [{"bbox": [...], "fill": "#rrggbb", "stroke": "#rrggbb|null"}]
    text_colors: list[str]       # unique hex colors from text spans
    images: list[ExtractedImage]

    def to_context_dict(self) -> dict: ...  # excludes data_url, keeps prompt compact
```

New class:
```python
class StructuralExtractor:
    @staticmethod
    def extract_page(page: fitz.Page, page_index: int) -> PageMetadata: ...
    @staticmethod
    def extract_all(pdf_path: Path) -> list[PageMetadata]: ...  # returns [] on failure
```

- Colors via `page.get_drawings()` — fitz 0.0–1.0 floats → `#rrggbb` hex
- Images via `page.get_images(full=True)` + `doc.extract_image(xref)` → base64 data URL
- Text colors via `page.get_text("dict")["blocks"]` → span colors → deduplicated hex list

Unit tests: mock `fitz.open()`, assert PageMetadata fields, hex formatting, graceful failure.

**Verify:** `pytest tests/test_structural_extractor.py -v`

---

## Task 4 — ImageInjector
**Files:** `src/pdf2html_api/services/image_injector.py`, `tests/test_image_injector.py`

```python
class ImageInjector:
    @staticmethod
    def inject(html: str, images: list[ExtractedImage]) -> str: ...
    @staticmethod
    def inject_all(page_html_list: list[str], page_metadata_list: list[PageMetadata]) -> list[str]: ...
```

- BeautifulSoup finds `<img data-img-ref="img_N">` → replaces `src` with `data_url`
- Unmatched refs → `src=""`, no crash
- Per-page failures return original HTML unchanged

Unit tests: single/multiple replacement, unmatched ref, empty page, mismatched list lengths.

**Verify:** `pytest tests/test_image_injector.py -v`

---

### ✅ CHECKPOINT B

---

## Task 5 — LLM + PageProcessor Integration
**Files:** `src/pdf2html_api/llm.py`, `src/pdf2html_api/services/page_processor.py`

`llm.py`:
- `image_page_to_html(self, image_path, css_mode, structural_context=None)`
- If structural_context not None: append JSON block to system prompt
- Raise max_tokens call to 8000

`page_processor.py`:
- `process_pages(..., page_metadata: list[PageMetadata] | None = None)`
- `_convert_page(..., structural_context=None)`
- Zip image_paths with page_metadata (or `[None] * n` if not provided)

**Verify:** `pytest tests/ -v` — all existing tests still pass (None defaults preserve backward compat).

---

## Task 6 — Pipeline Wiring + Integration Tests
**Files:** `src/pdf2html_api/services/conversion_pipeline.py`, `tests/test_conversion_pipeline.py`

After `render_pdf_to_images()`:
```python
page_metadata_list = StructuralExtractor.extract_all(pdf_path)  # [] on failure
```

Pass to `PageProcessor.process_pages(..., page_metadata=page_metadata_list)`.

After page processing:
```python
page_html_list = ImageInjector.inject_all(page_html_list, page_metadata_list)
```

Integration tests: assert StructuralExtractor and ImageInjector are called; assert graceful degradation on extractor failure; assert PDFResponse shape unchanged.

**Verify:** `pytest tests/ -v` — full suite green.

---

## End-to-End Verification
1. `python run_api.py`
2. POST any structured PDF to `POST /convert`
3. Open HTML in browser — verify colors, images, layouts
4. `pytest tests/ --cov=src --cov-report=term-missing` — ≥80% coverage, all green
