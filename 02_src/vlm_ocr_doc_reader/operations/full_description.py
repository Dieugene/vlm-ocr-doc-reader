"""Full description operation - contract with project 07_agentic-doc-processing."""

import json
import logging
import re
from typing import Optional, List, Any, Dict

from .base import BaseOperation
from ..schemas.document import DocumentData, HeaderInfo

logger = logging.getLogger(__name__)

# VLM prompts
PROMPT_TEXT = """
Ты анализируешь страницы документа. Работай в три прохода.

## НУМЕРАЦИЯ СТРАНИЦ
Каждая страница маркирована в верхнем левом углу: [G1], [G2], [G3] и т.д.
Эти маркеры — точные идентификаторы страниц.
При вызове ask_ocr используй ЧИСЛО ИЗ МАРКИРОВКИ как page_num.
Пример: видишь маркер [G5] -> вызывай ask_ocr(page_num=5, ...).

## ПРОХОД 1 — Извлечение текста
Прочитай ВСЕ страницы и извлеки ПОЛНЫЙ текст: заголовки, параграфы, списки, таблицы.
Делай это сам, по изображениям — НЕ вызывай OCR для общего текста.

## ПРОХОД 2 — Реестр OCR-сущностей
Просмотри извлечённый текст и составь список precision-critical данных, которые ты мог прочитать неточно:
- URL и email-адреса
- Идентификаторы: ОГРН, ИНН, КПП, СНИЛС, номера документов
- ФИО (точное написание)
- Телефоны, почтовые адреса
- Коды, артикулы, номера счетов

Для каждого такого значения запомни: на какой оно странице (по маркеру [G{N}]) и какой ориентир рядом (текст до/после).

## ПРОХОД 3 — OCR-верификация
Вызови ask_ocr для КАЖДОГО значения из реестра, группируя по страницам.
Формат вызова: ask_ocr(page_num=N, prompt="найди <что именно>, ориентир: <текст рядом>")

После получения OCR-результатов — ПОДСТАВЬ их вместо своих значений.
OCR-результат ВСЕГДА в приоритете над твоим прочтением.

## Формат финального ответа
Верни ПОЛНЫЙ текст документа в plain text, сохраняя структуру (заголовки, списки, абзацы).
Все precision-critical значения должны быть из OCR.
"""

PROMPT_STRUCTURE = """
Проанализируй эти страницы и опиши иерархическую структуру документа.
Для каждого заголовка укажи:
- Уровень (1 для основных, 2 для подзаголовков, и т.д.)
- Текст заголовка
- Номер страницы

Формат ответа (JSON):
{
  "headers": [
    {"level": 1, "title": "1. Введение", "page": 1},
    {"level": 2, "title": "1.1. Актуальность", "page": 2}
  ]
}
"""


