"""Integration test — full pipeline: DocumentProcessor → FullDescriptionOperation.

Requires DASHSCOPE_API_KEY (or QWEN_API_KEY) in .env.
Tests are skipped if the key is not set or is dummy.
"""

import os
from pathlib import Path

import pytest

from vlm_ocr_doc_reader.core.processor import DocumentProcessor
from vlm_ocr_doc_reader.operations.full_description import FullDescriptionOperation

_DUMMY_KEYS = frozenset({"test", "test-key", "test-api-key-123"})


def _is_dashscope_key_valid():
    key = (os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY") or "").strip()
    return bool(key) and key.lower() not in _DUMMY_KEYS


skip_no_api = pytest.mark.skipif(
    not _is_dashscope_key_valid(),
    reason="DASHSCOPE_API_KEY (or QWEN_API_KEY) not set or is dummy",
)

# Use 02_src root for test PDF (03_data is under 02_src)
_SRC_ROOT = Path(__file__).resolve().parent.parent.parent  # 02_src
TEST_PDF = _SRC_ROOT / "03_data" / "test_document.pdf"


@skip_no_api
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
