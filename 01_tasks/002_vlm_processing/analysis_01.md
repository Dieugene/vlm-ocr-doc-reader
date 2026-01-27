# Технический план: VLM Processing (критический путь)

**Версия:** 1.0
**Дата:** 2025-01-27
**Задача:** 002_vlm_processing

---

## 1. Анализ задачи

Необходимо реализовать критический путь системы VLM-OCR документ-ридера: три базовых компонента, которые обеспечат работу всех операций извлечения данных.

**Компоненты:**
1. **VLM Client** - техническая обертка над Gemini REST API с retry-логикой и throttling
2. **VLM Agent** - агентская сущность с tool calling loop (agentic подход)
3. **DocumentProcessor** - главный класс для работы с документами (PDF и PNG)

**Ключевые требования:**
- Работа с реальным Gemini API как можно раньше
- Retry на 429 и 500-599 ошибки
- Throttling с min_interval_s=0.6
- Tool calling loop максимум 10 итераций
- Поддержка PDF (авторендеринг) и массива PNG как входных данных
- Unit тесты для всех компонентов

---

## 2. Текущее состояние

### Reference реализации (02_src/_reference/)

**Доступны готовые паттерны для переиспользования:**

1. **gemini_client.py** - базовый Gemini REST API клиент
   - `_make_request_with_retry()` - retry с exponential backoff на 429 и 500-599
   - `generate_content()` - простые запросы с JSON mode
   - `generate_content_with_tools()` - function calling API
   - Логирование запросов/ответов

2. **vlm_client.py** - обертка с throttling
   - `_throttle()` - гарантия min_interval_s между вызовами
   - Регистрация попыток и лимитов

3. **pdf_utils.py** - рендеринг PDF в PNG
   - `render_pages_batch()` - батчевый рендеринг с DPI/quality
   - pymupdf (fitz) для рендеринга

4. **hybrid_dialogue.py** - пример tool calling loop
   - `_process_group_with_phases()` - agentic loop с tools
   - `_execute_function_call()` - выполнение tools
   - Управление историей сообщений

**Что НЕ переносить:**
- Специфичные поля аудиторских заключений
- Domain логику конкретных задач

### Существующая структура 02_src/

Папка `02_src/` пустая - нужно создать структуру модуля `vlm_ocr_doc_reader/` согласно архитектуре.

---

## 3. Предлагаемое решение

### 3.1. Общий подход

**Архитектура:**
- Создать модуль `vlm_ocr_doc_reader/` в `02_src/`
- Реализовать 3 компонента последовательно: VLM Client → VLM Agent → DocumentProcessor
- Переиспользовать паттерны из reference, адаптируя под новые интерфейсы

**Тестирование:**
- Unit тесты для каждого компонента
- Интеграционные тесты с реальным API (требует GEMINI_API_KEY)

**Конфигурация:**
- API ключ через переменную окружения GEMINI_API_KEY
- Настройки через dataclass (VLMConfig, ProcessorConfig)

### 3.2. Компоненты

#### Компонент 1: VLM Client

**Файлы:**
- `vlm_ocr_doc_reader/core/vlm_client.py` - BaseVLMClient, GeminiVLMClient

**Назначение:** Техническая обертка над Gemini REST API

**Интерфейс BaseVLMClient:**
```python
class BaseVLMClient:
    def invoke(
        prompt: str,
        images: List[bytes],
        tools: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Универсальный метод вызова VLM.
        Returns:
            С tools: {"function_calls": [...], "text": Optional[str]}
            Без tools: {"text": str, "usage": {...}}
        """
```

**Ключевая логика GeminiVLMClient:**
- **Retry:** на 429 (rate limit) и 500-599 (server errors)
- **Exponential backoff:** sleep_s = backoff_base ** (attempt - 1)
- **Throttling:** гарантия min_interval_s между вызовами
- **Логирование:** запросов, ответов, retry attempts

**Зависимости:**
- requests (HTTP клиент)
- time (throttling)
- typing, dataclasses (типы)

**Reference:** `02_src/_reference/gemini_client.py`, `02_src/_reference/vlm_client.py`

#### Компонент 2: VLM Agent

**Файл:**
- `vlm_ocr_doc_reader/core/vlm_agent.py` - VLMAgent

