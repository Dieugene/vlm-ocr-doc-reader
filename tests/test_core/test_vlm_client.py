"""Unit tests for VLM Client."""

import time
from unittest.mock import Mock, patch, MagicMock
import pytest
import requests

from vlm_ocr_doc_reader.core.vlm_client import GeminiVLMClient, BaseVLMClient
from vlm_ocr_doc_reader.schemas.config import VLMConfig


@pytest.fixture
def vlm_config():
    """Create VLM config for testing."""
    return VLMConfig(
        api_key="test_api_key",
        model="gemini-2.5-flash",
        timeout_sec=10,
        max_retries=3,
        backoff_base=1.5,
        min_interval_s=0.6,
    )


@pytest.fixture
def mock_images():
    """Create mock PNG images."""
    # Create minimal PNG bytes (1x1 transparent pixel)
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"


class TestBaseVLMClient:
    """Test BaseVLMClient interface."""

    def test_base_client_is_abstract(self):
        """Test that BaseVLMClient cannot be instantiated directly."""
        client = BaseVLMClient()
        with pytest.raises(NotImplementedError):
            client.invoke("test", [])


class TestGeminiVLMClientRetry:
    """Test retry logic in GeminiVLMClient."""

    def test_retry_on_429_status(self, vlm_config):
        """Test that client retries on 429 (rate limit) status."""
        client = GeminiVLMClient(vlm_config)

        # Mock response sequence: 429 -> 429 -> 200
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.text = "Rate limit exceeded"

        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": '{"result": "success"}'}
                    ]
                }
            }]
        }

        with patch('requests.post') as mock_post:
            mock_post.side_effect = [
                mock_response_429,
                mock_response_429,
                mock_response_200
            ]

            result = client.invoke("test prompt", [])

            # Should have made 3 attempts
            assert mock_post.call_count == 3
            assert result["text"]["result"] == "success"

    def test_retry_on_503_status(self, vlm_config):
        """Test that client retries on 503 (server error) status."""
        client = GeminiVLMClient(vlm_config)

        # Mock response sequence: 503 -> 200
        mock_response_503 = Mock()
        mock_response_503.status_code = 503
        mock_response_503.text = "Service unavailable"

        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": '{"result": "success"}'}
                    ]
                }
            }]
        }

        with patch('requests.post') as mock_post:
            mock_post.side_effect = [mock_response_503, mock_response_200]

            result = client.invoke("test prompt", [])

            # Should have made 2 attempts
            assert mock_post.call_count == 2
            assert result["text"]["result"] == "success"

    def test_retry_exhaustion(self, vlm_config):
        """Test that client raises exception after max retries."""
        client = GeminiVLMClient(vlm_config)

        # Mock response always returns 429
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.text = "Rate limit exceeded"
        mock_response_429.raise_for_status.side_effect = requests.HTTPError("429 Client Error")

        with patch('requests.post') as mock_post:
            mock_post.return_value = mock_response_429

            with pytest.raises(requests.HTTPError):
                client.invoke("test prompt", [])

            # Should have made max_retries attempts
            assert mock_post.call_count == vlm_config.max_retries

    def test_no_retry_on_400_status(self, vlm_config):
        """Test that client does NOT retry on 400 (client error) status."""
        client = GeminiVLMClient(vlm_config)

        # Mock response returns 400
        mock_response_400 = Mock()
        mock_response_400.status_code = 400
        mock_response_400.text = "Bad request"
        mock_response_400.raise_for_status.side_effect = requests.HTTPError("400 Client Error")

        with patch('requests.post') as mock_post:
            mock_post.return_value = mock_response_400

            with pytest.raises(requests.HTTPError):
                client.invoke("test prompt", [])

            # Should have made only 1 attempt (no retry)
            assert mock_post.call_count == 1


