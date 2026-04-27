# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Service Overview

`pdf2llm2html` is a FastAPI microservice that converts PDFs to HTML using OpenAI Vision API. It is called by the Templify dashboard via `POST /convert` during the onboarding flow when users upload a PDF to create a template.

## Commands

```bash
# Install (dev mode with test dependencies)
pip install -e ".[dev]"

# Start development server
python run_api.py
# OR
uvicorn src.pdf2html_api.main:app --host 0.0.0.0 --port 8000 --reload

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_smoke.py -v

# Run a single test function
pytest tests/test_page_processor.py::test_single_page_inline -v

# Run tests with coverage
pytest tests/ --cov=src --cov-report=html

# Docker
docker build -t pdf2html-api .
docker run -p 8000:8000 -e OPENAI_API_KEY=sk-... pdf2html-api
```

**Pytest config** (in `pyproject.toml`): `asyncio_mode = "auto"`, `pythonpath = ["."]`

## Environment Variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | Validated at startup |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Vision-capable model required |
| `HOST` | No | `0.0.0.0` | |
| `PORT` | No | `8000` | |

Copy `env.example` to `.env` to get started.

## Architecture

### Request Flow

```
POST /convert (PDFRequest)
  → SettingsConfigurator.configure()      # merge request params into Settings
  → CSSModeValidator.validate()           # validate css_mode
  → ConversionPipeline.execute()
      → PDFDownloader.download()          # async HTTP download, saves to temp dir
      → render_pdf_to_images()            # PyMuPDF → PNG per page
      → HTMLGeneratorFactory.build()      # construct OpenAI client
      → PageProcessor.process_pages()     # parallel image→HTML via ThreadPoolExecutor
      → merge_pages()                     # assemble final HTML doc
      → (optional) SampleJSONExtractor    # detect template variables via LLM
      → (optional) apply_sample_json_to_html()  # replace values with {{placeholders}}
  → BackgroundTask: cleanup temp files
  → PDFResponse (html, pages_processed, model_used, css_mode, sample_json)
```

### Source Layout

```
src/pdf2html_api/
├── main.py                 # HTTP layer: routes, Pydantic models (PDFRequest, PDFResponse)
├── config.py               # Settings (Pydantic), get_settings()
├── llm.py                  # HTMLGenerator class — OpenAI Vision API calls with Tenacity retry
├── pdf_to_images.py        # PDF → PNG using PyMuPDF
├── html_merge.py           # merge_pages() — assembles final HTML document
├── css_styles.py           # CSS constants: BASE_CSS, GRID_CSS, COLUMNS_CSS
├── prompts/                # Markdown prompt templates loaded at runtime
│   ├── image_to_html.md    # Prompt for page image → HTML conversion
│   └── html_to_sample_json.md  # Prompt for variable extraction
└── services/
    ├── conversion_pipeline.py    # Orchestrates the full workflow
    ├── page_processor.py         # Parallel per-page processing
    ├── pdf_downloader.py         # Async download with content-type validation
    ├── html_generator_factory.py # Factory for HTMLGenerator
    ├── settings_configurator.py  # Merges PDFRequest into Settings
    ├── css_mode_validator.py     # Valid modes: grid, columns, single
    ├── sample_json_extractor.py  # LLM-based variable detection
    └── sample_json_to_html.py    # BeautifulSoup placeholder replacement
```

### Key Design Decisions

- **Layered**: `main.py` owns HTTP concerns only; `services/` owns business logic; `llm.py`, `pdf_to_images.py`, `html_merge.py` are pure utilities.
- **Parallel page processing**: `PageProcessor` uses `ThreadPoolExecutor` for multi-page PDFs; single pages are processed inline without threading overhead.
- **Graceful degradation**: Per-page LLM errors produce an error placeholder div rather than aborting the entire conversion.
- **Retry logic**: `HTMLGenerator.generate_html()` uses Tenacity (`stop_after_attempt(3)`, `wait_exponential`) for transient OpenAI failures.
- **Temp file cleanup**: `ConversionArtifacts` holds references to temp PDF and image files; `main.py` registers a `BackgroundTask` to clean up after response is sent.
- **CSS modes**: The `css_mode` parameter (`grid` | `columns` | `single`) controls how multi-column layouts are rendered in the output HTML.
