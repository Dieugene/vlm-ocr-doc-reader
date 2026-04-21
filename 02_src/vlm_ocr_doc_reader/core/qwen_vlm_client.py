"""Qwen VLM client — DashScope OpenAI-compatible endpoint.

Thin pass-through: accepts OpenAI-style messages and tools directly, sends to
DashScope, returns assistant message in the same internal format.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

import requests

from ..schemas.config import VLMConfig
from .vlm_client import BaseVLMClient

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"


class QwenVLMClient(BaseVLMClient):
    """Qwen VLM client via DashScope OpenAI-compatible API."""

    def __init__(
        self,
        config: VLMConfig,
        endpoint: str = DEFAULT_ENDPOINT,
    ) -> None:
        if not config.api_key:
            raise ValueError("DashScope API key is required for QwenVLMClient")
        self.config = config
        self.endpoint = endpoint
        self._last_call_ts: Optional[float] = None

    def _throttle(self) -> None:
        if self._last_call_ts is None:
            return
        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < self.config.min_interval_s:
            time.sleep(self.config.min_interval_s - elapsed)

    def _post_with_retry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Optional[str] = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                logger.info(
                    f"VLM request attempt {attempt}/{self.config.max_retries} "
                    f"model={payload.get('model')}"
                )
                resp = requests.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.config.timeout_sec,
                )
                status = resp.status_code
                is_retryable = status == 429 or (500 <= status < 600)

                if is_retryable and attempt < self.config.max_retries:
                    last_error = f"status={status}, body={resp.text[:400]}"
                    sleep_s = self.config.backoff_base ** (attempt - 1)
                    logger.warning(
                        f"DashScope {status}, retry {attempt}/{self.config.max_retries} "
                        f"after {sleep_s:.1f}s"
                    )
                    time.sleep(sleep_s)
                    continue

                if is_retryable:
                    logger.error(
                        f"Retryable error but out of retries "
                        f"(attempt {attempt}/{self.config.max_retries})"
                    )
                    resp.raise_for_status()

                if status >= 400:
                    logger.info(
                        f"Request failed status={status}, not retrying (client error)"
                    )
                    logger.error(f"Response content: {resp.text[:800]}")
                    resp.raise_for_status()

                return resp.json()

            except requests.exceptions.RequestException as e:
                status_code = None
                if getattr(e, "response", None) is not None:
                    status_code = e.response.status_code
                is_net = isinstance(
                    e,
                    (requests.exceptions.Timeout, requests.exceptions.ConnectionError),
                )
                is_status_retryable = (
                    (status_code == 429 or (500 <= status_code < 600))
                    if status_code
                    else False
                )
                if (is_net or is_status_retryable) and attempt < self.config.max_retries:
                    last_error = str(e)
                    sleep_s = self.config.backoff_base ** (attempt - 1)
                    logger.warning(
                        f"DashScope request failed, retry "
                        f"{attempt}/{self.config.max_retries} after {sleep_s:.1f}s: {e}"
                    )
                    time.sleep(sleep_s)
                    continue

                logger.error(f"DashScope request failed after {attempt} attempts: {e}")
                if getattr(e, "response", None) is not None:
                    logger.error(f"Response content: {e.response.text[:800]}")
                raise

        raise requests.RequestException(
            f"DashScope request failed after {self.config.max_retries} retries: {last_error}"
        )

    @staticmethod
    def _parse_choice(data: Dict[str, Any]) -> Dict[str, Any]:
        choices = data.get("choices") or []
        if not choices:
            raise ValueError(f"DashScope response has no choices: {data}")
        msg = choices[0].get("message") or {}

        content = msg.get("content")
        if isinstance(content, list):
            # Collapse content parts into plain text (we only use text output)
            parts_text = [p.get("text", "") for p in content if isinstance(p, dict)]
            content = "".join(parts_text) or None

        raw_tool_calls = msg.get("tool_calls") or None
        tool_calls: Optional[List[Dict[str, Any]]] = None
        if raw_tool_calls:
            tool_calls = []
            for idx, tc in enumerate(raw_tool_calls):
                fn = tc.get("function") or {}
                tool_calls.append(
                    {
                        "id": tc.get("id") or f"call_{idx}",
                        "type": "function",
                        "function": {
                            "name": fn.get("name", ""),
                            "arguments": fn.get("arguments", "") or "",
                        },
                    }
                )

        return {
            "message": {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            },
            "usage": data.get("usage"),
        }

    def invoke(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        self._throttle()

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools

        logger.info(
            f"Sending request to Qwen {self.config.model} "
            f"with {len(messages)} messages, tools={'yes' if tools else 'no'}"
        )

        t0 = time.monotonic()
        data = self._post_with_retry(payload)
        latency = time.monotonic() - t0
        self._last_call_ts = time.monotonic()
        logger.info(f"Request completed in {latency:.3f}s")

        return self._parse_choice(data)


__all__ = ["QwenVLMClient", "DEFAULT_ENDPOINT"]
