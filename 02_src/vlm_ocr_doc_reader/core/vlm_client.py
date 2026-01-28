"""VLM Client - Technical wrapper over Gemini REST API with retry and throttling."""

import base64
import json
import logging
import time
from typing import Dict, List, Optional, Any

import requests

from ..schemas.config import VLMConfig

logger = logging.getLogger(__name__)


class BaseVLMClient:
    """Base interface for VLM clients.

    Provides universal invoke() method that supports both:
    - Simple text/image prompts
    - Function calling with tools
    """

    def invoke(
        self,
        prompt: str,
        images: List[bytes],
        tools: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Invoke VLM with prompt and images.

        Args:
            prompt: Text prompt
            images: List of images (PNG bytes)
            tools: Optional tool definitions for function calling

        Returns:
            With tools: {"function_calls": [...], "text": Optional[str]}
            Without tools: {"text": str, "usage": {...}}
        """
        raise NotImplementedError


class GeminiVLMClient(BaseVLMClient):
    """Gemini REST API client with retry logic and throttling.

    Features:
    - Retry on 429 (rate limit) and 500-599 (server errors)
    - Exponential backoff with configurable base
    - Throttling with minimum interval between requests
    - Support for function calling
    """

    def __init__(self, config: VLMConfig):
        """Initialize Gemini VLM client.

        Args:
            config: VLM configuration
        """
        self.config = config
        self._last_call_ts: Optional[float] = None
        self._calls_made = 0

        # Build API URL
        self.url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.config.model}:generateContent?key={self.config.api_key}"
        )

        if not self.config.api_key:
            logger.warning("Gemini API Key is not set!")

    def _throttle(self) -> None:
        """Guarantee min_interval_s between calls.

        Uses time.monotonic() for correct timing even if system time changes.
        """
        if self._last_call_ts is None:
            return

        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < self.config.min_interval_s:
            sleep_time = self.config.min_interval_s - elapsed
            logger.debug(f"Throttling: sleeping {sleep_time:.3f}s")
            time.sleep(sleep_time)

    def _make_request_with_retry(
        self,
        url: str,
        headers: Dict,
        payload: Dict
    ) -> Dict:
        """Make POST request with retry logic.

        Retries on:
        - 429 (rate limit)
        - 500-599 (server errors)

        Exponential backoff formula: sleep_s = backoff_base ** (attempt - 1)

        Args:
            url: Request URL
            headers: Request headers
            payload: Request payload

        Returns:
            Response JSON

        Raises:
            requests.RequestException: If all retries exhausted
        """
        last_error = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                logger.info(f"VLM request attempt {attempt}/{self.config.max_retries}")
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.config.timeout_sec
                )
                status = response.status_code

                # Check if we should retry (ONLY on 429 and 500-599)
                is_retryable = status == 429 or (500 <= status < 600)

                # For retryable errors - retry with backoff (if we have retries left)
                if is_retryable and attempt < self.config.max_retries:
                    last_error = f"status={status}, body={response.text[:400]}"
                    sleep_s = self.config.backoff_base ** (attempt - 1)
                    logger.warning(
                        f"Gemini API {status} error, retry {attempt}/{self.config.max_retries} "
                        f"after {sleep_s:.1f}s"
                    )
                    time.sleep(sleep_s)
                    continue

                # For retryable errors but we're out of retries - raise
                if is_retryable and attempt >= self.config.max_retries:
                    logger.error(f"Retryable error but out of retries (attempt {attempt}/{self.config.max_retries})")
                    response.raise_for_status()

                # For non-retryable errors (4xx except 429) - raise immediately
                if not is_retryable and status >= 400:
                    logger.info(f"Request failed with status={status}, not retrying (client error)")
                    response.raise_for_status()

                # Success case
                return response.json()

            except requests.exceptions.RequestException as e:
                # Check if this is a retryable error based on status code
                status_code = None
                if hasattr(e, 'response') and e.response is not None:
                    status_code = e.response.status_code

                is_retryable_error = status_code == 429 or (500 <= status_code < 600) if status_code else False

                # Only retry on retryable errors if we have retries left
                if is_retryable_error and attempt < self.config.max_retries:
                    last_error = str(e)
                    sleep_s = self.config.backoff_base ** (attempt - 1)
                    logger.warning(
                        f"Gemini API request failed, retry {attempt}/{self.config.max_retries} "
                        f"after {sleep_s:.1f}s: {e}"
                    )
                    time.sleep(sleep_s)
                    continue

                # Last attempt or non-retryable error - log and raise
                logger.error(f"Gemini API request failed after {attempt} attempts: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Response content: {e.response.text}")
                raise

        # Should not reach here
        raise requests.RequestException(
            f"Gemini API request failed after {self.config.max_retries} retries: {last_error}"
        )

    def invoke(
        self,
        prompt: str,
        images: List[bytes],
        tools: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Invoke VLM with prompt and images.

        Args:
            prompt: Text prompt
            images: List of images (PNG bytes)
            tools: Optional tool definitions for function calling

        Returns:
            With tools: {"function_calls": [...], "text": Optional[str]}
            Without tools: {"text": str, "usage": {...}}
        """
        # Apply throttling
        self._throttle()

        # Build message parts
        parts = [{"text": prompt}]

        for img_bytes in images:
            b64_data = base64.b64encode(img_bytes).decode('utf-8')
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": b64_data
                }
            })

        # Build payload
        payload: Dict[str, Any] = {
            "contents": [{
                "parts": parts
            }]
        }

        # Add tools if provided
        if tools:
            payload["tools"] = tools
        # No JSON mode for simple prompts - return plain text

        headers = {'Content-Type': 'application/json'}

        logger.info(
            f"Sending request to Gemini {self.config.model} "
            f"with {len(images)} images, tools={'yes' if tools else 'no'}"
        )

        # Make request with retry
        start_ts = time.monotonic()
        result = self._make_request_with_retry(self.url, headers, payload)
        latency = time.monotonic() - start_ts

        self._last_call_ts = time.monotonic()
        self._calls_made += 1

        logger.info(f"Request completed in {latency:.3f}s")

        # Parse response
        return self._parse_response(result, tools is not None)

    def _parse_response(self, result: Dict, with_tools: bool) -> Dict[str, Any]:
        """Parse Gemini API response.

        Args:
            result: Raw API response
            with_tools: Whether tools were used

        Returns:
            Parsed response dict

        Raises:
            ValueError: If response format is invalid
        """
        try:
            candidate = result.get('candidates', [])[0]
            content = candidate.get('content', {})
            parts_resp = content.get('parts', [])

            if with_tools:
                # Parse function calls and text
                function_calls = []
                text_parts = []

                for part in parts_resp:
                    if 'functionCall' in part:
                        func_call = {
                            "name": part['functionCall']['name'],
                            "args": part['functionCall'].get('args', {})
                        }
                        function_calls.append(func_call)
                        logger.debug(f"Found functionCall: {func_call['name']}")
                    elif 'text' in part:
                        text_parts.append(part['text'])

                text_content = '\n'.join(text_parts) if text_parts else None

                return {
                    "function_calls": function_calls if function_calls else None,
                    "text": text_content,
                    "raw": result
                }
            else:
                # Simple text response - return as string, not parsed JSON
                text_content = parts_resp[0].get('text', '')
                logger.debug(f"Response text length: {len(text_content)}")

                return {
                    "text": text_content,
                    "raw": result
                }

        except (KeyError, IndexError) as e:
            logger.error(f"Failed to parse Gemini response: {e}. Raw response: {result}")
            raise ValueError(f"Failed to parse Gemini response: {e}") from e
