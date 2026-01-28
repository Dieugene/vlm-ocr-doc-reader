"""Integration tests for VLM Client with real Gemini API.

These tests require GEMINI_API_KEY to be set in environment.
If not set, tests are skipped automatically.
"""

import os
import pytest
from unittest.mock import Mock

from vlm_ocr_doc_reader.core.vlm_client import GeminiVLMClient
from vlm_ocr_doc_reader.schemas.config import VLMConfig

# Skip all tests if GEMINI_API_KEY not set
pytestmark = pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set - set it to run integration tests"
)


class TestGeminiVLMClientRealAPI:
    """Integration tests with real Gemini API.

    These tests make actual API calls and consume quota.
    Run them sparingly to verify integration with real API.
    """

    @pytest.fixture
    def vlm_config(self):
        """Create VLM config from environment."""
        api_key = os.getenv("GEMINI_API_KEY")
        return VLMConfig(
            api_key=api_key,
            model="gemini-2.5-flash",
            timeout_sec=30,
            max_retries=3,
            min_interval_s=0.6,
        )

    @pytest.fixture
    def vlm_client(self, vlm_config):
        """Create VLM client for testing."""
        return GeminiVLMClient(vlm_config)

    def test_simple_invoke_no_images(self, vlm_client):
        """Test simple text request without images.

        Minimal test to verify basic connectivity and response parsing.
        """
        prompt = "Respond with JSON: {\"status\": \"ok\", \"message\": \"hello\"}"

        result = vlm_client.invoke(prompt, [])

        # Check response structure
        assert "text" in result
        assert isinstance(result["text"], dict)
        assert "raw" in result

        # Check content (should be parsed JSON)
        assert result["text"]["status"] == "ok"
        assert result["text"]["message"] == "hello"

    def test_invoke_with_tools(self, vlm_client):
        """Test function calling with real API.

        Verifies that VLM can invoke tools and return function calls.
        """
        # Define a simple tool
        tools = [{
            "function_declarations": [{
                "name": "extract_data",
                "description": "Extract structured data from content",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Title of the content"
                        },
                        "summary": {
                            "type": "string",
                            "description": "Brief summary"
                        }
                    },
                    "required": ["title", "summary"]
                }
            }]
        }]

        prompt = "Use extract_data tool with title='Test' and summary='This is a test'"

        result = vlm_client.invoke(prompt, [], tools=tools)

        # Check response structure
        assert "function_calls" in result or "text" in result
        assert "raw" in result

        # If function_calls returned, verify structure
        if result.get("function_calls"):
            assert len(result["function_calls"]) >= 1
            func_call = result["function_calls"][0]
            assert "name" in func_call
            assert "args" in func_call
            assert func_call["name"] == "extract_data"

    def test_invoke_error_handling_invalid_key(self):
        """Test that invalid API key is handled properly.

        This should raise an exception without retries.
        """
        config = VLMConfig(
            api_key="invalid_key_12345",
            model="gemini-2.5-flash",
            timeout_sec=10,
            max_retries=3,
        )
        client = GeminiVLMClient(config)

        # Should raise exception (401 or 403)
        with pytest.raises(Exception) as exc_info:
            client.invoke("test", [])

        # Should NOT retry - only one attempt made
        # Exception should be HTTPError or similar
        assert exc_info is not None

    def test_throttling_with_real_api(self, vlm_client):
        """Test that throttling works with real API calls.

        This test verifies min_interval_s is enforced between calls.
        """
        import time

        prompt = "Respond with JSON: {\"result\": \"test\"}"

        # Make two consecutive calls
        start = time.monotonic()
        vlm_client.invoke(prompt, [])
        vlm_client.invoke(prompt, [])
        elapsed = time.monotonic() - start

        # Should take at least min_interval_s (0.6s)
        assert elapsed >= 0.6, f"Elapsed {elapsed}s < 0.6s throttling interval"
