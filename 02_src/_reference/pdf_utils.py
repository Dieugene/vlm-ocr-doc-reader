import fitz  # pymupdf
from typing import List, Tuple
import io
from functools import lru_cache
from PIL import Image

from .logger import setup_logger

logger = setup_logger("pdf_utils")


@lru_cache(maxsize=128)
def get_page_count(pdf_path: str) -> int:
    """
    Returns the number of pages in the PDF. Cached by path to avoid re-opening
    the same file repeatedly during triage.
    """
    doc = fitz.open(pdf_path)
    try:
        return len(doc)
    finally:
        doc.close()


def render_pages_batch(
    pdf_path: str, page_indices: List[int], dpi: int = 110, quality: int = 80
) -> List[Tuple[int, bytes]]:
    """
    Renders selected pages to JPEG bytes. Indices are 0-based.
    Designed for low-dpi triage windows to control token usage.
    """
    if not page_indices:
        return []

    doc = fitz.open(pdf_path)
    results: List[Tuple[int, bytes]] = []
    try:
        for idx in page_indices:
            page = doc.load_page(idx)
            pix = page.get_pixmap(dpi=dpi)
            mode = "RGB" if pix.alpha == 0 else "RGBA"
            img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
            if mode == "RGBA":
                img = img.convert("RGB")

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            results.append((idx, buf.getvalue()))
        return results
    finally:
        doc.close()

def render_pages_for_gemini(pdf_path: str) -> List[Tuple[int, bytes]]:
    """
    Renders specific pages (1, 2-4, last 2) to images (JPEG bytes).
    Returns a list of tuples (page_number, image_bytes).
    """
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        indices = set()
        
        # Iteration 003: Render strictly first 8 pages
        limit = min(8, total_pages)
        for i in range(limit):
            indices.add(i)

        sorted_indices = sorted(list(indices))
        
        results = []
        logger.info(f"Rendering {len(sorted_indices)} pages from {pdf_path} (Total pages: {total_pages})")
        
        for idx in sorted_indices:
            page = doc.load_page(idx)
            # dpi=150 is usually a good balance between quality and token usage
            pix = page.get_pixmap(dpi=150) 
            
            # Convert to PIL Image to save as JPEG bytes
            mode = "RGB" if pix.alpha == 0 else "RGBA"
            img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
            if mode == "RGBA":
                img = img.convert("RGB")
            
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            results.append((idx + 1, buf.getvalue()))
            
        doc.close()
        return results
    except Exception as e:
        logger.error(f"Error rendering PDF {pdf_path}: {e}")
        raise