class TestGeminiVLMClientThrottling:
    """Test throttling logic in GeminiVLMClient."""

    def test_throttling_enforces_min_interval(self, vlm_config):
        """Test that throttling enforces minimum interval between calls."""
        # Use very small min_interval for faster testing
        vlm_config.min_interval_s = 0.2
        client = GeminiVLMClient(vlm_config)

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": '{"result": "success"}'}
                    ]
                }
            }]
        }

        with patch('requests.post') as mock_post:
            mock_post.return_value = mock_response

            # Make two consecutive calls
            start_time = time.monotonic()
            client.invoke("test1", [])
            client.invoke("test2", [])
            elapsed = time.monotonic() - start_time

            # Should take at least min_interval_s
            assert elapsed >= vlm_config.min_interval_s

    def test_throttling_standard_interval(self, vlm_config):
        """Test throttling with standard min_interval_s=0.6 from task_brief."""
        # Use standard value from task_brief
        vlm_config.min_interval_s = 0.6
        client = GeminiVLMClient(vlm_config)

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": '{"result": "success"}'}
                    ]
                }
            }]
        }

        with patch('requests.post') as mock_post:
            mock_post.return_value = mock_response

            # Make two consecutive calls
            start_time = time.monotonic()
            client.invoke("test1", [])
            client.invoke("test2", [])
            elapsed = time.monotonic() - start_time

            # Should take at least 0.6s (standard value)
            assert elapsed >= 0.6

    def test_throttling_first_call_immediate(self, vlm_config):
        """Test that first call has no delay."""
        vlm_config.min_interval_s = 1.0
        client = GeminiVLMClient(vlm_config)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": '{"result": "success"}'}
                    ]
                }
            }]
        }

        with patch('requests.post') as mock_post:
            mock_post.return_value = mock_response

            start_time = time.monotonic()
            client.invoke("test", [])
            elapsed = time.monotonic() - start_time

            # First call should be immediate (< 100ms)
            assert elapsed < 0.1


class TestGeminiVLMClientInvoke:
    """Test invoke method."""

    def test_invoke_without_tools(self, vlm_config):
        """Test invoke without tools returns text."""
        client = GeminiVLMClient(vlm_config)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": '{"answer": "42"}'}
                    ]
                }
            }]
        }

        with patch('requests.post') as mock_post:
            mock_post.return_value = mock_response

            result = client.invoke("What is the answer?", [])

            assert "text" in result
            assert result["text"]["answer"] == "42"
            assert "raw" in result

    def test_invoke_with_tools(self, vlm_config):
        """Test invoke with tools returns function_calls."""
        client = GeminiVLMClient(vlm_config)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "test_tool",
                                "args": {"param": "value"}
                            }
                        }
                    ]
                }
            }]
        }

        with patch('requests.post') as mock_post:
            mock_post.return_value = mock_response

            tools = [{
                "function_declarations": [{
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "param": {"type": "string"}
                        }
                    }
                }]
            }]

            result = client.invoke("Call tool", [], tools=tools)

            assert "function_calls" in result
            assert len(result["function_calls"]) == 1
            assert result["function_calls"][0]["name"] == "test_tool"
            assert result["function_calls"][0]["args"]["param"] == "value"

    def test_invoke_with_images(self, vlm_config, mock_images):
        """Test that images are base64 encoded in request."""
        client = GeminiVLMClient(vlm_config)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": '{"seen": true}'}
                    ]
                }
            }]
        }

        with patch('requests.post') as mock_post:
            mock_post.return_value = mock_response

            client.invoke("What do you see?", [mock_images])

            # Check that post was called
            assert mock_post.called
            call_args = mock_post.call_args

            # Verify payload contains inline_data
            payload = call_args[1]['json']
            contents = payload['contents'][0]
            parts = contents['parts']

            # First part should be text prompt
            assert parts[0]['text'] == "What do you see?"

            # Second part should be inline_data with base64 image
            assert 'inline_data' in parts[1]
            assert parts[1]['inline_data']['mime_type'] == 'image/png'
            assert 'data' in parts[1]['inline_data']
