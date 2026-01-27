# Архитектура проекта vlm-ocr-doc-reader

**Версия:** 1.0
**Дата:** 2025-01-27
**Статус:** Базовая архитектура

---

## Общее описание

**vlm-ocr-doc-reader** — универсальный Python-пакет для работы с документами через гибридный подход VLM + OCR.

### Ключевые особенности

1. **AI-агентская архитектура**: VLM как агент с function calling, OCR как специализированный tool
2. **Stateless + Stateful режимы**: Может работать без сохранения состояния или с персистентностью
3. **Plug-and-play операции**: Triage, Clustering, Extraction, Full Description как подключаемые модули
4. **Автоматическое state management**: При указании `state_dir` все операции автоматически сохраняются
5. **Батчинг по страницам**: Предсказуемое управление токенами без автоматического разбиения
6. **Контракт для 07_agentic-doc-processing**: Метод `describe_full()` возвращает `DocumentData`

---

## Концептуальная модель

```
┌─────────────────────────────────────────────────────────────────┐
│                    DocumentProcessor                            │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  State Management (опционально)                           │ │
│  │  • state_dir/                                             │ │
│  │    ├── pages/      # Рендеренные PNG с нумерацией         │ │
│  │    ├── cache/      # Кэш VLM ответов                      │ │
│  │    ├── data/       # Результаты (JSON/YAML)               │ │
│  │    └── logs/       # Логи выполнения                      │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  AI Agent Architecture                                     │ │
│  │  ┌──────────────────┐        ┌───────────────────┐        │ │
│  │  │   VLM Agent      │───────▶│   OCR Tool        │        │ │
│  │  │   (Gemini)       │        │   (Qwen)          │        │ │
│  │  │                  │◀───────│                   │        │ │
│  │  │ • Throttling     │        │ • Точное извлечение│       │ │
│  │  │ • Retry logic    │        │ • Нормализация    │        │ │
│  │  │ • Function call  │        │ • Проверка        │        │ │
│  │  └──────────────────┘        └───────────────────┘        │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Operations (plug-and-play)                                │ │
│  │  • TriageOperation          # Поиск релевантных страниц    │ │
│  │  • ClusteringOperation      # Смысловая кластеризация      │ │
│  │  • ExtractionOperation      # Извлечение по запросу        │ │
│  │  • FullDescriptionOperation # Полное описание (контракт)   │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Ключевые компоненты

### 1. DocumentProcessor (ядро)

**Назначение**: Главный класс пакета, фасад для всех операций.

**Расположение**: `vlm_ocr_doc_reader/core/processor.py`

**Ответственности**:
- Управление жизненным циклом документа
- Координация VLM Agent и OCR Tool
- Выполнение operations
- Автоматическое сохранение состояния (если `state_dir` задан)

**Интерфейс**:
```python
class DocumentProcessor:
    def __init__(
        self,
        source: Union[str, List[bytes]],  # PDF path или PNG list
        vlm_client: Optional[BaseVLMAgent] = None,
        ocr_client: Optional[BaseOCRTool] = None,
        state_dir: Optional[str] = None,  # Авто-сохранение
        config: Optional[Dict[str, Any]] = None
    ):

    # Operations
    def triage(self, prompt: str, pages: Optional[List[int]] = None) -> List[int]:
        """Найти страницы соответствующие prompt"""

    def cluster(self, prompt: str, pages: Optional[List[int]] = None) -> Dict[str, ClusterInfo]:
        """Кластеризовать страницы по смыслу"""

    def extract(self, prompt: str, pages: List[int]) -> Dict[str, Any]:
        """Извлечь информацию по запросу"""

    def describe_full(
        self,
        prompt: Optional[str] = None,
        pages: Optional[List[int]] = None
    ) -> DocumentData:
        """Полное описание (контракт для 07_agentic-doc-processing)"""

    # State management (автоматический, неявный для пользователя)
    def _save_state(self):
        """Сохранить текущее состояние"""

    def _load_state(self):
        """Загрузить состояние"""
