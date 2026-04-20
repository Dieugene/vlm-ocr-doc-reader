# Технический план: Task 010 — Workspace (DiskStorage рефакторинг)

## 1. Анализ задачи

Рефакторинг файлового storage в концепцию **workspace** из ADR-001: один workspace обслуживает несколько документов через поддиректории `{stem}_{content_hash6}`. Реализовать вычисление content hash, структуру каталогов документа и загрузку/инициализацию состояния по хешу содержимого. Задача готовит storage-слой для интеграции с DocumentReader (задача 011), не реализует публичный API.

---

## 2. Текущее состояние

### 2.1. DiskStorage (`02_src/vlm_ocr_doc_reader/core/state.py`)

- **Конструктор:** `DiskStorage(state_dir: Path)` — один state_dir на всё.
- **Структура:** `state_dir/cache/pages/`, `cache/vlm_responses/`, `results/`, `logs/`.
- **Ключи:** `pages/001` → `page_001.png`, `vlm_responses/X` → JSON, `results/X` → YAML.
- **Протокол:** `StorageBackend` (save, load, exists).

### 2.2. StateManager

- Использует `StorageBackend` для save_page, load_page, save_vlm_response, save_operation_result.
- Не знает про state.json/registry.json — это новая модель (задача 009).

### 2.3. DocumentProcessor (`processor.py`)

- Создаёт storage: `DiskStorage(config.state_dir)` если `state_dir` задан, иначе `MemoryStorage()`.
- `ProcessorConfig.state_dir` — опциональный Path.

### 2.4. CLI

- `create_run_dir()` → `output_dir/run_YYYYMMDD_HHMMSS/`.
- Передаёт `state_dir=run_dir` в ProcessorConfig.
- Текущая модель: один run = одна директория, без идентификации по содержимому.

### 2.5. Переиспользуемое

- `StorageBackend` Protocol — сохранить.
- `MemoryStorage` — без изменений.
- `StateManager` — должен работать с новым workspace-backed storage через тот же Protocol.

---

## 3. Предлагаемое решение

### 3.1. Общий подход

1. Ввести **WorkspacePaths** и **WorkspaceStorage** — новый слой для workspace-режима.
2. Реализовать **content-hash identity** через `compute_content_hash()` и `build_document_subdir_name()`.
3. Создать **WorkspaceBackend** — реализация `StorageBackend`, использующая `WorkspaceStorage` для совместимости с StateManager.
4. Добавить **open_document()** — фабрика для получения StateManager (memory или workspace) и флага `loaded_existing_state`.
5. **DiskStorage** — оставить для обратной совместимости (CLI v1, run_dir), но не расширять. В задаче 014 CLI перейдёт на workspace.

### 3.2. Scope

| In scope | Out of scope |
|----------|--------------|
| `compute_content_hash()`, `build_document_subdir_name()` | DocumentReader, scan/resolve orchestration |
| `WorkspacePaths`, `WorkspaceStorage` | Изменение full_description.py, VLM/OCR |
| `WorkspaceBackend` (StorageBackend) | CLI v2 (scan/resolve) |
| `open_document(pdf_path, workspace)` | Реализация Verify |
| state.json, registry.json, pages/ layout | Новые тестовые модули |

### 3.3. Контракты интерфейсов

#### WorkspacePaths

```python
@dataclass(frozen=True)
class WorkspacePaths:
    workspace_root: Path   # Корень workspace
    document_dir: Path    # workspace_root / "{stem}_{hash6}"
    pages_dir: Path       # document_dir / "pages"
    state_json: Path      # document_dir / "state.json"
    registry_json: Path   # document_dir / "registry.json"
```

#### Функции content-hash

```python
def compute_content_hash(pdf_path: Path) -> str:
    """SHA256 hex digest от байтов файла. Возвращает полный хеш (64 символа)."""

def build_document_subdir_name(pdf_path: Path, content_hash: str) -> str:
    """Возвращает '{stem}_{hash6}', где hash6 = content_hash[:6]."""
```

#### WorkspaceStorage

```python
class WorkspaceStorage:
    @classmethod
    def from_pdf(cls, pdf_path: Path, workspace: Path) -> "WorkspaceStorage":
        """Вычислить content_hash, собрать subdir, создать экземпляр.
        Не создаёт директории — это делает ensure_initialized()."""

    @property
    def paths(self) -> WorkspacePaths: ...

    def ensure_initialized(self) -> None:
        """Создать document_dir, pages_dir. Создать пустые state.json, registry.json если не существуют."""

    def load_state_json(self) -> dict:
        """Загрузить state.json. Если нет — вернуть {}."""

    def save_state_json(self, payload: dict) -> None: ...

    def load_registry_json(self) -> list[dict]:
        """Загрузить registry.json. Если нет — вернуть []."""

    def save_registry_json(self, payload: list[dict]) -> None: ...
```

