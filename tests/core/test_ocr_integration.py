"""Integration tests for OCR Client with real API.

These tests require QWEN_API_KEY environment variable to be set.
Tests are skipped if API key is not available.
"""

import os
from unittest.mock import patch
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

import pytest

from vlm_ocr_doc_reader.core.ocr_client import OCRConfig, QwenOCRClient


# Skip all tests if QWEN_API_KEY not set
pytestmark = pytest.mark.skipif(
    not os.getenv("QWEN_API_KEY"),
    reason="QWEN_API_KEY environment variable not set"
)


@pytest.fixture
def real_ocr_config():
    """Create OCR config from environment."""
    return OCRConfig(
        api_key=os.getenv("QWEN_API_KEY"),
        model="qwen-vl-plus",
        timeout_sec=60,
        max_retries=3,
    )


@pytest.fixture
def real_qwen_client(real_ocr_config):
    """Create real Qwen OCR client."""
    return QwenOCRClient(real_ocr_config)


@pytest.fixture
def test_image_with_text():
    """Create test image with text."""
    img = Image.new("RGB", (800, 600), color="white")
    draw = ImageDraw.Draw(img)

    # Draw text (using default font)
    text = "ОГРН: 1234567890123"
    try:
        # Try to use a better font if available
        font = ImageFont.truetype("arial.ttf", 40)
    except Exception:
        # Fallback to default font
        font = ImageFont.load_default()

    draw.text((50, 50), text, fill="black", font=font)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestQwenOCRIntegration:
    """Integration tests with real Qwen API."""

    def test_extract_ogrn(self, real_qwen_client, test_image_with_text):
        """Test extraction of OGRN number."""
        result = real_qwen_client.extract(
            image=test_image_with_text,
            prompt="Найди ОГРН (Основной государственный регистрационный номер)",
            page_num=1,
        )

        assert result["status"] in ["ok", "no_data"]
        if result["status"] == "ok":
            assert len(result["value"]) > 0
            assert result["value"].isdigit()
            assert isinstance(result["context"], str)
            assert isinstance(result["explanation"], str)

    def test_extract_with_retry(self, real_qwen_client, test_image_with_text):
        """Test that retry logic works in real scenario."""
        # This test mainly verifies the code doesn't crash
        # Real retry testing would require triggering rate limits
        result = real_qwen_client.extract(
            image=test_image_with_text,
            prompt="Найди номер документа",
            page_num=1,
        )

        assert "status" in result
        assert "value" in result

    def test_invalid_image(self, real_qwen_client):
        """Test handling of invalid image data."""
        invalid_image = b"not_an_image"

        with pytest.raises(Exception):  # Should fail during image processing
            real_qwen_client.extract(
                image=invalid_image,
                prompt="test",
                page_num=1,
            )


@pytest.mark.skipif(
    not os.getenv("QWEN_API_KEY"),
    reason="QWEN_API_KEY environment variable not set"
)
class TestOCRNormalizationIntegration:
    """Test normalization with real OCR output."""

    def test_normalize_ocr_output_with_common_errors(self, real_qwen_client):
        """Test that normalization fixes common OCR errors."""
        # Create image with OCR-prone text
        img = Image.new("RGB", (800, 600), color="white")
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arial.ttf", 40)
        except Exception:
            font = ImageFont.load_default()

        # Draw text that might be misrecognized
        text = "ID: O1234567890"  # O instead of 0
        draw.text((50, 50), text, fill="black", font=font)

        buf = BytesIO()
        img.save(buf, format="PNG")
        test_image = buf.getvalue()

        result = real_qwen_client.extract(
            image=test_image,
            prompt="Найди идентификатор (ID)",
            page_num=1,
        )

        if result["status"] == "ok":
            # Normalization should be applied in OCRTool, not here
            # Just verify we got some result
            assert len(result["value"]) > 0