```

**Ключевое поведение**:
- При инициализации с `state_dir`: пытается загрузить существующее состояние
- После каждой операции: автоматически сохраняет изменения
- Без `state_dir`: работает в stateless режиме

---

### 2. VLM Agent (агент)

**Назначение**: AI-агент с функцией вызова инструментов (OCR Tool).

**Расположение**: `vlm_ocr_doc_reader/core/vlm_agent.py`

**Архитектура**:
```python
class BaseVLMAgent(ABC):
    """Базовый интерфейс для VLM-агента"""

    @abstractmethod
    def ask(
        self,
        prompt: str,
        images: List[bytes],
        tools: Optional[List[Tool]] = None,
        history: Optional[List[Message]] = None
    ) -> VLMAgentResponse:
        """
        Задать вопрос VLM с возможностью function calling.

        Args:
            prompt: Текстовый запрос
            images: Список PNG-изображений
            tools: Список доступных tools (например, OCR)
            history: История диалога

        Returns:
            VLMAgentResponse с полем `tool_calls` для вызова OCR
        """


class GeminiVLMAgent(BaseVLMAgent):
    """Реализация через Google Gemini API"""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        min_interval_s: float = 0.6,  # Throttling
        max_retries: int = 3
    ):
        self.api_key = api_key
        self.model = model
        self.throttler = Throttler(min_interval_s)
        self.retry_handler = RetryHandler(max_retries)

    def ask(self, prompt, images, tools=None, history=None):
        # 1. Throttling
        self.throttler.wait()

        # 2. Если есть tools/history → generate_content_with_tools
        # 3. Иначе → generate_content (JSON mode)

        # 4. Retry logic для 429/5xx
        return self._call_with_retry(...)
```

**Ключевое отличие от "клиента"**:
- **Agent**: Умеет function calling, имеет историю диалога, принимает решения о вызове tools
- **Tool**: Исполняет конкретную задачу (OCR) по запросу агента

**Паттерн взаимодействия**:
```
VLM Agent → решает что нужно вызвать OCR
         → вызывает Tool (ask_ocr)
         → получает результат
         → формирует финальный ответ
```

---

### 3. OCR Tool (инструмент)

**Назначение**: Специализированный tool для точного извлечения данных.

**Расположение**: `vlm_ocr_doc_reader/core/ocr_tool.py`

**Архитектура**:
```python
class BaseOCRTool(ABC):
    """Базовый интерфейс для OCR-инструмента"""

    @abstractmethod
    def extract(
        self,
        image: bytes,
        question: str,
        expected_type: Optional[str] = None
    ) -> OCRResult:
        """
        Извлечь значение из изображения.

        Args:
            image: Одно PNG-изображение
            question: Конкретный вопрос ("найди ОГРН на этой странице")
            expected_type: "digits", "fio", etc.

        Returns:
            OCRResult {
                status: "ok" | "no_data" | "error",
                value: "извлеченное значение",
                context: "фрагмент текста",
                explanation: "пояснение"
            }
        """


class QwenOCRTool(BaseOCRTool):
    """Реализация через Alibaba Qwen VL (Dashscope)"""

    def extract(self, image, question, expected_type=None):
        # 1. Формирует OCR-specific prompt
        prompt = self._build_ocr_prompt(question)

        # 2. Вызывает Qwen API
        response = self._call_qwen_api(image, prompt)

        # 3. Парсит формат ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ
        parsed = self._parse_response(response)

        # 4. Нормализация (для expected_type="digits")
        if expected_type == "digits":
            parsed.value = normalize_digits(parsed.value)

        return parsed
```

**Формат ответа** (из 05_a_reports_ETL_02):
```
ЗНАЧЕНИЕ: <значение или НЕТ>
КОНТЕКСТ: <фрагмент текста>
ПОЯСНЕНИЕ: <как искал и что нашел>
```

**Нормализация цифр**: `O→0, o→0, l→1, I→1, S→5, B→8`

---

### 4. Operations (операции)

**Назначение**: Plug-and-play модули для различных задач обработки документов.

**Расположение**: `vlm_ocr_doc_reader/operations/`

#### Базовый интерфейс
```python
class BaseOperation(ABC):
    """Базовая операция над документом"""

    @abstractmethod
    def execute(
        self,
        processor: DocumentProcessor,
        prompt: str,
        pages: Optional[List[int]] = None,
        **kwargs
    ) -> Any:
        """Выполнить операцию"""
