# Task 013: Resolve — OCR без VLM, page-based batching

## Что нужно сделать
Реализовать Level 1 (`resolve`) в `DocumentReader` без участия VLM: брать pending OCR entities из Registry, группировать по страницам, выполнять OCR напрямую через OCR client/tool path, и записывать результаты обратно в Registry.

## Зачем
Это ключевое архитектурное решение ADR-001: Resolve должен быть механическим и детерминированным этапом, независимым от VLM, с управляемым batching и частичной обработкой страниц.

## Acceptance Criteria
- [ ] AC-1: `DocumentReader.resolve(pages=...)` не вызывает VLM.
- [ ] AC-2: Pending entities выбираются из Registry и фильтруются по страницам.
- [ ] AC-3: Реализован page-based batching (группировка сущностей по `page_num`).
- [ ] AC-4: OCR результат записывается в Registry (`value`, `context`, `resolution=1`).
- [ ] AC-5: Частичные ошибки не ломают весь resolve; успешные сущности сохраняются.
- [ ] AC-6: Повторный resolve идемпотентен (не резолвит уже resolved записи).

## Контекст

**Релевантные части ADR (копия):**
- Resolve = OCR-only, VLM не участвует.
- DocumentReader итерирует OCR Registry и вызывает OCR Client напрямую.
- Батчинг и partial failure обрабатываются в Resolve-логике.
- Гранулярность уровней — на уровне страницы.

**Интерфейсы и контракты (полностью):**

```python
class DocumentReader:
    def resolve(self, pages: Optional[Iterable[int]] = None) -> None:
        """
        Level 1:
        - take pending entities from state manager
        - filter by pages
        - group by page_num
        - execute OCR for each entity
        - persist resolved values and page statuses
        """
        ...
```

```python
def group_registry_by_page(entries: list[OCRRegistryEntry]) -> dict[int, list[OCRRegistryEntry]]:
    ...
```

```python
def apply_ocr_result(
    entry: OCRRegistryEntry,
    value: str | None,
    context: str | None,
) -> OCRRegistryEntry:
    # return updated entry with resolution=1 when value available
    ...
```

**Границы задачи 013:**
- Делает: resolve orchestration + page batching + registry updates.
- Не делает: verify voting strategy (015), CLI subcommands (014), redesign scan prompts (012).

**Существующий код для reference:**
- `02_src/vlm_ocr_doc_reader/core/reader.py` - placeholder resolve from 011.
- `02_src/vlm_ocr_doc_reader/core/ocr_client.py` - OCR client.
- `02_src/vlm_ocr_doc_reader/core/ocr_tool.py` - existing OCR tool contract.
- `02_src/vlm_ocr_doc_reader/core/state.py` - pending/upsert/page status API.
