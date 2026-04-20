"""Scan operation - Level 0 (VLM-only), produces OCR Registry candidates."""

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional, TypedDict

from ..core.state import OCRRegistryEntry

logger = logging.getLogger(__name__)


class ScanPayload(TypedDict, total=False):
    """Payload from VLM scan response."""

    text: str
    structure: Dict[str, Any]
    ocr_registry: List[Dict[str, Any]]


SCAN_PROMPT_TEXT = """
Ты анализируешь страницы документа. Работай в два прохода. **НЕ вызывай ask_ocr** — это запрещено.

## НУМЕРАЦИЯ СТРАНИЦ
Каждая страница маркирована в верхнем левом углу: [G1], [G2], [G3] и т.д.
Эти маркеры — точные идентификаторы страниц. Используй число из маркировки как page_num.

## ПРОХОД 1 — Извлечение текста
Прочитай ВСЕ страницы и извлеки ПОЛНЫЙ текст: заголовки, параграфы, списки, таблицы.
Делай это сам, по изображениям.

## ПРОХОД 2 — Реестр OCR-сущностей
Просмотри извлечённый текст и составь список precision-critical данных, которые ты мог прочитать неточно:
- URL и email-адреса
- Идентификаторы: ОГРН, ИНН, КПП, СНИЛС, номера документов
- ФИО (точное написание)
- Телефоны, почтовые адреса
- Коды, артикулы, номера счетов

Для каждого такого значения укажи: page_num (по маркеру [G{N}]), prompt (что искать), context (ориентир рядом, опционально).

## Формат ответа
Верни ТОЛЬКО валидный JSON в формате:

```json
{
  "text": "полный текст документа...",
  "structure": {"headers": [{"level": 1, "title": "...", "page": 1}]},
  "ocr_registry": [
    {"page_num": 5, "prompt": "найди ОГРН организации", "context": "рядом с реквизитами"},
    {"page_num": 5, "entity_id": "ogrn_p5", "prompt": "извлеки ИНН"}
  ]
}
```

Порядок полей: text, structure, ocr_registry. entity_id в ocr_registry опционален.
"""


def _clean_json_fence(text: str) -> str:
    """Remove markdown JSON fence from text."""
    pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def parse_scan_response(text: Optional[str]) -> ScanPayload:
    """Parse VLM text response into ScanPayload.

    Args:
        text: Raw VLM response text

    Returns:
        ScanPayload with text, structure, ocr_registry. Empty on parse error.
    """
    if not text or not isinstance(text, str):
        return ScanPayload(text="", structure={"headers": []}, ocr_registry=[])

    cleaned = _clean_json_fence(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse scan response JSON: {e}")
        return ScanPayload(text="", structure={"headers": []}, ocr_registry=[])

    if not isinstance(data, dict):
        return ScanPayload(text="", structure={"headers": []}, ocr_registry=[])

    result_text = data.get("text")
    if result_text is None:
        result_text = ""
    elif not isinstance(result_text, str):
        result_text = str(result_text)

    result_structure = data.get("structure")
    if result_structure is None or not isinstance(result_structure, dict):
        result_structure = {"headers": []}
    elif "headers" not in result_structure or not isinstance(
        result_structure.get("headers"), list
    ):
        result_structure = {**result_structure, "headers": []}

    result_registry = data.get("ocr_registry")
    if result_registry is None or not isinstance(result_registry, list):
        result_registry = []

    return ScanPayload(
        text=result_text,
        structure=result_structure,
        ocr_registry=result_registry,
    )


def normalize_scan_registry(
    raw_entries: List[Dict[str, Any]],
    fallback_page: Optional[int] = None,
) -> List[OCRRegistryEntry]:
    """Convert raw VLM dicts to OCRRegistryEntry list.

    Args:
        raw_entries: List of dicts from VLM (page_num, entity_id?, prompt, context?)
        fallback_page: Page to use when page_num missing/invalid

    Returns:
        List of OCRRegistryEntry with resolution=0, value=None
    """
    result: List[OCRRegistryEntry] = []
    for raw in raw_entries or []:
        if not isinstance(raw, dict):
            continue

        try:
            page_num = int(raw.get("page_num", 0))
        except (TypeError, ValueError):
            page_num = 0
        if page_num < 1 and fallback_page is not None:
            page_num = fallback_page
        if page_num < 1:
            logger.warning("Skipping registry entry with invalid page_num")
            continue

        prompt = raw.get("prompt")
        if not prompt or not isinstance(prompt, str):
            logger.warning("Skipping registry entry without prompt")
            continue

        entity_id = raw.get("entity_id")
        if isinstance(entity_id, str):
            entity_id = entity_id.strip()
        if not entity_id:  # empty, whitespace, or non-string (C2)
            entity_id = (
                f"scan_{page_num}_"
                f"{hashlib.sha256(prompt.encode()).hexdigest()[:8]}"
            )

        context = raw.get("context")
        if context is not None and not isinstance(context, str):
            context = str(context)

        result.append(
            OCRRegistryEntry(
                page_num=page_num,
                entity_id=entity_id,
                prompt=prompt,
                resolution=0,
                value=None,
                context=context,
                verified=False,
                confidence=None,
            )
        )
    return result