**Назначение:** Агентская сущность с tool calling loop

**Интерфейс:**
```python
class VLMAgent:
    def __init__(vlm_client: BaseVLMClient, max_iterations: int = 10)
    def register_tool(tool_def: Dict, handler: Callable) -> None
    def set_system_prompt(prompt: str) -> None
    def invoke(prompt: str, images: List[bytes]) -> Dict[str, Any]:
```

**Ключевая логика invoke():**
1. Добавить prompt в messages
2. Вызвать VLM с tools
3. Если есть function_calls:
   - Выполнить каждую функцию через handlers
   - Добавить результаты в messages
   - Повторить с шага 2 (max 10 итераций)
4. Если есть text - вернуть финальный ответ

**Tool definition формат:**
```python
tool_def = {
    "function_declarations": [{
        "name": "tool_name",
        "description": "...",
        "parameters": {
            "type": "object",
            "properties": {...},
            "required": [...]
        }
    }]
}
```

**Reference:** `02_src/_reference/hybrid_dialogue.py` (см. `_process_group_with_phases`)

#### Компонент 3: DocumentProcessor

**Файлы:**
- `vlm_ocr_doc_reader/core/processor.py` - DocumentProcessor
- `vlm_ocr_doc_reader/schemas/common.py` - PageInfo
- `vlm_ocr_doc_reader/schemas/config.py` - ProcessorConfig

**Назначение:** Главный класс для работы с документами

**Интерфейс:**
```python
class DocumentProcessor:
    def __init__(
        source: Union[Path, List[bytes]],
        vlm_client: BaseVLMClient,
        state_manager: Optional[StateManager] = None,
        auto_save: bool = True,
        config: Optional[ProcessorConfig] = None
    )

    @property
    def pages(self) -> List[PageInfo]

    @property
    def num_pages(self) -> int

    def save_state(self) -> None
    def load_state(self) -> None
```

**Логика инициализации:**
```python
if isinstance(source, Path):
    # PDF - рендерим через PDFRenderer
    renderer = PDFRenderer(RenderConfig(dpi=config.render_dpi))
    rendered = renderer.render_pdf(source)
    self._pages = [PageInfo(page_num=i+1, image=img) for i, img in rendered]
elif isinstance(source, list):
    # Массив PNG - используем как есть
    self._pages = [PageInfo(page_num=i+1, image=img) for i, img in enumerate(source)]
```

**Зависимости:**
- VLM Client (обязателен)
- PDF Renderer (для PDF исходников)
- State Manager (optional, создается если не передан)

### 3.3. Структуры данных

**PageInfo:**
```python
@dataclass
class PageInfo:
    page_num: int  # 1-based
    image: bytes   # Рендеренное изображение
```

**VLMConfig:**
```python
@dataclass
class VLMConfig:
    api_key: str
    model: str = "gemini-2.5-flash"
    timeout_sec: int = 60
    max_retries: int = 3
    backoff_base: float = 1.5
    min_interval_s: float = 0.6
```

**ProcessorConfig:**
```python
@dataclass
class ProcessorConfig:
    state_dir: Optional[Path] = None
    auto_save: bool = True
    render_dpi: int = 150
    log_level: str = "INFO"
```

### 3.4. Ключевые алгоритмы

**Retry с exponential backoff:**
- Повторять при 429 или 500-599
- Формула: sleep_s = backoff_base ** (attempt - 1)
- Максимум max_retries попыток

**Throttling:**
- Перед каждым вызовом: проверить время предыдущего
- Если elapsed < min_interval_s: sleep(min_interval_s - elapsed)

**Tool calling loop:**
- Максимум 10 итераций
- Каждая итерация: VLM → function_calls → выполнить → результаты → VLM
- Выход при text ответе или max_iterations

**PDF рендеринг:**
- Использовать pymupdf (fitz)
- DPI из config.render_dpi (дефолт 150)
- JPEG quality 85
- Возврат List[Tuple[page_num, image_bytes]]

### 3.5. Изменения в существующем коде

Существующий код отсутствует - создается новая структура с нуля.

**Reference файлы НЕ изменяются** - только переиспользуются как примеры.

---

## 4. План реализации

