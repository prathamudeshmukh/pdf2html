# SPEC.md — Enhanced PDF-to-HTML Conversion

## Objective

Improve `pdf2llm2html` to achieve **≥90% visual fidelity** when converting structured, design-heavy PDFs to HTML — for any document type (boarding passes, invoices, receipts, reports, certificates, etc.).

The current system's four key failure modes are:

1. **Background colors lost** — colored headers, section fills, and highlighted regions render as plain white
2. **Bordered/boxed layouts flattened** — info grids, cards, and structured panels collapse into plain text
3. **Embedded images missing** — QR codes, logos, and photos become broken `<img>` placeholders
4. **Complex multi-panel layouts collapse** — side-by-side sections fail to render correctly

The fix is a **hybrid extraction approach**: use PyMuPDF (already in the stack) to extract structural metadata and embedded images from the PDF _before_ the LLM call, then pass that context alongside the page image. The LLM then generates HTML using **Tailwind CSS utility classes** for all styling — replacing the custom CSS component library. Tailwind's JIT CDN supports arbitrary values (e.g. `bg-[#1a237e]`, `border-[#00bcd4]`) so the LLM can faithfully reproduce any color or spacing without pre-defined classes.

---

## Target Users / Stakeholders

- **Templify dashboard users** uploading PDFs during onboarding to create editable Handlebars templates
- **The Inngest pipeline** that calls `POST /convert` during the `upload/extract.html` background job
- **Direct API integrators** using `POST /convert`

---

## Core Features

### F1 — Embedded Image Extraction (PyMuPDF)

Use `fitz.Page.get_images()` and `fitz.Document.extract_image()` to pull every raster image from each PDF page. Encode each as a base64 data URL. Number them sequentially per page (`img_0`, `img_1`, …).

- New service: `services/structural_extractor.py` → `StructuralExtractor.extract_page(page) -> PageMetadata`
- `PageMetadata.images: list[ExtractedImage]` — each has `id`, `bbox`, `data_url`, `width`, `height`
- Pass image list to LLM prompt as a compact JSON block
- LLM emits `<img data-img-ref="img_N">` at the correct visual position
- New post-processor: `services/image_injector.py` → replaces `data-img-ref` attributes with actual `src="data:..."` inline after LLM generation

### F2 — Color & Structure Extraction (PyMuPDF)

Use PyMuPDF's drawing and block APIs to extract per-page:
- **Colored rectangles / filled regions** — background fill colors for any region
- **Text span colors** — foreground color of text blocks
- **Border/line elements** — rectangles with stroke colors and widths

Pass as compact JSON in the LLM system prompt so the LLM can apply accurate Tailwind arbitrary-value color classes (e.g. `bg-[#1a237e]`, `text-[#00bcd4]`, `border-[#1a237e]`).

Output shape (per page):
```json
{
  "colored_regions": [
    { "bbox": [x0, y0, x1, y1], "fill": "#1a237e", "stroke": null }
  ],
  "text_colors": ["#ffffff", "#1a237e", "#00bcd4"],
  "images": [
    { "id": "img_0", "bbox": [x0, y0, x1, y1], "width": 80, "height": 80 }
  ]
}
```

### F3 — Tailwind CSS Integration

Replace the custom CSS component library with **Tailwind CSS via CDN**. The merged HTML `<head>` will include:

```html
<script src="https://cdn.tailwindcss.com"></script>
```

This enables the LLM to use the full Tailwind utility vocabulary including arbitrary values:
- Layouts: `flex`, `grid`, `grid-cols-5`, `flex-1`, `flex-none`
- Spacing: `p-4`, `px-3`, `gap-2`, `mb-2`
- Colors: `bg-[#1a237e]`, `text-[#00bcd4]`, `border-[#1a237e]`
- Borders: `border`, `border-r`, `border-dashed`, `rounded-lg`, `rounded-none`
- Typography: `text-xs`, `text-sm`, `font-bold`, `text-white`, `uppercase`, `tracking-wide`
- Sizing: `w-full`, `min-w-0`, `h-auto`, `aspect-square`

