"""Unit tests for FullDescriptionOperation."""

import pytest
from unittest.mock import Mock, MagicMock

from vlm_ocr_doc_reader.operations import FullDescriptionOperation
from vlm_ocr_doc_reader.schemas import DocumentData, PageInfo


class MockDocumentProcessor:
    """Mock DocumentProcessor for testing."""

    def __init__(self, pages=None, vlm_agent=None):
        """Initialize mock processor.

        Args:
            pages: List of PageInfo objects
            vlm_agent: Mock VLM agent
        """
        self.pages = pages or []
        self.vlm_agent = vlm_agent or Mock()


class MockVLMAgent:
    """Mock VLM agent for testing."""

    def __init__(self, text_response=None, structure_response=None):
        """Initialize mock agent.

        Args:
            text_response: Response for text extraction
            structure_response: Response for structure extraction
        """
        self.text_response = text_response or "Sample document text"
        self.structure_response = structure_response or '{"headers": []}'
        self.invoke_count = 0

    def invoke(self, prompt, images):
        """Mock invoke method.

        Args:
            prompt: VLM prompt
            images: List of images

        Returns:
            Mock response dict
        """
        self.invoke_count += 1

        # Return different responses based on prompt
        # Check structure first before text (текст is contained in структура)
        if "structure" in prompt.lower() or "структура" in prompt.lower():
            return {"text": self.structure_response}
        elif "plain text" in prompt.lower() or "текст" in prompt.lower():
            return {"text": self.text_response}
        else:
            return {"text": ""}


@pytest.fixture
def sample_pages():
    """Create sample page data."""
    return [
        PageInfo(index=1, image=b"fake_image_1"),
        PageInfo(index=2, image=b"fake_image_2"),
        PageInfo(index=3, image=b"fake_image_3"),
    ]


@pytest.fixture
def mock_processor(sample_pages):
    """Create mock processor with pages."""
    vlm_agent = MockVLMAgent()
    return MockDocumentProcessor(pages=sample_pages, vlm_agent=vlm_agent)


