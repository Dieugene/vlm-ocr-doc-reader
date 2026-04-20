# Task 010: Workspace (DiskStorage рефакторинг)

## Что нужно сделать
Рефакторить текущий файловый storage в концепцию `workspace` из ADR-001: один workspace обслуживает несколько документов через поддиректории `{stem}_{content_hash6}`. Реализовать вычисление content hash, структуру каталогов документа и загрузку/инициализацию состояния по хешу содержимого.

## Зачем
Workspace нужен для устойчивой персистенции состояния документа независимо от пути файла и для корректной работы инкрементальных уровней `scan/resolve/verify`. Без этого `DocumentReader.open(..., workspace=...)` не сможет безопасно переиспользовать состояние.

## Acceptance Criteria
- [ ] AC-1: Реализована идентификация документа по содержимому (SHA256) и получение `content_hash6`.
- [ ] AC-2: Создается и используется директория документа `{stem}_{content_hash6}` внутри workspace.
- [ ] AC-3: В директории документа поддерживаются артефакты состояния: `state.json`, `registry.json`, `pages/`.
- [ ] AC-4: Поддержан сценарий повторного `open` того же содержимого (подхват состояния), включая перенос файла на другой путь.
- [ ] AC-5: Поддержан сценарий изменения содержимого файла (новый hash -> новая директория).
- [ ] AC-6: Режим без workspace (`workspace=None`) остается memory-only.

## Контекст

**Релевантные части ADR (копия):**

ADR-001, Решение 4 (Workspace):
- `workspace` задается явно пользователем.
- Каждый документ в `workspace` получает поддиректорию:
  - `{stem}_{content_hash6}`
- Пример структуры:
  - `workspace/<doc>/pages/`
  - `workspace/<doc>/registry.json`
  - `workspace/<doc>/state.json`

ADR-001, идентификация документа:
- Идентификатор строится по содержимому (SHA256), а не по пути.
- Переместили файл -> hash тот же -> состояние подхватывается.
- Изменили файл -> hash другой -> новая поддиректория.

ADR-001, логика open:
1. `workspace=None` -> memory mode.
2. Вычислить `content_hash`.
3. Собрать `subdir = f"{stem}_{content_hash[:6]}"`.
4. Если subdir есть -> загрузить состояние.
5. Иначе -> создать subdir и инициализировать пустое состояние.

**Интерфейсы и контракты (полностью):**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class WorkspacePaths:
    workspace_root: Path
    document_dir: Path
    pages_dir: Path
    state_json: Path
    registry_json: Path


def compute_content_hash(pdf_path: Path) -> str:
    """Return full SHA256 hex digest for file bytes."""
    ...


def build_document_subdir_name(pdf_path: Path, content_hash: str) -> str:
    """Return '<stem>_<hash6>'."""
    ...


class WorkspaceStorage:
    @classmethod
    def from_pdf(cls, pdf_path: Path, workspace: Path) -> "WorkspaceStorage": ...
    @property
    def paths(self) -> WorkspacePaths: ...
    def ensure_initialized(self) -> None: ...
    def load_state_json(self) -> dict: ...
    def save_state_json(self, payload: dict) -> None: ...
    def load_registry_json(self) -> list[dict]: ...
    def save_registry_json(self, payload: list[dict]) -> None: ...
```

```python
# Contract for integration with future DocumentReader.open()
def open_document(pdf_path: Path, workspace: Optional[Path]) -> tuple["StateManager", bool]:
    """
    Returns:
      state_manager: memory or workspace-backed manager
      loaded_existing_state: True if existing workspace document state was found
    """
    ...
```

**Границы задачи 010:**
- Делает: filesystem layout workspace + content hash identity + storage API.
- Не делает: публичный `DocumentReader` API и orchestration scan/resolve.

**Критерии готовности модуля:**
- Хранение состояния/реестра отделено от старого `state_dir/results`.
- Возможна одновременная работа с несколькими документами в одном workspace.
- Hash-based identity документирована и реализована через отдельные функции.
- Интерфейсы готовы для прямой интеграции в задаче 011.

**Существующий код для reference:**
- `02_src/vlm_ocr_doc_reader/core/state.py` - текущий `DiskStorage`.
- `02_src/vlm_ocr_doc_reader/core/processor.py` - текущее создание storage backend.
- `00_docs/architecture/decision_001_resolution_levels.md` - требования workspace.
- `00_docs/architecture/overview.md` - целевая архитектура.
