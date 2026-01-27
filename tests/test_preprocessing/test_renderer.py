"""Tests for PDF Renderer."""

import io
from pathlib import Path
from typing import List, Tuple

import pytest
from PIL import Image

from vlm_ocr_doc_reader.preprocessing.renderer import PDFRenderer, RenderConfig


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a simple multi-page PDF for testing.

    Args:
        tmp_path: Pytest temporary directory fixture

    Returns:
        Path to test PDF file
    """
    import fitz

    pdf_path = tmp_path / "test_document.pdf"

    # Create a 3-page PDF
    doc = fitz.open()
    for page_num in range(3):
        page = doc.new_page(width=595, height=842)  # A4 size
        # Add some text to identify the page
        text = f"Test Page {page_num + 1}"
        page.insert_text((50, 50), text, fontsize=24)

    doc.save(pdf_path)
    doc.close()

    return pdf_path


@pytest.fixture
def renderer() -> PDFRenderer:
    """Create PDF renderer instance with default config."""
    config = RenderConfig(dpi=150, quality=85, format="PNG")
    return PDFRenderer(config)


def test_render_pdf_all_pages(sample_pdf: Path, renderer: PDFRenderer) -> None:
    """Test rendering all pages from PDF.

    Args:
        sample_pdf: Test PDF fixture
        renderer: PDFRenderer fixture
    """
    results: List[Tuple[int, bytes]] = renderer.render_pdf(sample_pdf)

    # Should render all 3 pages
    assert len(results) == 3

    # Check page numbers are 1-based
    page_nums = [page_num for page_num, _ in results]
    assert page_nums == [1, 2, 3]

    # Check all images are valid PNG bytes
    for page_num, image_bytes in results:
        assert len(image_bytes) > 0
        # Verify it's a valid PNG
        img = Image.open(io.BytesIO(image_bytes))
        assert img.format == "PNG"
        assert img.width > 0
        assert img.height > 0


def test_render_pdf_specific_pages(sample_pdf: Path, renderer: PDFRenderer) -> None:
    """Test rendering specific pages from PDF.

    Args:
        sample_pdf: Test PDF fixture
        renderer: PDFRenderer fixture
    """
    # Render only pages 0 and 2 (0-based indices)
    page_indices = [0, 2]
    results: List[Tuple[int, bytes]] = renderer.render_pdf(
        sample_pdf, page_indices=page_indices
    )

    # Should render 2 pages
    assert len(results) == 2

    # Check page numbers (1-based)
    page_nums = [page_num for page_num, _ in results]
    assert page_nums == [1, 3]


def test_render_pdf_empty_indices(sample_pdf: Path, renderer: PDFRenderer) -> None:
    """Test rendering with empty page indices list.

    Args:
        sample_pdf: Test PDF fixture
        renderer: PDFRenderer fixture
    """
    results = renderer.render_pdf(sample_pdf, page_indices=[])
    assert len(results) == 0


def test_render_pdf_invalid_indices(sample_pdf: Path, renderer: PDFRenderer) -> None:
    """Test rendering with invalid page indices.

    Args:
        sample_pdf: Test PDF fixture
        renderer: PDFRenderer fixture
    """
    # Mix of valid and invalid indices
    page_indices = [0, 10, 2]  # 10 is out of bounds (only 3 pages: 0,1,2)
    results = renderer.render_pdf(sample_pdf, page_indices=page_indices)

    # Should only render valid pages
    assert len(results) == 2
    page_nums = [page_num for page_num, _ in results]
    assert page_nums == [1, 3]


def test_render_page_single(sample_pdf: Path, renderer: PDFRenderer) -> None:
    """Test rendering a single page.

    Args:
        sample_pdf: Test PDF fixture
        renderer: PDFRenderer fixture
    """
    # Render page 2 (1-based)
    image_bytes = renderer.render_page(sample_pdf, page_num=2)

    assert len(image_bytes) > 0

    # Verify it's a valid PNG
    img = Image.open(io.BytesIO(image_bytes))
    assert img.format == "PNG"
    assert img.width > 0
    assert img.height > 0


def test_render_page_with_custom_dpi(sample_pdf: Path) -> None:
    """Test rendering page with custom DPI override.

    Args:
        sample_pdf: Test PDF fixture
    """
    config = RenderConfig(dpi=100)
    renderer = PDFRenderer(config)

    # Render with default DPI (100)
    image_low_dpi = renderer.render_page(sample_pdf, page_num=1)

    # Render with custom DPI (200)
    image_high_dpi = renderer.render_page(sample_pdf, page_num=1, dpi=200)

    # Higher DPI should produce larger image
    img_low = Image.open(io.BytesIO(image_low_dpi))
    img_high = Image.open(io.BytesIO(image_high_dpi))

    assert img_high.width > img_low.width
    assert img_high.height > img_low.height


def test_render_page_invalid_number(sample_pdf: Path, renderer: PDFRenderer) -> None:
    """Test rendering with invalid page number.

    Args:
        sample_pdf: Test PDF fixture
        renderer: PDFRenderer fixture
    """
    with pytest.raises(ValueError, match="Invalid page number"):
        renderer.render_page(sample_pdf, page_num=10)  # Only 3 pages


def test_render_config_defaults() -> None:
    """Test RenderConfig default values."""
    config = RenderConfig()
    assert config.dpi == 150
    assert config.quality == 85
    assert config.format == "PNG"


def test_render_config_custom() -> None:
    """Test RenderConfig with custom values."""
    config = RenderConfig(dpi=200, quality=90, format="JPEG")
    assert config.dpi == 200
    assert config.quality == 90
    assert config.format == "JPEG"
