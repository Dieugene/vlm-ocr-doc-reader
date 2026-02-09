"""OCR Tool for agentic integration.

Provides tool definition and execution wrapper for OCR functionality.
The tool fetches page images from StateManager by page number,
so VLM Agent does not need to manage images itself.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from vlm_ocr_doc_reader.core.ocr_client import BaseOCRClient

if TYPE_CHECKING:
    from vlm_ocr_doc_reader.core.state import StateManager

logger = logging.getLogger(__name__)


class OCRTool:
    """OCR Tool - agentic wrapper for OCR execution.

    Used by VLM Agent through function calling mechanism.
    Provides tool definition for Gemini and execution handler.

    Fetches page images from StateManager internally -
    VLM Agent only needs to pass page_num and prompt.
    """

    def __init__(self, ocr_client: BaseOCRClient, state_manager: "StateManager") -> None:
        """Initialize OCR Tool.

        Args:
            ocr_client: OCR client instance (e.g., QwenOCRClient)
            state_manager: StateManager for fetching rendered page images
        """
        self.ocr_client = ocr_client
        self.state_manager = state_manager

    def to_tool_definition(self) -> Dict:
        """Generate tool definition for Gemini function calling.

        Returns:
            Tool definition in Gemini format
        """
        return {
            "function_declarations": [
                {
                    "name": "ask_ocr",
                    "description": (
                        "Точное извлечение ОДНОГО конкретного значения со страницы документа "
                        "через OCR. Используй ТОЛЬКО когда нужна посимвольная точность: "
                        "URL, email, номера (ОГРН, ИНН, КПП, телефон), ФИО, адреса, "
                        "коды документов. "
                        "НЕ используй для общего извлечения текста - это делай сам. "
                        "Один вызов = одно конкретное значение с одной страницы."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_num": {
                                "type": "integer",
                                "description": "Номер страницы документа (1-based)"
                            },
                            "prompt": {
                                "type": "string",
                                "description": (
                                    "Что именно извлечь. Будь конкретен: "
                                    "'найди URL источника 56', "
                                    "'извлеки ОГРН организации', "
                                    "'найди ФИО генерального директора'"
                                )
                            }
                        },
                        "required": ["page_num", "prompt"]
                    }
                }
            ]
        }

    def execute(self, page_num: int, prompt: str) -> Dict[str, Any]:
        """Execute OCR request.

        Fetches page image from StateManager by page_num,
        then sends it to OCR client for extraction.

        Args:
            page_num: Page number (1-based, as assigned by DocumentProcessor)
            prompt: Extraction prompt

        Returns:
            {
                "status": "ok" | "no_data" | "error",
                "value": str,
                "context": str,
                "explanation": str
            }
        """
        logger.info(f"OCR tool execution: page={page_num}, prompt='{prompt}'")

        # Fetch page image from storage
        image = self.state_manager.load_page(page_num)
        if image is None:
            error_msg = f"Page {page_num} not found in storage"
            logger.error(error_msg)
            return {
                "status": "error",
                "value": "",
                "context": "",
                "explanation": error_msg,
            }

        # Execute OCR via client
        result = self.ocr_client.extract(image, prompt, page_num)

        return result
