# Backlog проекта vlm-ocr-doc-reader

**Версия:** 1.0
**Дата:** 2025-01-27
**Статус:** Формирование

---

## Легенда

| ID | Название | Приоритет | Статус | Дата начала | Дата завершения |
|----|----------|-----------|--------|-------------|-----------------|
| 001 | ... | High/Medium/Low | Todo/In Progress/Done | YYYY-MM-DD | YYYY-MM-DD |

**Приоритеты**:
- **High**: Критично для v0.1.0 MVP
- **Medium**: Важно, но может быть отложено
- **Low**: Улучшения, оптимизации

**Статусы**:
- **Todo**: В backlog, не начата
- **In Progress**: В работе
- **Done**: Завершена
- **Blocked**: Заблокирована другой задачей

---

## Фаза 1: Infrastructure (Инфраструктура)

### 001 Настройка проекта и зависимостей
**Приоритет**: High
**Статус**: Todo
**Зависит от**: -

**Задача**:
- Создать структуру пакета `vlm_ocr_doc_reader/`
- Настроить `pyproject.toml` с зависимостями
- Добавить `.gitignore` (venv, .env, __pycache__, *.pyc)
- Настроить `pytest` для тестирования
- Добавить `pre-commit` hooks (black, ruff)

**Критерии готовности**:
- [ ] `pip install -e .` устанавливает пакет
- [ ] `pytest` запускается (пусть пока пустой)
- [ ] `black` и `ruff` работают

**Артефакты**:
- `pyproject.toml`
- `.gitignore`
- `vlm_ocr_doc_reader/__init__.py`

---

### 002 Базовые схемы данных (Schemas)
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 001

**Задача**:
- Создать `vlm_ocr_doc_reader/schemas/`
- Реализовать базовые Pydantic/dataclass схемы:
  - `DocumentData` (контракт для 07_agentic-doc-processing)
  - `HeaderInfo`
  - `TableInfo`
  - `ClusterInfo`
  - `PageInfo`
  - `OCRResult`

**Критерии готовности**:
- [ ] Все схемы импортируются из `vlm_ocr_doc_reader.schemas`
- [ ] `DocumentData` соответствует контракту
- [ ] Pydantic валидация работает

**Артефакты**:
- `schemas/document.py`
- `schemas/common.py`
- `schemas/__init__.py`

---

### 003 Логирование
**Приоритет**: Medium
**Статус**: Todo
**Зависит от**: 001

**Задача**:
- Создать `vlm_ocr_doc_reader/utils/logging.py`
- Реализовать `setup_logger(name, level, log_file=None)`
- Поддержка stdout + file (опционально)
- Формат: timestamp, level, module, message

**Критерии готовности**:
- [ ] Логи выводятся в stdout
- [ ] При `log_file` дублируются в файл
- [ ] Уровень логирования настраивается

**Артефакты**:
- `utils/logging.py`
- Тест в `tests/unit/test_logging.py`

---

### 004 Конфигурация
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 001, 002

**Задача**:
- Создать `vlm_ocr_doc_reader/schemas/config.py`
- Реализовать `ProcessorConfig` (Pydantic BaseModel):
  - `render_dpi: int = 150`
  - `render_quality: int = 85`
  - `batch_size: int = 10`
  - `batch_overlap: int = 2`
  - `log_level: str = "INFO"`
  - `page_numbering: bool = True`
  - `numbering_position: str = "bottom_right"`
- Чтение из `.env` через переменные окружения

**Критерии готовности**:
- [ ] Конфигурация валидируется через Pydantic
- [ ] Переменные окружения переопределяют defaults
- [ ] Можно передать программно при создании процессора

**Артефакты**:
- `schemas/config.py`
- `.env.example`
- Тест в `tests/unit/test_config.py`

---

## Фаза 2: Preprocessing (Предпроцессинг)

### 005 PDF Renderer
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 001, 004

