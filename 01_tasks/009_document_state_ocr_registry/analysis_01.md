# Техническое задание: DocumentState + OCR Registry (Задача 009)

## 1. Анализ задачи

Ввести модель состояния документа для Resolution Levels (ADR-001): `DocumentState` с `page_states`, `metadata` и персистентным `OCRRegistry`. Подготовить API для задач 011–013: `scan` создаёт реестр OCR-сущностей, `resolve`/`verify` обновляют его без VLM. Без явной модели и Registry невозможна поэтапная обработка scan/resolve/verify.

---

## 2. Scope

### In-scope
- Структуры данных: `OCRRegistryEntry`, `DocumentMetadata`, `DocumentState` (новая модель)
- API StateManager: save/load document state, save/load registry, upsert, pending_entities, page_status, set_page_resolution
- Сериализация/десериализация в JSON через StorageBackend
- Расширение DiskStorage для ключей `document_state/state` и `ocr_registry/registry`
- Идемпотентность upsert по `entity_id`
- Обратная совместимость: DocumentProcessor, OCRTool, существующие тесты продолжают работать

### Out-of-scope
- DocumentReader, orchestration scan/resolve/verify
- CLI v2, Workspace (задача 010)
- Реализация стратегии Verify (Level 2)
- Новые тестовые модули

---

## 3. Текущее состояние

### Релевантный код

**`02_src/vlm_ocr_doc_reader/core/state.py`:**
- `DocumentState` — pages (Dict[int, bytes]), vlm_responses, operation_results. Используется StateManager для кэша страниц и результатов.
- `StateManager` — save_page, load_page, save_vlm_response, save_operation_result, save_state, load_state. Инициализируется с `DocumentState()`.
- `StorageBackend` (Protocol), `MemoryStorage`, `DiskStorage` — save/load по ключу.

**`DiskStorage._get_file_path(key)`:**
- Поддерживает `pages/N`, `vlm_responses/name`, `results/name`. Формат ключа: `type/name`.
- Не поддерживает document_state и ocr_registry.

**`DocumentProcessor`** создаёт StateManager с MemoryStorage или DiskStorage, передаёт его в OCRTool. OCRTool вызывает `state_manager.load_page(page_num)`.

**Экспорт:** `core/__init__.py` экспортирует DocumentState, StateManager. Тесты `test_state.py` используют DocumentState, StateManager, DiskStorage.

---

## 4. Предлагаемое решение

### 4.1. Общий подход

Добавить новую модель состояния (Resolution Levels) рядом с существующей, не заменяя её. StateManager получает атрибут для resolution-state и новые методы. DiskStorage расширяется двумя ключами. Сериализация — JSON, dataclasses через `asdict` и фабрику из dict.

### 4.2. Структуры данных

#### OCRRegistryEntry
```python
@dataclass
class OCRRegistryEntry:
    page_num: int
    entity_id: str
    prompt: str
    resolution: Literal[0, 1, 2] = 0
    value: Optional[str] = None
    context: Optional[str] = None
    verified: bool = False
    confidence: Optional[str] = None
```
- `entity_id` — уникальный идентификатор сущности (ключ для upsert).
- `resolution` — текущий уровень: 0=scan, 1=resolved, 2=verified.
- `value`, `context` — заполняются при Resolve.
- `verified`, `confidence` — для Verify (Level 2).

#### DocumentMetadata
```python
@dataclass
class DocumentMetadata:
    source_path: Optional[str] = None
    content_hash: Optional[str] = None
    pages_total: int = 0
    created_at: Optional[str] = None  # ISO 8601
```

#### DocumentState (новая модель)
```python
PageResolution = Literal["none", "scan", "resolved", "verified"]

@dataclass
class DocumentState:
    page_states: Dict[int, PageResolution]  # page_num -> статус
    ocr_registry: List[OCRRegistryEntry]
    metadata: DocumentMetadata
```
Имя `DocumentState` конфликтует с существующим. В коде использовать `ResolutionDocumentState` (внутреннее имя), в публичном API — `DocumentState` после задачи 011. Для задачи 009 — `ResolutionDocumentState` в `state.py`, экспорт как `ResolutionDocumentState` (или оставить `DocumentState` и переименовать старый в `ProcessingCache` — см. раздел 4.5).

**Решение по именованию:** Оставить существующий `DocumentState` без изменений (AC-6). Новую модель назвать `ResolutionDocumentState` (в коде; в task_brief — DocumentStateV2, в ADR — DocumentState). Экспортировать в `core/__init__.py` для использования в задаче 011.

