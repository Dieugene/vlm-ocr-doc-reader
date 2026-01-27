"""PDF Renderer for converting PDF pages to PNG images."""

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # pymupdf
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class RenderConfig:
    """Configuration for PDF rendering."""

    dpi: int = 150
    quality: int = 85  # Not used for PNG, kept for compatibility
    format: str = "PNG"


class PDFRenderer:
    """Renders PDF pages to PNG images using pymupdf (fitz)."""

    def __init__(self, config: RenderConfig):
        """Initialize PDF renderer with configuration.

        Args:
            config: Render configuration (DPI, quality, format)
        """
        self.config = config

    def render_pdf(
        self,
        pdf_path: Path,
        page_indices: Optional[List[int]] = None,
    ) -> List[Tuple[int, bytes]]:
        """Render PDF pages to PNG bytes.

        Args:
            pdf_path: Path to PDF file
            page_indices: List of page indices (0-based), None = all pages

        Returns:
            List of (page_num, image_bytes) tuples
            page_num is 1-based for user convenience
        """
        doc = fitz.open(pdf_path)
        try:
            total_pages = len(doc)

            if page_indices is None:
                page_indices = list(range(total_pages))

            logger.info(
                f"Rendering {len(page_indices)} pages from {pdf_path} "
                f"(Total pages: {total_pages}, DPI: {self.config.dpi})"
            )

            results: List[Tuple[int, bytes]] = []

            for idx in page_indices:
                if idx < 0 or idx >= total_pages:
                    logger.warning(f"Invalid page index {idx}, skipping")
                    continue

                page = doc.load_page(idx)
                pix = page.get_pixmap(dpi=self.config.dpi)

                # Determine image mode based on alpha channel
                mode = "RGB" if pix.alpha == 0 else "RGBA"
                img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

                # Convert RGBA to RGB for consistency
                if mode == "RGBA":
                    img = img.convert("RGB")

                # Save as PNG bytes
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                image_bytes = buf.getvalue()

                # Return 1-based page number for user convenience
                results.append((idx + 1, image_bytes))

            logger.info(f"Successfully rendered {len(results)} pages")
            return results

        finally:
            doc.close()

    def render_page(
        self,
        pdf_path: Path,
        page_num: int,
        dpi: Optional[int] = None,
    ) -> bytes:
        """Render a single page with custom DPI override.

        Args:
            pdf_path: Path to PDF file
            page_num: 1-based page number
            dpi: Custom DPI override, None = use config default

        Returns:
            PNG image bytes

        Raises:
            ValueError: If page_num is invalid
        """
        render_dpi = dpi if dpi is not None else self.config.dpi

        doc = fitz.open(pdf_path)
        try:
            total_pages = len(doc)

            # Convert to 0-based index
            page_idx = page_num - 1

            if page_idx < 0 or page_idx >= total_pages:
                raise ValueError(
                    f"Invalid page number {page_num} "
                    f"(must be 1-{total_pages})"
                )

            logger.info(
                f"Rendering page {page_num} from {pdf_path} "
                f"(DPI: {render_dpi})"
            )

            page = doc.load_page(page_idx)
            pix = page.get_pixmap(dpi=render_dpi)

            mode = "RGB" if pix.alpha == 0 else "RGBA"
            img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

            if mode == "RGBA":
                img = img.convert("RGB")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            image_bytes = buf.getvalue()

            logger.info(
                f"Successfully rendered page {page_num} "
                f"(size: {len(image_bytes)} bytes)"
            )

            return image_bytes

        finally:
            doc.close()
