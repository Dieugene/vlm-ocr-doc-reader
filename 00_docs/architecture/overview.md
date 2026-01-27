# Архитектура проекта vlm-ocr-doc-reader

**Версия:** 1.0
**Дата:** 2025-01-27
**Статус:** Черновик архитектуры

---

## 1. Концептуальная модель

### Разделение Agent vs Client

Модуль базируется на концептуальном разделении агентского и технического уровней:

- **VLM Agent** - агентская сущность (промпты, tool calling loop, инструменты)
- **VLM Client** - техническая реализация (REST/SDK, throttling, retry)
- **OCR Tool** - агентская сущность (алгоритм вызова, конфигурация)
- **OCR Client** - техническая реализация OCR API

```mermaid
graph TB
    subgraph "DocumentProcessor"
        DP[DocumentProcessor]

        subgraph "VLM Agent"
            Agent[VLM Agent]
            Prompts[System/User Prompts]
            Tools[Available Tools]
            Loop[Tool Calling Loop<br/>max 10 iterations]
        end

        subgraph "VLM Client"
            VLMClient[VLM Client]
            VLM_API[REST/SDK]
            VLM_Throttle[Throttling]
            VLM_Retry[Retry Logic]
        end

        subgraph "OCR Tool"
            OCRTool[OCR Tool]
            OCRAlgo[Algorithm]
        end

        subgraph "OCR Client"
            OCRClient[OCR Client]
            OCR_API[REST/SDK]
            OCR_Throttle[Throttling]
            OCR_Retry[Retry Logic]
        end

        DP --> Agent
        Agent --> Prompts
        Agent --> Tools
        Agent --> Loop
        Agent -.uses.-> VLMClient
        VLMClient --> VLM_API
        VLMClient --> VLM_Throttle
        VLMClient --> VLM_Retry

        Tools --> OCRTool
        OCRTool --> OCRAlgo
        OCRTool -.uses.-> OCRClient
        OCRClient --> OCR_API
        OCRClient --> OCR_Throttle
        OCRClient --> OCR_Retry

        Loop -.calls.-> Tools
    end

    subgraph "Operations"
        Ops[Operations]
    end

    DP --> Ops
    Ops -.uses.-> Agent
```

### Ключевые принципы

1. **Agent → Client relation**: VLM Agent использует VLM Client, OCR Tool использует OCR Client
2. **Tool Calling Loop**: VLM → tool call → выполнить tool → вернули в VLM → повтор до max 10 итераций
3. **Все клиенты имеют retry-логику**
4. **OCR Tool** - отдельная сущность, используется VLM Agent через tools
5. **Прямой вызов OCR** - не поддерживается (только через VLM Agent)

---

## 2. Структура модулей

> **📢 Оговорка для Tech Lead:**
>
> Привет! Это предложение структуры от Architect. Ты волен корректировать состав файлов и организацию модулей исходя из результатов твоего анализа.
>
> **ВАЖНО:** Ориентируйся на проект `05_a_reports_ETL_02` - там уже есть рабочая реализация VLM/OCR клиентов, рендеринга PDF, батчинга. Переиспользуй паттерны.
>
> **⚠️ Если у тебя нет доступа к `05_a_reports_ETL_02` или `07_agentic-doc-processing`** - остановись и запроси доступ у пользователя.
>
> -- Architect

```
vlm_ocr_doc_reader/
├── __init__.py                    # Public API: UniversalDocumentProcessor
│
├── core/
│   ├── __init__.py
│   ├── processor.py               # DocumentProcessor (главный класс)
│   ├── vlm_agent.py               # VLMAgent (промпты, tool calling loop)
│   ├── vlm_client.py              # BaseVLMClient, GeminiVLMClient
│   ├── ocr_tool.py                # OCRTool (алгоритм вызова)
│   ├── ocr_client.py              # BaseOCRClient, QwenOCRClient
│   └── state.py                   # DocumentState, StorageBackends (memory/disk)
│
├── operations/
│   ├── __init__.py
│   ├── base.py                    # BaseOperation (абстрактный класс)
│   ├── full_description.py        # FullDescriptionOperation (контракт для 07)
│   ├── clustering.py              # ClusteringOperation
│   ├── triage.py                  # TriageOperation
│   └── extraction.py              # ExtractionOperation
│
├── preprocessing/
│   ├── __init__.py
│   ├── renderer.py                # PDFRenderer (pdf → png)
│   └── page_numberer.py           # PageNumberer (нумерация страниц, future)
│
├── schemas/
│   ├── __init__.py
│   ├── document.py                # DocumentData (контракт), TableInfo, HeaderInfo
│   ├── common.py                  # PageInfo, ClusterInfo, TriageResult
│   └── config.py                  # ProcessorConfig, VLMConfig, OCRConfig
│
└── utils/
    ├── __init__.py
    ├── batching.py                # PageBatching (из 05_a_reports_ETL_02)
    ├── normalization.py           # OCRNormalization (O→0, l→1)
    └── logging.py                 # Logger setup
```

