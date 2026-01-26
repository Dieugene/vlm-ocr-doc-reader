# Спецификация: vlm-ocr-doc-reader (универсальный модуль работы с документами)

**Версия:** 1.0
**Дата:** 2025-01-26
**Статус:** Начальная спецификация для реализации

---

## Назначение пакета

**vlm-ocr-doc-reader** — универсальный Python-пакет для работы с документами через Vision Language Models (VLM) и OCR.

**Целевая аудитория:** Проекты, требующие:
- Извлечения структурированных данных из PDF/изображений
- Анализа больших документов (сотни страниц)
- Точного извлечения чисел/идентификаторов (OCR)
- Универсального интерфейса для разных VLM/OCR моделей

**Уникальность:** Гибридный подход — VLM для понимания контекста + OCR для точности.

---

## Архитектурные принципы

### 1. Разделение VLM и OCR

```
VLM (Vision Language Model)          OCR (Optical Character Recognition)
├── Понимание контекста             ├── Точное извлечение чисел
├── Диалоги, рассуждения            ├── Точное извлечение идентификаторов
├── Структурированный вывод          ├── Нормализация (O→0, l→1)
└── Мультимодальность (текст+картинки) └── Проверка согласованности
```

### 2. Базовые интерфейсы

```python
BaseVLMClient        ← GeminiVLMClient, ClaudeVLMClient, ...
BaseOCRClient        ← QwenOCRClient, TesseractOCRClient, ...
```

### 3. Универсальный процессор

```python
UniversalDocumentProcessor
├── triage()           # Выборка страниц
├── add_cluster()      # Кластеризация страниц
├── get_cluster()      # Получение кластера
├── cluster_by_prompt()# Авто-кластеризация
├── ask_vlm()          # Вопрос к VLM
├── ask_ocr()          # Точное извлечение через OCR
└── describe_full()    # Полное описание (основной метод)
```

---

## Структура пакета

```
vlm-ocr-doc-reader/
├── pyproject.toml              # Конфигурация пакета
├── README.md                   # Документация для пользователей
├── LICENSE                     # Лицензия
│
├── vlm_ocr_doc_reader/
│   ├── __init__.py            # Публичный API
│   ├── __version__.py         # Версия
│   │
│   ├── clients/               # Клиенты VLM и OCR
│   │   ├── __init__.py
│   │   ├── base.py            # BaseVLMClient, BaseOCRClient
│   │   ├── gemini_vlm.py      # GeminiVLMClient
│   │   ├── qwen_ocr.py        # QwenOCRClient
│   │   └── config.py          # Конфигурация клиентов
│   │
│   ├── processor.py           # UniversalDocumentProcessor
│   ├── triage.py              # TriageEngine
│   ├── clustering.py          # Кластеризация страниц
│   ├── extraction.py          # Логика извлечения
│   │
│   ├── schemas/               # Pydantic модели
│   │   ├── __init__.py
│   │   ├── document.py        # DocumentData, DocumentStructure
│   │   ├── triage.py          # TriageResult
│   │   ├── cluster.py         # ClusterInfo
│   │   └── answer.py          # Answer от ask_vlm/ask_ocr
│   │
│   ├── utils/                 # Утилиты
│   │   ├── __init__.py
│   │   ├── image_utils.py     # Рендеринг, кэширование страниц
│   │   ├── normalization.py   # Нормализация цифр (для OCR)
│   │   └── logging.py         # Логирование
│   │
│   └── config.py              # Глобальная конфигурация
│
├── tests/                     # Тесты
│   ├── unit/                  # Unit-тесты
│   ├── integration/           # Интеграционные тесты
│   └── fixtures/              # Тестовые данные
│
└── examples/                  # Примеры использования
    ├── basic_usage.py
    ├── custom_vlm_client.py
    └── advanced_clustering.py
```

---

## Детальная спецификация компонентов

