# vlm-ocr-doc-reader

Универсальный Python-пакет для работы с документами через Vision Language Models (VLM) и OCR. Гибридный подход — VLM для понимания контекста + OCR для точности извлечения данных.

## Обзор

Пакет предназначен для проектов, требующих:
- Извлечения структурированных данных из PDF/изображений
- Анализа больших документов (сотни страниц)
- Точного извлечения чисел/идентификаторов (OCR)
- Универсального интерфейса для разных VLM/OCR моделей

## Ключевые возможности

- **Гибридный подход:** VLM для понимания контекста + OCR для точности
- **Универсальные клиенты:** BaseVLMClient и BaseOCRClient с множеством реализаций
- **Operations-based API:** Гибкие операции для различных задач анализа документов
- **State Management:** Автоматическое кэширование и сохранение результатов
- **CLI интерфейс:** Быстрая обработка документов из командной строки

## Установка

### Из GitHub

Клонируйте репозиторий и установите локально:

```bash
# Клонирование репозитория
git clone https://github.com/your-org/vlm-ocr-doc-reader.git
cd vlm-ocr-doc-reader

# Создание виртуального окружения (рекомендуется)
python -m venv .venv
source .venv/bin/activate  # На Windows: .venv\Scripts\activate

# Установка в режиме редактирования
pip install -e .
```

### Зависимости

Основные зависимости устанавливаются автоматически:
- requests>=2.31.0
- python-dotenv>=1.0.0
- Pillow>=10.0.0
- pymupdf>=1.23.0
- PyYAML>=6.0.0
- pydantic>=2.0.0

## Быстрый старт

### Базовое использование

```python
from pathlib import Path
from vlm_ocr_doc_reader import (
    GeminiVLMClient,
    VLMConfig,
    DocumentProcessor,
    ProcessorConfig,
    FullDescriptionOperation
)

# 1. Настройка VLM клиента
vlm_config = VLMConfig(api_key="ваш-gemini-api-ключ")
vlm_client = GeminiVLMClient(vlm_config)

# 2. Создание процессора с PDF файлом
processor = DocumentProcessor(
    source=Path("report.pdf"),
    vlm_client=vlm_client
)

# 3. Создание операции и выполнение
operation = FullDescriptionOperation(processor)
result = operation.execute()

# 4. Доступ к результатам
print(f"Длина текста: {len(result.text)} символов")
print(f"Найдено заголовков: {len(result.structure['headers'])}")
for header in result.structure['headers'][:5]:
    print(f"  Уровень {header['level']}: {header['title']} (стр. {header['page']})")
```

### С сохранением состояния

```python
from pathlib import Path
from vlm_ocr_doc_reader import (
    GeminiVLMClient,
    VLMConfig,
    DocumentProcessor,
    ProcessorConfig,
    FullDescriptionOperation
)

# Настройка с директорией для кэширования
vlm_config = VLMConfig(api_key="ваш-api-ключ")
processor_config = ProcessorConfig(
    state_dir=Path("./output"),
    render_dpi=150
)

processor = DocumentProcessor(
    source=Path("large_document.pdf"),
    vlm_client=vlm_client,
    config=processor_config
)

# Результаты автоматически сохранятся в ./output/results/
operation = FullDescriptionOperation(processor)
result = operation.execute()

# Структура вывода:
# ./output/
# ├── cache/
# │   ├── pages/page_001.png, page_002.png, ...
# │   └── vlm_responses/response_full_desc.json
# ├── results/
# │   └── full_description.yaml
# └── logs/
#     └── vlm_ocr.log
```

### Из массива PNG изображений

```python
from pathlib import Path
from vlm_ocr_doc_reader import GeminiVLMClient, VLMConfig, DocumentProcessor, FullDescriptionOperation

# Загрузка PNG изображений как bytes
images = [
    Path("page1.png").read_bytes(),
    Path("page2.png").read_bytes(),
    Path("page3.png").read_bytes(),
]

# Обработка из изображений
vlm_config = VLMConfig(api_key="ваш-api-ключ")
vlm_client = GeminiVLMClient(vlm_config)

processor = DocumentProcessor(source=images, vlm_client=vlm_client)
operation = FullDescriptionOperation(processor)
result = operation.execute()
```

### Использование .env файла

Создайте файл `.env` в корне проекта:

```env
GEMINI_API_KEY=ваш-gemini-api-ключ
QWEN_API_KEY=ваш-qwen-api-ключ
```

