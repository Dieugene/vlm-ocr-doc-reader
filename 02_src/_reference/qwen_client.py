"""Qwen client for numeric/ID OCR via DashScope OpenAI-compatible endpoint."""

from __future__ import annotations

import base64
import json
import os
import re
import time
from io import BytesIO
from typing import Any, Dict, List, Optional

import requests
from PIL import Image


class QwenClientError(RuntimeError):
    """Raised when Qwen call fails."""


def parse_qwen_text_response(response_text: str) -> Dict[str, Any]:
    """
    Parse Qwen response in ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ format.
    
    Returns:
        {
            "status": "ok" | "no_data" | "error",
            "value": str,  # digits only, or empty
            "context": str,  # text fragment where found
            "explanation": str  # reasoning
        }
    """
    value_match = re.search(r"ЗНАЧЕНИЕ:\s*(\S+)", response_text)
    context_match = re.search(r"КОНТЕКСТ:\s*(.+?)(?=\nПОЯСНЕНИЕ:|$)", response_text, re.DOTALL)
    explanation_match = re.search(r"ПОЯСНЕНИЕ:\s*(.+)", response_text, re.DOTALL)
    
    value_raw = value_match.group(1).strip() if value_match else ""
    context = context_match.group(1).strip() if context_match else ""
    explanation = explanation_match.group(1).strip() if explanation_match else ""
    
    # Нормализация value: оставляем только цифры
    if value_raw.upper() == "НЕТ" or value_raw == "-":
        value = ""
        status = "no_data"
    else:
        # Извлекаем только цифры
        value = re.sub(r"[^\d]", "", value_raw)
        status = "ok" if value else "no_data"
    
    # Fallback: если ничего не распарсилось, ищем любые цифры в ответе
    if not value and not context and not explanation:
        # Возможно, Qwen ответил просто числом
        digits_only = re.sub(r"[^\d]", "", response_text)
        if len(digits_only) >= 10:  # Минимальная длина для ОГРН/ОРНЗ
            return {
                "status": "ok",
                "value": digits_only,
                "context": "",
                "explanation": "fallback: extracted digits from raw response",
            }
    
    return {
        "status": status,
        "value": value,
        "context": context,
        "explanation": explanation,
    }


