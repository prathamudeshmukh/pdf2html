"""Main FastAPI application for PDF2HTML API."""

import tempfile
import time
import logging
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, HttpUrl

from .config import get_settings
from .html_merge import merge_pages
from .llm import HTMLGenerator
from .pdf_to_images import render_pdf_to_images, cleanup_temp_images
from .variableExtractor.html_variables import HTMLVariableExtractor
from src.pdf2html_api.sample_json_generator import SampleJSONGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pdf2html_api.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
    max_parallel_workers: Optional[int] = 3
    extract_variables: Optional[bool] = False


class PDFResponse(BaseModel):
    """Response model for PDF conversion."""
    html: str
    pages_processed: int
    model_used: str
    css_mode: str
    sample_json: Optional[dict[str, str]] = None


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "PDF2HTML API",
        "version": "0.1.0",
        "endpoints": {
            "convert": "/convert",
            "docs": "/docs",
            "health": "/health"
        }
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
    request_id = f"req_{int(time.time() * 1000)}"
    total_start_time = time.time()
    
    logger.info(f"[{request_id}] Starting PDF to HTML conversion for URL: {request.pdf_url}")
    logger.info(f"[{request_id}] Model: {request.model}, DPI: {request.dpi}, CSS Mode: {request.css_mode}")
    
    try:
        # Load settings
        settings_start = time.time()
        settings = get_settings()
        settings_time = time.time() - settings_start
        logger.info(f"[{request_id}] Settings loaded in {settings_time:.3f}s")
        
        # Override settings with request parameters
        settings.model = request.model
        settings.dpi = request.dpi
        settings.max_tokens = request.max_tokens
        settings.temperature = request.temperature
        settings.max_parallel_workers = request.max_parallel_workers
        
        # Validate CSS mode
        if request.css_mode not in ["grid", "columns", "single"]:
            raise HTTPException(
                status_code=400,
                detail=f"CSS mode must be 'grid', 'columns', or 'single', got '{request.css_mode}'"
            )
        settings.css_mode = request.css_mode
        
        # Step 1: Download PDF from URL
        download_start = time.time()
        logger.info(f"[{request_id}] Step 1: Downloading PDF from URL...")
        pdf_path = await _download_pdf_from_url(str(request.pdf_url))
        download_time = time.time() - download_start
        logger.info(f"[{request_id}] PDF downloaded in {download_time:.3f}s, size: {pdf_path.stat().st_size / 1024:.1f}KB")
        
        # Step 2: Convert PDF to images
        render_start = time.time()
        logger.info(f"[{request_id}] Step 2: Converting PDF to images (DPI: {settings.dpi})...")
        image_paths, temp_dir = render_pdf_to_images(pdf_path, settings.dpi)
        render_time = time.time() - render_start
        logger.info(f"[{request_id}] PDF rendered to {len(image_paths)} images in {render_time:.3f}s")
        
        # Add cleanup to background tasks
        background_tasks.add_task(_cleanup_files, pdf_path, image_paths, temp_dir)
        
        # Step 3: Initialize HTML generator
        init_start = time.time()
        logger.info(f"[{request_id}] Step 3: Initializing HTML generator...")
        html_generator = HTMLGenerator(
            api_key=settings.openai_api_key,
            model=settings.model,
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
        )
        init_time = time.time() - init_start
        logger.info(f"[{request_id}] HTML generator initialized in {init_time:.3f}s")
        
        # Step 4: Convert each page to HTML (with parallel processing)
        llm_start = time.time()
        logger.info(f"[{request_id}] Step 4: Converting {len(image_paths)} pages to HTML...")
        
        # Use parallel processing for multiple pages
        if len(image_paths) > 1:
            page_html_list = await _convert_pages_parallel(
                html_generator, image_paths, settings.css_mode, request_id, settings.max_parallel_workers
            )
        else:
            # Single page - no need for parallel processing
            page_html_list = []
            for i, image_path in enumerate(image_paths, 1):
                page_start = time.time()
                logger.info(f"[{request_id}] Processing page {i}/{len(image_paths)}...")
                try:
                    html = html_generator.image_page_to_html(image_path, settings.css_mode)
                    page_html_list.append(html)
                    page_time = time.time() - page_start
                    logger.info(f"[{request_id}] Page {i} completed in {page_time:.3f}s, HTML length: {len(html)} chars")
                except Exception as e:
                    page_time = time.time() - page_start
                    logger.error(f"[{request_id}] Page {i} failed after {page_time:.3f}s: {e}")
                    # Continue with other pages instead of failing completely
                    page_html_list.append(
                        f'<section class="page"><p class="ocr-uncertain">[Error processing page {i}: {e}]</p></section>'
                    )
        
        llm_time = time.time() - llm_start
        logger.info(f"[{request_id}] All pages processed in {llm_time:.3f}s (avg: {llm_time/len(image_paths):.3f}s per page)")
        
        # Step 5: Merge pages into final HTML
        merge_start = time.time()
        logger.info(f"[{request_id}] Step 5: Merging pages into final HTML...")
        final_html = merge_pages(page_html_list, settings.css_mode)
        html_with_variables = None
        sample_json = None

        # ✅ OPTIONAL VARIABLE EXTRACTION
        if request.extract_variables:
            logger.info(f"[{request_id}] Extracting template variables from HTML")

            extractor = HTMLVariableExtractor(
                api_key=settings.openai_api_key,
                model=settings.model,
                temperature=0.0,
                max_tokens=2000,
            )

            try:
                html_with_variables = extractor.extract(final_html)

                logger.info(
                    f"[{request_id}] Variable extraction completed "
                )
            except Exception as e:
                logger.error(f"[{request_id}] Variable extraction failed: {e}")
                # IMPORTANT: do not fail PDF conversion
            
        # Only generate sample JSON if extraction succeeded
        if html_with_variables:
            sample_json_generator = SampleJSONGenerator(
                api_key=settings.openai_api_key,
                model=settings.model,
                temperature=0,
                max_tokens=1000
        )

            try:
                sample_json = sample_json_generator.generate(html_with_variables)
            except Exception as e:
                logger.error(f"[{request_id}] Sample JSON generation failed: {e}")
                sample_json = {}


        merge_time = time.time() - merge_start
        logger.info(f"[{request_id}] HTML merged in {merge_time:.3f}s, final length: {len(final_html)} chars")
        
        # Calculate total time and log summary
        total_time = time.time() - total_start_time
        logger.info(f"[{request_id}] Conversion completed successfully in {total_time:.3f}s")
        logger.info(f"[{request_id}] Performance breakdown:")
        logger.info(f"[{request_id}]   - Settings: {settings_time:.3f}s ({settings_time/total_time*100:.1f}%)")
        logger.info(f"[{request_id}]   - Download: {download_time:.3f}s ({download_time/total_time*100:.1f}%)")
        logger.info(f"[{request_id}]   - Render: {render_time:.3f}s ({render_time/total_time*100:.1f}%)")
        logger.info(f"[{request_id}]   - Init: {init_time:.3f}s ({init_time/total_time*100:.1f}%)")
        logger.info(f"[{request_id}]   - LLM Processing: {llm_time:.3f}s ({llm_time/total_time*100:.1f}%)")
        logger.info(f"[{request_id}]   - Merge: {merge_time:.3f}s ({merge_time/total_time*100:.1f}%)")
        
        return PDFResponse(
            html=html_with_variables if request.extract_variables and html_with_variables else final_html,
            pages_processed=len(page_html_list),
            model_used=settings.model,
            css_mode=settings.css_mode,
            sample_json=sample_json if request.extract_variables else None
        )
        
    except Exception as e:
        total_time = time.time() - total_start_time
        logger.error(f"[{request_id}] Conversion failed after {total_time:.3f}s: {e}")
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


