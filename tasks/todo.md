# Todo

## Task 1 — Resolution + Model Path
- [ ] `pdf_to_images.py`: DPI default 200→300
- [ ] `pdf_to_images.py`: `max_size` 1024→2048 in `_optimize_image_for_api`
- [ ] Run `pytest tests/ -v` — all pass

## Task 2 — Tailwind Integration + Prompt Rewrite
- [ ] `html_merge.py`: Add Tailwind CDN `<script>` before `</head>`
- [ ] `prompts/image_to_html.md`: Rewrite with Tailwind classes + structural context format
- [ ] `tests/test_smoke.py`: Add assertion for Tailwind script tag
- [ ] Run `pytest tests/test_smoke.py -v` — all pass

## ✅ CHECKPOINT A — existing tests green, Tailwind in output

## Task 3 — StructuralExtractor
- [ ] Create `services/structural_extractor.py` (`ExtractedImage`, `PageMetadata`, `StructuralExtractor`)
- [ ] Create `tests/test_structural_extractor.py` (mock fitz, assert extraction, hex format, graceful failure)
- [ ] Run `pytest tests/test_structural_extractor.py -v` — all pass

## Task 4 — ImageInjector
- [ ] Create `services/image_injector.py` (`ImageInjector.inject`, `.inject_all`)
- [ ] Create `tests/test_image_injector.py` (single/multi replace, unmatched ref, empty page)
- [ ] Run `pytest tests/test_image_injector.py -v` — all pass

## ✅ CHECKPOINT B — new services isolated and tested

## Task 5 — LLM + PageProcessor Integration
- [ ] `llm.py`: Add `structural_context=None` param, inject into system prompt, max_tokens→8000
- [ ] `page_processor.py`: Add `page_metadata` param, pass per-page context to generator
- [ ] Run `pytest tests/ -v` — all existing tests still pass

## Task 6 — Pipeline Wiring + Integration Tests
- [ ] `conversion_pipeline.py`: Wire StructuralExtractor after image rendering
- [ ] `conversion_pipeline.py`: Wire ImageInjector after page processing
- [ ] `tests/test_conversion_pipeline.py`: Add integration tests for new steps + graceful degradation
- [ ] Run `pytest tests/ -v` — full suite green
- [ ] Run `pytest tests/ --cov=src --cov-report=term-missing` — coverage ≥80%
