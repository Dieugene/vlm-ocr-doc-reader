# Задача 001: Base utilities

## Что нужно сделать

Реализовать базовые утилиты для работы с документами:
1. **PDF Renderer** - рендеринг PDF страниц в PNG изображения
2. **OCR нормализация** - утилита для исправления OCR ошибок (O→0, l→1, S→5, B→8)
3. **State Manager** - управление состоянием (Memory + Disk backends)

## Зачем

Это фундамент модуля, который используется всеми остальными задачами. PDF Renderer нужен для преобразования документов в изображения для VLM, OCR нормализация улучшает качество извлечения данных, State Manager обеспечивает персистентность для разработки и тестирования.

## Acceptance Criteria

- [ ] PDFRenderer.render_pdf() рендерит все страницы PDF в PNG
- [ ] PDFRenderer.render_page() рендерит одну страницу с кастомным DPI
- [ ] normalize_ocr_digits() выполняет замены O→0, l→1, S→5, B→8
- [ ] StateManager с Memory backend сохраняет/загружает данные в памяти
- [ ] StateManager с Disk backend сохраняет/загружает данные в JSON/YAML файлы
- [ ] Unit тесты для рендеринга (проверка размера изображений, DPI)
- [ ] Unit тесты для State Manager (проверка save/load)

## Контекст

### Implementation Plan: Задача 1 (Base utilities)

```python
from typing import List, Tuple, Optional
from pathlib import Path
from dataclasses import dataclass

@dataclass
class RenderConfig:
    """Конфигурация рендеринга."""
    dpi: int = 150
    quality: int = 85
    format: str = "PNG"

class PDFRenderer:
    """Рендеринг PDF страниц в изображения."""

    def __init__(self, config: RenderConfig):
        self.config = config

    def render_pdf(
        self,
        pdf_path: Path,
        page_indices: Optional[List[int]] = None
    ) -> List[Tuple[int, bytes]]:
        """Рендерит PDF страницы в PNG bytes.

        Args:
            pdf_path: Путь к PDF файлу
            page_indices: Список индексов (0-based), None = все страницы

        Returns:
            List of (page_num, image_bytes)
            page_num - 1-based номер страницы
        """
        pass

    def render_page(
        self,
        pdf_path: Path,
        page_num: int,
        dpi: Optional[int] = None
    ) -> bytes:
        """Рендерит одну страницу с кастомным DPI."""
        pass
```

**Reference:** `02_src/_reference/pdf_utils.py` из проекта 05_a_reports_ETL_02

**Ключевые параметры:**
- DPI: 110-150 (баланс качества/размера)
- Quality: 80-85 (для JPEG)
- Использовать pymupdf (fitz)

### OCR нормализация

```python
from typing import Optional

def normalize_ocr_digits(raw: str, expected_length: Optional[int] = None) -> Optional[str]:
    """OCR нормализация для числовых полей.

    Заменяет: O→0, l→1, I→1, S→5, B→8

    Args:
        raw: Сырой текст из OCR
        expected_length: Ожидаемая длина (optional)

    Returns:
        Нормализованная строка или None
    """
    cleaned = (
        str(raw)
        .replace(" ", "")
        .replace("\xa0", "")
        .replace("-", "")
        .replace("O", "0")
        .replace("o", "0")
        .replace("l", "1")
        .replace("I", "1")
        .replace("S", "5")
        .replace("B", "8")
    )

    digits = "".join(ch for ch in cleaned if ch.isdigit())

    if expected_length and len(digits) != expected_length:
        return None

    return digits or None
```

**Reference:** `02_src/_reference/tools.py` из проекта 05_a_reports_ETL_02

### State Manager

```python
from typing import Protocol, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass

class StorageBackend(Protocol):
    """Протокол хранилища состояния."""

    def save(self, key: str, value: Any) -> None:
        """Сохранить значение по ключу."""
        ...

    def load(self, key: str, default: Any = None) -> Any:
        """Загрузить значение по ключу."""
        ...

    def exists(self, key: str) -> bool:
        """Проверить существование ключа."""
        ...

class MemoryStorage:
    """In-memory хранилище."""
    def __init__(self):
        self._data: Dict[str, Any] = {}

class DiskStorage:
    """Файловое хранилище (JSON/YAML)."""
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.cache_dir = state_dir / "cache"
        self.results_dir = state_dir / "results"
        self.logs_dir = state_dir / "logs"

@dataclass
class DocumentState:
    """Состояние документа."""
    pages: Dict[int, bytes]  # page_num → image_bytes
    vlm_responses: Dict[str, Any]  # operation → response
    operation_results: Dict[str, Any]  # operation → result

class StateManager:
    """Менеджер состояния документа."""

    def __init__(self, storage: StorageBackend):
        self.storage = storage
        self.state = DocumentState(pages={}, vlm_responses={}, operation_results={})

    def save_page(self, page_num: int, image: bytes) -> None:
        """Сохранить рендеренную страницу."""

    def load_page(self, page_num: int) -> Optional[bytes]:
        """Загрузить рендеренную страницу."""

    def save_vlm_response(self, operation: str, response: Dict) -> None:
        """Сохранить VLM ответ."""

    def save_operation_result(self, operation: str, result: Any) -> None:
        """Сохранить результат operation (YAML формат)."""

    def save_state(self) -> None:
        """Явное сохранение всего состояния."""

    def load_state(self) -> None:
        """Загрузить состояние из storage."""
```

**Структура state_dir при DiskStorage:**

```
state_dir/
├── cache/
│   ├── pages/              # Рендеренные страницы (PNG)
│   │   ├── page_001.png
│   │   ├── page_002.png
│   │   └── ...
│   └── vlm_responses/      # VLM ответы (JSON)
│       ├── response_full_desc.json
│       └── response_cluster.json
│
├── results/                # Результаты operations (YAML)
│   ├── full_description.yaml
│   ├── clustering.yaml
│   ├── triage.yaml
│   └── extraction.yaml
│
├── logs/                   # Логи
│   └── vlm_ocr.log
│
└── state.json              # Metadata (auto_save, DPI, etc.)
```

### Критерии готовности модуля:

- Модуль возвращает валидные данные (PNG bytes, нормализованные строки)
- Интеграционные тесты проходят (PDF → страницы)
- Логирование настроено

### Существующий код для reference:

- `02_src/_reference/pdf_utils.py` - реализация рендеринга из 05_a_reports_ETL_02
- `02_src/_reference/tools.py` - реализация нормализации из 05_a_reports_ETL_02

### Другие ссылки:

- `00_docs/architecture/implementation_plan.md` - полный план реализации (см. Задачу 1)
- `00_docs/backlog.md` - реестр задач

### Конфигурация через .env

Для тестов с реальными API ключи должны передаваться через переменные окружения:
- `GEMINI_API_KEY` - для Gemini API (будет использоваться в Задаче 002)
- `QWEN_API_KEY` - для Qwen API (будет использоваться в Задаче 003)

В этой задаче API ключи не требуются.
