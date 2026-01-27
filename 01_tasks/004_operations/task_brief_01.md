# Задача 004: High-level operations

## Что нужно сделать

Реализовать высокоуровневые операции для анализа документов:
1. **BaseOperation** - абстрактный базовый класс для всех операций
2. **FullDescriptionOperation** - полный анализ документа (контракт с проектом 07)
3. **Схемы данных** - DocumentData, HeaderInfo, TableInfo

## Зачем

FullDescriptionOperation - это контракт с проектом 07_agentic-doc-processing. Она обеспечивает извлечение полного текста, иерархической структуры заголовков и таблиц из документа. Это приоритет P0 для v0.1.0.

## Acceptance Criteria

- [ ] BaseOperation определен как абстрактный базовый класс
- [ ] FullDescriptionOperation.execute() извлекает текст и структуру документа
- [ ] DocumentData схема соответствует контракту с проектом 07
- [ ] HeaderInfo схема для заголовков (level, title, page)
- [ ] TableInfo схема для таблиц (id, type, page, location, preview)
- [ ] Unit тесты для FullDescriptionOperation (mock VLM)
- [ ] Интеграционный тест: PDF → DocumentData (с реальным API)
- [ ] Проверка контракта с проектом 07 (совпадение схем)

## Контекст

### Implementation Plan: Задача 4 (High-level operations)

```python
from abc import ABC, abstractmethod

class BaseOperation(ABC):
    """Базовый класс для всех operations."""

    def __init__(self, processor: DocumentProcessor):
        """Инициализация operation с процессором."""
        self.processor = processor

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Выполнить операцию."""
        pass
```

### Схемы данных

```python
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class HeaderInfo:
    """Информация о заголовке."""
    level: int  # 1, 2, 3...
    title: str
    page: int

@dataclass
class TableInfo:
    """Информация о таблице."""
    id: str  # "table_1", "table_2", ...
    type: str  # "NUMERIC" или "TEXT_MATRIX"
    page: int
    location: Dict[str, Any]  # {"bbox": [x1, y1, x2, y2], "page": int}
    preview: str  # Краткое описание
    cell_flattened: Optional[List[str]] = None  # Для TEXT_MATRIX (future)

@dataclass
class DocumentData:
    """Результат полного анализа документа - контракт с проектом 07."""
    text: str  # Полный текст документа
    structure: Dict[str, Any]  # {"headers": [HeaderInfo, ...]}
    tables: List[Dict[str, Any]] = field(default_factory=list)  # Пока пустой
```

### FullDescriptionOperation

```python
from typing import Optional, List

class FullDescriptionOperation(BaseOperation):
    """Полное описание документа - контракт с проектом 07.

    Приоритет P0 для v0.1.0
    """

    def __init__(
        self,
        processor: DocumentProcessor,
        render_dpi: Optional[int] = None
    ):
        """Инициализация operation.

        Args:
            processor: Экземпляр DocumentProcessor
            render_dpi: Переопределение DPI для рендеринга (optional)
        """
        super().__init__(processor)
        self.render_dpi = render_dpi

    def execute(
        self,
        pages: Optional[List[int]] = None
    ) -> DocumentData:
        """Полное описание документа.

        Args:
            pages: Specific страницы (None = все)

        Returns:
            DocumentData(text, structure, tables=[])
            tables пока пустой (реализация в будущих версиях)

        Algorithm:
        1. Если pages не None, отфильтровать processor.pages
        2. Построить промпты для VLM:
           - "Верни весь текст с этих страниц"
           - "Опиши иерархическую структуру: заголовки и их уровни"
        3. Вызвать VLM для каждого промпта
        4. Агрегировать результаты в DocumentData
        """
        pass
```

**VLM промпты:**
```
PROMPT_TEXT = "Верни весь текст с этих страниц в формате plain text. Сохраняй структуру заголовков."

PROMPT_STRUCTURE = """
Проанализируй эти страницы и опиши иерархическую структуру документа.
Для каждого заголовка укажи:
- Уровень (1 для основных, 2 для подзаголовков, и т.д.)
- Текст заголовка
- Номер страницы

Формат ответа (JSON):
{
  "headers": [
    {"level": 1, "title": "1. Введение", "page": 1},
    {"level": 2, "title": "1.1. Актуальность", "page": 2}
  ]
}
"""
```

**Пост-обработка:**
```python
# Парсинг JSON ответа VLM
import json

response = self.processor.vlm_agent.invoke(prompt_text, images)
text = response["text"]

response_structure = self.processor.vlm_agent.invoke(prompt_structure, images)
structure = json.loads(response_structure["text"])

return DocumentData(
    text=text,
    structure=structure,
    tables=[]  # Пока пустой
)
```

### Контракт с проектом 07

**FullDescriptionOperation.execute() возвращает DocumentData:**

```python
@dataclass
class DocumentData:
    text: str  # Полный текст документа
    structure: Dict[str, Any]  # {"headers": [...]}
    tables: List[Dict[str, Any]] = field(default_factory=list)
```

**Используется в проекте 07:**
- `02_src/processing/vlm_ocr_extractor.py`
- `02_src/processing/skeleton_builder.py`

**Совместимость:** Схемы совпадают с контрактом проекта 07 (согласно спецификации в `01_tasks/015_vlm_ocr_integration/vlm_ocr_doc_reader_spec.md`)

### Критерии готовности модуля:

- FullDescriptionOperation возвращает валидный DocumentData
- Текст извлекается полностью
- Структура заголовков корректна (level, title, page)
- Интеграционные тесты проходят (с реальным API)
- Контракт с проектом 07 соблюдается
- Логирование настроено

### Существующий код для reference:

- Задача 002 (VLM processing) - DocumentProcessor, VLM Agent используются как зависимости

### Другие ссылки:

- `00_docs/architecture/implementation_plan.md` - полный план реализации (см. Задачу 4)
- `00_docs/backlog.md` - реестр задач
- `00_docs/architecture/overview.md` - архитектура проекта (контракт с 07)

### Конфигурация через .env

API ключ для Gemini API:
- `GEMINI_API_KEY` - обязательно для тестов с реальным API

**ВАЖНО:** Все разработчики обязаны работать в виртуальном окружении. Установку библиотек выполнять через pip/poetry в venv.
