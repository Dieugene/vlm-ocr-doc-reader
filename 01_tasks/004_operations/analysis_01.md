# Технический план: Реализация High-level Operations

## 1. Анализ задачи

Реализовать высокоуровневые операции для анализа документов с приоритетом на **FullDescriptionOperation** — контракт с проектом 07_agentic-doc-processing. В v0.1.0 tables остается пустым (реализация в будущих версиях).

**Ключевое требование:** FullDescriptionOperation.execute() должен возвращать DocumentData с текстом и структурой заголовков для интеграции с проектом 07.

## 2. Текущее состояние

**Reference реализации в 02_src/_reference/:**
- `gemini_client.py` — GeminiRestClient с retry logic и exponential backoff
- `vlm_client.py` — VLMClient с throttling (min_interval_s: 0.6)
- `hybrid_dialogue.py` — HybridDialogueManager с function calling и агентическим циклом
- `pdf_utils.py` — рендеринг PDF→PNG (DPI: 110-150, quality: 80-85)
- `qwen_client.py` — QwenClient с форматом ответа ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ
- `tools.py` — пример tools для function calling

**Что нужно создать:**
1. Модуль operations/ в новой структуре пакета
2. BaseOperation — абстрактный базовый класс
3. FullDescriptionOperation — основной метод для контракта с проектом 07
4. Схемы данных в schemas/ — DocumentData, HeaderInfo, TableInfo

**Контракт с проектом 07 (из vlm_ocr_extractor.py):**
```python
@dataclass
class DocumentData:
    text: str  # Полный текст документа
    structure: Dict[str, Any]  # {"headers": [HeaderInfo, ...]}
    tables: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class HeaderInfo:
    level: int  # 1, 2, 3...
    title: str
    page: int
```

## 3. Предлагаемое решение

### 3.1. Общий подход

**Архитектура operations:**
- Operations импортируются как самостоятельные классы
- При создании получают экземпляр DocumentProcessor
- Вызов через `.execute()`
- BaseOperation определяет общий интерфейс

**Полная цепочка:**
```
DocumentProcessor (from task 002)
  ↓ использует VLM Agent
  ↓ использует VLM Client
FullDescriptionOperation(processor)
  ↓ .execute()
  ↓ вызывает VLM Agent с промптами
DocumentData(text, structure, tables=[])
```

### 3.2. Компоненты

#### 3.2.1. BaseOperation (operations/base.py)

**Назначение:** Абстрактный базовый класс для всех operations

**Интерфейс:**
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

**Зависимости:**
- DocumentProcessor из core/processor.py (будет создан в task 002)

#### 3.2.2. FullDescriptionOperation (operations/full_description.py)

**Назначение:** Полное описание документа — контракт с проектом 07

**Интерфейс:**
```python
from typing import Optional, List
from .base import BaseOperation
from ..schemas.document import DocumentData

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
        """
```

**Алгоритм execute():**
1. Если pages не None, отфильтровать processor.pages по индексам
2. Построить промпты для VLM:
   - PROMPT_TEXT: "Верни весь текст с этих страниц в формате plain text. Сохраняй структуру заголовков."
   - PROMPT_STRUCTURE: "Опиши иерархическую структуру документа. Для каждого заголовка укажи уровень (1, 2, 3...), текст, номер страницы. Формат ответа (JSON): {headers: [{level, title, page}]}"
3. Вызвать VLM Agent для каждого промпта с отфильтрованными изображениями
4. Парсинг JSON ответа для structure
5. Агрегация результатов в DocumentData

**VLM промпты (константы):**
```python
PROMPT_TEXT = (
    "Верни весь текст с этих страниц в формате plain text. "
    "Сохраняй структуру заголовков."
)

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
- Парсинг JSON через json.loads()
- Валидация структуры (проверка что headers есть и это list)
- При ошибке парсинга — логировать и возвращать пустую структуру

**Зависимости:**
- BaseOperation
- DocumentData из schemas/document.py
- DocumentProcessor с атрибутами:
  - `.pages` — List[PageInfo] или List[bytes]
  - `.vlm_agent` — VLM Agent с методом invoke()
- PageInfo из schemas/common.py (если используется)

#### 3.2.3. Схемы данных (schemas/)

**schemas/document.py:**
```python
from dataclasses import dataclass, field
from typing import List, Dict, Any

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
    cell_flattened: List[str] = None  # Для TEXT_MATRIX (future)

@dataclass
class DocumentData:
    """Результат полного анализа документа - контракт с проектом 07."""
    text: str  # Полный текст документа
    structure: Dict[str, Any]  # {"headers": [HeaderInfo, ...]}
    tables: List[Dict[str, Any]] = field(default_factory=list)  # Пока пустой
```

**schemas/common.py (если еще не создан):**
```python
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class PageInfo:
    """Информация о странице."""
    index: int  # Номер страницы (1-based)
    image: bytes  # PNG изображение
```

**schemas/config.py (если еще не создан):**
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ProcessorConfig:
    """Конфигурация процессора."""
    render_dpi: int = 150
    log_level: str = "INFO"
```

### 3.3. Изменения в существующем коде

**Новая структура модулей:**
```
vlm_ocr_doc_reader/
├── operations/
│   ├── __init__.py
│   ├── base.py                    # BaseOperation
│   └── full_description.py        # FullDescriptionOperation
├── schemas/
│   ├── __init__.py
│   ├── document.py                # DocumentData, HeaderInfo, TableInfo
│   └── common.py                  # PageInfo (если нужно)
└── ...
```

