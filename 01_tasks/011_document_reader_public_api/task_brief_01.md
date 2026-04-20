# Task 011: DocumentReader (публичный API)

## Что нужно сделать
Реализовать `DocumentReader` как единственную публичную точку входа модуля для v0.2.0. `DocumentReader` должен управлять lifecycle документа, работать с состоянием из задач 009/010, предоставлять API `scan/resolve/verify/page_status/pending_entities/get_document_data` и подготавливать платформу для задач 012/013.

## Зачем
Без `DocumentReader` невозможно перейти от монолитного `FullDescriptionOperation` к архитектуре Resolution Levels. CLI v2 и внешняя интеграция должны опираться на единый API слоя чтения документа.

## Acceptance Criteria
- [ ] AC-1: Добавлен публичный класс `DocumentReader` с `open(pdf_path, workspace=None)`.
- [ ] AC-2: При `workspace=None` используется memory mode; при `workspace` - подхват существующего состояния по content hash.
- [ ] AC-3: Реализованы методы `scan`, `resolve`, `verify` с page-based параметрами (без полной логики задач 012/013, но с корректным контрактом).
- [ ] AC-4: Реализованы методы `page_status`, `pending_entities`, `get_document_data`.
- [ ] AC-5: `DocumentReader` использует `StateManager` и `DocumentProcessor`, не ломая существующий `FullDescriptionOperation`.
- [ ] AC-6: Публичный API экспортирован в пакете (`__init__.py`) и готов для CLI v2 (задача 014).

## Контекст

**Релевантные части ADR (копия):**

ADR-001, Решение 3 (DocumentReader):
- `DocumentReader` - единственная точка входа для CLI, программного API, интеграций.
- Внутренняя структура:
  - `state: DocumentState`
  - `processor: DocumentProcessor`
  - `operations: Dict[str, Operation]`
- Публичный интерфейс:
  - `open(pdf, workspace)`
  - `scan(pages=None)`
  - `resolve(pages=None)`
  - `verify(pages=None)`
  - `page_status()`
  - `pending_entities(page=None)`
  - `get_document_data()`

ADR-001, Решение 4 (Workspace):
- `open` определяет документ по content hash и поднимает состояние из workspace.
- `workspace=None` -> memory mode без персистенции.

ADR-001, Решение 5 (Resolve без VLM):
- На `resolve` VLM не участвует; используется OCR Registry и OCR Client напрямую.
- Детальная реализация batching будет в задаче 013.

**Интерфейсы и контракты (полностью):**

```python
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from vlm_ocr_doc_reader.schemas.document import DocumentData
from vlm_ocr_doc_reader.core.state import OCRRegistryEntry, PageResolution


class DocumentReader:
    @classmethod
    def open(cls, pdf_path: Path | str, workspace: Optional[Path | str] = None) -> "DocumentReader":
        """Open document in memory or workspace mode."""
        ...

    def scan(self, pages: Optional[Iterable[int]] = None) -> None:
        """Level 0. For 011: orchestration contract + state updates stub-ready for 012."""
        ...

    def resolve(self, pages: Optional[Iterable[int]] = None) -> None:
        """Level 1. For 011: API contract + delegation points ready for 013."""
        ...

    def verify(self, pages: Optional[Iterable[int]] = None) -> None:
        """Level 2. For 011: interface only (not full strategy)."""
        ...

    def page_status(self) -> Dict[int, PageResolution]:
        ...

    def pending_entities(self, page: Optional[int] = None) -> List[OCRRegistryEntry]:
        ...

    def get_document_data(self) -> DocumentData:
        """Return latest known document data for integration compatibility."""
        ...
```

```python
# Internal orchestration contracts for 011
class DocumentReader:
    _pdf_path: Path
    _workspace: Optional[Path]
    _state_manager: "StateManager"
    _processor: "DocumentProcessor"

    def _normalize_pages(self, pages: Optional[Iterable[int]]) -> List[int]: ...
    def _ensure_open(self) -> None: ...
```

**Границы задачи 011:**
- Делает: публичный класс + lifecycle + интеграция состояния/процессора + API контракты.
- Не делает: финальную реализацию scan-промптов (012), OCR resolve batching (013), CLI v2 (014), verify strategy (015).

**Критерии готовности модуля:**
- Можно открыть PDF через `DocumentReader.open(...)` в memory/workspace режимах.
- Можно получить `page_status` и `pending_entities` из состояния.
- Интерфейсы `scan/resolve/verify` присутствуют и корректно ограничены по scope.
- `get_document_data` возвращает совместимый `DocumentData`.
- Нет регрессии в текущем `FullDescriptionOperation` runtime.

**Существующий код для reference:**
- `02_src/vlm_ocr_doc_reader/core/state.py` - состояние и workspace backend (после 009/010).
- `02_src/vlm_ocr_doc_reader/core/processor.py` - текущий orchestrator.
- `02_src/vlm_ocr_doc_reader/operations/full_description.py` - источник текущего end-to-end поведения.
- `00_docs/architecture/decision_001_resolution_levels.md` - архитектурные требования.
- `00_docs/architecture/overview.md` - целевая схема.