class TestFullDescriptionOperation:
    """Test suite for FullDescriptionOperation."""

    def test_initialization(self, mock_processor):
        """Test operation initialization."""
        operation = FullDescriptionOperation(mock_processor)

        assert operation.processor == mock_processor
        assert operation.render_dpi is None

    def test_initialization_with_dpi(self, mock_processor):
        """Test operation initialization with custom DPI."""
        operation = FullDescriptionOperation(mock_processor, render_dpi=200)

        assert operation.render_dpi == 200

    def test_execute_returns_document_data(self, mock_processor):
        """Test that execute returns DocumentData instance."""
        operation = FullDescriptionOperation(mock_processor)
        result = operation.execute()

        assert isinstance(result, DocumentData)
        assert hasattr(result, 'text')
        assert hasattr(result, 'structure')
        assert hasattr(result, 'tables')

    def test_execute_extracts_text(self, mock_processor):
        """Test that execute extracts text from document."""
        expected_text = "This is a sample document text"
        mock_processor.vlm_agent.text_response = expected_text

        operation = FullDescriptionOperation(mock_processor)
        result = operation.execute()

        assert result.text == expected_text

    def test_execute_extracts_structure(self, mock_processor):
        """Test that execute extracts structure from document."""
        mock_structure = '{"headers": [{"level": 1, "title": "Introduction", "page": 1}]}'
        mock_processor.vlm_agent.structure_response = mock_structure

        operation = FullDescriptionOperation(mock_processor)
        result = operation.execute()

        assert "headers" in result.structure
        assert len(result.structure["headers"]) == 1
        assert result.structure["headers"][0]["level"] == 1
        assert result.structure["headers"][0]["title"] == "Introduction"

    def test_execute_with_page_filter(self, mock_processor):
        """Test execute with specific page indices."""
        operation = FullDescriptionOperation(mock_processor)

        # Request only pages 1 and 2
        result = operation.execute(pages=[1, 2])

        # Should still return DocumentData
        assert isinstance(result, DocumentData)

        # VLM agent should be called (we can't verify exact pages without more complex mocking)
        assert mock_processor.vlm_agent.invoke_count >= 2  # text + structure

    def test_execute_tables_empty_in_v0_1_0(self, mock_processor):
        """Test that tables is empty list in v0.1.0."""
        operation = FullDescriptionOperation(mock_processor)
        result = operation.execute()

        assert result.tables == []

    def test_parse_valid_json_structure(self, mock_processor):
        """Test parsing valid JSON structure."""
        json_response = '''
        {
          "headers": [
            {"level": 1, "title": "1. Introduction", "page": 1},
            {"level": 2, "title": "1.1. Background", "page": 2}
          ]
        }
        '''
        mock_processor.vlm_agent.structure_response = json_response

        operation = FullDescriptionOperation(mock_processor)
        result = operation.execute()

        assert len(result.structure["headers"]) == 2
        assert result.structure["headers"][0]["title"] == "1. Introduction"
        assert result.structure["headers"][1]["title"] == "1.1. Background"

    def test_parse_json_with_markdown_fence(self, mock_processor):
        """Test parsing JSON wrapped in markdown fences."""
        json_with_fence = '''```json
        {
          "headers": [
            {"level": 1, "title": "Main Header", "page": 1}
          ]
        }
        ```'''
        mock_processor.vlm_agent.structure_response = json_with_fence

        operation = FullDescriptionOperation(mock_processor)
        result = operation.execute()

        assert len(result.structure["headers"]) == 1
        assert result.structure["headers"][0]["title"] == "Main Header"

    def test_handle_invalid_json(self, mock_processor):
        """Test handling of invalid JSON response."""
        mock_processor.vlm_agent.structure_response = "Not valid JSON"

        operation = FullDescriptionOperation(mock_processor)
        result = operation.execute()

        # Should return empty headers on error
        assert result.structure["headers"] == []

    def test_handle_malformed_headers(self, mock_processor):
        """Test handling of malformed headers in JSON."""
        malformed_json = '''
        {
          "headers": [
            {"level": 1, "title": "Valid Header", "page": 1},
            {"level": 2, "title": "Missing Page"},
            "not a dict",
            {"level": 3, "page": 3}
          ]
        }
        '''
        mock_processor.vlm_agent.structure_response = malformed_json

        operation = FullDescriptionOperation(mock_processor)
        result = operation.execute()

        # Should only include valid headers
        assert len(result.structure["headers"]) == 1
        assert result.structure["headers"][0]["title"] == "Valid Header"

    def test_filter_pages_with_pageinfo_objects(self, sample_pages):
        """Test filtering pages when using PageInfo objects."""
        processor = MockDocumentProcessor(
            pages=sample_pages,
            vlm_agent=MockVLMAgent()
        )
        operation = FullDescriptionOperation(processor)

        # Filter to pages 1 and 3
        filtered = operation._filter_pages(sample_pages, [1, 3])

        assert len(filtered) == 2
        assert filtered[0].index == 1
        assert filtered[1].index == 3

    def test_filter_pages_returns_all_when_none(self, sample_pages):
        """Test that filtering with None returns all pages."""
        processor = MockDocumentProcessor(
            pages=sample_pages,
            vlm_agent=MockVLMAgent()
        )
        operation = FullDescriptionOperation(processor)

        filtered = operation._filter_pages(sample_pages, None)

        assert len(filtered) == len(sample_pages)

    def test_extract_images_from_pageinfo(self, sample_pages):
        """Test extracting images from PageInfo objects."""
        processor = MockDocumentProcessor(
            pages=sample_pages,
            vlm_agent=MockVLMAgent()
        )
        operation = FullDescriptionOperation(processor)

        images = operation._extract_images(sample_pages)

        assert len(images) == 3
        assert images[0] == b"fake_image_1"
        assert images[1] == b"fake_image_2"
        assert images[2] == b"fake_image_3"

    def test_extract_images_from_bytes(self):
        """Test extracting images when pages are bytes."""
        pages_bytes = [b"img1", b"img2", b"img3"]
        processor = MockDocumentProcessor(
            pages=pages_bytes,
            vlm_agent=MockVLMAgent()
        )
        operation = FullDescriptionOperation(processor)

        images = operation._extract_images(pages_bytes)

        assert len(images) == 3
        assert images == pages_bytes

    def test_clean_json_fence(self):
        """Test JSON fence cleaning."""
        processor = MockDocumentProcessor(vlm_agent=MockVLMAgent())
        operation = FullDescriptionOperation(processor)

        # With fence
        text_with_fence = '```json\n{"key": "value"}\n```'
        cleaned = operation._clean_json_fence(text_with_fence)
        assert cleaned == '{"key": "value"}'

        # Without fence
        text_no_fence = '{"key": "value"}'
        cleaned = operation._clean_json_fence(text_no_fence)
        assert cleaned == '{"key": "value"}'

        # With json keyword only
        text_json_only = '```\n{"key": "value"}\n```'
        cleaned = operation._clean_json_fence(text_json_only)
        assert cleaned == '{"key": "value"}'