**Задача**:
- Создать `vlm_ocr_doc_reader/preprocessing/renderer.py`
- Реализовать `PDFRenderer` (из 05_a_reports_ETL_02):
  - `render(pdf_path, page_indices=None, dpi=150, quality=85)`
  - Возвращает `List[Tuple[int, bytes]]` (page_number, png_bytes)
  - Использует PyMuPDF (fitz)
  - Автоматическое удаление alpha-канала
- Кэширование в `state_dir/pages/` (если задан)

**Критерии готовности**:
- [ ] PDF конвертируется в PNG
- [ ] DPI настраивается
- [ ] Кэширование работает (повторный вызов берет из кэша)
- [ ] Интеграционный тест с реальным PDF

**Артефакты**:
- `preprocessing/renderer.py`
- `tests/unit/test_renderer.py` (mock fitz)
- `tests/integration/test_renderer_pdf.py` (реальный PDF)

---

### 006 Page Numberer
**Приоритет**: Medium
**Статус**: Todo
**Зависит от**: 001

**Задача**:
- Создать `vlm_ocr_doc_reader/preprocessing/page_numberer.py`
- Реализовать `PageNumberer`:
  - `add_numbers(images: List[Tuple[int, bytes]]) -> List[Tuple[int, bytes]]`
  - Параметры: `position`, `font_size`, `opacity`
  - Использует PIL/Pillow
  - 4 позиции: top_left, top_right, bottom_left, bottom_right
- Наносит номер страницы на изображение

**Критерии готовности**:
- [ ] Номера добавляются на изображения
- [ ] Позиция настраивается
- [ ] Прозрачность работает
- [ ] Тест с реальными изображениями

**Артефакты**:
- `preprocessing/page_numberer.py`
- `tests/unit/test_page_numberer.py`

---

### 007 Cache Manager
**Приоритет**: Medium
**Статус**: Todo
**Зависит от**: 001

**Задача**:
- Создать `vlm_ocr_doc_reader/preprocessing/cache.py`
- Реализовать `CacheManager`:
  - `get_pages(source, renderer)` — возвращает страницы из кэша или рендерит
  - `save_result(operation, data)` — сохраняет результат операции
  - `load_result(operation)` — загружает кэшированный результат
- Управление папками: `pages/`, `cache/`, `data/`, `logs/`

**Критерии готовности**:
- [ ] Страницы кэшируются в `pages/`
- [ ] Результаты операций сохраняются
- [ ] Повторные вызовы берут из кэша

**Артефакты**:
- `preprocessing/cache.py`
- `tests/unit/test_cache.py`

---

## Фаза 3: VLM Agent & OCR Tool

### 008 Base VLM Agent Interface
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 001, 002

**Задача**:
- Создать `vlm_ocr_doc_reader/core/vlm_agent.py`
- Определить `BaseVLMAgent` (ABC):
  - `ask(prompt, images, tools=None, history=None) -> VLMAgentResponse`
  - Абстрактный метод
- Определить `VLMAgentResponse` (dataclass):
  - `content: str`
  - `tool_calls: Optional[List[ToolCall]]`

**Критерии готовности**:
- [ ] Интерфейс определен
- [ ] Нельзя создать инстанс без реализации

**Артефакты**:
- `core/vlm_agent.py`
- Тест в `tests/unit/test_vlm_agent.py`

---

### 009 Throttling & Retry Logic
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 001

**Задача**:
- Создать `vlm_ocr_doc_reader/utils/throttling.py`
- Реализовать `Throttler(min_interval_s=0.6)`
- Реализовать `RetryHandler(max_retries=3, backoff_base=1.5)`
- Jitter для backoff (0.3)

**Критерии готовности**:
- [ ] Throttler выдерживает интервалы
- [ ] RetryHandler делает exponential backoff
- [ ] Jitter работает
- [ ] Unit тесты

**Артефакты**:
- `utils/throttling.py`
- `tests/unit/test_throttling.py`

---

### 010 Gemini VLM Agent Implementation
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 008, 009

