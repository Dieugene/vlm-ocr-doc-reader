"""Unit tests for VLM Agent."""

from unittest.mock import Mock, patch
import pytest

from vlm_ocr_doc_reader.core.vlm_agent import VLMAgent
from vlm_ocr_doc_reader.core.vlm_client import BaseVLMClient


@pytest.fixture
def mock_vlm_client():
    """Create mock VLM client."""
    client = Mock(spec=BaseVLMClient)

    # Default: return text response (no tools)
    client.invoke.return_value = {
        "text": "Final answer",
        "raw": {}
    }

    return client


@pytest.fixture
def mock_images():
    """Create mock PNG images."""
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"


class TestVLMAgentToolRegistration:
    """Test tool registration."""

    def test_register_tool(self, mock_vlm_client):
        """Test tool registration."""
        agent = VLMAgent(mock_vlm_client)

        tool_def = {
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
        }

        handler = Mock(return_value={"result": "ok"})
        agent.register_tool(tool_def, handler)

        assert "test_tool" in agent.tools
        assert agent.tools["test_tool"] == handler
        assert tool_def in agent.tool_definitions

    def test_set_system_prompt(self, mock_vlm_client):
        """Test setting system prompt."""
        agent = VLMAgent(mock_vlm_client)

        agent.set_system_prompt("You are a helpful assistant")

        assert len(agent.messages) == 1
        assert agent.messages[0]["role"] == "user"
        assert agent.messages[0]["parts"][0]["text"] == "You are a helpful assistant"


class TestVLMAgentInvoke:
    """Test invoke method with tool calling loop."""

    def test_invoke_one_iteration_no_tools(self, mock_vlm_client):
        """Test invoke with immediate text response (1 iteration)."""
        agent = VLMAgent(mock_vlm_client)

        result = agent.invoke("Test prompt", [])

        assert result["text"] == "Final answer"
        assert result["iterations"] == 1
        assert mock_vlm_client.invoke.called

    def test_invoke_two_iterations_with_tool(self, mock_vlm_client):
        """Test invoke with tool calling (2 iterations)."""
        agent = VLMAgent(mock_vlm_client)

        # Register tool
        tool_def = {
            "function_declarations": [{
                "name": "ask_ocr",
                "description": "Ask OCR",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "page_num": {"type": "integer"},
                        "prompt": {"type": "string"}
                    },
                    "required": ["page_num", "prompt"]
                }
            }]
        }

        handler = Mock(return_value={"status": "success", "value": "12345"})
        agent.register_tool(tool_def, handler)

        # Mock VLM responses:
        # 1. First call: request tool call
        # 2. Second call: return text
        mock_vlm_client.invoke.side_effect = [
            {
                "function_calls": [
                    {"name": "ask_ocr", "args": {"page_num": 1, "prompt": "extract"}}
                ],
                "text": None
            },
            {
                "function_calls": None,
                "text": "The value is 12345"
            }
        ]

        result = agent.invoke("Extract data", [])

        # Should have called VLM twice
        assert mock_vlm_client.invoke.call_count == 2

        # Tool should have been executed
        handler.assert_called_once_with(page_num=1, prompt="extract")

        # Final result
        assert result["text"] == "The value is 12345"
        assert result["iterations"] == 2
        assert len(result["function_results"]) == 1

    def test_invoke_ten_iterations(self, mock_vlm_client):
        """Test invoke with 10 tool calling iterations."""
        agent = VLMAgent(mock_vlm_client, max_iterations=10)

        # Register tool
        tool_def = {
            "function_declarations": [{
                "name": "step",
                "description": "Step function",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "n": {"type": "integer"}
                    }
                }
            }]
        }

        handler = Mock(return_value={"step": "done"})
        agent.register_tool(tool_def, handler)

        # Mock VLM responses: 9 tool calls, then final text
        responses = []
        for i in range(9):
            responses.append({
                "function_calls": [{"name": "step", "args": {"n": i}}],
                "text": None
            })
        responses.append({
            "function_calls": None,
            "text": "Completed after 9 steps"
        })

        mock_vlm_client.invoke.side_effect = responses

        result = agent.invoke("Execute steps", [])

        # Should have completed all 10 iterations
        assert mock_vlm_client.invoke.call_count == 10
        assert result["iterations"] == 10
        assert result["text"] == "Completed after 9 steps"
        assert len(result["function_results"]) == 9

    def test_invoke_max_iterations_exceeded(self, mock_vlm_client):
        """Test that agent stops after max_iterations."""
        agent = VLMAgent(mock_vlm_client, max_iterations=3)

        tool_def = {
            "function_declarations": [{
                "name": "loop",
                "description": "Loop forever",
                "parameters": {}
            }]
        }

        handler = Mock(return_value={"continue": True})
        agent.register_tool(tool_def, handler)

        # Mock VLM to always request tool call
        mock_vlm_client.invoke.return_value = {
            "function_calls": [{"name": "loop", "args": {}}],
            "text": None
        }

        result = agent.invoke("Loop", [])

        # Should have stopped after max_iterations
        assert mock_vlm_client.invoke.call_count == 3
        assert result["text"] is None
        assert "error" in result
        assert "Max iterations" in result["error"]

    def test_invoke_tool_error_handling(self, mock_vlm_client):
        """Test that tool errors are handled gracefully."""
        agent = VLMAgent(mock_vlm_client)

        tool_def = {
            "function_declarations": [{
                "name": "failing_tool",
                "description": "Tool that fails",
                "parameters": {}
            }]
        }

        # Handler raises exception
        handler = Mock(side_effect=ValueError("Tool failed"))
        agent.register_tool(tool_def, handler)

        # Mock VLM responses
        mock_vlm_client.invoke.side_effect = [
            {
                "function_calls": [{"name": "failing_tool", "args": {}}],
                "text": None
            },
            {
                "function_calls": None,
                "text": "Tool failed, continuing"
            }
        ]

        result = agent.invoke("Test", [])

        # Should handle error and continue
        assert mock_vlm_client.invoke.call_count == 2
        assert result["text"] == "Tool failed, continuing"

        # Tool result should contain error
        func_result = result["function_results"][0]
        assert func_result["result"]["status"] == "error"
        assert "Tool failed" in func_result["result"]["error"]

    def test_invoke_unknown_tool(self, mock_vlm_client):
        """Test that unknown tool returns error."""
        agent = VLMAgent(mock_vlm_client)

        # Mock VLM to call unknown tool
        mock_vlm_client.invoke.side_effect = [
            {
                "function_calls": [{"name": "unknown_tool", "args": {}}],
                "text": None
            },
            {
                "function_calls": None,
                "text": "Tool not found"
            }
        ]

        result = agent.invoke("Test", [])

        # Should handle gracefully
        assert result["text"] == "Tool not found"
        func_result = result["function_results"][0]
        assert func_result["result"]["status"] == "error"
        assert "Unknown tool" in func_result["result"]["error"]

    def test_invoke_no_response_error(self, mock_vlm_client):
        """Test error handling when VLM returns neither calls nor text."""
        agent = VLMAgent(mock_vlm_client)

        # Mock VLM returns empty response
        mock_vlm_client.invoke.return_value = {
            "function_calls": None,
            "text": None
        }

        result = agent.invoke("Test", [])

        assert result["text"] is None
        assert "error" in result
        assert "No function calls" in result["error"]
