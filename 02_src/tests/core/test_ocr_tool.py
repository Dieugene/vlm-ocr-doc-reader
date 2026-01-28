"""Unit tests for OCR Tool."""

from unittest.mock import Mock

import pytest

from vlm_ocr_doc_reader.core.ocr_tool import OCRTool
from vlm_ocr_doc_reader.core.ocr_client import BaseOCRClient


class MockOCRClient(BaseOCRClient):
    """Mock OCR client for testing."""

    def extract(self, image: bytes, prompt: str, page_num: int):
        """Mock extract method."""
        if "ОГРН" in prompt:
            return {
                "status": "ok",
                "value": "O123456789012",  # Contains O instead of 0
                "context": "ОГРН O123456789012",
                "explanation": "Found in document",
            }
        elif "notfound" in prompt.lower():
            return {
                "status": "no_data",
                "value": "",
                "context": "",
                "explanation": "Not found",
            }
        else:
            return {
                "status": "ok",
                "value": "12345678901",
                "context": "Test context",
                "explanation": "Test explanation",
            }


@pytest.fixture
def mock_ocr_client():
    """Create mock OCR client."""
    client = MockOCRClient()
    # Wrap extract to track calls
    client.extract = Mock(wraps=client.extract)
    return client


@pytest.fixture
def ocr_tool(mock_ocr_client):
    """Create OCR tool."""
    return OCRTool(mock_ocr_client)


@pytest.fixture
def sample_image():
    """Create sample image bytes."""
    return b"fake_image_bytes"


class TestOCRTool:
    """Test OCRTool."""

    def test_init(self, mock_ocr_client):
        """Test initialization."""
        tool = OCRTool(mock_ocr_client)
        assert tool.ocr_client == mock_ocr_client

    def test_to_tool_definition(self, ocr_tool):
        """Test tool definition generation."""
        definition = ocr_tool.to_tool_definition()

        assert "function_declarations" in definition
        assert len(definition["function_declarations"]) == 1

        func = definition["function_declarations"][0]
        assert func["name"] == "ask_ocr"
        assert "description" in func
        assert "parameters" in func

        params = func["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "page_num" in params["properties"]
        assert "prompt" in params["properties"]
        assert params["required"] == ["page_num", "prompt"]

    def test_execute_success(self, ocr_tool, sample_image):
        """Test successful execution with normalization."""
        result = ocr_tool.execute(page_num=1, prompt="найди ОГРН", image=sample_image)

        assert result["status"] == "ok"
        assert result["value"] == "O123456789012"
        assert result["value_normalized"] == "0123456789012"  # O -> 0
        assert "context" in result
        assert "explanation" in result

    def test_execute_no_data(self, ocr_tool, sample_image):
        """Test execution when no data found."""
        result = ocr_tool.execute(page_num=2, prompt="find notfound", image=sample_image)

        assert result["status"] == "no_data"
        assert result["value"] == ""
        assert "value_normalized" not in result  # No normalization for no_data

    def test_execute_normalization_failure(self, sample_image):
        """Test execution when normalization returns empty."""
        # Mock client returns value without digits (after normalization)
        mock_client = Mock()
        mock_client.extract.return_value = {
            "status": "ok",
            "value": "XYZ",  # No digits after normalization
            "context": "Test",
            "explanation": "Test",
        }

        tool = OCRTool(mock_client)
        result = tool.execute(page_num=1, prompt="test", image=sample_image)

        # Should change status to no_data when normalization returns None/empty
        assert result["status"] == "no_data"
        assert result["value_normalized"] is None

    def test_execute_calls_ocr_client(self, ocr_tool, sample_image):
        """Test that execute calls OCR client extract."""
        page_num = 5
        prompt = "test prompt"

        result = ocr_tool.execute(page_num=page_num, prompt=prompt, image=sample_image)

        # Verify OCR client was called
        ocr_tool.ocr_client.extract.assert_called_once()
        call_args = ocr_tool.ocr_client.extract.call_args
        assert call_args[0][0] == sample_image
        assert call_args[0][1] == prompt
        assert call_args[0][2] == page_num
