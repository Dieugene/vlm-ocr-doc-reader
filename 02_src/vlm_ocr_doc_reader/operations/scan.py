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
Ты анализируешь страницы документа и извлекаешь из них текст, иерархическую структуру и реестр precision-critical значений для последующей OCR-верификации. **НЕ вызывай ask_ocr** — это запрещено.

## НУМЕРАЦИЯ СТРАНИЦ
Каждая страница маркирована в верхнем левом углу: [G1], [G2], [G3] и т.д. Число из маркера — это page_num. Для каждой записи в ocr_registry указывай page_num ТОЙ страницы, на которой значение физически видно.

## ИЗВЛЕКАЕМЫЙ ТЕКСТ
Прочитай все переданные страницы и извлеки полный текст: заголовки, параграфы, списки, таблицы.

## СТРУКТУРА
Собери список заголовков с уровнем (1, 2, 3, ...) и номером страницы.

## OCR REGISTRY

Цель реестра — список конкретных precision-critical значений, которые имеет смысл перепроверить точечным OCR. Каждая запись должна проходить все три критерия:

1. **Атомарность.** Одно значение, которое можно выписать в одну строку: один URL, одно число, одна ФИО, одна дата. Запрещены групповые сущности: «найди все URL», «извлеки ссылки на источники [1]–[5]», «список идентификаторов». Если значений несколько — заведи несколько записей, по одной на каждое.
2. **Конкретность.** `prompt` должен описать значение так, чтобы другой человек мог найти его на странице, не видя её. Проверка: подставь текст `prompt` в голове к чужой странице — очевидно ли, что именно искать? Запрещены общие формулировки: «найди пример числа», «извлеки что-нибудь важное», «найди заголовок».
3. **Обоснованность.** `context` обязателен — 5–15 слов текста, которые реально присутствуют на странице рядом с искомым значением. Если не можешь сформулировать осмысленный context — значение не атомарно или ты его не видишь, пропусти.

Типы значений, которые обычно попадают в реестр: URL, email, идентификаторы (ОГРН, ИНН, КПП, ISIN, тикеры, номера документов, артикулы), полные ФИО, телефоны, почтовые адреса, номера счетов/IBAN/SWIFT, конкретные числовые пороги и лимиты из правил с их единицами измерения, полные даты. Это ориентир, не обязательный чек-лист — не добавляй значение «для галочки», если оно не удовлетворяет трём критериям выше.

Поля записи:
- `page_num` — по маркеру [G{N}]
- `prompt` — «найди <конкретное значение>» или «извлеки <конкретное значение>» с якорем на место
- `context` — 5–15 слов соседнего текста, реально присутствующих на странице
- `entity_id` — опционально

Лучше меньше, но точно. Если на странице нет ни одного значения, удовлетворяющего трём критериям — для этой страницы в registry ничего не добавляй.

## ФОРМАТ ОТВЕТА
Верни ТОЛЬКО валидный JSON, без пояснений вне JSON:

```json
{
  "text": "полный текст документа...",
  "structure": {"headers": [{"level": 1, "title": "...", "page": 1}]},
  "ocr_registry": [
    {"page_num": 2, "prompt": "извлеки минимальный процент free float по требованиям ASX после 2016 года", "context": "были введены требования 20% free float 19 февраля 2016 года"},
    {"page_num": 7, "prompt": "найди URL источника номер 17", "context": "17. https://www.hsfkramer.com/..."}
  ]
}
```

Порядок ключей: text, structure, ocr_registry.
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