The existing `BASE_CSS` is retained for page/document structure (`.page`, `.document` container), but the component-level CSS (`GRID_CSS`, `COLUMNS_CSS`) is no longer the primary styling mechanism — it remains as a fallback for `css_mode` backward compatibility.

### F4 — Rewritten LLM Prompt (`image_to_html.md`)

Rewrite the prompt to:
- Instruct the LLM to use **Tailwind utility classes** for all element-level styling
- Use Tailwind arbitrary-value syntax for colors from the structural metadata (e.g. `bg-[#1a237e]`)
- Emit `<img data-img-ref="img_N">` for images listed in the structural metadata, placed at the visual position matching the metadata `bbox`
- Be general-purpose — not optimized for any single document type
- Increase output token budget to **8 000** (up from 4 000) for complex, dense pages
- Keep existing anti-hallucination and reading-order rules

### F5 — Image Resolution Improvement

- Increase PDF render DPI: `200` → `300` (improves QR codes, small text, fine borders)
- Increase Vision API image cap: `max_size=1024` → `max_size=2048` in `_optimize_image_for_api`
- Keeps within OpenAI payload limits while preserving fine layout detail

### F6 — Model Upgrade Path

Wire `OPENAI_MODEL` env var to support `gpt-4o` alongside the current `gpt-4o-mini` default. Complex structured PDFs benefit significantly from `gpt-4o`'s stronger visual layout understanding. Keep `gpt-4o-mini` as the default to avoid surprise cost increases; users opt in via env var.

---

## Non-Goals (Out of Scope for This Spec)

- Pixel-perfect reproduction of photo backgrounds in advertisement banners
- Embedded font extraction or custom font matching
- Changes to `SampleJSONExtractor` or Handlebars placeholder flow
- Support for encrypted/password-protected PDFs
- New API endpoints or changes to `PDFRequest` / `PDFResponse` shape
- Tailwind build/purge pipeline (CDN-only; no tree-shaking required for this use case)

---

## Acceptance Criteria

For any structured PDF (boarding pass, invoice, certificate, report), the output HTML must:

- [ ] Preserve background colors for colored header bars, section fills, and highlighted regions via Tailwind `bg-[#hex]` classes or inline style
- [ ] Render embedded images (logos, QR codes, photos) as `<img src="data:image/...">` with actual content, not broken placeholders
- [ ] Reproduce multi-column and flex-row layouts (info grids, side-by-side panels) using Tailwind `flex` / `grid` utilities
- [ ] Preserve bordered containers (cards, info boxes) using Tailwind `border`, `rounded-*`, and `divide-*` utilities
- [ ] Preserve text colors for highlighted/branded text via Tailwind `text-[#hex]`
- [ ] Preserve all text content accurately (no hallucination, no dropped text)
- [ ] Produce valid, self-contained HTML that renders correctly in a browser without external dependencies (except Tailwind CDN)
- [ ] Existing API contract unchanged — same `PDFRequest` / `PDFResponse` shape
- [ ] Per-page extraction failures degrade gracefully (error placeholder, not 500)
- [ ] All existing tests continue to pass

---

## Architecture

### Updated Pipeline

```
POST /convert (PDFRequest)
  → SettingsConfigurator.configure()
  → CSSModeValidator.validate()
  → ConversionPipeline.execute()
      → PDFDownloader.download()
      → render_pdf_to_images()              # DPI=300, max_size=2048
      → [NEW] StructuralExtractor.extract() # PyMuPDF → list[PageMetadata]
      → HTMLGeneratorFactory.build()
      → PageProcessor.process_pages()       # passes PageMetadata per page to generator
      → [NEW] ImageInjector.inject_all()    # replaces data-img-ref → base64 src
      → merge_pages()                       # now includes Tailwind CDN in <head>
      → (optional) SampleJSONExtractor
      → (optional) apply_sample_json_to_html()
  → BackgroundTask: cleanup temp files
  → PDFResponse
```

