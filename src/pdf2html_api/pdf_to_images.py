"""Convert PDF pages to images using PyMuPDF."""

import tempfile
from pathlib import Path
from typing import List

import fitz  # PyMuPDF


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
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    # Open the PDF document
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        raise ValueError(f"Failed to open PDF file {pdf_path}: {e}")
    
    if doc.page_count == 0:
        doc.close()
        raise ValueError(f"PDF file {pdf_path} has no pages")
    
    # Calculate zoom factor from DPI
    # PyMuPDF uses 72 DPI as base, so zoom = target_dpi / 72
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    
    # Create temporary directory for images
    temp_dir = tempfile.TemporaryDirectory()
    image_paths = []
    
    try:
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            
            # Render page to pixmap
            pix = page.get_pixmap(matrix=mat)
            
            # Save as PNG
            image_path = Path(temp_dir.name) / f"page_{page_num + 1:03d}.png"
            pix.save(str(image_path))
            
            image_paths.append(image_path)
            
            # Clean up pixmap
            pix = None
            
    finally:
        doc.close()
    
    # Return both the image paths and the temp directory object
    # The caller is responsible for cleanup when done with the images
    return image_paths, temp_dir


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