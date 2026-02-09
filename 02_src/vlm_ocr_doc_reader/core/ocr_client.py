"""OCR Client for Qwen VL API.

Provides OCR functionality with retry logic for robust numeric/ID extraction.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, Optional

import requests
from PIL import Image

logger = logging.getLogger(__name__)


class QwenClientError(RuntimeError):
    """Raised when Qwen API call fails after all retries."""


@dataclass
class OCRConfig:
    """Configuration for OCR client.

    Attributes:
        api_key: Qwen API key (from env var QWEN_API_KEY if not provided)
        model: Model name (default: qwen-vl-plus)
        timeout_sec: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        backoff_base: Base for exponential backoff calculation
    """
    api_key: Optional[str] = None
    model: str = "qwen-vl-plus"
    timeout_sec: int = 60
    max_retries: int = 3
    backoff_base: float = 1.5

    def __post_init__(self):
        """Load API key from environment if not provided."""
        if self.api_key is None:
            self.api_key = os.getenv("QWEN_API_KEY")
        if not self.api_key:
            raise ValueError("QWEN_API_KEY is required (set in environment or pass explicitly)")


class BaseOCRClient(ABC):
    """Base interface for OCR clients.

    All OCR clients must implement the extract() method with consistent return format.
    """

    @abstractmethod
    def extract(
        self,
        image: bytes,
        prompt: str,
        page_num: int
    ) -> Dict[str, Any]:
        """Extract data from image.

        Args:
            image: Image bytes (PNG/JPEG)
            prompt: Extraction prompt/question
            page_num: Page number for logging

        Returns:
            {
                "status": "ok" | "no_data" | "error",
                "value": str,  # Extracted value (as-is from document)
                "context": str,  # Text fragment where found
                "explanation": str  # Reasoning
            }
        """
        raise NotImplementedError


class QwenOCRClient(BaseOCRClient):
    """Qwen VL OCR client with retry logic.

    Uses OpenAI-compatible endpoint for Qwen VL model.
    Implements exponential backoff retry for rate limits and server errors.
    """

    def __init__(self, config: OCRConfig) -> None:
        """Initialize Qwen OCR client.

        Args:
            config: OCR configuration
        """
        self.config = config
        self.endpoint = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    def _build_url(self) -> str:
        """Build API endpoint URL."""
        return f"{self.endpoint}/chat/completions"

    def _image_to_base64(self, image_bytes: bytes) -> str:
        """Convert image bytes to base64 PNG string.

        Args:
            image_bytes: Input image bytes

        Returns:
            Base64-encoded PNG string
        """
        # Convert to PNG to avoid JPEG artifacts
        img = Image.open(BytesIO(image_bytes))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _parse_qwen_response(self, response_text: str) -> Dict[str, Any]:
        """Parse Qwen response in ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ format.

        Args:
            response_text: Raw response text from Qwen

        Returns:
            Parsed response with status/value/context/explanation
        """
        value_match = re.search(r"ЗНАЧЕНИЕ:\s*(.+?)(?=\nКОНТЕКСТ:|\nПОЯСНЕНИЕ:|$)", response_text, re.DOTALL)
        context_match = re.search(r"КОНТЕКСТ:\s*(.+?)(?=\nПОЯСНЕНИЕ:|$)", response_text, re.DOTALL)
        explanation_match = re.search(r"ПОЯСНЕНИЕ:\s*(.+)", response_text, re.DOTALL)

        value_raw = value_match.group(1).strip() if value_match else ""
        context = context_match.group(1).strip() if context_match else ""
        explanation = explanation_match.group(1).strip() if explanation_match else ""

        # Return raw value - normalization should be optional/controlled by caller
        if value_raw.upper() == "НЕТ" or value_raw == "-" or not value_raw:
            status = "no_data"
            value = ""
        else:
            status = "ok"
            value = value_raw

        return {
            "status": status,
            "value": value,
            "context": context,
            "explanation": explanation,
        }

    def extract(
        self,
        image: bytes,
        prompt: str,
        page_num: int
    ) -> Dict[str, Any]:
        """Extract data from image using Qwen VL API.

        Args:
            image: Image bytes (PNG/JPEG)
            prompt: Extraction prompt/question
            page_num: Page number for logging

        Returns:
            {
                "status": "ok" | "no_data" | "error",
                "value": str,
                "context": str,
                "explanation": str
            }

        Raises:
            QwenClientError: If all retry attempts fail
        """
        url = self._build_url()
        img_b64 = self._image_to_base64(image)

        # Build messages with system prompt for structured output
        messages = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Ты точный OCR-помощник. Твоя задача - извлечь конкретное значение из изображения документа.\n\n"
                            "ФОРМАТ ОТВЕТА (строго соблюдай):\n"
                            "ЗНАЧЕНИЕ: <извлечённое значение целиком, или НЕТ если не найдено>\n"
                            "КОНТЕКСТ: <фрагмент текста вокруг найденного значения>\n"
                            "ПОЯСНЕНИЕ: <где искал и что нашёл/не нашёл>\n\n"
                            "ПРАВИЛА:\n"
                            "- Возвращай значение ТОЧНО как в документе, не изменяй и не сокращай\n"
                            "- URL возвращай полностью, включая протокол и весь путь\n"
                            "- Числа, ФИО, адреса - точно как написано\n"
                            "- Если значение не найдено, ЗНАЧЕНИЕ: НЕТ\n\n"
                            "ПРИМЕР (URL):\n"
                            "ЗНАЧЕНИЕ: https://example.com/path/to/page\n"
                            "КОНТЕКСТ: См. подробнее: https://example.com/path/to/page (раздел 3)\n"
                            "ПОЯСНЕНИЕ: Нашёл URL в нижней части страницы после слова 'подробнее'\n\n"
                            "ПРИМЕР (ID):\n"
                            "ЗНАЧЕНИЕ: 1234567890123\n"
                            "КОНТЕКСТ: ОГРН: 1234567890123\n"
                            "ПОЯСНЕНИЕ: Нашёл после метки 'ОГРН:' в шапке документа\n\n"
                            "ПРИМЕР (не найдено):\n"
                            "ЗНАЧЕНИЕ: НЕТ\n"
                            "КОНТЕКСТ: -\n"
                            "ПОЯСНЕНИЕ: Искал на странице, но указанные данные отсутствуют"
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                    {
                        "type": "text",
                        "text": f"Страница {page_num}. Задание: {prompt}\n\nОтветь в формате ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ.",
                    },
                ],
            },
        ]

        body: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0.0,
            "top_p": 0.9,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }

        last_error: Optional[str] = None

        for attempt in range(1, self.config.max_retries + 1):
            start_time = time.time()
            try:
                resp = requests.post(
                    url,
                    json=body,
                    headers=headers,
                    timeout=self.config.timeout_sec
                )
                status = resp.status_code
                latency_ms = int((time.time() - start_time) * 1000)

                # Retry on rate limit or server errors
                if status == 429 or (500 <= status < 600):
                    last_error = f"status={status}, body={resp.text[:400]}"
                    logger.warning(
                        f"Qwen API attempt {attempt}/{self.config.max_retries}: "
                        f"status={status}, latency={latency_ms}ms, will retry"
                    )
                    if attempt < self.config.max_retries:
                        sleep_s = self.config.backoff_base ** (attempt - 1)
                        time.sleep(sleep_s)
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()
                payload = resp.json()

                # Extract response content
                choices = payload.get("choices") or []
                if not choices:
                    raise QwenClientError(f"No choices in response: {payload}")

                message = choices[0].get("message") or {}
                content = message.get("content")

                response_text = ""
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            parts.append(item.get("text", ""))
                        elif isinstance(item, str):
                            parts.append(item)
                    response_text = "\n".join(parts).strip()
                elif isinstance(content, str):
                    response_text = content.strip()

                if not response_text:
                    raise QwenClientError("Empty content in Qwen response")

                result = self._parse_qwen_response(response_text)
                logger.info(
                    f"Qwen OCR page={page_num} | prompt='{prompt}' | "
                    f"status={result['status']} | value='{result['value']}' | "
                    f"context='{result['context']}' | latency={latency_ms}ms"
                )
                return result

            except requests.HTTPError as exc:
                latency_ms = int((time.time() - start_time) * 1000)
                text = getattr(exc.response, "text", "")[:400] if getattr(exc, "response", None) is not None else str(exc)
                last_error = text
                logger.warning(
                    f"Qwen API HTTP error: attempt={attempt}/{self.config.max_retries}, "
                    f"latency={latency_ms}ms, error={text[:200]}"
                )
                if attempt < self.config.max_retries:
                    sleep_s = self.config.backoff_base ** (attempt - 1)
                    time.sleep(sleep_s)
                    continue
                raise QwenClientError(f"Qwen request failed: {text}") from exc

            except Exception as exc:
                latency_ms = int((time.time() - start_time) * 1000)
                last_error = str(exc)
                logger.warning(
                    f"Qwen API error: attempt={attempt}/{self.config.max_retries}, "
                    f"latency={latency_ms}ms, error={str(exc)[:200]}"
                )
                if attempt < self.config.max_retries:
                    sleep_s = self.config.backoff_base ** (attempt - 1)
                    time.sleep(sleep_s)
                    continue
                raise QwenClientError(f"Qwen request failed: {exc}") from exc

        raise QwenClientError(f"Qwen request failed after {self.config.max_retries} attempts: {last_error}")