**Импорты в operations/__init__.py:**
```python
from .base import BaseOperation
from .full_description import FullDescriptionOperation

__all__ = ["BaseOperation", "FullDescriptionOperation"]
```

**Импорты в schemas/__init__.py:**
```python
from .document import DocumentData, HeaderInfo, TableInfo
from .common import PageInfo

__all__ = ["DocumentData", "HeaderInfo", "TableInfo", "PageInfo"]
```

## 4. План реализации

1. **Шаг 1:** Создать структуру модулей operations/ и schemas/
2. **Шаг 2:** Реализовать schemas/document.py с dataclass: DocumentData, HeaderInfo, TableInfo
3. **Шаг 3:** Реализовать schemas/common.py с PageInfo (если нужно)
4. **Шаг 4:** Реализовать operations/base.py с BaseOperation
5. **Шаг 5:** Реализовать operations/full_description.py:
   - Инициализация с processor и render_dpi
   - Метод execute() с фильтрацией страниц
   - VLM промпты (PROMPT_TEXT, PROMPT_STRUCTURE)
   - Вызов VLM Agent
   - Парсинг JSON ответа
   - Возврат DocumentData
6. **Шаг 6:** Обновить __init__.py в operations/ и schemas/
7. **Шаг 7:** Unit тесты для FullDescriptionOperation с mock VLM Agent
8. **Шаг 8:** Интеграционный тест с реальным Gemini API

## 5. Технические критерии приемки

- [ ] TC-1: BaseOperation определен как абстрактный базовый класс с методом execute()
- [ ] TC-2: FullDescriptionOperation.execute() возвращает DocumentData с text и structure
- [ ] TC-3: DocumentData.text содержит полный текст документа
- [ ] TC-4: DocumentData.structure["headers"] содержит список HeaderInfo с level, title, page
- [ ] TC-5: DocumentData.tables пустой список в v0.1.0
- [ ] TC-6: Unit тесты покрывают:
  - Инициализацию FullDescriptionOperation
  - Фильтрацию страниц при pages=[1, 2, 3]
  - Парсинг JSON ответа от VLM
  - Обработку ошибок парсинга JSON
- [ ] TC-7: Интеграционный тест проходит с реальным Gemini API (простой PDF 2-3 страницы)
- [ ] TC-8: Схема DocumentData совпадает с контрактом проекта 07
- [ ] TC-9: Логирование настроено (INFO уровень по умолчанию)
- [ ] TC-10: Код документирован (docstrings для классов и методов)

## 6. Важные детали для Developer

**Интеграция с DocumentProcessor (из task 002):**
- FullDescriptionOperation зависит от DocumentProcessor
- DocumentProcessor должен иметь:
  - `.pages` — список PageInfo или bytes
  - `.vlm_agent` — VLM Agent с методом `invoke(prompt, images)`
- Если DocumentProcessor еще не реализован — создать mock для unit тестов

**VLM Agent invoke() интерфейс:**
```python
# Ожидаемый интерфейс VLM Agent
response = vlm_agent.invoke(prompt, images)
# response: Dict с ключом "text" (str или JSON)
```

**Парсинг JSON ответа VLM:**
- VLM может вернуть JSON обернутый в markdown fences (```json ... ```)
- Нужна очистка перед json.loads(): убрать ```json и ```
- При ошибке парсинга — логировать warning и возвращать пустую структуру

**Фильтрация страниц:**
- pages параметр — список индексов (1-based: [1, 2, 3])
- Если processor.pages это List[PageInfo] — фильтровать по .index
- Если processor.pages это List[bytes] — фильтровать по индексу списка

**API ключ Gemini:**
- GEMINI_API_KEY передается через .env файл
- Использовать python-dotenv для загрузки
- В тестах использовать mock VLM Agent

**Интеграционные тесты с реальным API:**
- Обязательны для проверки контракта с проектом 07
- Использовать простой PDF документ (2-3 страницы с заголовками)
- Проверять что DocumentData соответствует контракту

**Reference реализации:**
- Переиспользовать паттерны из 02_src/_reference/gemini_client.py:
  - Retry logic с exponential backoff
  - Throttling (min_interval_s: 0.6)
  - Обработка ошибок API

**Логирование:**
- Настроить логгер для operations: `logging.getLogger("vlm_ocr_doc_reader.operations")`
- Логировать ключевые шаги execute():
  - "Starting full description operation"
  - "Filtering pages: {len(filtered)} from {len(total)}"
  - "Calling VLM for text extraction"
  - "Calling VLM for structure extraction"
  - "Parsing structure JSON: success/error"

**Ограничения v0.1.0:**
- tables всегда пустой список []
- Без классификации таблиц (NUMERIC/TEXT_MATRIX)
- Без cell flattening для таблиц
- Простая фильтрация страниц (без сложной логики)

**Работа в виртуальном окружении:**
- Обязательно создать venv перед установкой зависимостей
- Установить зависимости через pip: `pip install requests python-dotenv pillow pydantic`
- pytest для тестов: `pip install pytest pytest-mock`

**Проверка контракта с проектом 07:**
- Сравнить схемы DocumentData с 07_agentic-doc-processing/02_src/processing/vlm_ocr_extractor.py
- Убедиться что поля совпадают: text, structure, tables
- Проверить что structure["headers"] содержит level, title, page
