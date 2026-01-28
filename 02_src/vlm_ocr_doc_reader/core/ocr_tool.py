"""OCR Tool for agentic integration.

Provides tool definition and execution wrapper for OCR functionality.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from vlm_ocr_doc_reader.core.ocr_client import BaseOCRClient
from vlm_ocr_doc_reader.utils.normalization import normalize_ocr_digits

logger = logging.getLogger(__name__)


class OCRTool:
    """OCR Tool - agentic wrapper for OCR execution.

    Used by VLM Agent through function calling mechanism.
    Provides tool definition for Gemini and execution handler.
    """

    def __init__(self, ocr_client: BaseOCRClient) -> None:
        """Initialize OCR Tool.

        Args:
            ocr_client: OCR client instance (e.g., QwenOCRClient)
        """
        self.ocr_client = ocr_client

    def to_tool_definition(self) -> Dict:
        """Generate tool definition for Gemini function calling.

        Returns:
            Tool definition in Gemini format
        """
        return {
            "function_declarations": [
                {
                    "name": "ask_ocr",
                    "description": "Извлечь данные с изображения через OCR",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_num": {
                                "type": "integer",
                                "description": "Номер страницы для извлечения"
                            },
                            "prompt": {
                                "type": "string",
                                "description": "Запрос для извлечения данных (например, 'найди ОГРН')"
                            }
                        },
                        "required": ["page_num", "prompt"]
                    }
                }
            ]
        }

    def execute(self, page_num: int, prompt: str, image: bytes) -> Dict[str, Any]:
        """Execute OCR request with post-processing.

        Args:
            page_num: Page number
            prompt: Extraction prompt
            image: Image bytes (PNG format)

        Returns:
            {
                "status": "ok" | "no_data" | "error",
                "value": str,
                "value_normalized": str,  # Post-processed digits
                "context": str,
                "explanation": str
            }
        """
        logger.info(f"OCR tool execution: page={page_num}, prompt='{prompt}'")

        # Execute OCR via client
        result = self.ocr_client.extract(image, prompt, page_num)

        # Post-processing for numeric fields
        if result["status"] == "ok":
            normalized = normalize_ocr_digits(result["value"])
            if normalized:
                result["value_normalized"] = normalized
                logger.debug(
                    f"OCR normalized: page={page_num}, raw='{result['value']}', "
                    f"normalized='{normalized}'"
                )
            else:
                # Normalization failed - treat as no data
                result["status"] = "no_data"
                result["value_normalized"] = None
                logger.warning(
                    f"OCR normalization failed: page={page_num}, raw='{result['value']}'"
                )

        return result
