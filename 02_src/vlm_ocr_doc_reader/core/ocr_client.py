"""OCR Client for Qwen VL OCR API (DashScope OpenAI-compatible endpoint).

Single-image, multi-question batched extraction. extract() is a thin wrapper
over extract_batch([prompt])[0] so single-prompt callers stay the same shape.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Optional

import requests
from PIL import Image

logger = logging.getLogger(__name__)


class QwenClientError(RuntimeError):
    """Raised when Qwen API call fails after all retries."""


@dataclass
class OCRConfig:
    """Configuration for OCR client.

    Attributes:
        api_key: DashScope API key (from env DASHSCOPE_API_KEY / QWEN_API_KEY)
        model: Model name (default: qwen-vl-ocr-2025-11-20)
        timeout_sec: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        backoff_base: Base for exponential backoff calculation
    """
    api_key: Optional[str] = None
    model: str = "qwen-vl-ocr-2025-11-20"
    timeout_sec: int = 60
    max_retries: int = 3
    backoff_base: float = 1.5

    def __post_init__(self):
        if self.api_key is None:
            self.api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
        if not self.api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY or QWEN_API_KEY is required "
                "(set in environment or pass explicitly)"
            )


class BaseOCRClient(ABC):
    """Base interface for OCR clients."""

    @abstractmethod
    def extract_batch(
        self,
        image: bytes,
        prompts: List[str],
        page_num: int,
    ) -> List[Dict[str, Any]]:
        """Extract multiple values from one image in a single request.

        Returns one result dict per prompt, in the same order. Each dict has
        keys: status ("ok"|"no_data"|"error"), value, context, explanation.
        """
        raise NotImplementedError

    def extract(
        self,
        image: bytes,
        prompt: str,
        page_num: int,
    ) -> Dict[str, Any]:
        """Single-prompt convenience wrapper around extract_batch."""
        results = self.extract_batch(image, [prompt], page_num)
        return results[0] if results else {
            "status": "error",
            "value": "",
            "context": "",
            "explanation": "Empty result from extract_batch",
        }


_TASK_BLOCK_RE = re.compile(
    r"\[ЗАДАЧА\s+(\d+)\](.*?)(?=\[ЗАДАЧА\s+\d+\]|$)",
    re.DOTALL,
)
_VALUE_RE = re.compile(
    r"ЗНАЧЕНИЕ:\s*(.+?)(?=\n\s*КОНТЕКСТ:|\n\s*ПОЯСНЕНИЕ:|$)", re.DOTALL
)
_CONTEXT_RE = re.compile(
    r"КОНТЕКСТ:\s*(.+?)(?=\n\s*ПОЯСНЕНИЕ:|$)", re.DOTALL
)
_EXPLAIN_RE = re.compile(r"ПОЯСНЕНИЕ:\s*(.+)", re.DOTALL)
_DIGIT_LIKE_RE = re.compile(r"^[\d\s\-\.]+$")


def parse_qwen_text_response(response_text: str) -> Dict[str, Any]:
    """Parse a single ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ block."""
    value_match = _VALUE_RE.search(response_text)
    context_match = _CONTEXT_RE.search(response_text)
    explain_match = _EXPLAIN_RE.search(response_text)

    value_raw = value_match.group(1).strip() if value_match else ""
    context = context_match.group(1).strip() if context_match else ""
    explanation = explain_match.group(1).strip() if explain_match else ""

    if not value_raw and response_text.strip() and _DIGIT_LIKE_RE.match(response_text.strip()):
        return {
            "status": "ok",
            "value": response_text.strip(),
            "context": "",
            "explanation": "fallback",
        }

    if value_raw.upper() == "НЕТ" or value_raw == "-" or not value_raw:
        return {
            "status": "no_data",
            "value": "",
            "context": context,
            "explanation": explanation,
        }

    return {
        "status": "ok",
        "value": value_raw,
        "context": context,
        "explanation": explanation,
    }


def parse_multi_task_response(
    response_text: str,
    expected: int,
) -> List[Dict[str, Any]]:
    """Parse a multi-task response into `expected` blocks, in order.

    Missing blocks yield status='error'. Extra blocks beyond `expected` are
    ignored.
    """
    results: Dict[int, Dict[str, Any]] = {}
    for match in _TASK_BLOCK_RE.finditer(response_text):
        try:
            idx = int(match.group(1))
        except ValueError:
            continue
        if idx < 1 or idx > expected:
            continue
        results[idx] = parse_qwen_text_response(match.group(2))

    # Single-task fallback: model may have skipped the [ЗАДАЧА 1] header
    if expected == 1 and 1 not in results:
        results[1] = parse_qwen_text_response(response_text)

    out: List[Dict[str, Any]] = []
    for i in range(1, expected + 1):
        if i in results:
            out.append(results[i])
        else:
            out.append({
                "status": "error",
                "value": "",
                "context": "",
                "explanation": f"Missing [ЗАДАЧА {i}] block in response",
            })
    return out


_SYSTEM_PROMPT = (
    "Ты точный OCR-помощник. Тебе дана одна страница документа и нумерованный "
    "список задач извлечения. Для КАЖДОЙ задачи верни ровно один блок в "
    "формате:\n\n"
    "[ЗАДАЧА N]\n"
    "ЗНАЧЕНИЕ: <извлечённое значение целиком, или НЕТ если не найдено>\n"
    "КОНТЕКСТ: <фрагмент текста вокруг найденного значения>\n"
    "ПОЯСНЕНИЕ: <где искал и что нашёл/не нашёл>\n\n"
    "ПРАВИЛА:\n"
    "- N — номер задачи из списка (1, 2, 3, ...)\n"
    "- ЗНАЧЕНИЕ возвращай точно как в документе, не изменяй и не сокращай\n"
    "- URL возвращай полностью, включая протокол и весь путь\n"
    "- Числа, ФИО, адреса, идентификаторы — посимвольно как написано\n"
    "- Если значение не найдено — ЗНАЧЕНИЕ: НЕТ\n"
    "- Не пропускай задачи и не объединяй ответы между задачами\n"
    "- Блоки идут в том же порядке, что задачи в списке\n\n"
    "ПРИМЕР (две задачи):\n"
    "[ЗАДАЧА 1]\n"
    "ЗНАЧЕНИЕ: https://example.com/path/to/page\n"
    "КОНТЕКСТ: См. подробнее: https://example.com/path/to/page (раздел 3)\n"
    "ПОЯСНЕНИЕ: Нашёл URL в нижней части после слова 'подробнее'\n\n"
    "[ЗАДАЧА 2]\n"
    "ЗНАЧЕНИЕ: НЕТ\n"
    "КОНТЕКСТ: -\n"
    "ПОЯСНЕНИЕ: Email на странице отсутствует"
)


class QwenOCRClient(BaseOCRClient):
    """Qwen VL OCR client (DashScope OpenAI-compatible endpoint, multi-question)."""

    def __init__(self, config: OCRConfig) -> None:
        self.config = config
        self.endpoint = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    def _build_url(self) -> str:
        return f"{self.endpoint}/chat/completions"

    @staticmethod
    def _image_to_base64(image_bytes: bytes) -> str:
        img = Image.open(BytesIO(image_bytes))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _build_payload(
        self,
        image_b64: str,
        prompts: List[str],
        page_num: int,
    ) -> Dict[str, Any]:
        if len(prompts) == 1:
            user_text = (
                f"Страница {page_num}. Выполни одну задачу:\n"
                f"1. {prompts[0]}\n\n"
                "Верни блок [ЗАДАЧА 1] с ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ."
            )
        else:
            tasks_str = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(prompts))
            user_text = (
                f"Страница {page_num}. Выполни {len(prompts)} задач:\n"
                f"{tasks_str}\n\n"
                f"Верни {len(prompts)} блоков [ЗАДАЧА N] подряд, по одному на каждую задачу."
            )

        return {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": _SYSTEM_PROMPT}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                        {"type": "text", "text": user_text},
                    ],
                },
            ],
            "temperature": 0.0,
            "top_p": 0.9,
        }

    def _post_with_retry(self, payload: Dict[str, Any]) -> str:
        url = self._build_url()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }
        last_error: Optional[str] = None

        for attempt in range(1, self.config.max_retries + 1):
            start_time = time.time()
            try:
                resp = requests.post(
                    url, json=payload, headers=headers, timeout=self.config.timeout_sec
                )
                # DashScope responds with UTF-8 but without `charset` in Content-Type;
                # requests then falls back to ISO-8859-1 per RFC 2616 and garbles Cyrillic.
                resp.encoding = "utf-8"
                latency_ms = int((time.time() - start_time) * 1000)
                status = resp.status_code

                if status == 429 or (500 <= status < 600):
                    last_error = f"status={status}, body={resp.text[:400]}"
                    logger.warning(
                        f"Qwen API attempt {attempt}/{self.config.max_retries}: "
                        f"status={status}, latency={latency_ms}ms, will retry"
                    )
                    if attempt < self.config.max_retries:
                        time.sleep(self.config.backoff_base ** (attempt - 1))
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()
                payload_json = resp.json()

                choices = payload_json.get("choices") or []
                if not choices:
                    raise QwenClientError(f"No choices in response: {payload_json}")

                message = choices[0].get("message") or {}
                content = message.get("content")
                if isinstance(content, list):
                    parts = [
                        item.get("text", "")
                        for item in content
                        if isinstance(item, dict) and item.get("type") == "text"
                    ]
                    response_text = "\n".join(parts).strip()
                elif isinstance(content, str):
                    response_text = content.strip()
                else:
                    response_text = ""

                if not response_text:
                    raise QwenClientError("Empty content in Qwen response")
                return response_text

            except requests.HTTPError as exc:
                latency_ms = int((time.time() - start_time) * 1000)
                resp_obj = getattr(exc, "response", None)
                text = getattr(resp_obj, "text", "")[:400] if resp_obj is not None else str(exc)
                last_error = text
                logger.warning(
                    f"Qwen API HTTP error: attempt={attempt}/{self.config.max_retries}, "
                    f"latency={latency_ms}ms, error={text[:200]}"
                )
                if attempt < self.config.max_retries:
                    time.sleep(self.config.backoff_base ** (attempt - 1))
                    continue
                raise QwenClientError(f"Qwen request failed: {text}") from exc

            except (requests.ConnectionError, requests.Timeout) as exc:
                latency_ms = int((time.time() - start_time) * 1000)
                last_error = str(exc)
                logger.warning(
                    f"Qwen API network error: attempt={attempt}/{self.config.max_retries}, "
                    f"latency={latency_ms}ms, error={str(exc)[:200]}"
                )
                if attempt < self.config.max_retries:
                    time.sleep(self.config.backoff_base ** (attempt - 1))
                    continue
                raise QwenClientError(f"Qwen request failed: {exc}") from exc

        raise QwenClientError(
            f"Qwen request failed after {self.config.max_retries} attempts: {last_error}"
        )

    def extract_batch(
        self,
        image: bytes,
        prompts: List[str],
        page_num: int,
    ) -> List[Dict[str, Any]]:
        if not prompts:
            return []

        img_b64 = self._image_to_base64(image)
        payload = self._build_payload(img_b64, prompts, page_num)

        start_time = time.time()
        response_text = self._post_with_retry(payload)
        latency_ms = int((time.time() - start_time) * 1000)

        results = parse_multi_task_response(response_text, len(prompts))
        ok = sum(1 for r in results if r["status"] == "ok")
        no_data = sum(1 for r in results if r["status"] == "no_data")
        err = sum(1 for r in results if r["status"] == "error")
        logger.info(
            f"Qwen OCR page={page_num} | tasks={len(prompts)} | "
            f"ok={ok} no_data={no_data} error={err} | latency={latency_ms}ms"
        )
        return results