```

#### TriageOperation
```python
class TriageOperation(BaseOperation):
    """Поиск релевантных страниц по промпту"""

    def execute(self, processor, prompt, pages=None, max_pages=20):
        # 1. Батчинг по страницам (из конфига)
        # 2. Вызов VLM с prompt
        # 3. Парсинг номеров страниц из ответа
        # 4. Сохранение результата в state_dir/data/triage/*.json
        return selected_pages
```

#### ClusteringOperation
```python
class ClusteringOperation(BaseOperation):
    """Смысловая кластеризация страниц"""

    def execute(self, processor, prompt, pages=None):
        # 1. Вызов VLM с prompt
        # 2. Парсинг кластеров
        # 3. Сохранение в state_dir/data/clusters/*.yaml
        return {cluster_name: ClusterInfo(...)}
```

#### ExtractionOperation
```python
class ExtractionOperation(BaseOperation):
    """Извлечение информации по запросу"""

    def execute(self, processor, prompt, pages):
        # 1. Подготовка batch prompts
        # 2. Вызов VLM Agent (может вызывать OCR Tool)
        # 3. Агрегация результатов
        # 4. Сохранение в state_dir/data/extractions/*.yaml
        return extracted_data
```

#### FullDescriptionOperation (контракт)
```python
class FullDescriptionOperation(BaseOperation):
    """Полное описание документа для 07_agentic-doc-processing"""

    def execute(
        self,
        processor,
        prompt=None,  # Опциональный кастомный prompt
        pages=None
    ) -> DocumentData:
        """
        Возвращает DocumentData {
            text: str,  # Полный текст
            structure: {headers: [...]},  # Заголовки
            tables: [...]  # С cell flattening
        }
        """
        # 1. Batch prompts:
        #    - "Верни весь текст"
        #    - "Опиши структуру (заголовки)"
        #    - "Найди таблицы, классифицируй, сделай cell flattening"
        #
        # 2. Вызов VLM Agent
        # 3. Агрегация в DocumentData
        # 4. Сохранение в state_dir/data/full_description.yaml

        return DocumentData(...)
```

---

### 5. Preprocessing (предпроцессинг)

**Расположение**: `vlm_ocr_doc_reader/preprocessing/`

#### PDFRenderer
```python
class PDFRenderer:
    """Конвертация PDF → PNG с настраиваемым DPI"""

    def __init__(self, dpi: int = 150, quality: int = 85):
        self.dpi = dpi
        self.quality = quality

    def render(
        self,
        pdf_path: str,
        page_indices: Optional[List[int]] = None
    ) -> List[Tuple[int, bytes]]:
        """
        Рендеринг страниц.

        Returns:
            List[(page_number, png_bytes)]
        """
        # Используем PyMuPDF (fitz)
        # Сохраняет в state_dir/pages/ если задан
```

**Особенности**:
- DPI: параметр рендеринга, не глобальной конфигурации
- Автоматическое удаление alpha-канала
- Кэширование в state_dir/pages/

#### PageNumberer (новый компонент)
```python
class PageNumberer:
    """Добавление визуальных номеров на страницы"""

    def __init__(
        self,
        position: str = "bottom_right",  # top_left, top_right, bottom_left, bottom_right
        font_size: int = 12,
        opacity: float = 0.7
    ):
        self.position = position
        self.font_size = font_size
        self.opacity = opacity

    def add_numbers(
        self,
        images: List[Tuple[int, bytes]]
    ) -> List[Tuple[int, bytes]]:
        """
        Добавить номера на изображения.

        Args:
            images: List[(page_number, png_bytes)]

        Returns:
            List[(page_number, png_bytes_with_number)]
        """
        # Использует PIL/Pillow
        # Наносит номер в указанную позицию
