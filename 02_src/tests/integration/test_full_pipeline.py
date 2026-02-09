"""Integration test — full pipeline: DocumentProcessor → FullDescriptionOperation.

Requires GEMINI_API_KEY (and optionally QWEN_API_KEY) environment variables.
Tests are skipped if GEMINI_API_KEY is not set.
"""

import os
from pathlib import Path

import pytest

from vlm_ocr_doc_reader.core.processor import DocumentProcessor
from vlm_ocr_doc_reader.operations.full_description import FullDescriptionOperation

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
skip_no_gemini = pytest.mark.skipif(
    not GEMINI_API_KEY, reason="GEMINI_API_KEY not set"
)

TEST_PDF = Path(r"D:\_storage_cbr\020_docs_vision\08_vlm-ocr-doc-reader\03_data\test_document.pdf")


@skip_no_gemini
class TestFullPipeline:
    """Full pipeline integration test."""

    def test_full_description_extracts_text(self):
        """Test that FullDescriptionOperation produces non-empty text."""
        processor = DocumentProcessor(
            source=TEST_PDF,
            auto_save=True,
        )

        operation = FullDescriptionOperation(processor)
        result = operation.execute()

        # DocumentData should have non-empty text
        assert result.text is not None
        assert len(result.text) > 50, f"Text too short: {result.text[:100]}"

        # Structure should have headers list
        assert "headers" in result.structure

    def test_full_description_limited_pages(self):
        """Test FullDescriptionOperation on a subset of pages."""
        processor = DocumentProcessor(
            source=TEST_PDF,
            auto_save=True,
        )

        # Process only first page
        operation = FullDescriptionOperation(processor)
        result = operation.execute(pages=[1])

        assert result.text is not None
        assert len(result.text) > 10
