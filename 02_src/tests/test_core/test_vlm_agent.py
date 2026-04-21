"""Tests for VLMAgent — real DashScope / Qwen VLM calls.

Requires DASHSCOPE_API_KEY (or QWEN_API_KEY) in .env.
Tests are skipped if the key is not set or is dummy.
"""

import os
from pathlib import Path

import pytest

from vlm_ocr_doc_reader.core.qwen_vlm_client import QwenVLMClient
from vlm_ocr_doc_reader.core.vlm_agent import VLMAgent
from vlm_ocr_doc_reader.schemas.config import VLMConfig
from vlm_ocr_doc_reader.preprocessing.renderer import PDFRenderer, RenderConfig

_DUMMY_KEYS = frozenset({"test", "test-key", "test-api-key-123"})


def _is_dashscope_key_valid():
    key = (os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY") or "").strip()
    return bool(key) and key.lower() not in _DUMMY_KEYS


API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
skip_no_api = pytest.mark.skipif(
    not _is_dashscope_key_valid(),
    reason="DASHSCOPE_API_KEY (or QWEN_API_KEY) not set or is dummy",
)

_SRC_ROOT = Path(__file__).resolve().parent.parent.parent  # 02_src
TEST_PDF = _SRC_ROOT / "03_data" / "test_document.pdf"


@pytest.fixture(scope="module")
def page_images():
    """Render test PDF pages."""
    renderer = PDFRenderer(RenderConfig(dpi=150))
    rendered = renderer.render_pdf(TEST_PDF)
    return {num: img for num, img in rendered}


@pytest.fixture
def vlm_client():
    """Create real QwenVLMClient."""
    config = VLMConfig(api_key=API_KEY)
    return QwenVLMClient(config)


@skip_no_api
class TestVLMAgentReal:
    """Real API tests for VLMAgent."""

    def test_invoke_no_tools(self, vlm_client, page_images):
        """Text extraction without tools — agent returns text in 1 iteration."""
        agent = VLMAgent(vlm_client)
        img = page_images[1]

        result = agent.invoke(
            "Кратко опиши эту страницу (1-2 предложения).",
            [img],
        )

        assert result["text"] is not None
        assert len(result["text"]) > 10
        assert result["iterations"] == 1
        assert result.get("function_results") is None

    def test_invoke_with_tool(self, vlm_client, page_images):
        """Agent registers and may invoke an ask_ocr-shaped tool."""
        agent = VLMAgent(vlm_client)
        img = page_images[1]

        tool_def = {
            "type": "function",
            "function": {
                "name": "ask_ocr",
                "description": (
                    "Точное извлечение одного значения со страницы документа через "
                    "OCR. Используй для URL, ID, ФИО."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "page_num": {
                            "type": "integer",
                            "description": "Номер страницы",
                        },
                        "prompt": {"type": "string", "description": "Что извлечь"},
                    },
                    "required": ["page_num", "prompt"],
                },
            },
        }

        def mock_ocr_handler(page_num: int, prompt: str):
            return {
                "status": "ok",
                "value": "https://example.com/test-url",
                "context": "See: https://example.com/test-url",
                "explanation": "Found URL on page",
            }

        agent.register_tool(tool_def, mock_ocr_handler)

        result = agent.invoke(
            "На этой странице есть URL? Извлеки его через ask_ocr (page_num=1).",
            [img],
        )

        # Agent must return text (model decides whether to invoke the tool)
        assert result["text"] is not None
        assert isinstance(result["text"], str)

    def test_multi_turn(self, vlm_client, page_images):
        """Two sequential invocations — agent remembers prior turn."""
        agent = VLMAgent(vlm_client)
        img = page_images[1]

        result1 = agent.invoke(
            "Запомни кодовое слово: БАНАН. Ответь только 'запомнил'.",
            [img],
        )
        assert result1["text"] is not None

        result2 = agent.invoke(
            "Какое кодовое слово я просил запомнить? Ответь одним словом.",
            [],
        )
        assert result2["text"] is not None
        assert "банан" in result2["text"].lower()
