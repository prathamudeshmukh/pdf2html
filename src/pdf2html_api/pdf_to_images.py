"""Convert PDF pages to images using PyMuPDF."""

import tempfile
import time
import logging
from pathlib import Path
from typing import List

import fitz  # PyMuPDF

# Optional PIL import for image optimization
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

logger = logging.getLogger(__name__)


def render_pdf_to_images(pdf_path: Path, dpi: int = 200) -> tuple[List[Path], tempfile.TemporaryDirectory]:
    """
    Render each PDF page to a PNG image.
    
    Args:
        pdf_path: Path to the input PDF file
        dpi: Resolution for rendering (dots per inch)
        
    Returns:
        Tuple of (list of paths to the generated PNG images, temporary directory object)
        
    Raises:
        FileNotFoundError: If PDF file doesn't exist
        ValueError: If PDF file is invalid or empty
    """
    render_start = time.time()
    logger.info(f"Starting PDF to image conversion: {pdf_path}, DPI: {dpi}")
    
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    # Open the PDF document
    open_start = time.time()
    try:
        doc = fitz.open(str(pdf_path))
        open_time = time.time() - open_start
        logger.info(f"PDF opened in {open_time:.3f}s, pages: {doc.page_count}")
    except Exception as e:
        open_time = time.time() - open_start
        logger.error(f"Failed to open PDF after {open_time:.3f}s: {e}")
        raise ValueError(f"Failed to open PDF file {pdf_path}: {e}")
    
    if doc.page_count == 0:
        doc.close()
        raise ValueError(f"PDF file {pdf_path} has no pages")
    
    # Calculate zoom factor from DPI
    # PyMuPDF uses 72 DPI as base, so zoom = target_dpi / 72
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    logger.info(f"Using zoom factor: {zoom:.2f} (DPI: {dpi})")
    
    # Create temporary directory for images
    temp_dir = tempfile.TemporaryDirectory()
    image_paths = []
    
    try:
        for page_num in range(doc.page_count):
            page_start = time.time()
            logger.info(f"Rendering page {page_num + 1}/{doc.page_count}...")
            
            page = doc.load_page(page_num)
            
            # Render page to pixmap
            pixmap_start = time.time()
            pix = page.get_pixmap(matrix=mat)
            pixmap_time = time.time() - pixmap_start
            logger.info(f"  Pixmap created in {pixmap_time:.3f}s, size: {pix.width}x{pix.height}")
            
            # Save as PNG
            save_start = time.time()
            image_path = Path(temp_dir.name) / f"page_{page_num + 1:03d}.png"
            pix.save(str(image_path))
            save_time = time.time() - save_start
            logger.info(f"  Image saved in {save_time:.3f}s: {image_path}")
            
            # Optimize image for API if PIL is available
            if PIL_AVAILABLE:
                optimized_path = _optimize_image_for_api(image_path)
                image_paths.append(optimized_path)
                logger.info(f"  Image optimized: {image_path.name} -> {optimized_path.name}")
            else:
                image_paths.append(image_path)
            
            # Clean up pixmap
            pix = None
            
            page_time = time.time() - page_start
            logger.info(f"Page {page_num + 1} completed in {page_time:.3f}s")
            
    finally:
        doc.close()
    
    render_time = time.time() - render_start
    logger.info(f"PDF to image conversion completed in {render_time:.3f}s")
    logger.info(f"Generated {len(image_paths)} images in {temp_dir.name}")
    
    # Return both the image paths and the temp directory object
    # The caller is responsible for cleanup when done with the images
    return image_paths, temp_dir


def _optimize_image_for_api(image_path: Path, max_size: int = 1024, quality: int = 85) -> Path:
    """
    Optimize image size for faster API processing.
    
    Args:
        image_path: Path to the original image
        max_size: Maximum dimension (width or height)
        quality: JPEG quality (1-100)
        
    Returns:
        Path to the optimized image
    """
    if not PIL_AVAILABLE:
        return image_path
    
    try:
        with Image.open(image_path) as img:
            original_size = img.size
            original_mode = img.mode
            
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Resize if too large
            if max(img.size) > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            # Save optimized image
            optimized_path = image_path.parent / f"optimized_{image_path.name}"
            img.save(optimized_path, 'PNG', optimize=True)
            
            optimized_size = img.size
            logger.info(f"Image optimized: {original_size} -> {optimized_size}, mode: {original_mode} -> RGB")
            
            return optimized_path
            
    except Exception as e:
        logger.warning(f"Failed to optimize image {image_path}: {e}")
        return image_path


def cleanup_temp_images(image_paths: List[Path], temp_dir: tempfile.TemporaryDirectory = None) -> None:
    """
    Clean up temporary image files and directory.
    
    Args:
        image_paths: List of image paths to clean up
        temp_dir: Temporary directory object to clean up
    """
    # Clean up the temporary directory if provided
    if temp_dir is not None:
        try:
            temp_dir.cleanup()
        except Exception:
            # Ignore cleanup errors
            pass
        return
    
    # Fallback cleanup for individual files (legacy support)
    for image_path in image_paths:
        try:
            if image_path.exists():
                image_path.unlink()
        except Exception:
            # Ignore cleanup errors
            pass
    
    # Try to remove the parent directory if it's empty
    if image_paths:
        try:
            temp_dir_path = image_paths[0].parent
            if temp_dir_path.exists() and not any(temp_dir_path.iterdir()):
                temp_dir_path.rmdir()
        except Exception:
            # Ignore cleanup errors
            pass 