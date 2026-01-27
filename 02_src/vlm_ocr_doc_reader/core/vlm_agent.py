"""VLM Agent - Agentic entity with tool calling loop."""

import base64
import json
import logging
from typing import Dict, List, Any, Callable, Optional

from .vlm_client import BaseVLMClient

logger = logging.getLogger(__name__)


class VLMAgent:
    """VLM Agent - agentic entity with tool calling loop.

    Features:
    - System prompt management
    - Tool registration with handlers
    - Tool calling loop (max 10 iterations)
    - Message history tracking
    """

    def __init__(
        self,
        vlm_client: BaseVLMClient,
        max_iterations: int = 10
    ):
        """Initialize VLM Agent.

        Args:
            vlm_client: VLM client instance
            max_iterations: Maximum number of tool calling iterations
        """
        self.vlm_client = vlm_client
        self.max_iterations = max_iterations
        self.messages: List[Dict] = []
        self.tools: Dict[str, Callable] = {}  # tool_name → handler
        self.tool_definitions: List[Dict] = []  # Tool definitions for VLM

    def register_tool(self, tool_def: Dict, handler: Callable) -> None:
        """Register a tool with its handler.

        Args:
            tool_def: Tool definition for VLM (Gemini format)
                      Example:
                      {
                          "function_declarations": [{
                              "name": "tool_name",
                              "description": "...",
                              "parameters": {
                                  "type": "object",
                                  "properties": {...},
                                  "required": [...]
                              }
                          }]
                      }
            handler: Function to execute when tool is called
                     Receives tool args as dict, returns result dict
        """
        # Extract tool name
        tool_name = tool_def["function_declarations"][0]["name"]
        self.tools[tool_name] = handler
        self.tool_definitions.append(tool_def)
        logger.info(f"Registered tool: {tool_name}")

    def set_system_prompt(self, prompt: str) -> None:
        """Set system prompt.

        Clears previous message history and sets system prompt.

        Args:
            prompt: System prompt text
        """
        # Gemini uses user role for system prompt
        self.messages = [{"role": "user", "parts": [{"text": prompt}]}]
        logger.debug("System prompt set")

    def invoke(self, prompt: str, images: List[bytes]) -> Dict[str, Any]:
        """Execute request with tool calling loop.

        Algorithm:
        1. Add prompt to messages
        2. Call VLM with tools
        3. If there are function_calls:
           - Execute each function via handlers
           - Add results to messages
           - Repeat from step 2 (max max_iterations)
        4. If there is text - return final answer

        Args:
            prompt: User prompt
            images: List of images (PNG bytes)

        Returns:
            Final response after tool calling loop:
            {"text": str, "function_results": Optional[List[Dict]]}
        """
        # Build user message
        user_parts = [{"text": prompt}]

        # Add images to message
        for img_bytes in images:
            b64_data = base64.b64encode(img_bytes).decode('utf-8')
            user_parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": b64_data
                }
            })

        # Add user message to history
        self.messages.append({
            "role": "user",
            "parts": user_parts
        })

        # Tool calling loop
        function_results: List[Dict] = []

        for iteration in range(self.max_iterations):
            logger.info(f"Tool calling iteration {iteration + 1}/{self.max_iterations}")

            # Prepare tools for VLM
            tools = self.tool_definitions if self.tool_definitions else None

            # Convert messages to VLM format (only text for now)
            # For Gemini API, we need to build the contents array
            try:
                # Call VLM
                response = self.vlm_client.invoke(
                    prompt="",  # Empty prompt, messages already contain context
                    images=[],  # Images already in messages
                    tools=tools
                )
            except Exception as e:
                logger.error(f"VLM call failed: {e}")
                return {
                    "text": None,
                    "error": str(e),
                    "function_results": function_results
                }

            function_calls = response.get("function_calls")
            text_response = response.get("text")

            # Check if model wants to call functions
            if function_calls:
                logger.info(f"Model requested {len(function_calls)} function calls")

                # Add model's function call to messages
                model_parts = []
                for fc in function_calls:
                    model_parts.append({
                        "functionCall": {
                            "name": fc["name"],
                            "args": fc["args"]
                        }
                    })

                self.messages.append({
                    "role": "model",
                    "parts": model_parts
                })

                # Execute all function calls
                function_responses = []
                for fc in function_calls:
                    func_name = fc["name"]
                    func_args = fc.get("args", {})

                    logger.info(f"Executing tool: {func_name} with args: {func_args}")

                    if func_name not in self.tools:
                        error_msg = f"Unknown tool: {func_name}"
                        logger.error(error_msg)
                        result = {"error": error_msg, "status": "error"}
                    else:
                        try:
                            handler = self.tools[func_name]
                            result = handler(**func_args)
                            logger.info(f"Tool {func_name} executed successfully")
                        except Exception as e:
                            error_msg = f"Tool {func_name} failed: {e}"
                            logger.exception(error_msg)
                            result = {"error": error_msg, "status": "error"}

                    function_results.append({
                        "name": func_name,
                        "args": func_args,
                        "result": result
                    })

                    # Add function response to messages
                    function_responses.append({
                        "functionResponse": {
                            "name": func_name,
                            "response": result
                        }
                    })

                # Add function responses to messages
                self.messages.append({
                    "role": "user",
                    "parts": function_responses
                })

                # Continue loop - model will process function results

            elif text_response:
                # Model returned text response (final answer)
                logger.info("Model returned text response (final answer)")

                # Add model's response to messages
                self.messages.append({
                    "role": "model",
                    "parts": [{"text": text_response}]
                })

                return {
                    "text": text_response,
                    "function_results": function_results if function_results else None,
                    "iterations": iteration + 1
                }

            else:
                # No function calls and no text - error
                error_msg = "No function calls and no text from model"
                logger.error(error_msg)
                return {
                    "text": None,
                    "error": error_msg,
                    "function_results": function_results
                }

        # Max iterations reached
        error_msg = f"Max iterations ({self.max_iterations}) reached in tool calling loop"
        logger.error(error_msg)
        return {
            "text": None,
            "error": error_msg,
            "function_results": function_results
        }