@app.post("/convert/html", response_class=HTMLResponse)
async def convert_pdf_to_html_direct(request: PDFRequest, background_tasks: BackgroundTasks):
    """
    Convert PDF from URL to HTML and return raw HTML response.
    
    This endpoint returns the HTML directly as the response body,
    useful for embedding or direct display.
    """
    try:
        # Load settings
        settings = get_settings()
        
        # Override settings with request parameters
        settings.model = request.model
        settings.dpi = request.dpi
        settings.max_tokens = request.max_tokens
        settings.temperature = request.temperature
        settings.max_parallel_workers = request.max_parallel_workers
        
        # Validate CSS mode
        if request.css_mode not in ["grid", "columns", "single"]:
            raise HTTPException(
                status_code=400,
                detail=f"CSS mode must be 'grid', 'columns', or 'single', got '{request.css_mode}'"
            )
        settings.css_mode = request.css_mode
        
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
        
        # Step 4: Convert each page to HTML (with parallel processing)
        if len(image_paths) > 1:
            page_html_list = await _convert_pages_parallel(
                html_generator, image_paths, settings.css_mode, f"req_{int(time.time() * 1000)}", settings.max_parallel_workers
            )
        else:
            # Single page - no need for parallel processing
            page_html_list = []
            for i, image_path in enumerate(image_paths, 1):
                try:
                    html = html_generator.image_page_to_html(image_path, settings.css_mode)
                    page_html_list.append(html)
                except Exception as e:
                    # Continue with other pages instead of failing completely
                    page_html_list.append(
                        f'<section class="page"><p class="ocr-uncertain">[Error processing page {i}: {e}]</p></section>'
                    )
        
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
    download_start = time.time()
    logger.info(f"Downloading PDF from: {url}")
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            logger.info("Making HTTP request...")
            response = await client.get(url)
            response.raise_for_status()
            
            # Check if content is actually a PDF
            content_type = response.headers.get("content-type", "").lower()
            if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                raise HTTPException(
                    status_code=400,
                    detail="URL does not point to a PDF file"
                )
            
            logger.info(f"Response received: {len(response.content)} bytes, Content-Type: {content_type}")
            
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(
                suffix=".pdf",
                delete=False,
                mode="wb"
            )
            
            # Write PDF content
            temp_file.write(response.content)
            temp_file.close()
            
            download_time = time.time() - download_start
            logger.info(f"PDF downloaded successfully in {download_time:.3f}s")
            
            return Path(temp_file.name)
            
    except httpx.HTTPStatusError as e:
        download_time = time.time() - download_start
        logger.error(f"HTTP error downloading PDF after {download_time:.3f}s: {e.response.status_code}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to download PDF: HTTP {e.response.status_code}"
        )
    except httpx.RequestError as e:
        download_time = time.time() - download_start
        logger.error(f"Request error downloading PDF after {download_time:.3f}s: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to download PDF: {str(e)}"
        )
    except Exception as e:
        download_time = time.time() - download_start
        logger.error(f"Unexpected error downloading PDF after {download_time:.3f}s: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error downloading PDF: {str(e)}"
        )


