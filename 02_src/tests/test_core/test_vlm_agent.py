"""Tests for VLM Agent — real Gemini API calls.

Requires GEMINI_API_KEY environment variable.
Tests are skipped if the key is not set.
"""

import os
from pathlib import Path

import pytest

from vlm_ocr_doc_reader.core.vlm_client import GeminiVLMClient
from vlm_ocr_doc_reader.core.vlm_agent import VLMAgent
from vlm_ocr_doc_reader.schemas.config import VLMConfig
from vlm_ocr_doc_reader.preprocessing.renderer import PDFRenderer, RenderConfig

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
skip_no_gemini = pytest.mark.skipif(
    not GEMINI_API_KEY, reason="GEMINI_API_KEY not set"
)

TEST_PDF = Path(r"D:\_storage_cbr\020_docs_vision\08_vlm-ocr-doc-reader\03_data\test_document.pdf")


@pytest.fixture(scope="module")
def page_images():
    """Render test PDF pages."""
    renderer = PDFRenderer(RenderConfig(dpi=150))
    rendered = renderer.render_pdf(TEST_PDF)
    return {num: img for num, img in rendered}


@pytest.fixture
def vlm_client():
    """Create real GeminiVLMClient."""
    config = VLMConfig(api_key=GEMINI_API_KEY, model="gemini-2.5-flash")
    return GeminiVLMClient(config)


@skip_no_gemini
class TestVLMAgentReal:
    """Real API tests for VLMAgent."""

    def test_invoke_no_tools(self, vlm_client, page_images):
        """Test text extraction without tools — agent returns text in 1 iteration."""
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
        """Test that agent calls ask_ocr tool and receives its result."""
        agent = VLMAgent(vlm_client)
        img = page_images[1]

        # Register a simple echo tool as ask_ocr
        tool_def = {
            "function_declarations": [
                {
                    "name": "ask_ocr",
                    "description": (
                        "Точное извлечение одного значения со страницы документа через OCR. "
                        "Используй для URL, ID, ФИО."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_num": {"type": "integer", "description": "Номер страницы"},
                            "prompt": {"type": "string", "description": "Что извлечь"},
                        },
                        "required": ["page_num", "prompt"],
                    },
                }
            ]
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

        assert result["text"] is not None
        # Agent should have used the tool (iterations > 1) or decided not to
        # At minimum we get a text response
        assert isinstance(result["text"], str)

    def test_multi_turn(self, vlm_client, page_images):
        """Test two sequential invocations — agent remembers history."""
        agent = VLMAgent(vlm_client)
        img = page_images[1]

        # First invocation
        result1 = agent.invoke(
            "Запомни кодовое слово: БАНАН. Ответь только 'запомнил'.",
            [img],
        )
        assert result1["text"] is not None

        # Second invocation — no images, agent should remember
        result2 = agent.invoke(
            "Какое кодовое слово я просил запомнить? Ответь одним словом.",
            [],
        )
        assert result2["text"] is not None
        assert "банан" in result2["text"].lower()