**Задача**:
- Создать `vlm_ocr_doc_reader/core/gemini_vlm_agent.py`
- Реализовать `GeminiVLMAgent(BaseVLMAgent)`:
  - Инициализация: `api_key`, `model`, `min_interval_s`, `max_retries`
  - `ask()` с throttling и retry
  - Два режима:
    - `generate_content()` (JSON mode) — без tools/history
    - `generate_content_with_tools()` (function calling) — с tools/history
  - Использует `Throttler` и `RetryHandler`
  - Обработка 429/5xx ошибок
- REST API через `google-generativeai` или `requests`

**Критерии готовности**:
- [ ] Вызовы к Gemini API работают
- [ ] Throttling соблюдается
- [ ] Retry для 429/5xx
- [ ] Function calling работает
- [ ] Интеграционный тест с реальным API (mock)

**Артефакты**:
- `core/gemini_vlm_agent.py`
- `tests/unit/test_gemini_vlm_agent.py` (mock API)
- `tests/integration/test_gemini_vlm_agent.py` (реальный API, опционально)

---

### 011 Base OCR Tool Interface
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 001, 002

**Задача**:
- Создать `vlm_ocr_doc_reader/core/ocr_tool.py`
- Определить `BaseOCRTool` (ABC):
  - `extract(image, question, expected_type=None) -> OCRResult`
  - Абстрактный метод
- Определить `OCRResult` (dataclass):
  - `status: str` ("ok" | "no_data" | "error")
  - `value: str`
  - `context: str`
  - `explanation: str`

**Критерии готовности**:
- [ ] Интерфейс определен
- [ ] `OCRResult` соответствует формату из 05_a_reports_ETL_02

**Артефакты**:
- `core/ocr_tool.py`
- Тест в `tests/unit/test_ocr_tool.py`

---

### 012 OCR Normalization Utils
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 001

**Задача**:
- Создать `vlm_ocr_doc_reader/utils/normalization.py`
- Реализовать `normalize_digits(text: str) -> str`:
  - `O, o → 0`
  - `l, I → 1`
  - `S → 5`
  - `B → 8`
  - Удаление нецифровых символов

**Критерии готовности**:
- [ ] Нормализация работает согласно правилам
- [ ] Unit тесты

**Артефакты**:
- `utils/normalization.py`
- `tests/unit/test_normalization.py`

---

### 013 Qwen OCR Tool Implementation
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 011, 012

**Задача**:
- Создать `vlm_ocr_doc_reader/core/qwen_ocr_tool.py`
- Реализовать `QwenOCRTool(BaseOCRTool)`:
  - Инициализация: `api_key`, `model="qwen-vl-plus"`, `endpoint`
  - `extract()`:
    - Формирует OCR prompt (ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ)
    - Вызывает Qwen API (OpenAI-совместимый)
    - Парсит ответ по формату
    - Нормализует цифры (если `expected_type="digits"`)
  - Проверка согласованности value и context

**Критерии готовности**:
- [ ] Вызовы к Qwen API работают
- [ ] Парсинг ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ работает
- [ ] Нормализация применяется
- [ ] Интеграционный тест с реальным API

**Артефакты**:
- `core/qwen_ocr_tool.py`
- `tests/unit/test_qwen_ocr_tool.py` (mock API)
- `tests/integration/test_qwen_ocr_tool.py` (реальный API, опционально)

---

### 014 VLM + OCR Integration (Function Calling)
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 010, 013

**Задача**:
- Создать `vlm_ocr_doc_reader/core/agent_tools.py`
- Реализовать интеграцию VLM Agent + OCR Tool:
  - Определить `ask_ocr` tool для function calling
  - Логика:
    1. VLM Agent получает prompt
    2. VLM решает вызвать OCR
    3. VLM Agent выполняет `ask_ocr`
    4. VLM Agent получает результат OCR
    5. VLM Agent формирует финальный ответ