### Шаг 1: Структура модуля и базовые схемы
1. Создать структуру `vlm_ocr_doc_reader/` согласно `00_docs/architecture/overview.md`
2. Создать `schemas/common.py` - PageInfo
3. Создать `schemas/config.py` - VLMConfig, ProcessorConfig
4. Создать `__init__.py` с публичным API

### Шаг 2: VLM Client
1. Создать `core/vlm_client.py` - BaseVLMClient, GeminiVLMClient
2. Реализовать `_make_request_with_retry()` с exponential backoff
3. Реализовать `_throttle()` для min_interval_s
4. Реализовать `invoke()` с поддержкой tools
5. Добавить логирование запросов/ответов

### Шаг 3: Unit тесты для VLM Client
1. Тест retry на 429 (mock response с status 429)
2. Тест retry на 500-599 (mock response с status 503)
3. Тест throttling (замер времени между вызовами)
4. Тест без retry (status 200)

### Шаг 4: VLM Agent
1. Создать `core/vlm_agent.py` - VLMAgent
2. Реализовать `register_tool()` - регистрация tools с handlers
3. Реализовать `set_system_prompt()` - установка system prompt
4. Реализовать `invoke()` - tool calling loop (max 10 итераций)

### Шаг 5: Unit тесты для VLM Agent
1. Тест 1 итерации (VLM возвращает text сразу)
2. Тест 2 итерации (1 tool call → text)
3. Тест 10 итераций (множественные tools)
4. Тест max_iterations (11-я итерация не выполняется)

### Шаг 6: PDF Renderer
1. Создать `preprocessing/renderer.py` - PDFRenderer
2. Реализовать `render_pdf()` - рендеринг всех страниц
3. Настроить DPI/quality из config

### Шаг 7: DocumentProcessor
1. Создать `core/processor.py` - DocumentProcessor
2. Реализовать `__init__()` - поддержка PDF и PNG
3. Реализовать properties `pages`, `num_pages`
4. Интегрировать PDFRenderer, VLM Client, State Manager

### Шаг 8: Unit тесты для DocumentProcessor
1. Тест инициализации из PDF (мок рендеринга)
2. Тест инициализации из массива PNG
3. Тест properties `pages`, `num_pages`

### Шаг 9: Интеграционные тесты
1. Создать `.env` с GEMINI_API_KEY (локально, не коммитить)
2. Тест с реальным Gemini API (простой запрос без tools)
3. Тест с tool calling (mock handler)
4. Тест DocumentProcessor с реальным PDF (маленький файл)

### Шаг 10: Логирование и конфигурация
1. Настроить logger через `utils/logging.py`
2. Поддержка LOG_LEVEL из config
3. Логирование в state_dir/logs если задан

---

## 5. Технические критерии приемки

### VLM Client
- [TC-1] `GeminiVLMClient.invoke()` выполняет запросы к Gemini API
- [TC-2] Retry работает на 429 статусе (3 попытки с exponential backoff)
- [TC-3] Retry работает на 503 статусе (3 попытки)
- [TC-4] Throttling гарантирует min_interval_s=0.6 между вызовами
- [TC-5] Возврат function_calls при передаче tools
- [TC-6] Возврат text при запросе без tools

### VLM Agent
- [TC-7] `VLMAgent.invoke()` выполняет 1 итерацию при text ответе
- [TC-8] Tool calling loop работает для 2 итераций (tool → text)
- [TC-9] Tool calling loop работает для 10 итераций
- [TC-10] Максимум 10 итераций (11-я не выполняется)
- [TC-11] `register_tool()` регистрирует tools корректно
- [TC-12] `set_system_prompt()` устанавливает system prompt

### DocumentProcessor
- [TC-13] Инициализация из PDF файла (авторендеринг через PDFRenderer)
- [TC-14] Инициализация из массива PNG (используются как есть)
- [TC-15] `pages` возвращает список PageInfo с правильной нумерацией
- [TC-16] `num_pages` возвращает корректное количество страниц
- [TC-17] `save_state()` сохраняет состояние
- [TC-18] `load_state()` загружает состояние

### Интеграционные тесты
- [TC-19] Реальный запрос к Gemini API без tools
- [TC-20] Реальный запрос с function calling
- [TC-21] DocumentProcessor с реальным PDF файлом

