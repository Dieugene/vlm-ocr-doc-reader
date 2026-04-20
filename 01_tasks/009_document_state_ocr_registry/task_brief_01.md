# Task 009: DocumentState + OCR Registry

## Что нужно сделать
Реализовать новую модель состояния документа для Resolution Levels: `DocumentState` с `page_states`, `metadata` и персистентным `ocr_registry`. Подготовить API состояния для задач `011-013`, чтобы `scan` создавал реестр OCR-сущностей, а `resolve/verify` обновляли его без участия VLM.

## Зачем
Без явной модели состояния и OCR Registry невозможно разнести обработку на уровни `scan/resolve/verify` и выполнять инкрементальную обработку страниц. Это блокер для `DocumentReader` и всего критического пути v0.2.0.

## Acceptance Criteria
- [ ] AC-1: Введены структуры состояния документа: page-level статус, metadata, OCR Registry entries.
- [ ] AC-2: OCR Registry хранит поля: `page_num`, `entity_id`, `prompt`, `resolution`, `value`, `context`, `verified`, `confidence`.
- [ ] AC-3: Реализована загрузка/сохранение Registry и state через `StateManager` в виде сериализуемых структур.
- [ ] AC-4: Поддержана идемпотентность обновлений: повторная запись не дублирует сущности с тем же `entity_id`.
- [ ] AC-5: Добавлены методы чтения состояния, нужные для `DocumentReader` (`page_status`, pending entities по странице, обновление resolution).
- [ ] AC-6: Текущий код `DocumentProcessor` не ломается (обратная совместимость внутри v0.1 runtime до внедрения `DocumentReader`).

## Контекст

**Релевантные части ADR (копия):**

ADR-001, Решение 1 (Resolution Levels):
- Level 0 Scan: только VLM, OCR не вызывается; побочный продукт - OCR Registry.
- Level 1 Resolve: OCR вызывается по OCR Registry для выбранных страниц, VLM не участвует.
- Level 2 Verify: интерфейс в v0.2.0, стратегию откладываем.
- Гранулярность уровней - на уровне страницы.
- Идемпотентность: выполняется только то, что еще не сделано.

ADR-001, Решение 2 (OCR Registry):
- Персистентный артефакт в StateManager.
- Создается при Scan, заполняется при Resolve, верифицируется при Verify.
- Поля записи:
  - `page_num: int`
  - `entity_id: str`
  - `prompt: str`
  - `resolution: 0|1|2`
  - `value: str | null`
  - `context: str | null`
  - `verified: bool`
  - `confidence: str | null`

ADR-001, Последствия:
- Вводится `DocumentState` с `OCRRegistry` как персистентная модель знаний о документе.
- `StateManager` расширяется для хранения OCR Registry и page states.

**Интерфейсы и контракты (полностью):**

```python
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

ResolutionLevel = Literal[0, 1, 2]
PageResolution = Literal["none", "scan", "resolved", "verified"]


@dataclass
class OCRRegistryEntry:
    page_num: int
    entity_id: str
    prompt: str
    resolution: ResolutionLevel = 0
    value: Optional[str] = None
    context: Optional[str] = None
    verified: bool = False
    confidence: Optional[str] = None


@dataclass
class DocumentMetadata:
    source_path: Optional[str] = None
    content_hash: Optional[str] = None
    pages_total: int = 0
    created_at: Optional[str] = None


@dataclass
class DocumentStateV2:
    page_states: Dict[int, PageResolution] = field(default_factory=dict)
    ocr_registry: List[OCRRegistryEntry] = field(default_factory=list)
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)


class StateManager:
    def save_document_state(self, state: DocumentStateV2) -> None: ...
    def load_document_state(self) -> DocumentStateV2: ...
    def save_ocr_registry(self, entries: List[OCRRegistryEntry]) -> None: ...
    def load_ocr_registry(self) -> List[OCRRegistryEntry]: ...
    def upsert_ocr_entries(self, entries: List[OCRRegistryEntry]) -> int: ...
    def pending_entities(self, page_num: Optional[int] = None) -> List[OCRRegistryEntry]: ...
    def set_page_resolution(self, page_num: int, status: PageResolution) -> None: ...
    def page_status(self) -> Dict[int, PageResolution]: ...
```

**Границы задачи 009:**
- Делает: модели состояния + API состояния/реестра + сериализация.
- Не делает: `DocumentReader`, orchestration scan/resolve/verify, CLI.

**Критерии готовности модуля:**
- Состояние документа сериализуется/десериализуется без потери полей OCR Registry.
- Есть операция upsert по `entity_id` (идемпотентность).
- Есть чтение pending entities по странице и по всему документу.
- Есть обновление page-level resolution статусов.
- API готов для подключения в задаче 011 без изменения контрактов 009.

**Существующий код для reference:**
- `02_src/vlm_ocr_doc_reader/core/state.py` - текущие `DocumentState`, `StateManager`, `DiskStorage`.
- `02_src/vlm_ocr_doc_reader/core/processor.py` - текущее создание `StateManager`.
- `00_docs/architecture/decision_001_resolution_levels.md` - архитектурный источник требований.
- `00_docs/architecture/overview.md` - целевая схема v0.2.0.
