# Task 012: Scan — рефакторинг промптов, Registry из VLM

## Что нужно сделать
Реализовать Level 0 (`scan`) в `DocumentReader`: VLM читает страницы и возвращает структурированные данные (текст, структура, OCR Registry candidates), без OCR вызовов и без `ask_ocr` tool-calling.

## Зачем
`Scan` — первый проход по документу, который определяет, что именно нужно резолвить OCR на втором этапе. Без корректного Scan невозможно управлять точечным Resolve.

## Acceptance Criteria
- [ ] AC-1: `DocumentReader.scan(pages=...)` запускает VLM-only обработку и не вызывает OCR.
- [ ] AC-2: VLM-ответ содержит/трансформируется в OCR Registry entries (`entity_id`, `page_num`, `prompt` + поля состояния).
- [ ] AC-3: Результат scan обновляет `page_states` в `"scan"` и сохраняет OCR Registry в state.
- [ ] AC-4: Повторный scan по тем же страницам идемпотентен (upsert, без дублей).
- [ ] AC-5: `get_document_data()` отражает актуальный текст/structure после scan.
- [ ] AC-6: Вне scope: Resolve batching, Verify стратегия, CLI.

## Контекст

**Релевантные части ADR (копия):**
- Level 0 Scan: только VLM, OCR не вызывается.
- Побочный продукт Scan: OCR Registry как список сущностей для Level 1.
- Resolve/Verify выполняются отдельно.
- OCR Registry персистентен и обновляется инкрементально.

**Интерфейсы и контракты (полностью):**

```python
class DocumentReader:
    def scan(self, pages: Optional[Iterable[int]] = None) -> None:
        """
        Level 0:
        - read pages via VLM
        - extract text + headers/structure
        - produce OCR registry candidate entries
        - persist updates in StateManager
        """
        ...
```

```python
# Suggested internal payload contract (from VLM to scan parser)
class ScanPayload(TypedDict):
    text: str
    structure: dict
    ocr_registry: list[dict]  # each dict has page_num, entity_id?, prompt, context?
```

```python
# Minimum registry normalization in scan
def normalize_scan_registry(
    raw_entries: list[dict],
    fallback_page: int | None = None,
) -> list[OCRRegistryEntry]: ...
```

**Границы задачи 012:**
- Делает: scan prompt/response contract + state updates.
- Не делает: OCR execution (013), verify strategy (015), CLI wiring (014).

**Существующий код для reference:**
- `02_src/vlm_ocr_doc_reader/core/reader.py` - новый API orchestration (011).
- `02_src/vlm_ocr_doc_reader/operations/full_description.py` - старый монолитный prompt.
- `02_src/vlm_ocr_doc_reader/core/vlm_agent.py` - текущее взаимодействие с VLM.
- `02_src/vlm_ocr_doc_reader/core/state.py` - state + registry API.