### Покрытие тестами
- [TC-22] Unit тесты покрывают все методы VLM Client
- [TC-23] Unit тесты покрывают все методы VLM Agent
- [TC-24] Unit тесты покрывают DocumentProcessor

---

## 6. Важные детали для Developer

### Работа с реальным API

**ВАЖНО:** GEMINI_API_KEY должен быть в `.env` файле (не коммитить в git!)

```bash
# .env
GEMINI_API_KEY=your_actual_api_key_here
```

**Загрузка:**
```python
import os
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
```

### Retry логика - критичные детали

**Retry ТОЛЬКО на:**
- 429 (rate limit)
- 500-599 (server errors)

**НЕ retry на:**
- 4xx (кроме 429) - клиентские ошибки
- 400 bad request - ошибка в запросе
- 401 unauthorized - проблема с API ключом

**Exponential backoff:**
- `sleep_s = backoff_base ** (attempt - 1)`
- Пример: 1.5 ** 0 = 1s, 1.5 ** 1 = 1.5s, 1.5 ** 2 = 2.25s

### Throttling - точность

**Используй `time.monotonic()`** (не `time.time()`):
- Монотонные часы не зависят от системного времени
- Гарантируют корректную работу даже при изменении system time

### Tool calling loop - граничные случаи

**Что делать при:**
- **Нет function_calls и нет text** → ошибка, вернуть error
- **Пустой function_calls list** → ошибка
- **Max iterations достигнут** → ошибка, вернуть error
- **Handler выбросил exception** → логировать, продолжить loop или вернуть error

### PDF рендеринг - DPI и производительность

**DPI рекомендации:**
- 110 DPI - быстрый triage (низкое качество)
- 150 DPI - баланс (дефолт)
- 200+ DPI - точное извлечение данных

**JPEG quality:**
- 80-85 - оптимально для VLM
- 90+ - избыточно, большой размер

### Логирование - что логировать

**VLM Client:**
- Каждый запрос (model, images count)
- Retry attempts (статус, номер попытки)
- Успешные ответы (latency)
- Ошибки (статус, тело ответа)

**VLM Agent:**
- Регистрация tools
- Каждая итерация loop
- Function calls (имя, аргументы)
- Результаты execution

**DocumentProcessor:**
- Тип источника (PDF vs PNG)
- Количество страниц
- Рендеринг (если PDF)

### Тестирование - изоляция от реального API

**Используй mocking для unit тестов:**
```python
from unittest.mock import Mock, patch

# Мок HTTP ответа
mock_response = Mock()
mock_response.status_code = 200
mock_response.json.return_value = {"candidates": [...]}
```

**Интеграционные тесты - с реальным API:**
- Только при наличии GEMINI_API_KEY
- Пропускать тест если ключа нет (pytest skip)
- Минимальное количество запросов для экономии квоты

### State Management - для будущих задач

**В этой задаче:**
- Создай базовый интерфейс StateManager
- Реализуй MemoryStorage (хранение в RAM)
- DiskStorage и save_state/load_state можно как stubs (будет в задаче 004)

**Структура:**
```python
# core/state.py
class StateManager(ABC):
    @abstractmethod
    def save(self, key: str, value: Any) -> None: pass

    @abstractmethod
    def load(self, key: str) -> Any: pass

class MemoryStorage(StateManager):
    def __init__(self):
        self._storage = {}
    # ...
```

### Структура модуля - следуй архитектуре

**Обязательно:**
- `vlm_ocr_doc_reader/__init__.py` - публичный API (пока пустой или import DocumentProcessor)
- `vlm_ocr_doc_reader/core/` - основные компоненты
- `vlm_ocr_doc_reader/schemas/` - dataclasses
- `vlm_ocr_doc_reader/preprocessing/` - рендеринг
- `vlm_ocr_doc_reader/utils/` - вспомогательное (logging)

**НЕ создавай лишних файлов** - только необходимые для этой задачи.

---

## История изменений

| Версия | Дата | Изменения | Автор |
|--------|------|-----------|-------|
| 1.0 | 2025-01-27 | Первая версия технического задания | Analyst |
