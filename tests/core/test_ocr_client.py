"""Unit tests for OCR Client."""

from unittest.mock import Mock, patch

import pytest
import requests
from PIL import Image

from vlm_ocr_doc_reader.core.ocr_client import (
    OCRConfig,
    QwenClientError,
    QwenOCRClient,
)


@pytest.fixture
def ocr_config():
    """Create test OCR config."""
    return OCRConfig(
        api_key="test_api_key",
        model="qwen-vl-plus",
        timeout_sec=60,
        max_retries=3,
        backoff_base=1.5,
    )


@pytest.fixture
def qwen_client(ocr_config):
    """Create Qwen OCR client."""
    return QwenOCRClient(ocr_config)


@pytest.fixture
def sample_image():
    """Create sample test image."""
    img = Image.new("RGB", (100, 100), color="white")
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestOCRConfig:
    """Test OCRConfig dataclass."""

    def test_config_creation(self):
        """Test config creation with parameters."""
        config = OCRConfig(
            api_key="test_key",
            model="qwen-vl-max",
            timeout_sec=30,
            max_retries=5,
            backoff_base=2.0,
        )
        assert config.api_key == "test_key"
        assert config.model == "qwen-vl-max"
        assert config.timeout_sec == 30
        assert config.max_retries == 5
        assert config.backoff_base == 2.0

    def test_config_defaults(self):
        """Test config default values."""
        config = OCRConfig(api_key="test_key")
        assert config.model == "qwen-vl-plus"
        assert config.timeout_sec == 60
        assert config.max_retries == 3
        assert config.backoff_base == 1.5

    @patch.dict("os.environ", {"QWEN_API_KEY": "env_key"})
    def test_config_from_env(self):
        """Test config loads API key from environment."""
        config = OCRConfig()
        assert config.api_key == "env_key"

    def test_config_missing_api_key(self):
        """Test config raises error when API key not set."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="QWEN_API_KEY is required"):
                OCRConfig()


class TestQwenOCRClient:
    """Test QwenOCRClient."""

    def test_build_url(self, qwen_client):
        """Test URL building."""
        url = qwen_client._build_url()
        assert url == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"

    def test_image_to_base64(self, qwen_client, sample_image):
        """Test image conversion to base64."""
        b64 = qwen_client._image_to_base64(sample_image)
        assert isinstance(b64, str)
        assert len(b64) > 0
        # Base64 should contain only valid characters
        import base64
        try:
            base64.b64decode(b64)
        except Exception:
            pytest.fail("Invalid base64 string")

    def test_parse_qwen_response_success(self, qwen_client):
        """Test parsing successful Qwen response."""
        response_text = """
        ЗНАЧЕНИЕ: 22006042705
        КОНТЕКСТ: Руководитель аудита (ОРНЗ 22006042705)
        ПОЯСНЕНИЕ: Нашёл в центральной части страницы
        """
        result = qwen_client._parse_qwen_response(response_text)

        assert result["status"] == "ok"
        assert result["value"] == "22006042705"
        assert "ОРНЗ 22006042705" in result["context"]
        assert "Нашёл" in result["explanation"]

    def test_parse_qwen_response_no_data(self, qwen_client):
        """Test parsing Qwen response with no data."""
        response_text = """
        ЗНАЧЕНИЕ: НЕТ
        КОНТЕКСТ: -
        ПОЯСНЕНИЕ: Искал номер, но не нашёл
        """
        result = qwen_client._parse_qwen_response(response_text)

        assert result["status"] == "no_data"
        assert result["value"] == ""

    def test_parse_qwen_response_fallback(self, qwen_client):
        """Test parsing fallback when format is invalid."""
        response_text = "1234567890123"  # Just digits (13 digits for OGRN)
        result = qwen_client._parse_qwen_response(response_text)

        assert result["status"] == "ok"
        assert result["value"] == "1234567890123"
        assert "fallback" in result["explanation"]

    @patch("vlm_ocr_doc_reader.core.ocr_client.requests.post")
    def test_extract_success(self, mock_post, qwen_client, sample_image):
        """Test successful extraction."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "ЗНАЧЕНИЕ: 22006042705\nКОНТЕКСТ: Тест\nПОЯСНЕНИЕ: Найдено"
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        result = qwen_client.extract(sample_image, "найди ОРНЗ", 1)

        assert result["status"] == "ok"
        assert result["value"] == "22006042705"
        assert mock_post.called

    @patch("vlm_ocr_doc_reader.core.ocr_client.requests.post")
    def test_extract_retry_on_429(self, mock_post, qwen_client, sample_image):
        """Test retry logic on rate limit (429)."""
        # First call returns 429, second succeeds
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.text = "Rate limit exceeded"

        mock_response_ok = Mock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "ЗНАЧЕНИЕ: 123\nКОНТЕКСТ: Тест\nПОЯСНЕНИЕ: Ok"
                    }
                }
            ]
        }

        mock_post.side_effect = [mock_response_429, mock_response_ok]

        result = qwen_client.extract(sample_image, "test", 1)

        assert result["status"] == "ok"
        assert mock_post.call_count == 2

    @patch("vlm_ocr_doc_reader.core.ocr_client.requests.post")
    def test_extract_retry_on_500(self, mock_post, qwen_client, sample_image):
        """Test retry logic on server error (500)."""
        mock_response_500 = Mock()
        mock_response_500.status_code = 500
        mock_response_500.text = "Internal server error"

        mock_response_ok = Mock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "ЗНАЧЕНИЕ: 123\nКОНТЕКСТ: Тест\nПОЯСНЕНИЕ: Ok"
                    }
                }
            ]
        }

        mock_post.side_effect = [mock_response_500, mock_response_ok]

        result = qwen_client.extract(sample_image, "test", 1)

        assert result["status"] == "ok"
        assert mock_post.call_count == 2

    @patch("vlm_ocr_doc_reader.core.ocr_client.requests.post")
    def test_extract_max_retries_exceeded(self, mock_post, qwen_client, sample_image):
        """Test failure after max retries."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit"
        mock_response.raise_for_status.side_effect = requests.HTTPError()

        mock_post.return_value = mock_response

        with pytest.raises(QwenClientError, match="Qwen request failed"):
            qwen_client.extract(sample_image, "test", 1)

        # Should be called max_retries times
        assert mock_post.call_count == qwen_client.config.max_retries

    @patch("vlm_ocr_doc_reader.core.ocr_client.requests.post")
    def test_extract_http_error_retries(self, mock_post, qwen_client, sample_image):
        """Test that HTTP errors are retried (implementation retries all errors)."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_response.raise_for_status.side_effect = requests.HTTPError()

        mock_post.return_value = mock_response

        with pytest.raises(QwenClientError):
            qwen_client.extract(sample_image, "test", 1)

        # Current implementation retries all HTTP errors
        assert mock_post.call_count == qwen_client.config.max_retries
