"""Integration tests for FullDescriptionOperation with real Gemini API.

These tests require:
1. GEMINI_API_KEY in .env file
2. Network access to Gemini API
3. A sample PDF document for testing

Run with: pytest tests/integration/test_full_description_api.py -v
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

from vlm_ocr_doc_reader.operations import FullDescriptionOperation
from vlm_ocr_doc_reader.schemas import PageInfo


# Skip all tests if API key not available
pytestmark = pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set in environment"
)


class MockProcessor:
    """Mock processor that simulates DocumentProcessor contract."""

    def __init__(self, sample_pdf_path=None):
        """Initialize mock processor.

        Args:
            sample_pdf_path: Path to sample PDF for testing
        """
        self.sample_pdf_path = sample_pdf_path
        self.pages = []
        self.vlm_agent = MockVLMAgent()

        # Render pages if PDF provided
        if sample_pdf_path and Path(sample_pdf_path).exists():
            self._render_sample_pdf()

    def _render_sample_pdf(self):
        """Render sample PDF to pages."""
        try:
            import fitz  # pymupdf
            from io import BytesIO
            from PIL import Image

            doc = fitz.open(self.sample_pdf_path)

            for idx in range(min(len(doc), 5)):  # Max 5 pages for testing
                page = doc.load_page(idx)
                pix = page.get_pixmap(dpi=150)
                mode = "RGB" if pix.alpha == 0 else "RGBA"
                img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

                if mode == "RGBA":
                    img = img.convert("RGB")

                buf = BytesIO()
                img.save(buf, format="JPEG", quality=85)
                self.pages.append(PageInfo(index=idx + 1, image=buf.getvalue()))

            doc.close()

        except Exception as e:
            pytest.skip(f"Failed to render sample PDF: {e}")


class MockVLMAgent:
    """Mock VLM agent that calls real Gemini API."""

    def __init__(self):
        """Initialize mock agent with real Gemini client."""
        try:
            from vlm_ocr_doc_reader._reference.gemini_client import GeminiRestClient

            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not found")

            self.client = GeminiRestClient(api_key=api_key)

        except ImportError as e:
            pytest.skip(f"Failed to import GeminiRestClient: {e}")

    def invoke(self, prompt, images):
        """Invoke Gemini API with prompt and images.

        Args:
            prompt: Text prompt
            images: List of image bytes

        Returns:
            Dict with 'text' key
        """
        try:
            # Use generate_content for JSON response
            result = self.client.generate_content(prompt, images)

            # Result is already parsed JSON from generate_content
            # Convert back to text for consistency
            import json
            return {"text": json.dumps(result, ensure_ascii=False)}

        except Exception as e:
            pytest.fail(f"Gemini API call failed: {e}")


@pytest.fixture
def sample_pdf():
    """Path to sample PDF for testing.

    Create a simple test PDF if not available.
    """
    pdf_path = Path(__file__).parent.parent.parent / "03_data" / "test_document.pdf"

    # Create test PDF if not exists
    if not pdf_path.exists():
        _create_test_pdf(pdf_path)

    return pdf_path


def _create_test_pdf(pdf_path: Path):
    """Create a simple test PDF with headers and text.

    Args:
        pdf_path: Path where to save the PDF
    """
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
class TestFullDescriptionIntegration:
    """Integration tests with real Gemini API."""

    def test_extract_text_from_pdf(self, sample_pdf):
        """Test extracting text from real PDF."""
        processor = MockProcessor(sample_pdf)
        operation = FullDescriptionOperation(processor)

        result = operation.execute()

        # Should return DocumentData
        assert hasattr(result, 'text')
        assert hasattr(result, 'structure')
        assert hasattr(result, 'tables')

        # Text should be extracted
        assert len(result.text) > 0
        print(f"\nExtracted text length: {len(result.text)} chars")
        print(f"Text preview: {result.text[:200]}...")

    def test_extract_structure_from_pdf(self, sample_pdf):
        """Test extracting document structure."""
        processor = MockProcessor(sample_pdf)
        operation = FullDescriptionOperation(processor)

        result = operation.execute()

        # Should have structure
        assert "headers" in result.structure
        assert isinstance(result.structure["headers"], list)

        # Should find some headers
        print(f"\nFound {len(result.structure['headers'])} headers:")
        for h in result.structure["headers"]:
            print(f"  Level {h['level']}: {h['title']} (page {h['page']})")

    def test_tables_empty_in_v0_1_0(self, sample_pdf):
        """Test that tables is empty in v0.1.0."""
        processor = MockProcessor(sample_pdf)
        operation = FullDescriptionOperation(processor)

        result = operation.execute()

        assert result.tables == []

    def test_execute_with_page_filter(self, sample_pdf):
        """Test executing with page filter."""
        processor = MockProcessor(sample_pdf)
        operation = FullDescriptionOperation(processor)

        # Process only first 2 pages
        result = operation.execute(pages=[1, 2])

        # Should still return valid DocumentData
        assert len(result.text) > 0
        assert "headers" in result.structure

    def test_contract_compatibility(self, sample_pdf):
        """Test that result matches contract with project 07."""
        from vlm_ocr_doc_reader.schemas import DocumentData

        processor = MockProcessor(sample_pdf)
        operation = FullDescriptionOperation(processor)

        result = operation.execute()

        # Must be DocumentData instance
        assert isinstance(result, DocumentData)

        # Required fields
        assert isinstance(result.text, str)
        assert isinstance(result.structure, dict)
        assert isinstance(result.tables, list)

        # Structure must have headers
        assert "headers" in result.structure

        # Headers must have required fields
        for h in result.structure["headers"]:
            assert "level" in h
            assert "title" in h
            assert "page" in h
            assert isinstance(h["level"], int)
            assert isinstance(h["title"], str)
            assert isinstance(h["page"], int)


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "-s"])
