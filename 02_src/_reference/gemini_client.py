import requests
import base64
import json
import time
from typing import List, Dict, Any, Optional

TIMEOUT_S = 60  # Increased from 30s - needed for complex agentic iterations with long message history

from .config import settings
from .logger import setup_logger

logger = setup_logger("gemini_client")

class GeminiRestClient:
    def __init__(
        self,
        api_key: str = None,
        model: str = "gemini-2.5-flash",
        timeout: float = TIMEOUT_S,
        max_retries: int = 3,
        backoff_base: float = 1.5,
    ):
        self.api_key = api_key if api_key else settings.GEMINI_API_KEY
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        if not self.api_key:
            logger.warning("Gemini API Key is not set!")

        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

    def _make_request_with_retry(self, url: str, headers: Dict, payload: Dict) -> Dict:
        """
        Make POST request with retry logic for rate limits and server errors.
        Handles 429 (rate limit) and 500-599 (server errors) with exponential backoff.
        """
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                status = response.status_code

                # Retry on rate limit or server errors
                if status in {429} or 500 <= status < 600:
                    last_error = f"status={status}, body={response.text[:400]}"
                    if attempt < self.max_retries:
                        sleep_s = self.backoff_base ** (attempt - 1)
                        logger.warning(f"Gemini API {status} error, retry {attempt}/{self.max_retries} after {sleep_s:.1f}s")
                        time.sleep(sleep_s)
                        continue
                    # Last attempt - raise
                    response.raise_for_status()

                # Success or non-retryable error
                response.raise_for_status()
                return response.json()

            except requests.exceptions.RequestException as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    sleep_s = self.backoff_base ** (attempt - 1)
                    logger.warning(f"Gemini API request failed, retry {attempt}/{self.max_retries} after {sleep_s:.1f}s: {e}")
                    time.sleep(sleep_s)
                    continue
                # Last attempt - log and raise
                logger.error(f"Gemini API request failed after {self.max_retries} retries: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Response content: {e.response.text}")
                raise

        # Should not reach here, but just in case
        raise requests.exceptions.RequestException(f"Gemini API request failed after {self.max_retries} retries: {last_error}")

    def generate_content(self, prompt: str, images: List[bytes]) -> Dict:
        """
        Legacy method for backwards compatibility.
        Sends prompt and images to Gemini with JSON mode.
        Returns parsed JSON response.
        """
        parts = [{"text": prompt}]

        for img_bytes in images:
            b64_data = base64.b64encode(img_bytes).decode('utf-8')
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": b64_data
                }
            })

        payload = {
            "contents": [{
                "parts": parts
            }],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }

        headers = {'Content-Type': 'application/json'}

        logger.info(f"Sending request to Gemini {self.model} with {len(images)} images")

        # Make request with retry logic
        result = self._make_request_with_retry(self.url, headers, payload)

        # Extract text from response
        # candidates[0].content.parts[0].text
        try:
            candidate = result.get('candidates', [])[0]
            content = candidate.get('content', {})
            parts_resp = content.get('parts', [])
            text_content = parts_resp[0].get('text', '')

            logger.debug(f"Gemini raw response text length: {len(text_content)}")
            return json.loads(text_content)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse Gemini response: {e}. Raw response: {result}")
            raise

    def generate_content_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Sends messages to Gemini with optional tools (Function Calling API).

        Args:
            messages: List of message dicts with structure:
                [
                    {"role": "user", "parts": [{"text": "..."}, {"inline_data": {...}}]},
                    {"role": "model", "parts": [{"text": "..."}]},
                    {"role": "user", "parts": [{"functionResponse": {...}}]}
                ]
            tools: Optional tools definition for function calling:
                [
                    {
                        "function_declarations": [
                            {
                                "name": "function_name",
                                "description": "...",
                                "parameters": {"type": "object", "properties": {...}}
                            }
                        ]
                    }
                ]

        Returns:
            Dict with structure:
                {
                    "text": str or None,  # Text response if present
                    "function_calls": List[Dict] or None,  # Function calls if present
                    "raw": Dict  # Raw API response
                }
        """
        payload: Dict[str, Any] = {
            "contents": messages
        }

        if tools:
            payload["tools"] = tools

        # NOTE: Cannot use responseMimeType: "application/json" with Function Calling!
        # Gemini API returns error: "Function calling with a response mime type: 'application/json' is unsupported"
        # Therefore we clean markdown fence manually in hybrid_dialogue.py::_parse_batch_response

        headers = {'Content-Type': 'application/json'}

        logger.info(f"Sending request to Gemini {self.model} with {len(messages)} messages, tools={'yes' if tools else 'no'}")

        # Make request with retry logic
        result = self._make_request_with_retry(self.url, headers, payload)

        # LOG RAW RESPONSE
        logger.info(f"Gemini RAW response: {json.dumps(result, ensure_ascii=False, indent=2)}")

        # Extract response
        try:
                candidate = result.get('candidates', [])[0]
                content = candidate.get('content', {})
                parts_resp = content.get('parts', [])

                logger.info(f"Extracted parts_resp: {json.dumps(parts_resp, ensure_ascii=False, indent=2)}")

                # Check for function calls
                function_calls = []
                text_parts = []

                for part in parts_resp:
                    if 'functionCall' in part:
                        func_call = {
                            "name": part['functionCall']['name'],
                            "args": part['functionCall'].get('args', {})
                        }
                        function_calls.append(func_call)
                        logger.info(f"Found functionCall: {json.dumps(func_call, ensure_ascii=False)}")
                    elif 'text' in part:
                        text_parts.append(part['text'])
                        logger.info(f"Found text part (length={len(part['text'])}): {part['text'][:200]}...")

                text_content = '\n'.join(text_parts) if text_parts else None

                result_dict = {
                    "text": text_content,
                    "function_calls": function_calls if function_calls else None,
                    "raw": result
                }

                logger.info(f"Gemini parsed result: text={bool(text_content)} (len={len(text_content) if text_content else 0}), function_calls={len(function_calls) if function_calls else 0}")

                return result_dict

        except (KeyError, IndexError) as e:
            logger.error(f"Failed to parse Gemini response: {e}. Raw response: {result}")
            raise