#### Сериализация
- `OCRRegistryEntry` → dict: `dataclasses.asdict(entry)`.
- dict → `OCRRegistryEntry`: фабрика `OCRRegistryEntry(**d)` с обработкой отсутствующих полей (defaults).
- `DocumentMetadata`, `ResolutionDocumentState` — аналогично.
- `page_states`: ключи int в JSON как строки — при загрузке конвертировать `int(k)`.

### 4.3. Контракты StateManager

Новые методы (дополняют существующие):

| Метод | Сигнатура | Поведение |
|-------|-----------|-----------|
| save_document_state | `(state: ResolutionDocumentState) -> None` | Сериализует и сохраняет через storage. Ключ: `document_state/state`. |
| load_document_state | `() -> ResolutionDocumentState` | Загружает из storage. Если нет — возвращает пустое состояние (page_states={}, ocr_registry=[], metadata=DocumentMetadata()). |
| save_ocr_registry | `(entries: List[OCRRegistryEntry]) -> None` | Сохраняет весь список. Ключ: `ocr_registry/registry`. |
| load_ocr_registry | `() -> List[OCRRegistryEntry]` | Загружает список. Если нет — `[]`. |
| upsert_ocr_entries | `(entries: List[OCRRegistryEntry]) -> int` | Merge по entity_id: если есть — обновить (value, context, resolution, verified, confidence), иначе добавить. Сохранить в storage. Вернуть число изменённых/добавленных записей. |
| pending_entities | `(page_num: Optional[int] = None) -> List[OCRRegistryEntry]` | Фильтр: resolution < 1 (ещё не resolved). Если page_num задан — только для этой страницы. |
| set_page_resolution | `(page_num: int, status: PageResolution) -> None` | Обновить page_states[page_num], сохранить document_state. |
| page_status | `() -> Dict[int, PageResolution]` | Вернуть копию page_states. |

**Внутреннее состояние StateManager:**
- Добавить `self._resolution_state: ResolutionDocumentState` — кэш в памяти.
- При `load_document_state()` — заполнять `_resolution_state`.
- При `save_document_state()` — сохранять `_resolution_state` и обновлять кэш.
- `upsert_ocr_entries` — merge в `_resolution_state.ocr_registry`, затем save.

### 4.4. Ключевые алгоритмы

**Upsert по entity_id:**
1. Загрузить текущий registry (из `_resolution_state` или load).
2. Построить dict `entity_id -> index` для быстрого поиска.
3. Для каждой входящей записи: если entity_id есть — обновить поля (value, context, resolution, verified, confidence), иначе append.
4. Сохранить через save_ocr_registry, обновить _resolution_state.

**pending_entities:**
1. Взять ocr_registry из _resolution_state (или load).
2. Фильтр: `e.resolution < 1`.
3. Если page_num задан — дополнительно `e.page_num == page_num`.
4. Вернуть список (копию).

**Сериализация page_states:**
- JSON не поддерживает int как ключи dict — использовать строковые ключи при dump.
- При load — конвертировать ключи в int.

### 4.5. Изменения в существующем коде

#### `02_src/vlm_ocr_doc_reader/core/state.py`

1. **Добавить** (после импортов, до StorageBackend):
   - `ResolutionLevel = Literal[0, 1, 2]`
   - `PageResolution = Literal["none", "scan", "resolved", "verified"]`
   - `OCRRegistryEntry` (dataclass)
   - `DocumentMetadata` (dataclass)
   - `ResolutionDocumentState` (dataclass)

2. **Добавить** функции сериализации:
   - `_registry_to_dict(entries: List[OCRRegistryEntry]) -> List[dict]`
   - `_registry_from_dict(data: List[dict]) -> List[OCRRegistryEntry]`
   - `_resolution_state_to_dict(state: ResolutionDocumentState) -> dict`
   - `_resolution_state_from_dict(data: dict) -> ResolutionDocumentState`

3. **Расширить DiskStorage._get_file_path:**
   - `document_state/state` → `(state_dir / "state.json", "json")`
   - `ocr_registry/registry` → `(state_dir / "registry.json", "json")`

4. **Расширить StateManager:**
   - В `__init__`: `self._resolution_state = ResolutionDocumentState(page_states={}, ocr_registry=[], metadata=DocumentMetadata())`
   - Добавить 8 новых методов (см. 4.3)
   - При первом вызове load_document_state/load_ocr_registry — загружать в _resolution_state

5. **Не менять:** DocumentState, save_page, load_page, save_vlm_response, save_operation_result, save_state, load_state.

#### `02_src/vlm_ocr_doc_reader/core/__init__.py`
- Добавить экспорт: `OCRRegistryEntry`, `DocumentMetadata`, `ResolutionDocumentState`, `PageResolution`, `ResolutionLevel` (для использования в 011+). Либо отложить экспорт до 011 — по умолчанию экспортируем, т.к. API готов для 011.