class FullDescriptionOperation(BaseOperation):
    """Full document description operation - contract with project 07.

    This operation extracts:
    - Full text from document
    - Hierarchical structure (headers with levels)
    - Tables (empty in v0.1.0, will be implemented in future versions)

    Priority: P0 for v0.1.0
    """

    def __init__(
        self,
        processor: Any,
        render_dpi: Optional[int] = None
    ):
        """Initialize full description operation.

        Args:
            processor: DocumentProcessor instance
            render_dpi: Override DPI for rendering (optional)
        """
        super().__init__(processor)
        self.render_dpi = render_dpi

    def execute(
        self,
        pages: Optional[List[int]] = None
    ) -> DocumentData:
        """Execute full description operation.

        Args:
            pages: Specific page indices to process (None = all pages)

        Returns:
            DocumentData with text, structure, and empty tables list
        """
        logger.info("Starting FullDescriptionOperation")

        # Filter pages if specified
        all_pages = self._get_all_pages()
        filtered_pages = self._filter_pages(all_pages, pages)

        logger.info(
            f"Processing {len(filtered_pages)} pages "
            f"(filtered from {len(all_pages)} total)"
        )

        # Extract images
        images = self._extract_images(filtered_pages)

        # Call VLM for text extraction (pass page info for context)
        logger.info("Calling VLM for text extraction")
        text = self._extract_text(filtered_pages, images)

        # Call VLM for structure extraction (pass page info for context)
        logger.info("Calling VLM for structure extraction")
        structure = self._extract_structure(filtered_pages, images)

        # Return DocumentData (tables empty in v0.1.0)
        result = DocumentData(
            text=text,
            structure=structure,
            tables=[]
        )

        logger.info("FullDescriptionOperation completed successfully")
        return result

    def _get_all_pages(self) -> List[Any]:
        """Get all pages from processor.

        Returns:
            List of pages (PageInfo or bytes, depending on processor implementation)
        """
        # Access processor.pages - contract from DocumentProcessor
        if hasattr(self.processor, 'pages'):
            return self.processor.pages
        # Fallback: try to render if processor has render method
        elif hasattr(self.processor, '_render_pdf'):
            return self.processor._render_pdf(dpi=self.render_dpi or 150)
        else:
            raise RuntimeError(
                "DocumentProcessor must have 'pages' attribute or '_render_pdf' method"
            )

    def _filter_pages(
        self,
        all_pages: List[Any],
        page_indices: Optional[List[int]]
    ) -> List[Any]:
        """Filter pages by indices.

        Args:
            all_pages: All available pages
            page_indices: Page indices to filter (1-based, None = all)

        Returns:
            Filtered list of pages
        """
        if page_indices is None:
            return all_pages

        # Convert to 0-based if PageInfo objects
        if all_pages and hasattr(all_pages[0], 'index'):
            # PageInfo objects - filter by .index attribute
            filtered = [p for p in all_pages if p.index in page_indices]
            # Sort by index
            filtered.sort(key=lambda p: p.index)
            return filtered
        else:
            # Assume list is indexed 0-based, filter by position
            # Convert 1-based indices to 0-based
            indices_0based = [i - 1 for i in page_indices if 1 <= i <= len(all_pages)]
            return [all_pages[i] for i in sorted(indices_0based)]

    def _extract_images(self, pages: List[Any]) -> List[bytes]:
        """Extract image bytes from pages.

        Args:
            pages: List of pages (PageInfo or bytes)

        Returns:
            List of image bytes
        """
        images = []
        for page in pages:
            if hasattr(page, 'image'):
                # PageInfo object
                images.append(page.image)
            elif isinstance(page, bytes):
                # Raw image bytes
                images.append(page)
            else:
                raise ValueError(f"Unsupported page type: {type(page)}")
        return images

    def _extract_text(self, pages: List[Any], images: List[bytes]) -> str:
        """Extract text from images using VLM.

        Args:
            pages: List of pages (PageInfo objects with page numbers)
            images: List of page images

        Returns:
            Extracted text
        """
        # Build prompt with page information
        page_info = ""
        if pages and hasattr(pages[0], 'index'):
            page_numbers = [p.index for p in pages]
            page_info = f"\nНомера страниц: {page_numbers}\nИспользуй OCR tool указывая точный номер страницы."

        enhanced_prompt = PROMPT_TEXT + page_info

        # Call VLM agent via processor
        vlm_agent = self._get_vlm_agent()
        response = vlm_agent.invoke(enhanced_prompt, images)

        # Extract text from response
        if isinstance(response, dict):
            return response.get("text", "")
        elif isinstance(response, str):
            return response
        else:
            logger.warning(f"Unexpected VLM response type: {type(response)}")
            return str(response)

    def _extract_structure(self, pages: List[Any], images: List[bytes]) -> Dict[str, Any]:
        """Extract document structure using VLM.

        Args:
            pages: List of pages (PageInfo objects with page numbers)
            images: List of page images

        Returns:
            Structure dict with "headers" key
        """
        try:
            # Build prompt with page information
            page_info = ""
            if pages and hasattr(pages[0], 'index'):
                page_numbers = [p.index for p in pages]
                page_info = f"\nНомера страниц: {page_numbers}"

            enhanced_prompt = PROMPT_STRUCTURE + page_info

            # Call VLM agent via processor
            vlm_agent = self._get_vlm_agent()
            response = vlm_agent.invoke(enhanced_prompt, images)

            # Parse JSON response
            text = self._extract_response_text(response)

            if not text:
                logger.warning("Empty response from VLM for structure extraction")
                return {"headers": []}

            structure = self._parse_structure_response(text)

            logger.info(
                f"Parsed structure: {len(structure.get('headers', []))} headers found"
            )

            return structure
        except Exception as e:
            logger.error(f"Error extracting structure: {e}")
            return {"headers": []}

    def _get_vlm_agent(self) -> Any:
        """Get VLM agent from processor.

        Returns:
            VLM agent with invoke(prompt, images) method
        """
        if hasattr(self.processor, 'vlm_agent'):
            return self.processor.vlm_agent
        else:
            raise RuntimeError(
                "DocumentProcessor must have 'vlm_agent' attribute"
            )

    def _extract_response_text(self, response: Any) -> str:
        """Extract text from VLM response.

        Args:
            response: VLM response (dict or str)

        Returns:
            Response text
        """
        if isinstance(response, dict):
            return response.get("text", "")
        elif isinstance(response, str):
            return response
        else:
            return str(response)

    def _parse_structure_response(self, text: str) -> Dict[str, Any]:
        """Parse structure response from VLM.

        Args:
            text: JSON text from VLM

        Returns:
            Parsed structure dict with "headers" key
        """
        # Clean markdown fences if present
        cleaned = self._clean_json_fence(text)

        try:
            structure = json.loads(cleaned)

            # Validate structure
            if not isinstance(structure, dict):
                logger.warning(f"Structure is not a dict: {type(structure)}")
                return {"headers": []}

            if "headers" not in structure:
                logger.warning("Structure missing 'headers' key")
                return {"headers": []}

            if not isinstance(structure["headers"], list):
                logger.warning(f"'headers' is not a list: {type(structure['headers'])}")
                return {"headers": []}

            # Validate headers
            valid_headers = []
            for h in structure["headers"]:
                if isinstance(h, dict) and all(k in h for k in ["level", "title", "page"]):
                    valid_headers.append(h)
                else:
                    logger.warning(f"Invalid header format: {h}")

            structure["headers"] = valid_headers
            return structure

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse structure JSON: {e}")
            logger.debug(f"Raw text: {text[:500]}")
            return {"headers": []}

    def _clean_json_fence(self, text: str) -> str:
        """Remove markdown JSON fence from text.

        Args:
            text: Text that may contain ```json ... ```

        Returns:
            Cleaned text
        """
        # Remove ```json and ``` fences
        pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
        match = re.search(pattern, text, re.DOTALL)

        if match:
            return match.group(1).strip()

        # No fence found, return as is
        return text.strip()
