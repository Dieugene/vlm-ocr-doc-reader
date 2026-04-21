"""BaseVLMClient — provider-neutral contract for VLM calls.

Conversation history and tool-calling use an OpenAI-compatible message/tool
schema as internal representation:

    messages = [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "text"}  # or
        {"role": "user", "content": [
            {"type": "text", "text": "..."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
        ]},
        {"role": "assistant",
         "content": None,
         "tool_calls": [
             {"id": "call_0", "type": "function",
              "function": {"name": "ask_ocr",
                           "arguments": "{\"page_num\":1,\"prompt\":\"...\"}"}},
         ]},
        {"role": "tool", "tool_call_id": "call_0", "content": "<serialized result>"},
    ]

    tools = [
        {"type": "function",
         "function": {"name": "...", "description": "...",
                      "parameters": {<json-schema>}}},
    ]

This is an internal contract. Providers that don't speak OpenAI natively
translate to/from their own format inside their client implementation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class BaseVLMClient:
    """Provider-neutral VLM client contract.

    invoke() is the only public method. It accepts an OpenAI-style messages
    list and optional tools, returns a dict with the assistant message and
    optional usage info.
    """

    def invoke(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Send conversation to VLM, return assistant response.

        Args:
            messages: OpenAI-style conversation history
            tools: Optional OpenAI-style tool definitions

        Returns:
            {
                "message": {
                    "role": "assistant",
                    "content": str | None,
                    "tool_calls": list | None,
                },
                "usage": dict | None,
            }
        """
        raise NotImplementedError
