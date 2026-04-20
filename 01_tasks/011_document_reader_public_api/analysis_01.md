# Технический план: DocumentReader (публичный API)

## 1. Анализ задачи

Реализовать `DocumentReader` как единственную публичную точку входа модуля v0.2.0. Класс управляет lifecycle документа, интегрирует StateManager и DocumentProcessor из задач 009/010, предоставляет API `scan/resolve/verify/page_status/pending_entities/get_document_data`. Методы `scan`/`resolve`/`verify` — контракты и заглушки, готовые для подстановки логики в задачах 012/013/015.

**Цель:** Платформа для Resolution Levels без изменения существующего `FullDescriptionOperation` и CLI.

---

## 2. Текущее состояние

### Реализовано (009, 010)

- **`state.py`:** `ResolutionDocumentState`, `OCRRegistryEntry`, `PageResolution`, `DocumentMetadata`, `WorkspaceStorage`, `WorkspaceBackend`, `open_document(pdf_path, workspace)`, `StateManager` с `page_status()`, `pending_entities()`, `save_document_state()`, `load_document_state()`, `upsert_ocr_entries()`, `set_page_resolution()`.
- **`processor.py`:** `DocumentProcessor(source, state_manager, config)` — рендер PDF, сохранение страниц в state, `vlm_agent`, `pages`.
- **`full_description.py`:** `FullDescriptionOperation(processor).execute(pages)` — три прохода, возвращает `DocumentData`.
- **CLI:** `DocumentProcessor` + `FullDescriptionOperation`, сохранение результата в `results/full_description.yaml`.

### Переиспользовать

- `open_document()` — для инициализации StateManager (memory/workspace).
- `StateManager.page_status()`, `pending_entities()` — делегировать без обёрток.
- `DocumentProcessor` — создавать с `state_manager` из `open_document`, `source=pdf_path`.
- `DocumentData`, `HeaderInfo`, `TableInfo` — из `schemas/document.py`.

---

## 3. Предлагаемое решение

### 3.1. Общий подход

Создать класс `DocumentReader` в новом модуле `core/reader.py`. Конструктор закрытый; фабрика `open(pdf_path, workspace=None)` использует `open_document()` и создаёт `DocumentProcessor`. Методы `scan`/`resolve`/`verify` — заглушки с корректной сигнатурой и минимальной логикой (рендер страниц, обновление `page_states` для scan; для resolve/verify — только точки делегирования). `page_status` и `pending_entities` делегируют в StateManager. `get_document_data` собирает `DocumentData` из сохранённого результата или возвращает пустой.

### 3.2. Компоненты

#### DocumentReader

- **Назначение:** Публичный API, lifecycle документа, оркестрация StateManager и DocumentProcessor.
- **Файл:** `02_src/vlm_ocr_doc_reader/core/reader.py`
- **Интерфейс:** см. task_brief (open, scan, resolve, verify, page_status, pending_entities, get_document_data).
- **Зависимости:** `open_document`, `StateManager`, `DocumentProcessor`, `DocumentData`, `OCRRegistryEntry`, `PageResolution`, `ProcessorConfig`.

#### Внутренние атрибуты

- `_pdf_path: Path`
- `_workspace: Optional[Path]`
- `_state_manager: StateManager`
- `_processor: DocumentProcessor`

#### Вспомогательные методы (приватные)

- `_normalize_pages(pages: Optional[Iterable[int]]) -> List[int]` — None → все страницы документа, иначе валидация и сортировка.
- `_ensure_pages_rendered()` — гарантирует, что страницы отрендерены (processor уже делает это при init).

### 3.3. Структуры данных

Используются без изменений: `DocumentData`, `OCRRegistryEntry`, `PageResolution`, `ResolutionDocumentState`.

### 3.4. Ключевые алгоритмы

**DocumentReader.open(pdf_path, workspace):**

1. Привести `pdf_path` к `Path`, проверить существование файла.
2. Вызвать `open_document(pdf_path, workspace)` → `(state_manager, _)`.
3. Создать `ProcessorConfig(state_dir=None, auto_save=True, render_dpi=150)` (state_dir не используется — state_manager уже имеет backend).
4. Создать `DocumentProcessor(source=pdf_path, state_manager=state_manager, config=config)`.
5. Вернуть экземпляр `DocumentReader` с заполненными атрибутами.

**scan(pages=None):**

1. `pages = _normalize_pages(pages)`.
2. `_ensure_pages_rendered()` — страницы уже в processor после open.
3. Для каждой страницы из `pages` вызвать `state_manager.set_page_resolution(page_num, "scan")`.
4. Заглушка для 012: OCR Registry не заполняется (VLM не вызывается). Метод готов к подстановке вызова Scan-операции.

