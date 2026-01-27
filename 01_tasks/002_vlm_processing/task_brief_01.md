# Задача 002: VLM processing (критический путь)

## Что нужно сделать

Реализовать ядро системы для работы с VLM:
1. **VLM Client** - Gemini REST API клиент с retry и throttling
2. **VLM Agent** - агентская сущность с tool calling loop (max 10 итераций)
3. **DocumentProcessor** - главный класс для работы с документами

## Зачем

Это критический путь для всех операций. VLM Client обеспечивает надежную работу с Gemini API, VLM Agent реализует agentic подход с function calling, DocumentProcessor объединяет все компоненты в единый интерфейс.

## Acceptance Criteria

- [ ] GeminiVLMClient.invoke() выполняет запросы к Gemini API с retry и throttling
- [ ] VLMAgent.invoke() реализует tool calling loop (максимум 10 итераций)
- [ ] VLMAgent.register_tool() регистрирует tools с handlers
- [ ] DocumentProcessor инициализируется из PDF файла (автоматический рендеринг)
- [ ] DocumentProcessor инициализируется из массива PNG (используются как есть)
- [ ] DocumentProcessor.pages возвращает список PageInfo
- [ ] DocumentProcessor.num_pages возвращает количество страниц
- [ ] Unit тесты для VLM Client (retry на 429/500 ошибки)
- [ ] Unit тесты для throttling (min_interval_s = 0.6)
- [ ] Unit тесты для tool calling loop (1, 2, 10 итераций)
- [ ] Unit тесты для DocumentProcessor (PDF vs PNG источники)

## Контекст

### Implementation Plan: Задача 2 (VLM processing)

```python
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
from dataclasses import dataclass
import time

@dataclass
class VLMConfig:
    """Конфигурация VLM клиента."""
    api_key: str
    model: str = "gemini-2.5-flash"
    timeout_sec: int = 60
    max_retries: int = 3
    backoff_base: float = 1.5
    min_interval_s: float = 0.6  # Throttling

class BaseVLMClient:
    """Базовый интерфейс VLM клиента."""

    def invoke(
        self,
        prompt: str,
        images: List[bytes],
        tools: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Универсальный метод вызова VLM.

        Args:
            prompt: Текстовый промпт
            images: Список изображений (PNG bytes)
            tools: Если переданы - использовать function calling

        Returns:
            С tools: {"function_calls": [...], "text": Optional[str]}
            Без tools: {"text": str, "usage": {...}}
        """
        raise NotImplementedError

class GeminiVLMClient(BaseVLMClient):
    """Gemini REST API клиент с retry и throttling."""

    def __init__(self, config: VLMConfig):
        self.config = config
        self._last_call_ts: Optional[float] = None
        self._calls_made = 0

    def _throttle(self) -> None:
        """Гарантирует min_interval_s между вызовами."""
        if self._last_call_ts is None:
            return
        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < self.config.min_interval_s:
            time.sleep(self.config.min_interval_s - elapsed)

    def _make_request_with_retry(
        self,
        url: str,
        headers: Dict,
        payload: Dict
    ) -> Dict:
        """Retry с exponential backoff.

        Retry на: 429 (rate limit), 500-599 (server errors)
        Формула: sleep_s = backoff_base ** (attempt - 1)
        """
        pass
```

**Reference:** `02_src/_reference/gemini_client.py` и `02_src/_reference/vlm_client.py`

**Ключевые параметры:**
- `min_interval_s: 0.6` - throttling между вызовами
- `max_retries: 3` - количество попыток
- `backoff_base: 1.5` - exponential backoff

### VLM Agent

```python
from typing import List, Dict, Any, Callable, Optional

class VLMAgent:
    """VLM Agent - агентская сущность с tool calling loop.

    Отвечает за:
    - Управление промптами (system/user)
    - Tool calling loop (max 10 итераций)
    - Вызов tools
    """

    def __init__(
        self,
        vlm_client: BaseVLMClient,
        max_iterations: int = 10
    ):
        self.vlm_client = vlm_client
        self.max_iterations = max_iterations
        self.messages: List[Dict] = []
        self.tools: Dict[str, Callable] = {}  # tool_name → handler

    def register_tool(self, tool_def: Dict, handler: Callable) -> None:
        """Зарегистрировать tool.

        Args:
            tool_def: Определение tool для VLM
            handler: Функция-обработчик вызова tool
        """
        tool_name = tool_def["function_declarations"][0]["name"]
        self.tools[tool_name] = handler
        # Добавить tool_def в messages

    def set_system_prompt(self, prompt: str) -> None:
        """Установить system prompt."""
        self.messages = [{"role": "user", "parts": [{"text": prompt}]}]

    def invoke(self, prompt: str, images: List[bytes]) -> Dict[str, Any]:
        """Выполнить запрос с tool calling loop.

        Algorithm:
        1. Добавить prompt в messages
        2. Вызвать VLM с tools
        3. Если есть function_calls:
           - Выполнить каждую функцию через handlers
           - Добавить результаты в messages
           - Повторить с шага 2 (max 10 итераций)
        4. Если есть text - вернуть финальный ответ

        Returns:
            Финальный ответ после tool calling loop
        """
        pass
```