```

**Зачем нужно**:
- VLM может путаться в нумерации документа
- Визуальные номера дают детерминированную ссылку на страницу
- Помогает при восстановлении контекста

#### CacheManager
```python
class CacheManager:
    """Управление кэшем страниц и результатов"""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        self.pages_cache = Path(cache_dir) / "pages"
        self.results_cache = Path(cache_dir) / "results"

    def get_pages(self, source) -> List[bytes]:
        """Возвращает страницы из кэша или рендерит"""

    def save_result(self, operation: str, data: Any):
        """Сохраняет результат операции"""

    def load_result(self, operation: str) -> Optional[Any]:
        """Загружает кэшированный результат"""
```

---

### 6. State Management (управление состоянием)

**Расположение**: `vlm_ocr_doc_reader/core/state.py`

#### DocumentState
```python
@dataclass
class DocumentState:
    """Состояние обработки документа"""

    # Метаданные
    source: Union[str, List[bytes]]
    created_at: str
    updated_at: str

    # Страницы
    pages_rendered: List[int]  # Какие страницы отрендерены
    pages_metadata: Dict[int, PageInfo]  # Метаданные страниц

    # Кэшированные результаты
    triage_results: Dict[str, List[int]]  # {prompt: [pages]}
    clusters: Dict[str, ClusterInfo]
    extractions: Dict[str, Any]
    full_description: Optional[DocumentData]

    # Конфигурация (для воспроизводимости)
    config: Dict[str, Any]

    def save(self, state_dir: str):
        """Сохранить состояние"""
        # Технические данные → JSON
        # Контент (results) → YAML

    @classmethod
    def load(cls, state_dir: str) -> "DocumentState":
        """Загрузить состояние"""
```

#### Структура state_dir
```
state_dir/
├── pages/                    # Рендеренные PNG с номерами
│   ├── page_001.png
│   ├── page_002.png
│   └── ...
├── cache/                    # Кэш VLM ответов
│   ├── vlm_response_abc123.json
│   └── ...
├── data/                     # Результаты операций
│   ├── triage/
│   │   └── triage_001.json
│   ├── clusters/
│   │   └── clusters_001.yaml
│   ├── extractions/
│   │   └── extraction_001.yaml
│   └── full_description.yaml
├── logs/                     # Логи
│   └── vlm_ocr.log
└── state.json                # Техническое состояние
```

#### Автоматическое сохранение
```python
class DocumentProcessor:
    def _after_operation_hook(self, operation_name: str, result: Any):
        """Автоматически вызывается после каждой операции"""
        if self.state_dir:
            # 1. Сохранить результат
            self.cache_manager.save_result(operation_name, result)

            # 2. Обновить DocumentState
            self.state.update_operation(operation_name, result)

            # 3. Сохранить state.json
            self.state.save(self.state_dir)
```

**Ключевое поведение**:
- Пользователь НЕ вызывает явно `save_state()`
- Сохранение происходит автоматически после каждой операции
- При повторном создании `DocumentProcessor(source, state_dir=...)` состояние загружается автоматически

---

### 7. Batching (батчинг по страницам)

**Расположение**: `vlm_ocr_doc_reader/utils/batching.py`

**Подход из 05_a_reports_ETL_02**:
```python
class PageBatcher:
    """Разбиение страниц на батчи для VLM"""

    def __init__(
        self,
        batch_size: int = 10,  # Количество страниц в батче
        overlap: int = 2       # Перекрытие между батчами
    ):
        self.batch_size = batch_size
        self.overlap = overlap

    def create_batches(
        self,
        pages: List[int]
    ) -> List[List[int]]:
        """
        Создать батчи страниц.

        Examples:
            pages=[1,2,3,4,5,6,7,8], batch_size=3, overlap=1
            → [[1,2,3], [3,4,5], [5,6,7], [7,8]]
        """
        batches = []
        for i in range(0, len(pages), self.batch_size - self.overlap):
            batch = pages[i:i + self.batch_size]
            if batch:
                batches.append(batch)
        return batches