- Промпт-инжиниринг для инструкции VLM использовать OCR

**Критерии готовности**:
- [ ] VLM Agent вызывает OCR Tool через function calling
- [ ] Интеграционный тест с реальными API

**Артефакты**:
- `core/agent_tools.py`
- `tests/integration/test_agent_tools_integration.py`

---

## Фаза 4: State Management

### 015 Document State Schema
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 002

**Задача**:
- Создать `vlm_ocr_doc_reader/core/state.py`
- Реализовать `DocumentState` (dataclass):
  - Метаданные: `source`, `created_at`, `updated_at`
  - Страницы: `pages_rendered`, `pages_metadata`
  - Результаты: `triage_results`, `clusters`, `extractions`, `full_description`
  - Конфигурация: `config`
- Методы `save(state_dir)` и `load(state_dir)`

**Критерии готовности**:
- [ ] `DocumentState` сохраняется в JSON
- [ ] `DocumentState` загружается из JSON
- [ ] Unit тесты

**Артефакты**:
- `core/state.py`
- `tests/unit/test_state.py`

---

### 016 State Persistence (JSON/YAML)
**Приоритет**: Medium
**Статус**: Todo
**Зависит от**: 015

**Задача**:
- Реализовать persistence layer:
  - Технические данные → JSON (`state.json`)
  - Контент (results) → YAML (`data/*.yaml`)
- Создать структуру папок:
  - `state_dir/pages/`
  - `state_dir/cache/`
  - `state_dir/data/{triage,clusters,extractions}/`
  - `state_dir/logs/`
- Автоматическое создание папок

**Критерии готовности**:
- [ ] State сохраняется в JSON
- [ ] Results сохраняются в YAML
- [ ] Папки создаются автоматически

**Артефакты**:
- `core/persistence.py`
- Тест в `tests/unit/test_persistence.py`

---

## Фаза 5: DocumentProcessor (ядро)

### 017 DocumentProcessor Skeleton
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 004, 015

**Задача**:
- Создать `vlm_ocr_doc_reader/core/processor.py`
- Реализовать `DocumentProcessor` (skelton):
  - `__init__(source, vlm_client=None, ocr_client=None, state_dir=None, config=None)`
  - Создание клиентов по умолчанию (если не переданы)
  - Инициализация `CacheManager`
  - Загрузка/создание `DocumentState`
- Методы-заглушки для operations

**Критерии готовности**:
- [ ] `DocumentProcessor` создается
- [ ] Клиенты по умолчанию работают (через env)
- [ ] State загружается если `state_dir` существует

**Артефакты**:
- `core/processor.py`
- `tests/unit/test_processor.py`

---

### 018 DocumentProcessor Lifecycle
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 017

**Задача**:
- Реализовать lifecycle методы:
  - `_load_state()` — загрузка состояния
  - `_save_state()` — сохранение состояния
  - `_after_operation_hook(operation, result)` — авто-сохранение
- Автоматическое сохранение после каждой операции

**Критерии готовности**:
- [ ] Состояние сохраняется после операций
- [ ] При повторном создании состояние загружается
- [ ] Unit тесты

**Артефакты**:
- Обновленный `core/processor.py`
- `tests/unit/test_processor_lifecycle.py`

---

## Фаза 6: Operations (Операции)

### 019 Base Operation Interface
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 017

**Задача**:
- Создать `vlm_ocr_doc_reader/operations/base.py`
- Определить `BaseOperation` (ABC):
  - `execute(processor, prompt, pages=None, **kwargs) -> Any`

**Критерии готовности**:
- [ ] Интерфейс определен

**Артефакты**:
- `operations/base.py`

---

### 020 Page Batching Utils
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 001

**Задача**:
- Создать `vlm_ocr_doc_reader/utils/batching.py`
- Реализовать `PageBatcher`:
  - `__init__(batch_size=10, overlap=2)`
  - `create_batches(pages: List[int]) -> List[List[int]]`
- Логика наложения (overlap) между батчами