**Reference:** `02_src/_reference/hybrid_dialogue.py` (function calling pattern)

**Tool definition формат:**
```python
tool_def = {
    "function_declarations": [
        {
            "name": "ask_ocr",
            "description": "Извлечь данные с изображения",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_num": {"type": "integer"},
                    "prompt": {"type": "string"}
                },
                "required": ["page_num", "prompt"]
            }
        }
    ]
}
```

### DocumentProcessor

```python
from typing import Union, List, Optional
from pathlib import Path
from dataclasses import dataclass

@dataclass
class PageInfo:
    """Информация о странице."""
    page_num: int  # 1-based
    image: bytes  # Рендеренное изображение

@dataclass
class ProcessorConfig:
    """Конфигурация процессора."""
    state_dir: Optional[Path] = None
    auto_save: bool = True
    render_dpi: int = 150  # Дефолтный DPI для рендеринга
    log_level: str = "INFO"

class DocumentProcessor:
    """Главный класс для работы с документами.

    Поддерживаемые входные данные:
    - PDF файл (автоматический рендеринг)
    - Массив PNG (используются как есть)
    """

    def __init__(
        self,
        source: Union[Path, List[bytes]],
        vlm_client: BaseVLMClient,
        state_manager: Optional[StateManager] = None,
        auto_save: bool = True,
        config: Optional[ProcessorConfig] = None
    ):
        """Инициализация процессора.

        Args:
            source: PDF путь или список PNG bytes
            vlm_client: VLM клиент (обязателен)
            state_manager: State manager (optional, создается если не передан)
            auto_save: Автосохранение результатов operations
            config: Конфигурация процессора
        """
        # Если source - PDF, рендерим через PDFRenderer
        # Если source - список PNG, используем как есть
        pass

    @property
    def pages(self) -> List[PageInfo]:
        """Список всех страниц документа."""
        pass

    @property
    def num_pages(self) -> int:
        """Количество страниц."""
        pass

    def save_state(self) -> None:
        """Явное сохранение состояния (при auto_save=False)."""
        pass

    def load_state(self) -> None:
        """Загрузка состояния из state_dir."""
        pass
```

**Логика инициализации:**
```python
# Внутри __init__:
if isinstance(source, Path):
    # PDF - рендерим через PDFRenderer
    renderer = PDFRenderer(RenderConfig(dpi=config.render_dpi))
    rendered = renderer.render_pdf(source)
    self._pages = [PageInfo(page_num=i, image=img) for i, img in rendered]
elif isinstance(source, list):
    # Массив PNG - используем как есть
    self._pages = [PageInfo(page_num=i+1, image=img) for i, img in enumerate(source)]
```

### Критерии готовности модуля:

- VLM Client возвращает валидные ответы от Gemini API
- Tool calling loop работает корректно (1, 2, 10 итераций)
- DocumentProcessor корректно инициализируется из PDF и PNG
- Интеграционные тесты проходят (с реальным API)
- Логирование настроено

### Существующий код для reference:

- `02_src/_reference/gemini_client.py` - Gemini REST API клиент с retry
- `02_src/_reference/vlm_client.py` - VLM Client обертка с throttling
- `02_src/_reference/hybrid_dialogue.py` - Function calling pattern

### Другие ссылки:

- `00_docs/architecture/implementation_plan.md` - полный план реализации (см. Задачу 2)
- `00_docs/backlog.md` - реестр задач

### Конфигурация через .env

API ключ для Gemini API:
- `GEMINI_API_KEY` - обязательно для тестов с реальным API

**ВАЖНО:** Все разработчики обязаны работать в виртуальном окружении. Установку библиотек выполнять через pip/poetry в venv.