### Files to Create

| File | Responsibility |
|---|---|
| `src/pdf2html_api/services/structural_extractor.py` | PyMuPDF extraction → `PageMetadata` dataclass |
| `src/pdf2html_api/services/image_injector.py` | Post-LLM `data-img-ref` → `src="data:..."` replacement |

### Files to Modify

| File | Change |
|---|---|
| `src/pdf2html_api/html_merge.py` | Add Tailwind CDN `<script>` tag to `<head>` |
| `src/pdf2html_api/prompts/image_to_html.md` | Rewritten: Tailwind classes, structural metadata context, general-purpose instructions |
| `src/pdf2html_api/llm.py` | Accept `structural_context: dict` param; inject metadata into system prompt; increase `max_tokens` to 8000 |
| `src/pdf2html_api/pdf_to_images.py` | DPI default `200→300`; `max_size` `1024→2048` |
| `src/pdf2html_api/services/conversion_pipeline.py` | Wire `StructuralExtractor` and `ImageInjector` into pipeline |
| `src/pdf2html_api/services/page_processor.py` | Pass `page_metadata: PageMetadata` to `html_generator.image_page_to_html()` |

---

## Testing Strategy

### Unit Tests

**`tests/test_structural_extractor.py`**
- Mock a `fitz.Page` with known images and colored rectangles; assert `PageMetadata` fields are populated correctly
- Assert graceful return of empty `PageMetadata` on any extraction failure (no exception propagated)
- Assert hex color formatting is correct (`#rrggbb` lowercase)

**`tests/test_image_injector.py`**
- Input HTML with `<img data-img-ref="img_0">` + metadata list; assert output contains `src="data:image/..."`
- Assert unmatched refs are left as `<img src="">` without raising
- Assert multiple images on the same page are all replaced correctly

### Integration Tests

**`tests/test_conversion_pipeline.py`** (extend existing)
- Convert a real 1-page structured PDF; assert at least one `data:image/` string in output HTML
- Assert at least one Tailwind color class or `style="background-color:` in output
- Assert existing API response shape is unchanged (`html`, `pages_processed`, `model_used`, `css_mode`, `sample_json`)

### Regression

- All existing tests must pass without modification

### Manual Acceptance Test

Run a structured PDF (e.g. the boarding pass) through the local server and verify in a browser that the 10 acceptance criteria are met.

---

## Build Sequence

1. `StructuralExtractor` + unit tests (F2 color/image extraction)
2. `ImageInjector` + unit tests (F1 post-processing)
3. Update `pdf_to_images.py` — DPI and max_size (F5)
4. Update `llm.py` — accept `structural_context`, increase `max_tokens` (F4)
5. Rewrite `image_to_html.md` prompt — Tailwind, general-purpose, metadata context (F3 + F4)
6. Update `html_merge.py` — add Tailwind CDN to `<head>` (F3)
7. Wire pipeline: `ConversionPipeline` + `PageProcessor` (F1 + F2 integration)
8. Integration test pass
9. Manual acceptance test

---

## Boundaries

| Category | Rule |
|---|---|
| **Always** | Preserve existing `POST /convert` API contract — request/response shape unchanged |
| **Always** | Maintain graceful degradation — structural extraction failures produce empty `PageMetadata`, not 500s |
| **Always** | Keep `SampleJSONExtractor` and Handlebars placeholder pipeline intact |
| **Always** | HTML output must be self-contained (no external CSS files; Tailwind via CDN `<script>` only) |
| **Ask first** | Before switching the default model from `gpt-4o-mini` to `gpt-4o` (cost impact per conversion) |
| **Ask first** | Before raising DPI above 300 or max_size above 2048 (memory/latency tradeoff) |
| **Never** | Break backward compatibility with existing `css_mode` parameter values (`grid`, `columns`, `single`) |
| **Never** | Introduce a Tailwind build/purge step — CDN-only is intentional for self-contained output |
| **Never** | Block the HTTP response on image/color extraction failure — always degrade gracefully |
