"""VLM Agent — conversation + tool-calling loop, provider-neutral.

Uses OpenAI-style message/tool schema (see vlm_client.BaseVLMClient).
"""

from __future__ import annotations

import base64
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from .vlm_client import BaseVLMClient

logger = logging.getLogger(__name__)


def _user_parts(prompt: str, images: List[bytes]) -> List[Dict[str, Any]]:
    parts: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    for img in images:
        b64 = base64.b64encode(img).decode("utf-8")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            }
        )
    return parts


class VLMAgent:
    """Conversation-aware VLM agent with tool-calling loop."""

    def __init__(
        self,
        vlm_client: BaseVLMClient,
        max_iterations: int = 10,
        max_tool_workers: int = 1,
    ) -> None:
        self.vlm_client = vlm_client
        self.max_iterations = max_iterations
        self.max_tool_workers = max_tool_workers
        self.messages: List[Dict[str, Any]] = []
        self.tools: Dict[str, Callable] = {}
        self.tool_definitions: List[Dict[str, Any]] = []

    def register_tool(self, tool_def: Dict[str, Any], handler: Callable) -> None:
        """Register a tool.

        tool_def format (OpenAI-style):
            {"type": "function",
             "function": {"name": "...", "description": "...",
                          "parameters": {<json-schema>}}}
        """
        func = tool_def.get("function") or {}
        name = func.get("name")
        if not name:
            raise ValueError(f"Tool definition missing function.name: {tool_def}")
        self.tools[name] = handler
        self.tool_definitions.append(tool_def)
        logger.info(f"Registered tool: {name}")

    def set_system_prompt(self, prompt: str) -> None:
        """Reset history and set system prompt."""
        self.messages = [{"role": "system", "content": prompt}]
        logger.debug("System prompt set")

    def _append_user(self, prompt: str, images: List[bytes]) -> None:
        content: Any
        if images:
            content = _user_parts(prompt, images)
        else:
            content = prompt
        self.messages.append({"role": "user", "content": content})

    def invoke(self, prompt: str, images: List[bytes]) -> Dict[str, Any]:
        """Tool-calling loop until model returns text (final answer) or limit hit."""
        self._append_user(prompt, images)

        function_results: List[Dict[str, Any]] = []

        for iteration in range(self.max_iterations):
            logger.info(f"Tool calling iteration {iteration + 1}/{self.max_iterations}")
            tools = self.tool_definitions or None

            try:
                response = self.vlm_client.invoke(messages=self.messages, tools=tools)
            except Exception as e:
                logger.error(f"VLM call failed: {e}")
                return {
                    "text": None,
                    "error": str(e),
                    "function_results": function_results,
                }

            msg = response.get("message") or {}
            tool_calls = msg.get("tool_calls")
            text_content = msg.get("content")

            if tool_calls:
                logger.info(f"Model requested {len(tool_calls)} tool calls")
                # Persist assistant turn with tool_calls (content may be null)
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": text_content,
                        "tool_calls": tool_calls,
                    }
                )

                ordered = self._execute_tool_calls(tool_calls)
                for tc, result in ordered:
                    function_results.append(
                        {
                            "name": tc["function"]["name"],
                            "args": self._parse_args(tc["function"].get("arguments", "")),
                            "result": result,
                        }
                    )
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                continue

            if text_content:
                logger.info("Model returned final text")
                self.messages.append({"role": "assistant", "content": text_content})
                return {
                    "text": text_content,
                    "function_results": function_results or None,
                    "iterations": iteration + 1,
                }

            error_msg = "No tool calls and no text from model"
            logger.error(error_msg)
            return {
                "text": None,
                "error": error_msg,
                "function_results": function_results,
            }

        error_msg = f"Max iterations ({self.max_iterations}) reached in tool calling loop"
        logger.error(error_msg)
        return {
            "text": None,
            "error": error_msg,
            "function_results": function_results,
        }

    def invoke_no_tools(self, prompt: str, images: List[bytes]) -> Dict[str, Any]:
        """Single-turn call without tools. Appends user + assistant to history."""
        self._append_user(prompt, images)
        try:
            response = self.vlm_client.invoke(messages=self.messages, tools=None)
            msg = response.get("message") or {}
            text = msg.get("content") or ""
            if text:
                self.messages.append({"role": "assistant", "content": text})
            return {"text": text}
        except Exception as e:
            logger.error(f"VLM invoke_no_tools failed: {e}")
            return {"text": None, "error": str(e)}

    @staticmethod
    def _parse_args(raw: str) -> Dict[str, Any]:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse tool arguments as JSON: {raw[:200]!r}")
            return {}

    def _execute_tool_calls(
        self, tool_calls: List[Dict[str, Any]]
    ) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        def run_one(
            tc: Dict[str, Any],
        ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args = self._parse_args(fn.get("arguments", ""))
            logger.info(f"Tool call: {name}({args})")

            if name not in self.tools:
                error_msg = f"Unknown tool: {name}"
                logger.error(error_msg)
                return tc, {"error": error_msg, "status": "error"}

            try:
                result = self.tools[name](**args)
                logger.info(
                    f"Tool result: {name} -> "
                    f"status={result.get('status', '?')} | "
                    f"value='{result.get('value', '')}'"
                )
                return tc, result
            except Exception as e:
                error_msg = f"Tool {name} failed: {e}"
                logger.exception(error_msg)
                return tc, {"error": error_msg, "status": "error"}

        if self.max_tool_workers <= 1:
            return [run_one(tc) for tc in tool_calls]

        logger.info(
            f"Executing {len(tool_calls)} tool calls with {self.max_tool_workers} workers"
        )
        with ThreadPoolExecutor(max_workers=self.max_tool_workers) as pool:
            return list(pool.map(run_one, tool_calls))


__all__ = ["VLMAgent"]