```

**Применение**:
```python
# В операции
batcher = PageBatcher(batch_size=10, overlap=2)
batches = batcher.create_batches(selected_pages)

results = []
for batch in batches:
    batch_images = [self.pages[p] for p in batch]
    result = self.vlm_agent.ask(prompt, batch_images)
    results.append(result)

# Агрегация результатов
final_result = self._aggregate_results(results)
```

**Почему не по токенам**:
- Из 05_a_reports_ETL_02: автоматическое лимитирование токенов создавало проблемы
- Модель пыталась уложиться в лимит и теряла качество
- Прямое управление количеством страниц дает предсказуемость

---

### 8. Schemas (схемы данных)

**Расположение**: `vlm_ocr_doc_reader/schemas/`

#### DocumentData (контракт)
```python
@dataclass
class DocumentData:
    """
    Полные данные документа.
    КОНТРАКТ для 07_agentic-doc-processing
    """
    text: str  # Обязательное: полный текст
    structure: Dict[str, Any]  # Обязательное: {headers: [...]}
    tables: List[Dict[str, Any]] = field(default_factory=list)  # Опциональное


@dataclass
class HeaderInfo:
    """Заголовок документа"""
    level: int  # 1, 2, 3...
    title: str
    page: int


@dataclass
class TableInfo:
    """Информация о таблице"""
    id: str
    type: str  # "NUMERIC" или "TEXT_MATRIX"
    page: int
    location: Dict[str, Any]  # {x1, y1, x2, y2, page}
    preview: str  # Краткое описание
    cell_flattened: Optional[List[str]] = None  # Для TEXT_MATRIX
```

#### Прочие схемы
```python
@dataclass
class ClusterInfo:
    """Кластер страниц"""
    name: str
    pages: List[int]
    description: str
    created_at: Optional[str] = None


@dataclass
class PageInfo:
    """Метаданные страницы"""
    page_number: int
    source_file: str
    rendered_at: str
    has_number: bool  # Добавлен ли визуальный номер
    dpi: int
```

---

## Принципы взаимодействия

### 1. VLM Agent ↔ OCR Tool

```
┌──────────────────────────────────────────────────────────┐
│ VLM Agent                                                │
│                                                          │
│  1. Получает prompt + images                             │
│  2. Формирует запрос с function calling:                │
│     "У тебя есть tool ask_ocr для точного извлечения"    │
│  3. Вызывает Gemini API                                 │
│  4. Если VLM решает вызвать OCR:                        │
│     → Возвращает tool_calls: [{name: "ask_ocr", ...}]   │
│  5. VLM Agent выполняет tool_calls:                     │
│     → Вызывает OCR Tool                                 │
│     → Получает результат                                │
│     → Повторно вызывает VLM с tool_results              │
│  6. Формирует финальный ответ                           │
└──────────────────────────────────────────────────────────┘
```

### 2. Operations ↔ DocumentProcessor

```
Operation.execute(processor, prompt, pages)
        ↓
    1. Получает страницы из processor.pages
    2. Создает батчи (PageBatcher)
    3. Вызывает processor.vlm_agent.ask()
    4. Агрегирует результаты
    5. processor._save_state() (автоматически)
        ↓
    Возвращает результат