---

## 3. Ключевые архитектурные решения

### 3.1. Operations Organization

**⚠️ ВАЖНО: Правильный подход к работе с operations**

**Никаких** методов вида `processor.full_description()`, `processor.cluster()`, etc.!

**Только** подход через импорт и вызов `.execute()`:

```python
from vlm_ocr_doc_reader.operations import TriageOperation, ClusteringOperation, FullDescriptionOperation

# Операции импортируются как классы
triage = TriageOperation(processor)
cluster = ClusteringOperation(processor)
full_desc = FullDescriptionOperation(processor)

# Вызов через .execute()
result = triage.execute(prompt="найди страницы с таблицами")
result = cluster.execute(prompt="сгруппируй по смыслу")
result = full_desc.execute()
```

**Принятый подход:** Operations импортируются как самостоятельные классы, при создании получают экземпляр процессора

```python
from vlm_ocr_doc_reader.operations import TriageOperation, ClusteringOperation

# Операции импортируются как классы
triage = TriageOperation(processor)
cluster = ClusteringOperation(processor)

# Вызов напрямую
result = triage.execute(prompt="...")
```

**Обоснование:**
- Гибкость, операции независимы
- Явная связь с процессором
- Возможность использовать операции отдельно

### 3.2. State Management

**Единая точка управления:** `core/state.py`

**Стратегии хранения:**
- **Memory** - если `state_dir` не указан (по умолчанию)
- **Disk** - если указан `state_dir` (JSON/YAML)
- **Database** - future (через клиент БД)

**Архитектурный запас:** Базовый интерфейс `StorageBackend` с реализациями для memory/disk. В будущем можно добавить `DatabaseStorage`.

**Что сохраняется:**
- Рендеренные страницы (PNG)
- VLM ответы
- Результаты operations

### 3.3. Batching Strategy

**Подход:** По количеству страниц (из конфигурации клиента)

**Обоснование:**
- Проще и надежнее чем токен-лимиты
- Переиспользование паттерна из `05_a_reports_ETL_02`
- Токен-лимиты ошибкоопасны (модель пытается уложиться → ошибки)

**Batch size настраивается** в конфигурации VLM/OCR клиентов.

### 3.4. Приоритеты Operations для v0.1.0

- **P0:** `FullDescriptionOperation` - контракт для `07_agentic-doc-processing`
- **P1:** `ClusteringOperation` - кластеризация страниц
- **P2:** `TriageOperation`, `ExtractionOperation` - расширенная функциональность

### 3.5. Входные данные DocumentProcessor

**Поддерживаемые форматы:**
- **PDF файл** - автоматически рендерится в PNG через preprocessing/renderer.py
- **Массив PNG** - готовые страницы, используются как есть

**Логика:**
```python
# PDF - автоматический рендеринг
processor = DocumentProcessor(source="report.pdf")
# → внутренне вызывает renderer: PDF → [PNG, PNG, ...]

# Массив PNG - используется как есть
processor = DocumentProcessor(source=[page1_png, page2_png, ...])
```

**⚠️ Важно:** DPI для рендеринга PDF настраивается иерархически (см. 3.7)

### 3.6. Auto-save и State Management (детали)

**Гибридный подход к автосохранению:**

```python
from vlm_ocr_doc_reader.operations import FullDescriptionOperation

# Auto-save ВКЛЮЧЕН по умолчанию
processor = DocumentProcessor("report.pdf", state_dir="state")  # auto_save=True

full_desc = FullDescriptionOperation(processor)
result = full_desc.execute()  # ← автоматически сохранится в state_dir/results/full_description.yaml
```

**Эксперименты без автосохранения:**

```python
# Auto-save ВЫКЛЮЧЕН
processor = DocumentProcessor("report.pdf", state_dir="state", auto_save=False)

for prompt in test_prompts:
    triage = TriageOperation(processor)
    result = triage.execute(prompt)  # ← НЕ сохраняется

# Явное сохранение только удачного результата
processor.save_state()
```

**Структура state_dir:**

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
├── logs/                   # Логи (если state_dir задан)
│   └── vlm_ocr.log
│
└── state.json              # Metadata (auto_save, DPI, etc.)
```

**Форматы хранения:**
- **Technical** (PNG, JSON) - в `cache/`
- **Content** (results) - в `results/` как YAML (человеко-читаемые)
- **Metadata** - `state.json`

### 3.7. Иерархия настроек DPI для рендеринга

**Уровни настроек (от общего к частному):**

```python
# Уровень 1: Глобальный дефолт в процессоре
processor = DocumentProcessor("report.pdf", config={
    "render_dpi": 150  # разумный дефолт для всех операций
})

