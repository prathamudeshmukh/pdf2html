"""Main FastAPI application for PDF2HTML API.

This module is intentionally kept thin: it owns the HTTP contract
(request/response models, route handlers, error boundaries) and delegates
all business logic to the services layer.
"""

import logging
import time
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, HttpUrl

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
    description="Convert PDF pages to HTML using OpenAI Vision API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class PDFRequest(BaseModel):
    """Request model for PDF conversion."""

    pdf_url: HttpUrl
    model: Optional[str] = "gpt-4o-mini"
    dpi: Optional[int] = 200
    max_tokens: Optional[int] = 4000
    temperature: Optional[float] = 0.0
    css_mode: Optional[str] = "grid"
    max_parallel_workers: Optional[int] = 3
    extract_variables: Optional[bool] = False


class PDFResponse(BaseModel):
    """Response model for PDF conversion."""

    html: str
    pages_processed: int
    model_used: str
    css_mode: str
    sample_json: Optional[dict[str, str]] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "pdf2html-api"}


@app.post("/convert", response_model=PDFResponse)
async def convert_pdf_to_html(
    request: PDFRequest, background_tasks: BackgroundTasks
):
    """
    Convert PDF from URL to HTML using OpenAI Vision API.

    Returns:
        PDFResponse containing the merged HTML and conversion metadata.
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


@app.post("/convert/html", response_class=HTMLResponse)
async def convert_pdf_to_html_direct(
    request: PDFRequest, background_tasks: BackgroundTasks
):
    """
    Convert PDF from URL to HTML and return raw HTML.

    Useful for direct embedding or display without JSON wrapping.
    """
    request_id = f"req_{int(time.time() * 1000)}"
    logger.info(f"[{request_id}] POST /convert/html — {request.pdf_url}")

    try:
        pipeline = ConversionPipeline(request)
        result = await pipeline.execute(request_id)
        background_tasks.add_task(_cleanup_files, result.artifacts)

        return HTMLResponse(content=result.html, media_type="text/html")

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