**Критерии готовности**:
- [ ] Батчи создаются с overlap
- [ ] Unit тесты

**Артефакты**:
- `utils/batching.py`
- `tests/unit/test_batching.py`

---

### 021 Triage Operation
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 019, 020

**Задача**:
- Создать `vlm_ocr_doc_reader/operations/triage.py`
- Реализовать `TriageOperation(BaseOperation)`:
  - `execute(processor, prompt, pages=None, max_pages=20)`
  - Логика:
    1. Батчинг страниц
    2. Вызов VLM с prompt
    3. Парсинг номеров страниц из ответа
    4. Сохранение в `state_dir/data/triage/*.json`
- Добавить метод в `DocumentProcessor.triage()`

**Критерии готовности**:
- [ ] Triage находит релевантные страницы
- [ ] Результат сохраняется в state
- [ ] Интеграционный тест

**Артефакты**:
- `operations/triage.py`
- Обновление `core/processor.py` (метод `triage()`)
- `tests/integration/test_triage_operation.py`

---

### 022 Clustering Operation
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 019, 020

**Задача**:
- Создать `vlm_ocr_doc_reader/operations/clustering.py`
- Реализовать `ClusteringOperation(BaseOperation)`:
  - `execute(processor, prompt, pages=None)`
  - Логика:
    1. Батчинг страниц
    2. Вызов VLM с prompt ("сгруппируй страницы")
    3. Парсинг кластеров
    4. Сохранение в `state_dir/data/clusters/*.yaml`
- Добавить метод в `DocumentProcessor.cluster()`

**Критерии готовности**:
- [ ] Clustering группирует страницы
- [ ] `ClusterInfo` сохраняется в YAML
- [ ] Интеграционный тест

**Артефакты**:
- `operations/clustering.py`
- Обновление `core/processor.py` (метод `cluster()`)
- `tests/integration/test_clustering_operation.py`

---

### 023 Extraction Operation
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 019, 020, 014

**Задача**:
- Создать `vlm_ocr_doc_reader/operations/extraction.py`
- Реализовать `ExtractionOperation(BaseOperation)`:
  - `execute(processor, prompt, pages)`
  - Логика:
    1. Батчинг страниц
    2. Вызов VLM Agent (может вызывать OCR Tool)
    3. Агрегация результатов
    4. Сохранение в `state_dir/data/extractions/*.yaml`
- VLM Agent использует OCR Tool для чисел/идентификаторов
- Добавить метод в `DocumentProcessor.extract()`

**Критерии готовности**:
- [ ] Extraction извлекает данные
- [ ] VLM вызывает OCR для чисел
- [ ] Интеграционный тест

**Артефакты**:
- `operations/extraction.py`
- Обновление `core/processor.py` (метод `extract()`)
- `tests/integration/test_extraction_operation.py`

---

### 024 Full Description Operation (КОНТРАКТ)
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 019, 020, 014

**Задача**:
- Создать `vlm_ocr_doc_reader/operations/full_description.py`
- Реализовать `FullDescriptionOperation(BaseOperation)`:
  - `execute(processor, prompt=None, pages=None) -> DocumentData`
  - Логика:
    1. Batch prompts:
       - "Верни весь текст с этих страниц"
       - "Опиши иерархическую структуру (заголовки)"
       - "Найди все таблицы, классифицируй (NUMERIC/TEXT_MATRIX), сделай cell flattening для TEXT_MATRIX"
    2. Вызов VLM Agent
    3. Агрегация в `DocumentData`
    4. Сохранение в `state_dir/data/full_description.yaml`
- Кастомный prompt (опционально) для акцентирования аспектов
- Добавить метод в `DocumentProcessor.describe_full()`

**Критерии готовности**:
- [ ] Возвращает `DocumentData` согласно контракту
- [ ] Таблицы классифицируются на NUMERIC/TEXT_MATRIX
- [ ] Cell flattening для TEXT_MATRIX
- [ ] Интеграционный тест с реальным документом

