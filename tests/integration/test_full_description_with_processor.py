"""Integration test for FullDescriptionOperation with DocumentProcessor.

This test verifies that FullDescriptionOperation works correctly with the
real DocumentProcessor implementation.
"""

import os
import sys
import pytest
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "02_src"))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from vlm_ocr_doc_reader.core.processor import DocumentProcessor
from vlm_ocr_doc_reader.operations import FullDescriptionOperation
from vlm_ocr_doc_reader.schemas import DocumentData

# Skip tests if API key not available
pytestmark = pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set in environment"
)


@pytest.fixture
def sample_pdf():
    """Path to sample PDF for testing."""
    pdf_path = Path(__file__).parent.parent.parent / "03_data" / "test_document.pdf"

    # Create test PDF if not exists
    if not pdf_path.exists():
        _create_test_pdf(pdf_path)

    return pdf_path


def _create_test_pdf(pdf_path: Path):
    """Create a simple test PDF with headers and text."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch

        # Create parent directory
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        # Create PDF
        c = canvas.Canvas(str(pdf_path), pagesize=letter)

        # Page 1 - Main title
        c.setFont("Helvetica-Bold", 18)
        c.drawString(1 * inch, 10 * inch, "Test Document")
        c.setFont("Helvetica", 12)
        c.drawString(1 * inch, 9 * inch, "This is a test document for VLM OCR processing.")

        # Page 2 - Section 1
        c.showPage()
        c.setFont("Helvetica-Bold", 16)
        c.drawString(1 * inch, 10 * inch, "1. Introduction")
        c.setFont("Helvetica", 12)
        c.drawString(1 * inch, 9 * inch, "This is the introduction section.")

        # Page 3 - Subsection
        c.showPage()
        c.setFont("Helvetica-Bold", 14)
        c.drawString(1 * inch, 10 * inch, "1.1. Background")
        c.setFont("Helvetica", 12)
        c.drawString(1 * inch, 9 * inch, "Background information goes here.")

        c.save()

    except ImportError:
        pytest.skip("reportlab not installed - cannot create test PDF")
    except Exception as e:
        pytest.skip(f"Failed to create test PDF: {e}")


@pytest.mark.integration
class TestFullDescriptionWithProcessor:
    """Integration tests with DocumentProcessor."""

    def test_full_description_operation_with_processor(self, sample_pdf):
        """Test FullDescriptionOperation with real DocumentProcessor."""
        # Create processor from PDF
        processor = DocumentProcessor(source=sample_pdf)

        # Create operation
        operation = FullDescriptionOperation(processor)

        # Execute operation
        result = operation.execute()

        # Verify result
        assert isinstance(result, DocumentData)
        assert len(result.text) > 0
        assert "headers" in result.structure
        assert result.tables == []  # Empty in v0.1.0

        print(f"\n✓ Extracted {len(result.text)} characters")
        print(f"✓ Found {len(result.structure['headers'])} headers")

        for h in result.structure['headers']:
            print(f"  - Level {h['level']}: {h['title']} (page {h['page']})")

    def test_full_description_with_page_filter(self, sample_pdf):
        """Test FullDescriptionOperation with page filter."""
        processor = DocumentProcessor(source=sample_pdf)
        operation = FullDescriptionOperation(processor)

        # Process only first 2 pages
        result = operation.execute(pages=[1, 2])

        # Should still return valid DocumentData
        assert isinstance(result, DocumentData)
        assert len(result.text) > 0
        assert "headers" in result.structure

        print(f"\n✓ Processed pages 1-2, extracted {len(result.text)} characters")

    def test_contract_compliance(self, sample_pdf):
        """Test that result complies with contract from project 07."""
        processor = DocumentProcessor(source=sample_pdf)
        operation = FullDescriptionOperation(processor)

        result = operation.execute()

        # Must be DocumentData instance
        assert isinstance(result, DocumentData)

        # Required fields (contract with project 07)
        assert hasattr(result, 'text')
        assert hasattr(result, 'structure')
        assert hasattr(result, 'tables')

        assert isinstance(result.text, str)
        assert isinstance(result.structure, dict)
        assert isinstance(result.tables, list)

        # Structure must have headers
        assert "headers" in result.structure
        assert isinstance(result.structure["headers"], list)

        # Headers must have required fields
        for h in result.structure["headers"]:
            assert "level" in h
            assert "title" in h
            assert "page" in h
            assert isinstance(h["level"], int)
            assert isinstance(h["title"], str)
            assert isinstance(h["page"], int)

        print("\n✓ Contract compliance verified")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
