# Task 015: Verify — только интерфейс

## Что нужно сделать
Реализовать интерфейс Level 2 (`verify`) в `DocumentReader` без полноценной стратегии majority voting. Добавить контракты и базовые заглушки для последующих экспериментов.

## Зачем
Нужно зафиксировать API Verify в v0.2.0, чтобы CLI/API уже поддерживали точку расширения, даже если финальный алгоритм верификации будет позже.

## Acceptance Criteria
- [ ] AC-1: `DocumentReader.verify(pages=...)` реализован как публичный метод интерфейса.
- [ ] AC-2: Метод принимает страницы и корректно обрабатывает пустые/невалидные диапазоны.
- [ ] AC-3: Метод не ломает состояние и не мешает scan/resolve.
- [ ] AC-4: В state можно пометить подготовительные поля verify (`verified`, `confidence`) без сложного алгоритма.
- [ ] AC-5: Есть явные TODO/ограничения о том, что voting strategy отложена.

## Контекст

**Релевантные части ADR (копия):**
- Level 2 Verify: в текущей версии фиксируется только интерфейс.
- Реализация стратегии majority voting/confidence scoring откладывается.

**Интерфейсы и контракты (полностью):**

```python
class DocumentReader:
    def verify(self, pages: Optional[Iterable[int]] = None) -> None:
        """
        Level 2 interface only.
        No full majority-voting strategy in v0.2.0.
        """
        ...
```

```python
class VerifyResult(TypedDict, total=False):
    page_num: int
    entity_id: str
    verified: bool
    confidence: str
```

**Границы задачи 015:**
- Делает: стабильный API verify + безопасное поведение заглушки.
- Не делает: N-параллельные OCR-вызовы, voting algorithm.

**Существующий код для reference:**
- `02_src/vlm_ocr_doc_reader/core/reader.py` - текущий verify placeholder.
- `02_src/vlm_ocr_doc_reader/core/state.py` - поля `verified`, `confidence`.