Использование в коде:

```python
from pathlib import Path
from dotenv import load_dotenv
from vlm_ocr_doc_reader import DocumentProcessor, ProcessorConfig, FullDescriptionOperation

# Загрузка переменных окружения
load_dotenv()

# API ключ будет автоматически загружен из GEMINI_API_KEY
# Не нужно передавать vlm_client - он создается автоматически!
processor = DocumentProcessor(
    source=Path("document.pdf"),
    config=ProcessorConfig(state_dir=Path("./output"))
)

operation = FullDescriptionOperation(processor)
result = operation.execute()
```

## CLI интерфейс

Быстрая обработка документов из командной строки:

```bash
# Базовое использование
python -m vlm_ocr_doc_reader.cli document.pdf

# С пользовательской директорией для вывода
python -m vlm_ocr_doc_reader.cli document.pdf --output-dir ./my_results

# С произвольным DPI для рендеринга
python -m vlm_ocr_doc_reader.cli document.pdf --dpi 200 --output-dir ./output

# С отладочным логированием
python -m vlm_ocr_doc_reader.cli document.pdf --log-level DEBUG
```

**Примечание:** Убедитесь, что `GEMINI_API_KEY` установлен в файле `.env` или в переменных окружения перед запуском CLI.

## Структура модуля

```
vlm_ocr_doc_reader/
├── core/              # Основные компоненты обработки
│   ├── processor.py   # DocumentProcessor
│   ├── vlm_client.py  # VLM клиенты (Gemini)
│   ├── vlm_agent.py   # VLMAgent с tool calling
│   ├── ocr_client.py  # OCR клиенты (Qwen)
│   ├── ocr_tool.py    # OCRTool обертка
│   └── state.py       # Сохранение состояния (Memory/Disk)
├── operations/        # Операции над документами
│   ├── base.py        # Базовый класс BaseOperation
│   └── full_description.py  # FullDescriptionOperation
├── schemas/           # Схемы данных
│   ├── config.py      # Классы конфигурации (VLMConfig, ProcessorConfig, и т.д.)
│   ├── document.py    # DocumentData, HeaderInfo, TableInfo
│   └── common.py      # PageInfo, ClusterInfo, TriageResult
├── preprocessing/     # Утилиты предобработки
│   └── renderer.py    # Рендеринг PDF в PNG
├── utils/             # Утилиты
│   └── normalization.py  # Нормализация цифр OCR
└── cli.py             # Интерфейс командной строки
```

## Публичный API

### Основные классы
- `DocumentProcessor` - Главный класс обработки документов
- `BaseVLMClient`, `GeminiVLMClient` - VLM клиенты
- `VLMAgent` - VLM агент с tool calling loop
- `BaseOCRClient`, `QwenOCRClient` - OCR клиенты
- `OCRTool` - Обертка для OCR инструмента

### Операции
- `BaseOperation` - Базовый класс операций
- `FullDescriptionOperation` - Извлечение полного текста и структуры

### Схемы
- `ProcessorConfig`, `VLMConfig`, `OCRConfig`, `RenderConfig` - Конфигурация
- `DocumentData`, `HeaderInfo`, `TableInfo` - Данные документа
- `PageInfo`, `ClusterInfo`, `TriageResult` - Общие структуры данных

## Документация

- [Обзор архитектуры](00_docs/architecture/overview.md) - Архитектура и дизайн системы
- [План реализации](00_docs/architecture/implementation_plan.md) - Детали реализации
- [Backlog](00_docs/backlog.md) - Задачи разработки и статус

## Статус разработки

:warning: **Версия 0.1.0** - Ранний релиз с базовой функциональностью

**Реализовано:**
- ✅ FullDescriptionOperation (извлечение текста + структуры)
- ✅ State management (Memory + Disk бэкенды)
- ✅ CLI интерфейс
- ✅ Рендеринг PDF и нормализация OCR

**Запланировано:**
- ⏳ ClusteringOperation (семантическая группировка страниц)
- ⏳ TriageOperation (поиск страниц по критериям)
- ⏳ ExtractionOperation (извлечение полей)
- ⏳ Классификация таблиц (NUMERIC vs TEXT_MATRIX)

## Лицензия

MIT License - см. файл LICENSE для деталей

## Участие в разработке

Участие приветствуется! Проект использует AI-ассистированную разработку с четкими ролями агентов. См. директорию `.agents/` для деталей.

---

[English version](README_EN.md)