# Уровень 2: Переопределение в operation
full_desc = FullDescriptionOperation(
    processor,
    render_dpi=200  # выше для точности извлечения
)

# Уровень 3: Явный вызов renderer (редкий случай)
pages = processor._render_pdf(dpi=300)
```

**Принцип:** Настройки "сверху-вниз" - дефолт можно переопределить на любом уровне.

---

## 4. Интеграционные точки

### 4.1. Контракт с 07_agentic-doc-processing

**Основной метод:** `FullDescriptionOperation.execute()` возвращает `DocumentData`

**Структура DocumentData:**
```python
@dataclass
class DocumentData:
    text: str                                    # Полный текст документа
    structure: Dict[str, Any]                    # Иерархия заголовков
    tables: List[Dict[str, Any]] = field(default_factory=list)  # Таблицы
```

**Классификация таблиц:**
- `NUMERIC` - числовые таблицы
- `TEXT_MATRIX` - текстовые матрицы (с cell flattening)

**Cell Flattening:** Преобразование ячеек в список утверждений вида "заголовок строки + заголовок столбца → содержимое"

**⚠️ Важно:** Классификацию таблиц (NUMERIC/TEXT_MATRIX) в v0.1.0 не реализуем. Все таблицы возвращаем как есть без типа. Реализуем в будущих версиях.

### 4.2. Паттерны из 05_a_reports_ETL_02

**Переиспользовать:**
- `GeminiRestClient` - базовый VLM клиент с retry, exponential backoff
- `VLMClient` - обертка с throttling (min_interval_s: 0.6)
- `QwenClient` - OCR для числовых полей с форматом ответа:
  ```
  ЗНАЧЕНИЕ: <значение>
  КОНТЕКСТ: <фрагмент текста>
  ПОЯСНЕНИЕ: <объяснение>
  ```
- `pdf_utils.py` - рендеринг PDF→PNG (DPI: 110-150, quality: 80-85)
- PageBatching - группировка страниц (head/tail/union)
- HybridDialogueManager - function calling с инструментами
- **OCR нормализация:** O→0, l→1, S→5, B→8

**НЕ переносить:**
- Специфичные поля аудиторских заключений
- Field processors (доменная логика аудита)

### 4.3. Конфигурация модуля

**Источники конфигурации (в порядке приоритета):**

1. **Переменные окружения** (для секретов):
   ```bash
   GEMINI_API_KEY=xxx
   QWEN_API_KEY=yyy
   ```

2. **При создании процессора** (основная конфигурация):
   ```python
   processor = DocumentProcessor(
       source="report.pdf",
       state_dir="03_data/state",
       auto_save=True,
       config={
           "render_dpi": 150,
           "log_level": "INFO"
       }
   )
   ```

3. **На уровне operations** (переопределение):
   ```python
   full_desc = FullDescriptionOperation(processor, render_dpi=200)
   ```

**Логирование:**
- **По умолчанию:** stdout (уровень INFO)
- **Если задан state_dir:** additionally → `state_dir/logs/vlm_ocr.log`
- **Настройка:** через `config["log_level"]` или переменную `VLM_LOG_LEVEL`

---

## 5. Ограничения v0.1.0

### Технологические ограничения

- **Только Gemini VLM** (`gemini-2.5-flash`)
- **Только Qwen OCR** (`qwen-vl-plus`)
- **Без аутентификации** - API ключи через переменные окружения
- **Хранение state** - только в памяти или в файлах (JSON/YAML)

### Функциональные ограничения

- **Простой triage** - только по промпту (без сложного алгоритма)
- **Без PageNumberer** - нумерация страниц не реализована (future)
- **Без классификации таблиц** - NUMERIC/TEXT_MATRIX не реализуем (future)
- **State management** - реализовать возможность сохранения состояния (будет использоваться при разработке и тестировании пайплайнов)

### Архитектурные ограничения

- **Без расширения клиентов** - нельзя добавить Claude VLM или Tesseract OCR
- **Без custom operations** - нельзя зарегистрировать свою операцию
- **Без batch prompts оптимизации** - последовательные вызовы

---

**История изменений:**

| Дата | Версия | Изменения | Автор |
|------|--------|-----------|-------|
| 2025-01-27 | 1.1 | Добавлены входные данные, auto-save, DPI иерархия, OCR формат, конфигурация, явный акцент на operations подход | Architect |
| 2025-01-27 | 1.0 | Черновик архитектуры | Architect |