#### WorkspaceBackend (StorageBackend)

```python
class WorkspaceBackend:
    """Реализация StorageBackend для workspace. Используется StateManager."""

    def __init__(self, workspace_storage: WorkspaceStorage) -> None: ...

    def save(self, key: str, value: Any) -> None:
        # pages/NNN → pages_dir/page_NNN.png (binary)
        # vlm_responses/X → document_dir/vlm_responses/response_X.json
        # results/X → document_dir/results/X.yaml

    def load(self, key: str, default: Any = None) -> Any: ...

    def exists(self, key: str) -> bool: ...
```

Структура document_dir для совместимости с StateManager:

```
{document_dir}/
├── pages/           # page_001.png, page_002.png, ...
├── vlm_responses/   # response_X.json (переходная совместимость)
├── results/         # X.yaml (переходная совместимость)
├── state.json
└── registry.json
```

#### open_document

```python
def open_document(
    pdf_path: Path,
    workspace: Optional[Path],
) -> tuple[StateManager, bool]:
    """
    Returns:
        state_manager: MemoryStorage-backed если workspace=None, иначе WorkspaceBackend
        loaded_existing_state: True если document_dir существовал и state.json был загружен
    """
```

### 3.4. Алгоритм content-hash identity

1. **compute_content_hash(pdf_path):**
   - Открыть файл в бинарном режиме.
   - Прочитать содержимое (chunked для больших файлов: 64KB блоки).
   - Вычислить SHA256 через `hashlib.sha256()`.
   - Вернуть `.hexdigest()` (64 символа).

2. **build_document_subdir_name(pdf_path, content_hash):**
   - `stem = pdf_path.stem` (имя без расширения).
   - `hash6 = content_hash[:6]`.
   - Вернуть `f"{stem}_{hash6}"`.
   - Санитизация stem: заменить недопустимые символы (например `/\:*?"<>|`) на `_` для Windows-совместимости.

3. **WorkspaceStorage.from_pdf(pdf_path, workspace):**
   - `content_hash = compute_content_hash(pdf_path)`.
   - `subdir_name = build_document_subdir_name(pdf_path, content_hash)`.
   - `document_dir = workspace / subdir_name`.
   - Собрать WorkspacePaths, вернуть экземпляр WorkspaceStorage.

4. **Логика open_document:**
   - `workspace is None` → `StateManager(MemoryStorage())`, `loaded_existing_state=False`.
   - Иначе: `WorkspaceStorage.from_pdf()`, `ensure_initialized()`.
   - `loaded_existing_state = paths.state_json.exists()` до ensure_initialized (или после — проверить наличие данных).
   - Создать `WorkspaceBackend(workspace_storage)`, `StateManager(WorkspaceBackend)`.
   - Вернуть `(state_manager, loaded_existing_state)`.

### 3.5. Формат state.json (минимальный для задачи 010)

```json
{
  "source_path": "/path/to/file.pdf",
  "content_hash": "a1b2c3d4e5f6...",
  "created_at": "2026-02-20T14:30:00",
  "pages_total": 0,
  "page_states": {}
}
```

При первой инициализации — пустая структура. Заполнение — задача 009/011.

### 3.6. Изменения по файлам

| Файл | Действие |
|------|----------|
| `02_src/vlm_ocr_doc_reader/core/state.py` | Добавить WorkspacePaths, compute_content_hash, build_document_subdir_name, WorkspaceStorage, WorkspaceBackend, open_document. DiskStorage оставить. |
| `02_src/vlm_ocr_doc_reader/core/__init__.py` | Экспортировать WorkspacePaths, WorkspaceStorage, open_document. |
| `02_src/vlm_ocr_doc_reader/core/processor.py` | Не менять в задаче 010. Интеграция через open_document — в задаче 011. |
| `02_src/vlm_ocr_doc_reader/cli.py` | Не менять. Продолжает использовать state_dir + DiskStorage. |

### 3.7. Важные детали