```

### 3. State Management

**Создание с state_dir**:
```python
processor = DocumentProcessor(
    source="report.pdf",
    state_dir="03_data/doc_state"
)
# ↓ Автоматически загружает состояние если есть
# ↓ Если нет — создает новое
```

**Выполнение операций**:
```python
pages = processor.triage("найди таблицы")
# ↓ Выполняет TriageOperation
# ↓ Автоматически сохраняет в state_dir/data/triage/*.json
# ↓ Автоматически обновляет state.json
```

**Повторное создание**:
```python
processor2 = DocumentProcessor(
    source="report.pdf",
    state_dir="03_data/doc_state"
)
# ↓ Загружает сохраненное состояние
# ↓ Можно продолжить работу с того же места
```

---

## Технологический стек

### Ядро
- **Python**: ≥3.10
- **Pydantic**: Валидация данных и схемы
- **dataclasses**: Структуры данных

### VLM
- **Google Gemini**: gemini-2.5-flash (по умолчанию)
- **google-generativeai**: Клиентская библиотека
- **Будущее**: Claude, GPT-4V

### OCR
- **Alibaba Qwen VL**: qwen-vl-plus (по умолчанию)
- **openai**: OpenAI-совместимый API
- **Будущее**: Tesseract, EasyOCR

### PDF Processing
- **PyMuPDF (fitz)**: Рендеринг PDF → PNG
- **Pillow**: Манипуляции с изображениями

### Storage
- **JSON**: Технические данные (state, metadata)
- **YAML**: Результаты анализа (человекочитаемые)

### Логирование
- **logging**: Стандартная библиотека
- **stdout + file**: Двойной вывод

---

## Ограничения и допущения

### v0.1.0 (MVP)

**Что включено**:
- GeminiVLMAgent + QwenOCRTool
- 4 базовые операции (Triage, Clustering, Extraction, FullDescription)
- State management (JSON/YAML)
- PDF рендеринг с PageNumberer
- Батчинг по страницам

**Что НЕ включено**:
- Автоматический batching по токенам (резервный вариант)
- Дополнительные VLM/OCR клиенты
- Сложный triage algorithm (из 05_a_reports_ETL_02)
- Batch processing нескольких документов

### Будущие версии

**v0.2.0**: Сложный triage algorithm
**v0.3.0**: Claude VLM клиент
**v0.4.0**: Кэширование результатов извлечения
**v0.5.0**: Batch processing для нескольких документов

---

## Интеграционные точки

### С 05_a_reports_ETL_02 (переиспользование)

**Что берем**:
- Throttling логика (VLMClient)
- Retry с exponential backoff (GeminiRestClient)
- OCR формат ответа (ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ)
- PDF рендеринг (pdf_utils.py)

**Что НЕ берем**:
- Field processors (специфично для аудита)
- HybridDialogueManager (сложно для универсального модуля)

### С 07_agentic-doc-processing (контракт)

**Метод интеграции**:
```python
# В 07_agentic-doc-processing
vlm_ocr_module = DocumentProcessor(source=pdf_path)
document_data = vlm_ocr_module.describe_full()

# document_data → DocumentSkeleton
```

**Критичные данные**:
- `DocumentData.text`: Полный текст
- `DocumentData.structure.headers`: Иерархия заголовков
- `DocumentData.tables`: С cell flattening для TEXT_MATRIX

---

## Метрики качества

### Производительность
- Throttling: 0.6s между вызовами VLM
- Рендеринг: ~0.5s per page (DPI=150)
- Кэширование: Пропускает повторные вызовы

### Надежность
- Retry logic: 3 попытки с backoff
- Graceful degradation: OCR опционален
- State recovery: После сбоя можно продолжить

### Точность
- VLM: Понимание контекста, структура
- OCR: Точность для чисел, идентификаторов
- Нормализация: O→0, l→1, S→5, B→8

---

## TODO (архитектурные решения для принятия)

### ADR-001: Формат storage
**Вопрос**: Подготовиться к будущему перехвату в БД
**Решение**: Абстрагировать storage интерфейс

### ADR-002: Batch size по умолчанию
**Вопрос**: Какой batch_size использовать по умолчанию?
**Варианты**: 5, 10, 20 страниц

### ADR-003: PageNumberer по умолчанию
**Вопрос**: Включать ли нумерацию страниц по умолчанию?
**Варианты**: Всегда включено, опционально, никогда

---

## Связанные документы

- `vlm_ocr_doc_reader_spec.md`: Исходная спецификация
- `00_docs/backlog.md`: Реестр задач
- `05_a_reports_ETL_02/`: Опытная реализация (для изучения)
- `07_agentic-doc-processing/`: Потребитель модуля
