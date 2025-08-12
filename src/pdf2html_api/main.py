"""Main FastAPI application for PDF2HTML API."""

import tempfile
from pathlib import Path
from typing import Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, HttpUrl

from .config import get_settings
from .html_merge import merge_pages
from .llm import HTMLGenerator
from .pdf_to_images import cleanup_temp_images, render_pdf_to_images

# Initialize FastAPI app
app = FastAPI(
    title="PDF2HTML API",
    description="Convert PDF pages to HTML using OpenAI Vision API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


class PDFRequest(BaseModel):
    """Request model for PDF conversion."""

    pdf_url: HttpUrl
    model: Optional[str] = "gpt-4o-mini"
    dpi: Optional[int] = 200
    max_tokens: Optional[int] = 4000
    temperature: Optional[float] = 0.0
    css_mode: Optional[str] = "grid"


class PDFResponse(BaseModel):
    """Response model for PDF conversion."""

    html: str
    pages_processed: int
    model_used: str
    css_mode: str


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "PDF2HTML API",
        "version": "0.1.0",
        "endpoints": {"convert": "/convert", "docs": "/docs", "health": "/health"},
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "pdf2html-api"}


@app.post("/convert", response_model=PDFResponse)
async def convert_pdf_to_html(request: PDFRequest, background_tasks: BackgroundTasks):
    """
    Convert PDF from URL to HTML using OpenAI Vision API.

    This endpoint:
    1. Downloads the PDF from the provided URL
    2. Converts each page to an image
    3. Uses OpenAI Vision API to extract HTML from each page
    4. Merges all pages into a complete HTML document
    5. Returns the final HTML

    Args:
        request: PDFRequest containing the PDF URL and optional parameters
        background_tasks: FastAPI background tasks for cleanup

    Returns:
        PDFResponse containing the HTML and metadata

    Raises:
        HTTPException: If any step in the process fails
    """
    try:
        # Load settings
        settings = get_settings()

        # Override settings with request parameters
        settings.model = request.model
        settings.dpi = request.dpi
        settings.max_tokens = request.max_tokens or 4000
        settings.temperature = request.temperature or 0.0

        # Validate CSS mode
        if request.css_mode not in ["grid", "columns", "single"]:
            raise HTTPException(
                status_code=400,
                detail=f"CSS mode must be valid got '{request.css_mode}'",
            )
        settings.css_mode = request.css_mode or "grid"

        # Step 1: Download PDF from URL
        pdf_path = await _download_pdf_from_url(str(request.pdf_url))

        # Step 2: Convert PDF to images
        image_paths, temp_dir = render_pdf_to_images(pdf_path, settings.dpi)

        # Add cleanup to background tasks
        background_tasks.add_task(_cleanup_files, pdf_path, image_paths, temp_dir)

        # Step 3: Initialize HTML generator
        html_generator = HTMLGenerator(
            api_key=settings.openai_api_key,
            model=settings.model,
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
        )

        # Step 4: Convert each page to HTML
        page_html_list = []

        for i, image_path in enumerate(image_paths, 1):
            try:
                html = html_generator.image_page_to_html(image_path, settings.css_mode)
                page_html_list.append(html)
            except Exception as e:
                err = '<section class="page"> '
                '<p class="ocr-uncertain">'
                f"  [Error processing page {i}: {e}]"
                "</p>"
                "</section>"
                # Continue with other pages instead of failing completely
                page_html_list.append(err)

        # Step 5: Merge pages into final HTML
        final_html = merge_pages(page_html_list, settings.css_mode)

        return PDFResponse(
            html=final_html,
            pages_processed=len(page_html_list),
            model_used=settings.model,
            css_mode=settings.css_mode,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


@app.post("/convert/html", response_class=HTMLResponse)
async def convert_pdf_to_html_direct(
    request: PDFRequest, background_tasks: BackgroundTasks
):
    """
    Convert PDF from URL to HTML and return raw HTML response.

    This endpoint returns the HTML directly as the response body,
    useful for embedding or direct display.
    """
    try:
        # Load settings
        settings = get_settings()

        # Override settings with request parameters
        settings.model = request.model or "gpt-4o-mini"
        settings.dpi = request.dpi or 200
        settings.max_tokens = request.max_tokens or 4000
        settings.temperature = request.temperature or 0.0

        # Validate CSS mode
        if request.css_mode not in ["grid", "columns", "single"]:
            raise HTTPException(
                status_code=400,
                detail=f"CSS mode must be valid, got '{request.css_mode}'",
            )
        settings.css_mode = request.css_mode or "grid"

        # Step 1: Download PDF from URL
        pdf_path = await _download_pdf_from_url(str(request.pdf_url))

        # Step 2: Convert PDF to images
        image_paths, temp_dir = render_pdf_to_images(pdf_path, settings.dpi)

        # Add cleanup to background tasks
        background_tasks.add_task(_cleanup_files, pdf_path, image_paths, temp_dir)

        # Step 3: Initialize HTML generator
        html_generator = HTMLGenerator(
            api_key=settings.openai_api_key,
            model=settings.model,
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
        )

        # Step 4: Convert each page to HTML
        page_html_list = []

        for i, image_path in enumerate(image_paths, 1):
            try:
                html = html_generator.image_page_to_html(image_path, settings.css_mode)
                page_html_list.append(html)
            except Exception as e:
                # Continue with other pages instead of failing completely
                err = '<section class="page"> '
                '<p class="ocr-uncertain">'
                f"  [Error processing page {i}: {e}]"
                "</p>"
                "</section>"
                page_html_list.append(err)

        # Step 5: Merge pages into final HTML
        final_html = merge_pages(page_html_list, settings.css_mode)

        return HTMLResponse(content=final_html, media_type="text/html")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


async def _download_pdf_from_url(url: str) -> Path:
    """
    Download PDF from URL to a temporary file.

    Args:
        url: URL of the PDF to download

    Returns:
        Path to the downloaded PDF file

    Raises:
        HTTPException: If download fails
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Check if content is actually a PDF
            content_type = response.headers.get("content-type", "").lower()
            if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                raise HTTPException(
                    status_code=400, detail="URL does not point to a PDF file"
                )

            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(
                suffix=".pdf", delete=False, mode="wb"
            )

            # Write PDF content
            temp_file.write(response.content)
            temp_file.close()

            return Path(temp_file.name)

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to download PDF: HTTP {e.response.status_code}",
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Failed to download PDF: {str(e)}")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Unexpected error downloading PDF: {str(e)}"
        )


def _cleanup_files(
    pdf_path: Path, image_paths: list, temp_dir: tempfile.TemporaryDirectory
):
    """
    Clean up temporary files.

    Args:
        pdf_path: Path to the downloaded PDF file
        image_paths: List of image paths
        temp_dir: Temporary directory object
    """
    try:
        # Clean up PDF file
        if pdf_path.exists():
            pdf_path.unlink()
    except Exception:
        pass

    try:
        # Clean up images and temp directory
        cleanup_temp_images(image_paths, temp_dir)
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