async def _convert_pages_parallel(html_generator, image_paths, css_mode, request_id, max_workers=3):
    """
    Convert multiple pages to HTML in parallel using ThreadPoolExecutor.
    
    Args:
        html_generator: HTML generator instance
        image_paths: List of image paths
        css_mode: CSS mode for layout
        request_id: Request ID for logging
        max_workers: Maximum number of parallel workers
        
    Returns:
        List of HTML strings for each page
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    logger.info(f"[{request_id}] Starting parallel processing with {max_workers} workers")
    
    def process_single_page_sync(image_path, page_index):
        """Process a single page synchronously (will run in thread pool)."""
        page_start = time.time()
        logger.info(f"[{request_id}] Processing page {page_index + 1}/{len(image_paths)}...")
        
        try:
            html = html_generator.image_page_to_html(image_path, css_mode)
            page_time = time.time() - page_start
            logger.info(f"[{request_id}] Page {page_index + 1} completed in {page_time:.3f}s, HTML length: {len(html)} chars")
            return html
        except Exception as e:
            page_time = time.time() - page_start
            logger.error(f"[{request_id}] Page {page_index + 1} failed after {page_time:.3f}s: {e}")
            return f'<section class="page"><p class="ocr-uncertain">[Error processing page {page_index + 1}: {e}]</p></section>'
    
    # Create a thread pool executor
    loop = asyncio.get_event_loop()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks to the thread pool
        futures = []
        for i, image_path in enumerate(image_paths):
            future = loop.run_in_executor(
                executor, 
                process_single_page_sync, 
                image_path, 
                i
            )
            futures.append(future)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*futures, return_exceptions=True)
    
    # Handle any exceptions
    page_html_list = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[{request_id}] Page {i + 1} failed with exception: {result}")
            page_html_list.append(f'<section class="page"><p class="ocr-uncertain">[Error processing page {i + 1}: {result}]</p></section>')
        else:
            page_html_list.append(result)
    
    logger.info(f"[{request_id}] Parallel processing completed for {len(image_paths)} pages")
    return page_html_list


def _cleanup_files(pdf_path: Path, image_paths: list, temp_dir: tempfile.TemporaryDirectory):
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