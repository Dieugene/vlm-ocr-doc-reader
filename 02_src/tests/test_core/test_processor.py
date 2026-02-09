"""Tests for DocumentProcessor — real API calls.

Requires GEMINI_API_KEY environment variable.
Tests are skipped if the key is not set.
"""

import os
from pathlib import Path

import pytest

from vlm_ocr_doc_reader.core.processor import DocumentProcessor
from vlm_ocr_doc_reader.core.state import MemoryStorage, StateManager

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
skip_no_gemini = pytest.mark.skipif(
    not GEMINI_API_KEY, reason="GEMINI_API_KEY not set"
)

TEST_PDF = Path(r"D:\_storage_cbr\020_docs_vision\08_vlm-ocr-doc-reader\03_data\test_document.pdf")


@skip_no_gemini
class TestDocumentProcessorReal:
    """Real API tests for DocumentProcessor."""

    def test_init_from_pdf(self):
        """Test processor initialization from PDF renders pages and saves to state."""
        storage = MemoryStorage()
        sm = StateManager(storage)

        processor = DocumentProcessor(
            source=TEST_PDF,
            state_manager=sm,
            auto_save=True,
        )

        assert processor.num_pages > 0
        assert len(processor.pages) == processor.num_pages

        # Pages should be saved in storage
        for page in processor.pages:
            assert storage.exists(f"pages/{page.index:03d}")

    def test_init_creates_vlm_agent_with_tools(self):
        """Test that processor auto-creates VLM agent with OCR tool if keys are set."""
        processor = DocumentProcessor(
            source=TEST_PDF,
            auto_save=True,
        )

        assert processor.vlm_agent is not None
        assert processor.state_manager is not None
        assert processor.num_pages > 0

    def test_vlm_agent_invoke_through_processor(self):
        """Test that the VLM agent created by processor can invoke."""
        processor = DocumentProcessor(
            source=TEST_PDF,
            auto_save=True,
        )

        # Use the agent to describe the first page
        img = processor.pages[0].image
        result = processor.vlm_agent.invoke(
            "Кратко опиши эту страницу (1-2 предложения).",
            [img],
        )

        assert result["text"] is not None
        assert len(result["text"]) > 10