- **stem санитизация:** На Windows `Path.stem` может содержать символы, недопустимые в имени папки. Заменить `/\:*?"<>|` на `_`.
- **Пустой PDF:** `compute_content_hash` должен корректно обработать пустой файл (хеш от b"").
- **ensure_initialized:** Идемпотентен. Не перезаписывает существующие state.json/registry.json.
- **loaded_existing_state:** Считать True, если до вызова `ensure_initialized` уже существовал `document_dir` и в нём был `state.json` с непустым содержимым. Или проще: `state_json.exists()` после ensure (но ensure создаёт пустой файл). Уточнение: `loaded_existing_state = document_dir.exists() and state_json.exists()` до ensure — т.е. мы обнаружили ранее созданный workspace для этого документа.
- **Кодировка JSON:** UTF-8, `ensure_ascii=False`, `indent=2`.

---

## 4. План реализации для Developer

1. **Модуль workspace (или в state.py):**
   - Добавить `compute_content_hash(pdf_path: Path) -> str`.
   - Добавить `build_document_subdir_name(pdf_path, content_hash) -> str` с санитизацией stem.
   - Добавить `WorkspacePaths` dataclass.
   - Добавить класс `WorkspaceStorage` с `from_pdf`, `paths`, `ensure_initialized`, `load/save_state_json`, `load/save_registry_json`.

2. **WorkspaceBackend:**
   - Реализовать `StorageBackend` (save, load, exists).
   - Маппинг: `pages/NNN` → `pages_dir/page_NNN.png`, `vlm_responses/X` → `vlm_responses/response_X.json`, `results/X` → `results/X.yaml`.
   - Создать поддиректории `vlm_responses`, `results` в `ensure_initialized`.

3. **open_document:**
   - Реализовать ветвление workspace=None / workspace задан.
   - Вызов `WorkspaceStorage.from_pdf`, `ensure_initialized`.
   - Определение `loaded_existing_state`.
   - Создание StateManager с нужным backend.

4. **Экспорты:**
   - Обновить `core/__init__.py`.

5. **Проверка:**
   - Ручной прогон: open_document с workspace, повторный open того же файла (loaded_existing_state=True), open после изменения файла (новая директория), open без workspace (memory).

---

## 5. Технические критерии приемки

- [ ] TC-1: `compute_content_hash` возвращает 64-символьный SHA256 hex для любого PDF.
- [ ] TC-2: `build_document_subdir_name` возвращает `{stem}_{hash6}` с санитизированным stem.
- [ ] TC-3: `WorkspaceStorage.from_pdf` создаёт корректные WorkspacePaths.
- [ ] TC-4: `ensure_initialized` создаёт document_dir, pages/, state.json, registry.json, vlm_responses/, results/.
- [ ] TC-5: `open_document(pdf, None)` возвращает StateManager(MemoryStorage), loaded_existing_state=False.
- [ ] TC-6: `open_document(pdf, workspace)` при первом вызове — новая директория, loaded_existing_state=False.
- [ ] TC-7: Повторный `open_document` того же файла (тот же content hash) — loaded_existing_state=True.
- [ ] TC-8: После изменения содержимого PDF — новая поддиректория, loaded_existing_state=False.
- [ ] TC-9: StateManager с WorkspaceBackend корректно сохраняет и загружает pages (OCRTool.load_page работает).

---

## 6. Риски и проверки готовности

| Риск | Митигация |
|------|-----------|
| Большие PDF при хешировании | Читать чанками 64KB, не загружать весь файл в память. |
| Коллизия hash6 | 6 hex = 16^6 вариантов. Для задачи 010 достаточно. Документировать в docstring. |
| Race при параллельном open одного документа | Не в scope 010. Задача 011 может добавить file locking при необходимости. |

**Проверки готовности:**
- Существующие тесты StateManager/DiskStorage проходят (не ломаем).
- Ручная проверка сценариев AC-1–AC-6 из task_brief.
- Интерфейсы готовы для вызова из `DocumentReader.open()` в задаче 011.

---

## 7. Промпт для Developer

```
Ты — агент Developer (см. .agents/developer.md).

Прочитай:
- .agents/developer.md
- AGENTS.md
- Все файлы из 00_docs/standards/common/
- Все файлы из 00_docs/standards/developer/
- 01_tasks/010_workspace_diskstorage_refactor/task_brief_01.md
- 01_tasks/010_workspace_diskstorage_refactor/analysis_01.md
- 00_docs/architecture/decision_001_resolution_levels.md

Задача: Реализуй Workspace (DiskStorage рефакторинг) согласно техническому заданию. Не создавай новых тестовых модулей. Сохрани обратную совместимость DiskStorage и MemoryStorage.

После завершения сформируй промпт для Reviewer.
```