**Артефакты**:
- `operations/full_description.py`
- Обновление `core/processor.py` (метод `describe_full()`)
- `tests/integration/test_full_description_operation.py`

---

## Фаза 7: Интеграция и полные тесты

### 025 End-to-End Test (Stateful)
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 021, 022, 023, 024

**Задача**:
- Создать `tests/integration/test_e2e_stateful.py`
- Сценарий:
  1. Создать `DocumentProcessor` с `state_dir`
  2. Выполнить `triage()`
  3. Выполнить `cluster()`
  4. Выполнить `extract()`
  5. Выполнить `describe_full()`
  6. Проверить сохранение состояния
  7. Создать новый `DocumentProcessor` с тем же `state_dir`
  8. Проверить загрузку состояния
  9. Продолжить работу

**Критерии готовности**:
- [ ] Все операции работают последовательно
- [ ] Состояние сохраняется и загружается
- [ ] Можно продолжить работу после перезапуска

**Артефакты**:
- `tests/integration/test_e2e_stateful.py`
- Тестовый PDF документ

---

### 026 End-to-End Test (Stateless)
**Приоритет**: Medium
**Статус**: Todo
**Зависит от**: 021, 022, 023, 024

**Задача**:
- Создать `tests/integration/test_e2e_stateless.py`
- Сценарий:
  1. Создать `DocumentProcessor` без `state_dir`
  2. Выполнить все операции
  3. Проверить результаты
  4. Убедиться что ничего не сохраняется на диск

**Критерии готовности**:
- [ ] Stateless режим работает
- [ ] Никаких файлов не создается

**Артефакты**:
- `tests/integration/test_e2e_stateless.py`

---

### 027 Интеграционный тест с 07_agentic-doc-processing
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 024

**Задача**:
- Создать `tests/integration/test_contract_07_integration.py`
- Сценарий:
  1. Использовать `DocumentProcessor` как ожидается в 07_agentic-doc-processing
  2. Вызвать `describe_full()`
  3. Проверить что `DocumentData` соответствует контракту
  4. Проверить cell flattening для таблиц

**Критерии готовности**:
- [ ] Контракт соблюдается
- [ ] Данные могут быть использованы в 07_agentic-doc-processing

**Артефакты**:
- `tests/integration/test_contract_07_integration.py`

---

## Фаза 8: Документация и примеры

### 028 README.md
**Приоритет**: High
**Статус**: Todo
**Зависит от**: 024

**Задача**:
- Создать `README.md` в корне проекта
- Секции:
  - Краткое описание
  - Установка (`pip install`)
  - Быстрый старт (пример кода)
  - Основные методы
  - Конфигурация
  - Ссылка на документацию

**Критерии готовности**:
- [ ] Пользователь может установить и начать использовать

**Артефакты**:
- `README.md`

---

### 029 Примеры использования (examples/)
**Приоритет**: Medium
**Статус**: Todo
**Зависит от**: 024

**Задача**:
- Создать папку `examples/`
- Примеры:
  - `basic_usage.py` — базовое использование
  - `stateful_usage.py` — с сохранением состояния
  - `custom_agent.py` — свой VLM агент
  - `advanced_clustering.py` — кластеризация

**Критерии готовности**:
- [ ] Примеры запускаются
- [ ] Покрывают основные use cases

**Артефакты**:
- `examples/basic_usage.py`
- `examples/stateful_usage.py`
- `examples/custom_agent.py`
- `examples/advanced_clustering.py`

---

### 030 API Documentation
**Приоритет**: Medium
**Статус**: Todo
**Зависит от**: Все

**Задача**:
- Создать документацию API:
  - `DocumentProcessor` — методы и параметры
  - `BaseVLMAgent` — интерфейс
  - `BaseOCRTool` — интерфейс
  - Operations — интерфейс
  - Schemas — описание структур

**Критерии готовности**:
- [ ] Документация покрывает публичный API
- [ ] Есть примеры для каждого метода

