"""Tests for OCR Tool — real Qwen API calls.

Requires QWEN_API_KEY environment variable.
Tests are skipped if the key is not set.
"""

import os
from pathlib import Path

import pytest

from vlm_ocr_doc_reader.core.ocr_tool import OCRTool
from vlm_ocr_doc_reader.core.ocr_client import QwenOCRClient, OCRConfig
from vlm_ocr_doc_reader.core.state import StateManager, MemoryStorage
from vlm_ocr_doc_reader.preprocessing.renderer import PDFRenderer, RenderConfig

QWEN_API_KEY = os.getenv("QWEN_API_KEY")
skip_no_qwen = pytest.mark.skipif(
    not QWEN_API_KEY, reason="QWEN_API_KEY not set"
)

TEST_PDF = Path(r"D:\_storage_cbr\020_docs_vision\08_vlm-ocr-doc-reader\03_data\test_document.pdf")


@pytest.fixture(scope="module")
def page_images():
    """Render test PDF pages."""
    renderer = PDFRenderer(RenderConfig(dpi=150))
    rendered = renderer.render_pdf(TEST_PDF)
    return {num: img for num, img in rendered}


@pytest.fixture
def state_manager_with_pages(page_images):
    """Create StateManager pre-loaded with real page images."""
    storage = MemoryStorage()
    sm = StateManager(storage)
    for page_num, img in page_images.items():
        sm.save_page(page_num, img)
    return sm


@pytest.fixture
def ocr_tool(state_manager_with_pages):
    """Create OCRTool with real QwenOCRClient."""
    config = OCRConfig(api_key=QWEN_API_KEY)
    client = QwenOCRClient(config)
    return OCRTool(client, state_manager_with_pages)


@skip_no_qwen
class TestOCRToolReal:
    """Real API tests for OCRTool."""

    def test_execute_extracts_value(self, ocr_tool):
        """Test that OCR tool extracts a value from the first page."""
        result = ocr_tool.execute(page_num=1, prompt="Извлеки заголовок документа")

        assert result["status"] in ("ok", "no_data")
        if result["status"] == "ok":
            assert len(result["value"]) > 0
            assert isinstance(result["value"], str)

    def test_execute_page_not_found(self, ocr_tool):
        """Test error when requested page is not in storage."""
        result = ocr_tool.execute(page_num=999, prompt="test")

        assert result["status"] == "error"
        assert "999" in result["explanation"]
