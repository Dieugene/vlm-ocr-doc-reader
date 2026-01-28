"""Integration tests for base utilities (PDF Renderer + State Manager)."""

import io
from pathlib import Path

import fitz
import pytest
from PIL import Image

from vlm_ocr_doc_reader.core.state import DiskStorage, StateManager
from vlm_ocr_doc_reader.preprocessing.renderer import PDFRenderer, RenderConfig


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a simple multi-page PDF for integration testing."""
    pdf_path = tmp_path / "integration_test.pdf"

    # Create a 3-page PDF with different content
    doc = fitz.open()
    for page_num in range(3):
        page = doc.new_page(width=595, height=842)  # A4 size
        text = f"Integration Test - Page {page_num + 1}"
        page.insert_text((50, 50), text, fontsize=24)

        # Add some unique content per page
        if page_num == 0:
            page.insert_text((50, 100), "First page with header", fontsize=16)
        elif page_num == 1:
            page.insert_text((50, 100), "Second page with content", fontsize=16)
        else:
            page.insert_text((50, 100), "Third page with footer", fontsize=16)

    doc.save(pdf_path)
    doc.close()

    return pdf_path


def test_pdf_to_state_manager_workflow(sample_pdf: Path, tmp_path: Path) -> None:
    """Test complete workflow: PDF → render → StateManager.

    This test validates:
    1. PDF rendering produces valid PNG bytes
    2. All pages are rendered correctly
    3. StateManager can save and load pages
    4. DiskStorage creates proper file structure
    """
    # Setup
    render_config = RenderConfig(dpi=150)
    renderer = PDFRenderer(render_config)
    state_dir = tmp_path / "state"
    storage = DiskStorage(state_dir)
    state_manager = StateManager(storage)

    # Step 1: Render all pages from PDF
    print("\n=== Step 1: Rendering PDF pages ===")
    rendered_pages = renderer.render_pdf(sample_pdf)

    assert len(rendered_pages) == 3, "Should render all 3 pages"

    # Step 2: Save all rendered pages to StateManager
    print("\n=== Step 2: Saving pages to StateManager ===")
    for page_num, image_bytes in rendered_pages:
        print(f"  Saving page {page_num} ({len(image_bytes)} bytes)")
        state_manager.save_page(page_num, image_bytes)

        # Verify it's a valid PNG
        img = Image.open(io.BytesIO(image_bytes))
        assert img.format == "PNG", f"Page {page_num} should be PNG format"
        assert img.width > 0, f"Page {page_num} should have valid width"
        assert img.height > 0, f"Page {page_num} should have valid height"

    # Step 3: Verify StateManager saved all pages to disk
    print("\n=== Step 3: Verifying disk storage ===")
    for page_num in [1, 2, 3]:
        # Check file exists
        page_file = storage.pages_dir / f"page_{page_num:03d}.png"
        assert page_file.exists(), f"Page file {page_file} should exist"

        # Verify file size > 0
        assert page_file.stat().st_size > 0, f"Page file {page_file} should not be empty"
        print(f"  [OK] Page {page_num}: {page_file.stat().st_size} bytes")

    # Step 4: Load pages back from StateManager
    print("\n=== Step 4: Loading pages from StateManager ===")
    for page_num in [1, 2, 3]:
        loaded_bytes = state_manager.load_page(page_num)
        assert loaded_bytes is not None, f"Page {page_num} should be loadable"
        assert len(loaded_bytes) > 0, f"Page {page_num} should have data"

        # Verify it's still a valid PNG
        img = Image.open(io.BytesIO(loaded_bytes))
        assert img.format == "PNG"
        print(f"  [OK] Loaded page {page_num}: {img.width}x{img.height} pixels")

    # Step 5: Simulate operation results
    print("\n=== Step 5: Saving operation results ===")
    test_results = {
        "page_analysis": {
            "total_pages": 3,
            "pages_with_headers": [1],
            "pages_with_content": [2],
            "pages_with_footers": [3],
        },
        "metadata": {
            "dpi": 150,
            "format": "PNG",
        },
    }

    state_manager.save_operation_result("analysis", test_results)

    # Verify YAML file was created
    result_file = storage.results_dir / "analysis.yaml"
    assert result_file.exists(), "Result YAML file should exist"
    print(f"  [OK] Result file created: {result_file.stat().st_size} bytes")

    # Step 6: Load operation result back
    print("\n=== Step 6: Loading operation results ===")
    loaded_result = storage.load("results/analysis")
    assert loaded_result == test_results, "Loaded result should match saved result"
    print(f"  [OK] Loaded operation result with {len(loaded_result)} keys")

    # Step 7: Verify complete directory structure
    print("\n=== Step 7: Verifying directory structure ===")
    assert storage.cache_dir.exists()
    assert storage.pages_dir.exists()
    assert storage.vlm_responses_dir.exists()
    assert storage.results_dir.exists()
    assert storage.logs_dir.exists()
    print("  [OK] All directories created successfully")

    print("\n=== Integration test completed successfully ===")


def test_partial_rendering_workflow(sample_pdf: Path, tmp_path: Path) -> None:
    """Test workflow with selective page rendering."""
    # Setup
    renderer = PDFRenderer(RenderConfig(dpi=150))
    state_manager = StateManager(DiskStorage(tmp_path / "state"))

    # Render only pages 1 and 3 (indices 0 and 2)
    rendered_pages = renderer.render_pdf(sample_pdf, page_indices=[0, 2])

    assert len(rendered_pages) == 2

    # Save to state manager
    for page_num, image_bytes in rendered_pages:
        state_manager.save_page(page_num, image_bytes)

    # Verify only specified pages are saved
    assert state_manager.load_page(1) is not None
    assert state_manager.load_page(3) is not None
    assert state_manager.load_page(2) is None  # Not rendered


def test_custom_dpi_rendering_workflow(sample_pdf: Path, tmp_path: Path) -> None:
    """Test workflow with custom DPI settings."""
    renderer = PDFRenderer(RenderConfig(dpi=100))
    state_manager = StateManager(DiskStorage(tmp_path / "state"))

    # Render with default DPI (100)
    image_100dpi = renderer.render_page(sample_pdf, page_num=1)
    state_manager.save_page(1, image_100dpi)

    # Render with higher DPI (200)
    image_200dpi = renderer.render_page(sample_pdf, page_num=1, dpi=200)
    state_manager.save_page(1, image_200dpi)  # Overwrite

    # Load back and verify higher resolution
    loaded = state_manager.load_page(1)
    assert loaded is not None

    img = Image.open(io.BytesIO(loaded))
    assert img.width > 500  # Should be larger with 200 DPI