class QwenClient:
    """
    Minimal OpenAI-compatible client for Qwen VL used to extract numeric/ID answers.
    One call = one image = one question. Response is expected to be JSON.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        model: str = "qwen-vl-plus",
        timeout_sec: int = 60,
        max_retries: int = 3,
        backoff_base: float = 1.5,
    ) -> None:
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError("DASHSCOPE_API_KEY is required (set in environment or pass explicitly)")
        self.endpoint = (
            endpoint or os.getenv("DASHSCOPE_API_ENDPOINT") or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
        self.model = model
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    def _build_url(self) -> str:
        return f"{self.endpoint}/chat/completions"

    def _image_to_base64(self, image_bytes: bytes) -> str:
        # Convert to PNG to avoid JPEG artifacts if needed
        img = Image.open(BytesIO(image_bytes))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def ask_number(self, image_bytes: bytes, page_num: int, question: str) -> Dict[str, Any]:
        """
        Asks Qwen to extract a numeric/ID answer for given question on a page image.
        Returns parsed response with status/value/context/explanation.
        """
        url = self._build_url()
        img_b64 = self._image_to_base64(image_bytes)
        messages = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Ты точный OCR-помощник для извлечения числовых идентификаторов из документов.\n\n"
                            "ФОРМАТ ОТВЕТА (строго соблюдай):\n"
                            "ЗНАЧЕНИЕ: <только цифры без пробелов, или НЕТ если не найдено>\n"
                            "КОНТЕКСТ: <фрагмент текста с извлечённым числом>\n"
                            "ПОЯСНЕНИЕ: <краткое объяснение, где искал и что нашёл/не нашёл>\n\n"
                            "ПРИМЕР УСПЕШНОГО ОТВЕТА:\n"
                            "ЗНАЧЕНИЕ: 22006042705\n"
                            "КОНТЕКСТ: Руководитель аудита, по результатам которого составлено аудиторское заключение (ОРНЗ 22006042705)\n"
                            "ПОЯСНЕНИЕ: Нашёл после фразы 'составлено аудиторское заключение' в центральной части\n\n"
                            "ПРИМЕР ПРИ ОТСУТСТВИИ ДАННЫХ:\n"
                            "ЗНАЧЕНИЕ: НЕТ\n"
                            "КОНТЕКСТ: -\n"
                            "ПОЯСНЕНИЕ: Искал номер после 'ОГРН:' в указанном блоке, но такого текста не нашёл на странице"
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
                        "text": f"Страница {page_num}. Задание: {question}\n\nОтветь в формате ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ.",
                    },
                ],
            },
        ]
        
        # СТАРЫЙ JSON-ФОРМАТ (закомментирован для возможного отката):
        # messages = [
        #     {
        #         "role": "system",
        #         "content": [
        #             {
        #                 "type": "text",
        #                 "text": (
        #                     "Ты точный OCR-помощник для числовых идентификаторов. "
        #                     "Отвечай ТОЛЬКО валидным JSON с ключами status и value. "
        #                     "status: ok|no_data|error. value: строка с цифрами без пробелов/знаков. "
        #                     "Если нет данных — status=no_data и value=\"\"."
        #                 ),
        #             }
        #         ],
        #     },
        #     {
        #         "role": "user",
        #         "content": [
        #             {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
        #             {
        #                 "type": "text",
        #                 "text": f"Страница (global_index) {page_num}. Вопрос: {question}. Верни JSON как {{\"status\": \"ok|no_data|error\", \"value\": \"\"}}.",
        #             },
        #         ],
        #     },
        # ]
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 200,
            # response_format убран - Qwen отвечает в текстовом формате ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        last_error: Optional[str] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(url, json=body, headers=headers, timeout=self.timeout_sec)
                status = resp.status_code
                if status in {429} or 500 <= status < 600:
                    last_error = f"status={status}, body={resp.text[:400]}"
                    if attempt < self.max_retries:
                        sleep_s = self.backoff_base ** (attempt - 1)
                        time.sleep(sleep_s)
                        continue
                    resp.raise_for_status()
                resp.raise_for_status()
                payload = resp.json()
                
                # Извлекаем текст из ответа API
                choices = payload.get("choices") or []
                if not choices:
                    raise QwenClientError(f"No choices in response: {payload}")
                message = choices[0].get("message") or {}
                content = message.get("content")
                response_text = ""
                if isinstance(content, list):
                    parts: List[str] = []
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
                
                # Парсим новый текстовый формат ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ
                return parse_qwen_text_response(response_text)
            except requests.HTTPError as exc:
                text = getattr(exc.response, "text", "")[:400] if getattr(exc, "response", None) is not None else str(exc)
                last_error = text
                if attempt < self.max_retries:
                    sleep_s = self.backoff_base ** (attempt - 1)
                    time.sleep(sleep_s)
                    continue
                raise QwenClientError(f"Qwen request failed: {text}") from exc
            except Exception as exc:  # pragma: no cover - network
                last_error = str(exc)
                if attempt < self.max_retries:
                    sleep_s = self.backoff_base ** (attempt - 1)
                    time.sleep(sleep_s)
                    continue
                raise QwenClientError(f"Qwen request failed: {exc}") from exc

        raise QwenClientError(f"Qwen request failed: {last_error}")

    # СТАРЫЙ JSON-ПАРСЕР (закомментирован для возможного отката):
    # def _parse_json_response(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    #     choices = payload.get("choices") or []
    #     if not choices:
    #         raise QwenClientError(f"No choices in response: {payload}")
    #     message = choices[0].get("message") or {}
    #     content = message.get("content")
    #     text_payload = ""
    #     if isinstance(content, list):
    #         parts: List[str] = []
    #         for item in content:
    #             if isinstance(item, dict) and item.get("type") == "text":
    #                 parts.append(item.get("text", ""))
    #             elif isinstance(item, str):
    #                 parts.append(item)
    #         text_payload = "\n".join(parts).strip()
    #     elif isinstance(content, str):
    #         text_payload = content.strip()
    #     if not text_payload:
    #         raise QwenClientError("Empty content in Qwen response")
    #     try:
    #         parsed = json.loads(text_payload)
    #     except json.JSONDecodeError as exc:
    #         raise QwenClientError(f"Failed to parse Qwen JSON: {exc} | text={text_payload}") from exc
    #     if not isinstance(parsed, dict):
    #         raise QwenClientError(f"Qwen JSON is not object: {parsed}")
    #     return parsed

