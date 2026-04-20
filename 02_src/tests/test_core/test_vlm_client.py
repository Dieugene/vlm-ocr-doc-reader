"""Tests for VLM Client — real Gemini API calls.

Requires GEMINI_API_KEY in .env (real key, not dummy).
Tests are skipped if the key is not set or is dummy.
"""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from vlm_ocr_doc_reader.core.vlm_client import GeminiVLMClient, BaseVLMClient
from vlm_ocr_doc_reader.schemas.config import VLMConfig
from vlm_ocr_doc_reader.preprocessing.renderer import PDFRenderer, RenderConfig

_DUMMY_KEYS = frozenset({"test", "test-key", "test-api-key-123"})


def _is_gemini_key_valid():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return bool(key) and key.lower() not in _DUMMY_KEYS


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
skip_no_gemini = pytest.mark.skipif(
    not _is_gemini_key_valid(), reason="GEMINI_API_KEY not set or is dummy"
)

_SRC_ROOT = Path(__file__).resolve().parent.parent.parent  # 02_src
TEST_PDF = _SRC_ROOT / "03_data" / "test_document.pdf"


@pytest.fixture(scope="module")
def page_images():
    """Render first page of test PDF to PNG bytes."""
    renderer = PDFRenderer(RenderConfig(dpi=150))
    rendered = renderer.render_pdf(TEST_PDF)
    # Return dict {page_num: bytes}
    return {num: img for num, img in rendered}


@pytest.fixture(scope="module")
def vlm_client():
    """Create real GeminiVLMClient."""
    config = VLMConfig(api_key=GEMINI_API_KEY, model="gemini-2.5-flash")
    return GeminiVLMClient(config)


class TestBaseVLMClient:
    """Test BaseVLMClient interface."""

    def test_base_client_is_abstract(self):
        """Test that BaseVLMClient.invoke raises NotImplementedError."""
        client = BaseVLMClient()
        with pytest.raises(NotImplementedError):
            client.invoke("test", [])


@skip_no_gemini
class TestGeminiVLMClientReal:
    """Real API tests for GeminiVLMClient."""

    def test_invoke_simple(self, vlm_client, page_images):
        """Test simple text extraction from one page."""
        img = page_images[1]
        result = vlm_client.invoke(
            prompt="Кратко опиши, что изображено на этой странице (1-2 предложения).",
            images=[img],
        )

        assert "text" in result
        assert isinstance(result["text"], str)
        assert len(result["text"]) > 10

    def test_invoke_with_contents(self, vlm_client, page_images):
        """Test invoke with full contents array (multi-turn)."""
        import base64

        img = page_images[1]
        b64 = base64.b64encode(img).decode("utf-8")

        contents = [
            {
                "role": "user",
                "parts": [
                    {"text": "Скажи одно слово: 'привет'"},
                ],
            },
            {
                "role": "model",
                "parts": [{"text": "привет"}],
            },
            {
                "role": "user",
                "parts": [
                    {"text": "Теперь кратко опиши эту страницу (1-2 предложения)."},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": b64,
                        }
                    },
                ],
            },
        ]

        result = vlm_client.invoke(contents=contents)

        assert "text" in result
        assert isinstance(result["text"], str)
        assert len(result["text"]) > 10

    def test_invoke_with_tools(self, vlm_client, page_images):
        """Test that VLM returns function_calls when tools are provided."""
        img = page_images[1]
        tools = [
            {
                "function_declarations": [
                    {
                        "name": "ask_ocr",
                        "description": "Extract a specific value from a document page via OCR.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "page_num": {"type": "integer", "description": "Page number"},
                                "prompt": {"type": "string", "description": "What to extract"},
                            },
                            "required": ["page_num", "prompt"],
                        },
                    }
                ]
            }
        ]

        result = vlm_client.invoke(
            prompt="На этой странице есть какой-нибудь URL? Если да, извлеки его через ask_ocr (page_num=1).",
            images=[img],
            tools=tools,
        )

        # Model should either call the tool or return text
        assert "text" in result or "function_calls" in result


class TestGeminiVLMClientRetry:
    """Unit-level retry behavior tests for GeminiVLMClient."""

    def _make_client(self) -> GeminiVLMClient:
        config = VLMConfig(
            api_key="unit-test-key",
            model="gemini-2.5-flash",
            timeout_sec=1,
            max_retries=3,
            backoff_base=1.0,
            min_interval_s=0.0,
        )
        return GeminiVLMClient(config)

    @staticmethod
    def _success_payload(text: str = "ok") -> dict:
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": text}],
                    }
                }
            ]
        }

    def test_retries_on_read_timeout_then_succeeds(self):
        """Client should retry on ReadTimeout and recover if next attempt succeeds."""
        client = self._make_client()

        timeout_exc = requests.exceptions.ReadTimeout("read timeout")
        ok_response = Mock()
        ok_response.status_code = 200
        ok_response.json.return_value = self._success_payload("hello")

        with patch("vlm_ocr_doc_reader.core.vlm_client.time.sleep", return_value=None), patch(
            "vlm_ocr_doc_reader.core.vlm_client.requests.post",
            side_effect=[timeout_exc, ok_response],
        ) as post_mock:
            result = client.invoke(prompt="hello", images=[])

        assert post_mock.call_count == 2
        assert result["text"] == "hello"

    def test_exhausts_retries_on_read_timeout(self):
        """Client should retry up to max_retries on ReadTimeout then raise."""
        client = self._make_client()
        timeout_exc = requests.exceptions.ReadTimeout("read timeout")

        with patch("vlm_ocr_doc_reader.core.vlm_client.time.sleep", return_value=None), patch(
            "vlm_ocr_doc_reader.core.vlm_client.requests.post",
            side_effect=timeout_exc,
        ) as post_mock:
            with pytest.raises(requests.exceptions.ReadTimeout):
                client.invoke(prompt="hello", images=[])

        assert post_mock.call_count == client.config.max_retries