#### `02_src/vlm_ocr_doc_reader/schemas/`
- Не добавлять сюда — модели состояния остаются в `core/state.py` (логически часть StateManager).

---

## 5. План реализации (поэтапно для Developer)

### Этап 1: Модели данных
1. В `state.py` добавить `ResolutionLevel`, `PageResolution`, `OCRRegistryEntry`, `DocumentMetadata`, `ResolutionDocumentState`.
2. Добавить функции `_registry_to_dict`, `_registry_from_dict`, `_resolution_state_to_dict`, `_resolution_state_from_dict` с учётом int-ключей в page_states.

### Этап 2: Расширение DiskStorage
3. В `_get_file_path` добавить ветки для `document_state/state` и `ocr_registry/registry`.
4. Убедиться, что save/load для json работают с dict/list (уже поддерживается).

### Этап 3: Методы StateManager
5. Добавить `_resolution_state` в `__init__`.
6. Реализовать `save_document_state`, `load_document_state`.
7. Реализовать `save_ocr_registry`, `load_ocr_registry`.
8. Реализовать `upsert_ocr_entries` (merge по entity_id).
9. Реализовать `pending_entities`, `set_page_resolution`, `page_status`.

### Этап 4: Интеграция и экспорт
10. Обновить `core/__init__.py` — экспорт новых типов.
11. Прогнать существующие тесты — убедиться, что DocumentProcessor, StateManager, OCRTool работают без регрессий.

---

## 6. Технические критерии приемки

- [ ] TC-1: `ResolutionDocumentState`, `OCRRegistryEntry`, `DocumentMetadata` сериализуются в JSON и восстанавливаются без потери полей.
- [ ] TC-2: `upsert_ocr_entries` с тем же `entity_id` обновляет запись, не дублирует.
- [ ] TC-3: `pending_entities(page_num=5)` возвращает только записи с resolution < 1 и page_num=5.
- [ ] TC-4: `page_status()` возвращает актуальный Dict[int, PageResolution].
- [ ] TC-5: `set_page_resolution(3, "scan")` обновляет состояние и сохраняет при DiskStorage.
- [ ] TC-6: Существующие тесты `test_state.py`, `test_processor.py` проходят.
- [ ] TC-7: MemoryStorage и DiskStorage поддерживают новые ключи.

---

## 7. Важные детали для Developer

- **Конфликт имён:** Существующий `DocumentState` не трогать. Новая модель — `ResolutionDocumentState`. В docstring можно указать алиас "DocumentState (resolution-level)".
- **Ключи int в JSON:** `json.dump` превращает `{1: "scan"}` в `{"1": "scan"}`. При загрузке — `{int(k): v for k, v in data.items()}`.
- **Пустой load:** Если файла нет — возвращать пустое состояние, не бросать исключение.
- **DiskStorage.state_dir:** Файлы `state.json` и `registry.json` — в корне `state_dir`, не в cache_dir.
- **Обратная совместимость:** DocumentProcessor создаёт StateManager как раньше. Новые методы не вызываются из текущего кода — только готовность API.

---

## 8. Риски и проверки готовности

| Риск | Митигация |
|------|-----------|
| Забыть конвертацию int-ключей в page_states | Явно описать в сериализации, проверить round-trip |
| Регрессия DocumentProcessor/OCRTool | Запустить существующие тесты после каждого этапа |
| Несовместимость с будущим Workspace (010) | Использовать ключи document_state/state, ocr_registry/registry — задача 010 может менять путь, но контракт StateManager остаётся |

**Проверка готовности:**
- Все 7 TC выполнены.
- `python -m pytest 02_src/tests/test_core/test_state.py 02_src/tests/test_core/test_processor.py -v` — зелёный.

---

## 9. Промпт для Developer

```
Ты — агент Developer (см. .agents/developer.md).

Прочитай:
- .agents/developer.md
- AGENTS.md
- Все файлы из 00_docs/standards/common/
- Все файлы из 00_docs/standards/developer/
- 01_tasks/009_document_state_ocr_registry/task_brief_01.md
- 01_tasks/009_document_state_ocr_registry/analysis_01.md
- 00_docs/architecture/decision_001_resolution_levels.md

Задача: Реализуй DocumentState + OCR Registry согласно техническому заданию (analysis_01.md). Следуй поэтапному плану. Не создавай новых тестовых модулей. Убедись, что существующие тесты проходят.

После завершения создай implementation_01.md и сформируй промпт для Reviewer.
```