### 1. Базовые интерфейсы (clients/base.py)

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseVLMClient(ABC):
    """Базовый интерфейс для VLM (Vision Language Model)

    VLM используется для:
    - Понимания контекста документа
    - Извлечения структуры (заголовки, иерархия)
    - Описания схем, диаграмм, таблиц
    - Диалогов с пользователем
    """

    @abstractmethod
    def ask_vlm(
        self,
        prompt: str,
        images: List[bytes],
        tools: Optional[List[Dict]] = None,
        history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Задать вопрос VLM с изображениями.

        Args:
            prompt: Текстовый запрос
            images: Список PNG-изображений
            tools: Опциональные tools для Function Calling
            history: История диалога (для многошаговых запросов)

        Returns:
            Dict с ответом (формат зависит от реализации)
        """
        pass


class BaseOCRClient(ABC):
    """Базовый интерфейс для OCR (точное извлечение)

    OCR используется для:
    - Точного извлечения чисел (ОГРН, ИНН, суммы)
    - Точного извлечения идентификаторов
    - Нормализации оптических ошибок (O→0, l→1, S→5, B→8)
    """

    @abstractmethod
    def ask_ocr(
        self,
        image: bytes,
        question: str,
        expected_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Задать вопрос OCR для точного извлечения.

        Args:
            image: Одно PNG-изображение
            question: Конкретный вопрос ("найди ОГРН на этой странице")
            expected_type: Ожидаемый тип ("digits", "fio", etc.)

        Returns:
            {
                "status": "ok" | "no_data" | "error",
                "value": "извлеченное значение",
                "context": "фрагмент текста откуда извлечено",
                "explanation": "пояснение где нашел"
            }
        """
        pass
```

---

### 2. Реализация Gemini VLM (clients/gemini_vlm.py)

```python
from .base import BaseVLMClient
from ..utils.logging import get_logger

class GeminiVLMClient(BaseVLMClient):
    """Реализация VLM через Google Gemini API"""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        timeout: int = 60,
        max_retries: int = 3
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = get_logger(__name__)

        # Throttling параметры
        self.min_interval_s = 0.6
        self.last_call_ts = None

    def ask_vlm(
        self,
        prompt: str,
        images: List[bytes],
        tools: Optional[List[Dict]] = None,
        history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Вызов Gemini API с throttling и retry.

        Использует generate_content_with_tools() если есть tools/history,
        иначе generate_content() (JSON mode).
        """
        # Throttling
        self._throttle()

        # Подготовка запроса
        if tools or history:
            return self._call_with_tools(prompt, images, tools, history)
        else:
            return self._call_json_mode(prompt, images)

    def _throttle(self):
        """Задержка между вызовами"""
        if self.last_call_ts:
            elapsed = time.time() - self.last_call_ts
            if elapsed < self.min_interval_s:
                time.sleep(self.min_interval_s - elapsed)

    def _call_with_tools(self, prompt, images, tools, history):
        """Вызов с Function Calling"""
        # Реализация через Gemini REST API
        pass

    def _call_json_mode(self, prompt, images):
        """Вызов в JSON mode"""
        # Реализация через Gemini REST API
        pass
```

**Требования:**
- Throttling: `MIN_INTERVAL_S=0.6`
- Retry: экспоненциальный backoff для 429/5xx
- Логирование всех вызовов
- Поддержка Function Calling (tools, history)
- JSON mode для простых запросов

---

### 3. Реализация Qwen OCR (clients/qwen_ocr.py)

```python
from .base import BaseOCRClient
from ..utils.normalization import normalize_digits

class QwenOCRClient(BaseOCRClient):
    """Реализация OCR через Alibaba Qwen VL (DashScope)"""

    def __init__(
        self,
        api_key: str,
        model: str = "qwen-vl-plus",
        endpoint: Optional[str] = None
    ):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint or "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def ask_ocr(
        self,
        image: bytes,
        question: str,
        expected_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Точное извлечение через Qwen.

        Использует текстовый формат ответа:
        ЗНАЧЕНИЕ: <значение>
        КОНТЕКСТ: <фрагмент текста>
        ПОЯСНЕНИЕ: <пояснение>
        """
        # Подготовка prompt
        prompt = self._build_ocr_prompt(question)

        # Вызов API
        response = self._call_qwen_api(image, prompt)

        # Парсинг ответа
        parsed = self._parse_qwen_response(response)

        # Нормализация
        if expected_type == "digits":
            parsed["value"] = normalize_digits(parsed["value"])

        return parsed

    def _build_ocr_prompt(self, question: str) -> str:
        """Сформировать prompt для OCR"""
        return f"""
Извлеки значение из изображения: {question}

Отвечай в формате:
ЗНАЧЕНИЕ: <только значение или НЕТ>
КОНТЕКСТ: <фрагмент текста где нашел>
ПОЯСНЕНИЕ: <как искал и что нашел>
"""

    def _parse_qwen_response(self, response: str) -> Dict:
        """Парсинг ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ формата"""
        import re

        value_match = re.search(r"ЗНАЧЕНИЕ:\s*(\S+)", response)
        context_match = re.search(r"КОНТЕКСТ:\s*(.+?)(?=\nПОЯСНЕНИЕ:|$)", response, re.DOTALL)
        explanation_match = re.search(r"ПОЯСНЕНИЕ:\s*(.+)", response, re.DOTALL)

        value = value_match.group(1).strip() if value_match else ""
        context = context_match.group(1).strip() if context_match else ""
        explanation = explanation_match.group(1).strip() if explanation_match else ""

        # Определение статуса
        if value.upper() == "НЕТ" or value == "-":
            return {"status": "no_data", "value": "", "context": context, "explanation": explanation}
        elif value:
            return {"status": "ok", "value": value, "context": context, "explanation": explanation}
        else:
            return {"status": "error", "value": "", "context": "", "explanation": "failed to parse"}
```

**Требования:**
- Нормализация цифр: `O→0, o→0, l→1, I→1, S→5, B→8`
- Фильтр нецифровых символов
- Проверка длины (если expected_type="digits")
- Fallback: если формат не распознан → извлечь любые цифры

---

### 4. UniversalDocumentProcessor (processor.py)

```python
from typing import Union, List, Optional, Dict
from .clients.base import BaseVLMClient, BaseOCRClient
from .clients.gemini_vlm import GeminiVLMClient
from .clients.qwen_ocr import QwenOCRClient
from .schemas.document import DocumentData

class UniversalDocumentProcessor:
    """Универсальный процессор документов"""

    def __init__(
        self,
        source: Union[str, List[bytes]],
        vlm_client: Optional[BaseVLMClient] = None,
        ocr_client: Optional[BaseOCRClient] = None
    ):
        """
        Args:
            source: Путь к PDF или список PNG-изображений
            vlm_client: VLM клиент (по умолчанию GeminiVLMClient)
            ocr_client: OCR клиент (по умолчанию QwenOCRClient)
        """
        self.source = source
        self.vlm_client = vlm_client or self._create_default_vlm_client()
        self.ocr_client = ocr_client or self._create_default_ocr_client()

        # Кэширование страниц
        self._pages_cache: Dict[int, bytes] = {}

        # Кластеры
        self._clusters: Dict[str, ClusterInfo] = {}

    # === Triage ===
    def triage(
        self,
        prompt: str,
        method: str = "prompt",
        max_pages: int = 20
    ) -> List[int]:
        """
        Выборка страниц по промпту.

        Args:
            prompt: Описание искомых страниц ("страницы с таблицами")
            method: "prompt" — сейчас, "algorithm" — будущее
            max_pages: Максимум страниц для сканирования

        Returns:
            Список номеров страниц

        TODO: В будущем реализовать method="algorithm" из 05_a_reports_ETL_02
        """
        if method == "prompt":
            return self._triage_by_prompt(prompt, max_pages)
        else:
            raise NotImplementedError("Triage algorithm not implemented yet")

    def _triage_by_prompt(self, prompt: str, max_pages: int) -> List[int]:
        """Стартовая реализация — просто спросить VLM"""
        all_pages = self._get_all_pages()
        sample_pages = all_pages[:max_pages]

        response = self.ask_vlm(
            f"Найди страницы соответствующие: {prompt}. "
            f"Верни список номеров в формате [1, 5, 12].",
            sample_pages
        )

        return self._parse_page_numbers(response)

    # === Кластеризация ===
    def add_cluster(
        self,
        name: str,
        pages: List[int],
        description: str
    ):
        """Добавить кластер страниц"""
        self._clusters[name] = ClusterInfo(
            name=name,
            pages=pages,
            description=description
        )

    def get_cluster(self, name: str) -> ClusterInfo:
        """Получить кластер по имени"""
        if name not in self._clusters:
            raise ValueError(f"Cluster {name} not found")
        return self._clusters[name]

    def cluster_by_prompt(self, prompt: str) -> Dict[str, ClusterInfo]:
        """
        Автоматическая кластеризация по промпту.

        Args:
            prompt: "Сгруппируй страницы по смысловым блокам"

        Returns:
            {cluster_name: ClusterInfo, ...}
        """
        response = self.ask_vlm(
            f"{prompt}. Верни список кластеров с названиями, "
            f"описаниями и списками страниц.",
            self._get_all_pages()
        )

        return self._parse_clusters(response)

    # === Вопросы к документу ===
    def ask_vlm(
        self,
        prompt: str,
        images: Optional[List[bytes]] = None,
        cluster: Optional[str] = None,
        tools: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Вопрос к VLM по документу или кластеру.

        Args:
            prompt: Вопрос
            images: Изображения (по умолчанию все страницы)
            cluster: Имя кластера (если None — все страницы)
            tools: Tools для Function Calling

        Returns:
            Ответ VLM
        """
        if images is None:
            if cluster:
                cluster_info = self.get_cluster(cluster)
                images = [self._pages_cache[p] for p in cluster_info.pages]
            else:
                images = list(self._pages_cache.values())

        return self.vlm_client.ask_vlm(prompt, images, tools)

    def ask_ocr(
        self,
        question: str,
        page_num: int,
        expected_type: Optional[str] = None
    ) -> Dict:
        """
        Точное извлечение через OCR.

        Args:
            question: Конкретный вопрос ("найди ОГРН")
            page_num: Номер страницы
            expected_type: "digits", "fio", etc.

        Returns:
            {
                "status": "ok" | "no_data" | "error",
                "value": "...",
                "context": "...",
                "explanation": "..."
            }
        """
        image = self._pages_cache.get(page_num)
        if not image:
            raise ValueError(f"Page {page_num} not in cache. Call _load_pages() first.")

        return self.ocr_client.ask_ocr(image, question, expected_type)

    # === Полное описание (ОСНОВНОЙ МЕТОД) ===
    def describe_full(
        self,
        include_text: bool = True,
        include_diagrams: bool = True,
        include_tables_with_flattening: bool = True,
        pages: Optional[List[int]] = None
    ) -> DocumentData:
        """
        Полное описание документа — основной метод для интеграции.

        Args:
            include_text: Извлечь полный текст
            include_diagrams: Опиши схемы и диаграммы
            include_tables_with_flattening: Найди таблицы и сделай cell flattening
            pages: Specific страницы (None = все)

        Returns:
            DocumentData(text, structure, tables)

        Контракт для проекта 07_agentic-doc-processing.
        """
        all_pages = pages or self._get_all_pages()

        # Batch prompts для оптимизации
        prompts = []
        if include_text:
            prompts.append("Верни весь текст с этих страниц")
        if include_diagrams:
            prompts.append("Опиши все схемы, диаграммы и изображения")
        if include_tables_with_flattening:
            prompts.append("Найди все таблицы, классифицируй (NUMERIC/TEXT_MATRIX), "
                           "для TEXT_MATRIX сделай cell flattening")

        # Вызываем VLM
        results = [
            self.ask_vlm(prompt, all_pages)
            for prompt in prompts
        ]

        # Агрегируем в DocumentData
        return DocumentData(
            text=self._extract_text(results),
            structure=self._extract_structure(results),
            tables=self._extract_tables(results)
        )

    # === Внутренние методы ===
    def _get_all_pages(self) -> List[bytes]:
        """Получить все страницы (ренеринг или из источника)"""
        if isinstance(self.source, list):
            return self.source

        # Рендеринг PDF
        from ..utils.image_utils import render_pdf_to_images
        return render_pdf_to_images(self.source)

    def _create_default_vlm_client(self) -> BaseVLMClient:
        """Создать VLM клиент по умолчанию"""
        import os
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        return GeminiVLMClient(api_key=api_key)

    def _create_default_ocr_client(self) -> BaseOCRClient:
        """Создать OCR клиент по умолчанию"""
        import os
        api_key = os.environ.get("QWEN_API_KEY")
        if not api_key:
            # OCR опционален, возвращаем stub
            return StubOCRClient()

        return QwenOCRClient(api_key=api_key)
```

---

### 5. Схемы данных (schemas/document.py)

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class HeaderInfo(BaseModel):
    """Заголовок документа"""
    level: int = Field(..., description="Уровень заголовка (1, 2, 3...)")
    title: str = Field(..., description="Текст заголовка")
    page: int = Field(..., description="Номер страницы")


class DocumentStructure(BaseModel):
    """Структура документа"""
    headers: List[HeaderInfo] = Field(default_factory=list)


class TableInfo(BaseModel):
    """Информация о таблице"""
    id: str = Field(..., description="Уникальный ID")
    type: str = Field(..., description="NUMERIC или TEXT_MATRIX")
    page: int = Field(..., description="Номер страницы")
    location: Dict[str, Any] = Field(..., description="bbox {x1, y1, x2, y2, page}")
    preview: str = Field(..., description="Краткое описание")
    cell_flattened: Optional[List[str]] = Field(
        None,
        description="Cell flattening для TEXT_MATRIX"
    )


class DocumentData(BaseModel):
    """Полные данные документа — КОНТРАКТ для 07_agentic-doc-processing"""

    text: str = Field(..., description="Полный текст документа")
    structure: DocumentStructure = Field(..., description="Структура (заголовки)")
    tables: List[TableInfo] = Field(
        default_factory=list,
        description="Список таблиц с cell flattening"
    )
```

---

### 6. Другие схемы (schemas/triage.py, schemas/cluster.py)

```python
# triage.py
class TriageResult(BaseModel):
    """Результат triage"""
    prompt: str
    selected_pages: List[int]
    confidence: str  # "high" | "medium" | "low"


# cluster.py
class ClusterInfo(BaseModel):
    """Информация о кластере страниц"""
    name: str
    pages: List[int]
    description: str
    created_at: Optional[str] = None


# answer.py
class Answer(BaseModel):
    """Ответ от ask_vlm или ask_ocr"""
    status: str  # "ok" | "no_data" | "error"
    value: Optional[str]
    reasoning: List[str] = Field(default_factory=list)
    context: Optional[str] = None
    explanation: Optional[str] = None
```

---

## Зависимости пакета

### pyproject.toml

```toml
[project]
name = "vlm-ocr-doc-reader"
version = "0.1.0"
description = "Universal VLM-OCR document processing module"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.0.0",
    "requests>=2.31.0",
    "python-dotenv",
    "pillow",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov",
    "black",
    "ruff",
    "mypy",
]

gemini = [
    "google-generativeai",
]

qwen = [
    "openai",  # Qwen uses OpenAI-compatible API
]

all = [
    "vlm-ocr-doc-reader[gemini,qwen,dev]",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## Тестирование

### Unit-тесты (tests/unit/)

```python
# tests/unit/test_base_clients.py
def test_base_vlm_client_interface():
    """Проверить что BaseVLMClient требует ask_vlm"""
    assert hasattr(BaseVLMClient, 'ask_vlm')

# tests/unit/test_gemini_vlm.py
def test_gemini_vlm_throttling():
    """Проверить throttling между вызовами"""
    client = GeminiVLMClient(api_key="test")
    # Mock API calls
    # Проверить интервалы

# tests/unit/test_qwen_ocr.py
def test_qwen_ocr_normalization():
    """Проверить нормализацию цифр"""
    from vlm_ocr_doc_reader.utils.normalization import normalize_digits
    assert normalize_digits("O123l456B89") == "0123456889"
```

### Интеграционные тесты (tests/integration/)

```python
# tests/integration/test_full_pipeline.py
def test_describe_full_with_mock_vlm():
    """Проверить describe_full с моком VLM"""
    processor = UniversalDocumentProcessor(
        source="tests/fixtures/sample.pdf",
        vlm_client=MockVLMClient(),
        ocr_client=MockOCRClient()
    )

    result = processor.describe_full(
        include_text=True,
        include_diagrams=True,
        include_tables_with_flattening=True
    )

    assert isinstance(result, DocumentData)
    assert result.text != ""
    assert len(result.structure.headers) > 0
```

---

## Примеры использования (examples/)

### basic_usage.py

```python
from vlm_ocr_doc_reader import UniversalDocumentProcessor

# Создание процессора
processor = UniversalDocumentProcessor(source="report.pdf")

# Полное описание (основной метод)
data = processor.describe_full(
    include_text=True,
    include_diagrams=True,
    include_tables_with_flattening=True
)

print(f"Text length: {len(data.text)}")
print(f"Headers: {len(data.structure.headers)}")
print(f"Tables: {len(data.tables)}")
```

### advanced_clustering.py

```python
from vlm_ocr_doc_reader import UniversalDocumentProcessor

processor = UniversalDocumentProcessor(source="regulation.pdf")

# Triage — найти страницы с финансовыми таблицами
financial_pages = processor.triage("страницы с финансовыми таблицами")

# Кластеризация
processor.add_cluster(
    name="financial_statements",
    pages=financial_pages,
    description="Финансовые отчеты и таблицы"
)

# Вопрос по кластеру
answer = processor.ask_vlm(
    prompt="Какие показатели представлены в этих таблицах?",
    cluster="financial_statements"
)

print(answer)
```

### custom_vlm_client.py

```python
from vlm_ocr_doc_reader import UniversalDocumentProcessor
from vlm_ocr_doc_reader.clients import BaseVLMClient

# Своя реализация VLM клиента
class ClaudeVLMClient(BaseVLMClient):
    def ask_vlm(self, prompt, images, tools=None, history=None):
        # Реализация через Claude API
        pass

# Использование
processor = UniversalDocumentProcessor(
    source="document.pdf",
    vlm_client=ClaudeVLMClient(api_key="...")
)

data = processor.describe_full()
```

---

## Конфигурация

### Через переменные окружения (.env)

```bash
# VLM (Gemini)
GEMINI_API_KEY=your_gemini_key
VLM_MODEL=gemini-2.5-flash
VLM_MIN_INTERVAL_S=0.6
VLM_MAX_RETRIES=3

# OCR (Qwen)
QWEN_API_KEY=your_qwen_key
OCR_MODEL=qwen-vl-plus

# Логирование
VLM_LOG_LEVEL=INFO
VLM_LOG_FILE=vlm_ocr.log
```

### Программно

```python
from vlm_ocr_doc_reader import config

config.VLM_MODEL = "gemini-2.5-pro"
config.OCR_MODEL = "qwen-vl-max"
```

---

## Документация

### README.md (структура)

```markdown
# vlm-ocr-doc-reader

Универсальный модуль работы с документами через VLM и OCR.

## Установка

\`\`\`bash
pip install vlm-ocr-doc-reader
\`\`\`

## Быстрый старт

\`\`\`python
from vlm_ocr_doc_reader import UniversalDocumentProcessor

processor = UniversalDocumentProcessor("document.pdf")
data = processor.describe_full()
\`\`\`

## Основные методы

- `triage(prompt)` — выборка страниц
- `add_cluster(name, pages, desc)` — кластеризация
- `ask_vlm(prompt, cluster)` — вопрос к VLM
- `ask_ocr(question, page_num)` — точное извлечение
- `describe_full(...)` — полное описание

## API Reference

[Ссылка на docs/]

## Примеры

См. папку `examples/`
```

---

## Критерии готовности пакета

### Обязательные для v0.1.0

- [ ] Базовые интерфейсы `BaseVLMClient`, `BaseOCRClient`
- [ ] Реализация `GeminiVLMClient` с throttling и retry
- [ ] Реализация `QwenOCRClient` с нормализацией
- [ ] `UniversalDocumentProcessor` с методами:
  - [ ] `triage(prompt)` — по промпту
  - [ ] `add_cluster()`, `get_cluster()`, `cluster_by_prompt()`
  - [ ] `ask_vlm()`, `ask_ocr()`
  - [ ] `describe_full()` — возвращает `DocumentData`
- [ ] Схемы данных (`DocumentData`, `ClusterInfo`, etc.)
- [ ] Unit-тесты для основных компонентов
- [ ] README.md с примерами
- [ ] Пакет устанавливается через pip

### Опциональные для v0.1.0

- [ ] Function Calling в GeminiVLMClient
- [ ] Сложный triage algorithm (из 05_a_reports_ETL_02)
- [ ] Кэширование страниц на диск
- [ ] Логирование в файл
- [ ] Дополнительные реализации (Claude VLM, Tesseract OCR)

### TODO на будущие версии

- [ ] v0.2.0: Сложный triage algorithm
- [ ] v0.3.0: Claude VLM клиент
- [ ] v0.4.0: Кэширование результатов извлечения
- [ ] v0.5.0: Batch processing для нескольких документов

---

## Примечания для архитектора

### Ограничения

1. **Стартовая реализация:** Triage "по промпту", без сложного алгоритма
2. **Без State Management:** Пакет stateless, кэширование только в рамках сессии
3. **Без Аутентификации:** API ключи через переменные окружения
4. **Без БД:** Все в памяти, персистентность на стороне вызывающего кода

### Будущая расширяемость

Пакет спроектирован так, чтобы:
- Добавлять новые VLM/OCR клиенты (Claude, Tesseract, etc.)
- Расширять функциональность без слома API
- Поддерживать разные use cases (аудит, регламенты, контракты)

### Связь с 05_a_reports_ETL_02

**Что переиспользуем:**
- Идея разделения VLM и OCR
- Throttling и retry логика
- Формат ответа OCR (ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ)
- Опыт работы с Gemini и Qwen

**Что НЕ переносим:**
- Специфичные поля аудиторских заключений
- HybridDialogueManager (слишком специфично)
- Field processors (доменная логика)

---

## Передача Architect отдельного проекта

Этот документ — стартовая спецификация для создания пакета `vlm-ocr-doc-reader`.

**Архитектор нового проекта должен:**
1. Изучить эту спецификацию
2. Уточнить требования при необходимости
3. Создать детальный план реализации
4. Спроектировать интерфейсы
5. Передать Analyst/Developer на реализацию

**Входные данные для архитектора:**
- `05_a_reports_ETL_02/` — опытная реализация
- Эта спецификация — требования к универсальному модулю
- Контракт `DocumentData` из `07_agentic-doc-processing`

**Ожидаемые артефакты от архитектора:**
- Детальный ADR по структуре пакета
- Схемы интерфейсов (если отличаются от этой спецификации)
- Plan реализации для Analyst/Developer