**resolve(pages=None):**

1. `pages = _normalize_pages(pages)`.
2. Получить `pending = state_manager.pending_entities(page=None)` и отфильтровать по `pages` при необходимости.
3. Заглушка: если `pending` не пуст — залогировать; точка делегирования для 013: вызов `_resolve_entities(entities)` (метод-заглушка, 013 реализует).

**verify(pages=None):**

1. `pages = _normalize_pages(pages)`.
2. Интерфейс: залогировать вызов; реализация стратегии — задача 015.

**get_document_data():**

1. Загрузить из storage ключ `results/full_description` (YAML).
2. Если данные есть — собрать `DocumentData(text=..., structure=..., tables=...)`.
3. Иначе вернуть `DocumentData(text="", structure={"headers": []}, tables=[])`.

### 3.5. Изменения в существующем коде

- **`__init__.py`:** Добавить экспорт `DocumentReader`, `open_document` (если нужен для внешнего использования), типы `PageResolution`, `OCRRegistryEntry`.
- **`cli.py`:** Не менять (задача 014).
- **`processor.py`:** Не менять.
- **`state.py`:** Не менять.
- **`full_description.py`:** Не менять.

---

## 4. План реализации

1. Создать `02_src/vlm_ocr_doc_reader/core/reader.py` с классом `DocumentReader`.
2. Реализовать `open()`, `_normalize_pages()`, `_ensure_pages_rendered()`.
3. Реализовать `scan()`, `resolve()`, `verify()` как заглушки с контрактом.
4. Реализовать `page_status()`, `pending_entities()` — делегирование в StateManager.
5. Реализовать `get_document_data()` — загрузка из storage или пустой DocumentData.
6. Обновить `__init__.py`: экспорт `DocumentReader` и при необходимости `open_document`, `PageResolution`, `OCRRegistryEntry`.

---

## 5. Технические критерии приемки

- [ ] TC-1: `DocumentReader.open(pdf_path, workspace=None)` создаёт reader; при `workspace=None` — MemoryStorage; при `workspace=Path` — WorkspaceBackend, подхват состояния по content hash.
- [ ] TC-2: `scan(pages=None)` и `scan(pages=[1,2,3])` обновляют `page_states` для указанных страниц на `"scan"`; OCR Registry остаётся пустым (заглушка для 012).
- [ ] TC-3: `resolve(pages=None)` и `resolve(pages=[48,49])` имеют корректный контракт; логируют вызов; точка делегирования для 013 присутствует.
- [ ] TC-4: `verify(pages=None)` — интерфейс присутствует, реализация — заглушка.
- [ ] TC-5: `page_status()` возвращает `Dict[int, PageResolution]` из StateManager.
- [ ] TC-6: `pending_entities(page=None)` возвращает `List[OCRRegistryEntry]` из StateManager.
- [ ] TC-7: `get_document_data()` возвращает `DocumentData` (из storage или пустой).
- [ ] TC-8: Публичный API экспортирован в `__init__.py`.
- [ ] TC-9: Существующий `FullDescriptionOperation` и CLI работают без регрессии.

---

## 6. Разделение scope 011 от 012/013/014/015

| Задача | Scope | Не входит в 011 |
|--------|-------|-----------------|
| **011** | DocumentReader, open(), контракты scan/resolve/verify, page_status, pending_entities, get_document_data, экспорт | — |
| **012** | Scan: рефакторинг промптов, VLM возвращает OCR Registry, персистенция Registry | Логика Scan-промпта, вызов VLM для Registry |
| **013** | Resolve: итерация Registry, вызов OCR Client напрямую, page-based batching | Реальная реализация resolve, OCR-вызовы |
| **014** | CLI v2: субкоманды scan/resolve/verify/full-description, --workspace | Изменения в cli.py |
| **015** | Verify: N параллельных OCR, majority voting, confidence | Реализация стратегии Verify |

---

## 7. Важные детали для Developer

- **Не создавать новые тестовые модули** — по требованию постановки.
- **FullDescriptionOperation не трогать** — DocumentReader параллельный путь; CLI продолжает использовать старый flow.
- **StateManager.load/save** — использовать ключи `document_state/state`, `ocr_registry/registry`, `results/full_description` в соответствии с `WorkspaceBackend` и `DiskStorage`.
- **ProcessorConfig.state_dir** — при создании DocumentProcessor передавать `None`; StateManager уже имеет backend от `open_document`.
- **YAML для results** — при загрузке `get_document_data` использовать `yaml.safe_load`; структура: `{text, structure, tables}`.
- **Нумерация страниц** — везде 1-based, как в DocumentProcessor и StateManager.
