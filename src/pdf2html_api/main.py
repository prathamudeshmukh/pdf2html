"""Main FastAPI application for PDF2HTML API.

This module is intentionally kept thin: it owns the HTTP contract
(request/response models, route handlers, error boundaries) and delegates
all business logic to the services layer.
"""

import logging
import time
from typing import Annotated, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from .pdf_to_images import cleanup_temp_images
from .services.conversion_pipeline import ConversionArtifacts, ConversionPipeline

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("pdf2html_api.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PDF2HTML API",
    description=(
        "Convert PDF pages to HTML using the OpenAI Vision API.\n\n"
        "## Endpoints\n"
        "- **POST /convert** – Returns a JSON envelope with the merged HTML and conversion metadata.\n"
        "- **GET /health** – Liveness probe.\n"
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    license_info={"name": "MIT"},
    contact={"name": "Templify"},
)

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class PDFRequest(BaseModel):
    """Request model for PDF conversion."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "pdf_url": "https://example.com/sample.pdf",
                    "model": "gpt-4o-mini",
                    "dpi": 200,
                    "max_tokens": 4000,
                    "temperature": 0.0,
                    "css_mode": "grid",
                    "max_parallel_workers": 3,
                    "extract_variables": False,
                }
            ]
        }
    }

    pdf_url: Annotated[
        HttpUrl,
        Field(
            description="Publicly accessible URL of the PDF file to convert.",
            examples=["https://example.com/sample.pdf"],
        ),
    ]
    model: Annotated[
        Optional[str],
        Field(
            default="gpt-4o-mini",
            description="OpenAI vision model used for page analysis.",
            examples=["gpt-4o-mini", "gpt-4o"],
        ),
    ] = "gpt-4o-mini"
    dpi: Annotated[
        Optional[int],
        Field(
            default=200,
            ge=72,
            le=600,
            description="Resolution (dots per inch) used when rasterising each PDF page. Higher values improve accuracy but increase latency and cost.",
            examples=[150, 200, 300],
        ),
    ] = 200
    max_tokens: Annotated[
        Optional[int],
        Field(
            default=4000,
            ge=256,
            le=16384,
            description="Maximum number of tokens the model may generate per page.",
            examples=[2000, 4000, 8000],
        ),
    ] = 4000
    temperature: Annotated[
        Optional[float],
        Field(
            default=0.0,
            ge=0.0,
            le=2.0,
            description="Sampling temperature for the model. Use 0.0 for deterministic output.",
            examples=[0.0, 0.2],
        ),
    ] = 0.0
    css_mode: Annotated[
        Optional[str],
        Field(
            default="grid",
            description="CSS layout strategy applied to the generated HTML. `grid` preserves positional fidelity; `flex` is flow-based; `block` is the simplest fallback. Invalid values are rejected by the pipeline with a 500 error.",
            examples=["grid", "flex", "block"],
        ),
    ] = "grid"
    max_parallel_workers: Annotated[
        Optional[int],
        Field(
            default=3,
            ge=1,
            le=10,
            description="Number of PDF pages processed concurrently. Higher values reduce total latency but increase OpenAI API concurrency.",
            examples=[1, 3, 5],
        ),
    ] = 3
    extract_variables: Annotated[
        Optional[bool],
        Field(
            default=False,
            description="When `true`, the response includes a `sample_json` map of detected template variables (e.g. `{{name}}`) to their placeholder values.",
            examples=[False, True],
        ),
    ] = False


_RESPONSE_EXAMPLE = {
    "html": "<html>…</html>",
    "pages_processed": 3,
    "model_used": "gpt-4o-mini",
    "css_mode": "grid",
    "sample_json": {"{{name}}": "John Doe", "{{date}}": "2026-01-01"},
}

_RESPONSE_EXAMPLE_NO_VARS = {
    "html": "<html>…</html>",
    "pages_processed": 3,
    "model_used": "gpt-4o-mini",
    "css_mode": "grid",
    "sample_json": None,
}


class PDFResponse(BaseModel):
    """Response model for PDF conversion."""

    model_config = {"json_schema_extra": {"examples": [_RESPONSE_EXAMPLE, _RESPONSE_EXAMPLE_NO_VARS]}}

    html: Annotated[
        str,
        Field(description="Merged HTML document generated from all PDF pages."),
    ]
    pages_processed: Annotated[
        int,
        Field(description="Number of pages that were successfully converted.", ge=0),
    ]
    model_used: Annotated[
        str,
        Field(description="OpenAI model that performed the conversion."),
    ]
    css_mode: Annotated[
        str,
        Field(description="CSS layout mode applied to the output HTML."),
    ]
    sample_json: Annotated[
        Optional[dict[str, str]],
        Field(
            default=None,
            description="Detected template variables and their sample values. Only present when `extract_variables` is `true`.",
        ),
    ] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", tags=["Meta"], summary="API information", include_in_schema=False)
async def root():
    """Root endpoint with API information."""
    return {
        "message": "PDF2HTML API",
        "version": "0.1.0",
        "endpoints": {
            "convert": "/convert",
            "docs": "/docs",
            "health": "/health",
        },
    }


@app.get(
    "/health",
    tags=["Meta"],
    summary="Liveness probe",
    response_description="Service is healthy",
    responses={
        200: {"description": "Service is healthy and ready to accept requests."},
    },
)
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "pdf2html-api"}


@app.post(
    "/convert",
    response_model=PDFResponse,
    tags=["Conversion"],
    summary="Convert PDF to HTML (JSON)",
    response_description="Merged HTML and conversion metadata",
    responses={
        200: {
            "description": "PDF successfully converted. Returns merged HTML and metadata.",
            "content": {
                "application/json": {
                    "examples": {
                        "with_variables": {
                            "summary": "extract_variables=true — sample_json populated",
                            "value": _RESPONSE_EXAMPLE,
                        },
                        "without_variables": {
                            "summary": "extract_variables=false — sample_json omitted",
                            "value": _RESPONSE_EXAMPLE_NO_VARS,
                        },
                    }
                }
            },
        },
        422: {
            "description": "Validation error – the request body is malformed or a required field is missing.",
        },
        500: {
            "description": "Internal error during conversion (e.g. OpenAI API failure, invalid PDF).",
            "content": {
                "application/json": {
                    "example": {"detail": "Conversion failed: <error message>"}
                }
            },
        },
    },
)
async def convert_pdf_to_html(
    request: PDFRequest, background_tasks: BackgroundTasks
):
    """
    Convert a PDF (supplied as a URL) to a single merged HTML document using
    the OpenAI Vision API.

    Each page is rasterised to an image at the requested DPI, sent to the
    model for HTML extraction, and the results are stitched together before
    being returned.

    Temporary files created during processing are cleaned up automatically
    in the background after the response is sent.
    """
    request_id = f"req_{int(time.time() * 1000)}"
    logger.info(f"[{request_id}] POST /convert — {request.pdf_url}")

    try:
        pipeline = ConversionPipeline(request)
        result = await pipeline.execute(request_id)
        background_tasks.add_task(_cleanup_files, result.artifacts)

        return PDFResponse(
            html=result.html,
            pages_processed=result.pages_processed,
            model_used=result.model_used,
            css_mode=result.css_mode,
            sample_json=result.sample_json,
        )

    except Exception as exc:
        logger.error(f"[{request_id}] Conversion failed: {exc}")
        raise HTTPException(
            status_code=500, detail=f"Conversion failed: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Background-task helpers
# ---------------------------------------------------------------------------


def _cleanup_files(artifacts: ConversionArtifacts) -> None:
    """Delete temporary PDF and image files created during a conversion."""
    try:
        if artifacts.pdf_path.exists():
            artifacts.pdf_path.unlink()
    except Exception:
        pass

    try:
        cleanup_temp_images(artifacts.image_paths, artifacts.temp_dir)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