**Артефакты**:
- `docs/api.md` или docstrings в коде

---

## Фаза 9: Оптимизации и улучшения

### 031 Performance Optimization
**Приоритет**: Low
**Статус**: Todo
**Зависит от**: Все

**Задача**:
- Профилировать код
- Оптимизировать горячие точки
- Кэширование частых операций
- Асинхронные вызовы API (опционально)

**Критерии готовности**:
- [ ] Улучшение производительности на X%

**Артефакты**:
- Профилировочные отчеты
- Оптимизированный код

---

### 032 Error Handling Improvement
**Приоритет**: Medium
**Статус**: Todo
**Зависит от**: Все

**Задача**:
- Улучшить обработку ошибок
- Кастомные исключения:
  - `VLMOCRException` — базовое
  - `VLMAPIException` — ошибки VLM API
  - `OCRAPIException` — ошибки OCR API
  - `RenderingException` — ошибки рендеринга
- Graceful degradation

**Критерии готовности**:
- [ ] Ошибки обрабатываются корректно
- [ ] Пользователь получает понятные сообщения

**Артефакты**:
- `core/exceptions.py`
- Обработка ошибок в коде

---

### 033 Logging Enhancement
**Приоритет**: Low
**Статус**: Todo
**Зависит от**: 003

**Задача**:
- Добавить структурированное логирование
- Логирование всех API вызовов (prompt, response time, tokens)
- Ротация логов
- Метрики (количество вызовов, ошибки, etc.)

**Критерии готовности**:
- [ ] Логи детализированные
- [ ] Ротация работает

**Артефакты**:
- Обновленный `utils/logging.py`
- Конфигурация логирования

---

## TODO (будущие версии)

### 034 Сложный Triage Algorithm
**Приоритет**: Low
**Статус**: Todo
**Зависит от**: -

**Задача**:
- Реализовать сложный алгоритм triage из 05_a_reports_ETL_02
- Semantic similarity, embeddings
- Автоматическое определение кластеров

**Версия**: v0.2.0

---

### 035 Claude VLM Client
**Приоритет**: Low
**Статус**: Todo
**Зависит от**: -

**Задача**:
- Реализовать `ClaudeVLMAgent`
- Поддержка Claude 3.5 Sonnet

**Версия**: v0.3.0

---

### 036 Дополнительные OCR клиенты
**Приоритет**: Low
**Статус**: Todo
**Зависит от**: -

**Задача**:
- TesseractOCR
- EasyOCR

**Версия**: v0.4.0

---

### 037 Batch Processing для нескольких документов
**Приоритет**: Low
**Статус**: Todo
**Зависит от**: -

**Задача**:
- Обработка нескольких документов параллельно
- Прогресс-бар

**Версия**: v0.5.0

---

## Заметки

### Зависимости между задачами

**Критический путь**:
```
001 → 002 → 004 → 017 → 018 → 019 → 020 → 021/022/023/024 → 025/027
```

**Параллельные ветки**:
- 003 (logging) можно делать параллельно с 002
- 005, 006, 007 (preprocessing) можно делать параллельно после 001
- 008-014 (VLM/OCR) можно делать параллельно с 005-007

### Рекомендуемый порядок реализации

**Sprint 1** (Инфраструктура + Preprocessing):
- 001, 002, 003, 004
- 005, 006, 007

**Sprint 2** (VLM/OCR):
- 008, 009, 010, 011, 012, 013, 014

**Sprint 3** (State + Processor):
- 015, 016, 017, 018

**Sprint 4** (Operations):
- 019, 020, 021, 022, 023, 024

**Sprint 5** (Интеграция + Доки):
- 025, 026, 027, 028, 029, 030

### Метрики

**Всего задач**: 37
- High: 23
- Medium: 9
- Low: 5

**Завершено**: 0
**В работе**: 0
**В backlog**: 37

---

**Обновлено**: 2025-01-27
