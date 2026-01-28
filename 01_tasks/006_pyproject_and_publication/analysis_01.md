# Техническое задание: pyproject.toml и подготовка к публикации (GitHub)

## 1. Анализ задачи

Необходимо создать современную конфигурацию Python-пакета через `pyproject.toml` для локальной установки после клонирования из GitHub. Публичная публикация на PyPI не планируется. Основная цель - обеспечить удобную установку через `pip install -e .`, корректный публичный API через `__init__.py` и понятную документацию в README.

## 2. Текущее состояние

**Существующие файлы:**
- `02_src/vlm_ocr_doc_reader/__init__.py` - содержит только заголовок и пустой `__all__`
- `requirements.txt` - список всех зависимостей (core + testing)
- `README.md` - устаревший, требует обновления
- Модули пакета реализованы в `02_src/vlm_ocr_doc_reader/`:
  - `core/`: processor.py, vlm_client.py, vlm_agent.py, ocr_client.py, ocr_tool.py, state.py
  - `operations/`: base.py, full_description.py
  - `schemas/`: config.py, document.py, common.py
  - `preprocessing/`: renderer.py
  - `utils/`: normalization.py

**Архитектурные особенности:**
- Пакет находится в `02_src/vlm_ocr_doc_reader/`, НЕ в корне проекта
- Используются:dataclasses (Pydantic для валидации)
- Зависимости из requirements.txt уже согласованы

## 3. Предлагаемое решение

### 3.1. Общий подход

Создать `pyproject.toml` в корне проекта с использованием setuptools как build-backend. Настроить package discovery через `package-dir` для корректной работы с нестандартной структурой (`02_src/vlm_ocr_doc_reader`). Обновить `__init__.py` для экспорта публичного API. Переписать README.md с инструкциями по установке и примерами использования.

### 3.2. Компоненты

#### pyproject.toml
- **Назначение:** Конфигурация пакета согласно PEP 517/518
- **Ключевые секции:**
  - `[build-system]` - требует setuptools>=61.0
  - `[project]` - metadata (name, version, dependencies, requires-python)
  - `[tool.setuptools.package-dir]` - перенаправление из `vlm_ocr_doc_reader` в `02_src/vlm_ocr_doc_reader`
  - `[project.optional-dependencies]` - dev зависимости (pytest, pytest-mock, pytest-cov)
- **Dependencies:** Перенести из requirements.txt (кроме testing)

#### vlm_ocr_doc_reader/__init__.py
- **Назначение:** Экспорт публичного API
- **Экспортируемые сущности:**
  - `__version__ = "0.1.0"`
  - Core: `DocumentProcessor`, `BaseVLMClient`, `GeminiVLMClient`, `VLMAgent`, `BaseOCRClient`, `QwenOCRClient`, `OCRTool`
  - Operations: `BaseOperation`, `FullDescriptionOperation`
  - Schemas: `ProcessorConfig`, `VLMConfig`, `OCRConfig`, `RenderConfig`, `DocumentData`, `HeaderInfo`, `TableInfo`, `PageInfo`, `ClusterInfo`, `TriageResult`

#### README.md
- **Назначение:** Документация для пользователей
- **Секции:**
  1. Краткое описание модуля
  2. Установка (клонирование, venv, pip install -e .)
  3. Быстрый старт (базовый пример)
  4. Примеры использования (с state_dir, из массива PNG, с .env)
  5. Ссылки на документацию

#### .gitignore
- **Назначение:** Исключить артефакты сборки
- **Добавить:** `build/`, `dist/`, `*.egg-info/`, `__pycache__/`

### 3.3. Структуры данных

**Зависимости (из requirements.txt):**
```
Core:
- requests>=2.31.0
- python-dotenv>=1.0.0
- Pillow>=10.0.0
- pymupdf>=1.23.0
- PyYAML>=6.0.0
- pydantic>=2.0.0
- python-json-logger>=2.0.0

Dev (optional):
- pytest>=7.4.0
- pytest-mock>=3.12.0
- pytest-cov>=4.1.0
```

**Публичный API (импорты):**
```python
# Core
from .core.processor import DocumentProcessor
from .core.vlm_client import BaseVLMClient, GeminiVLMClient
from .core.vlm_agent import VLMAgent
from .core.ocr_client import BaseOCRClient, QwenOCRClient
from .core.ocr_tool import OCRTool

# Operations
from .operations.base import BaseOperation
from .operations.full_description import FullDescriptionOperation

# Schemas
from .schemas.config import ProcessorConfig, VLMConfig
from .schemas.document import DocumentData, HeaderInfo, TableInfo
from .schemas.common import PageInfo
```

### 3.4. Ключевые алгоритмы

**Установка пакета:**
1. Пользователь клонирует репозиторий
2. Создает виртуальное окружение: `python -m venv .venv`
3. Активирует venv
4. Устанавливает: `pip install -e .`
5. pip создает `vlm_ocr_doc_reader.egg-link` в site-packages, указывающий на `02_src/vlm_ocr_doc_reader`

**Package discovery в pyproject.toml:**
- Использовать `[tool.setuptools.package-dir]` для маппинга:
  ```toml
  [tool.setuptools.package-dir]
  vlm_ocr_doc_reader = "02_src/vlm_ocr_doc_reader"
  ```
- Указать `packages = ["vlm_ocr_doc_reader"]` или использовать `find:` с исключениями

**Валидация импортов:**
- После установки проверить: `python -c "from vlm_ocr_doc_reader import DocumentProcessor; print('OK')"`
- Проверить версию: `python -c "import vlm_ocr_doc_reader; print(vlm_ocr_doc_reader.__version__)"`

### 3.5. Изменения в существующем коде

**02_src/vlm_ocr_doc_reader/__init__.py:**
- Добавить импорты всех публичных классов
- Заполнить `__all__` списком экспортируемых имен
- Сохранить существующую документацию (docstring модуля)

**README.md:**
- Полностью переписать содержание
- Сохранить структуру проекта (добавить секцию "Структура модуля")
- Добавить примеры кода

**Создать .gitignore (если отсутствует):**
- Добавить python-специфичные исключения
- Добавить артефакты сборки

## 4. План реализации

1. **Шаг 1:** Создать `pyproject.toml` в корне проекта с metadata, dependencies и package-dir
2. **Шаг 2:** Обновить `02_src/vlm_ocr_doc_reader/__init__.py` - добавить импорты и заполнить `__all__`
3. **Шаг 3:** Переписать `README.md` с инструкциями по установке и примерами использования
4. **Шаг 4:** Создать/обновить `.gitignore` с исключениями для build/
5. **Шаг 5:** Протестировать установку: `pip install -e .` из корня проекта
6. **Шаг 6:** Проверить импорты: `python -c "from vlm_ocr_doc_reader import DocumentProcessor; print(DocumentProcessor)"`
7. **Шаг 7:** Создать unit тест для публичного API (проверка всех импортов из `__init__.py`)

## 5. Технические критерии приемки

- [ ] TC-1: `pyproject.toml` создан с корректным `[build-system]` (setuptools>=61.0)
- [ ] TC-2: `pyproject.toml` содержит `[project]` с name="vlm-ocr-doc-reader", version="0.1.0", requires-python=">=3.10"
- [ ] TC-3: `pyproject.toml` содержит `[tool.setuptools.package-dir]` с маппингом в `02_src/vlm_ocr_doc_reader`
- [ ] TC-4: `pip install -e .` выполняется успешно из корня проекта
- [ ] TC-5: `from vlm_ocr_doc_reader import DocumentProcessor` выполняется успешно
- [ ] TC-6: Все классы из task_brief импортируются без ошибок
- [ ] TC-7: `vlm_ocr_doc_reader.__version__` возвращает "0.1.0"
- [ ] TC-8: README.md содержит секцию "Установка" с командой `pip install -e .`
- [ ] TC-9: README.md содержит 3+ примера использования (базовый, с state_dir, из PNG)
- [ ] TC-10: `.gitignore` исключает `build/`, `dist/`, `*.egg-info/`
- [ ] TC-11: Unit тест проверяет все импорты из `__init__.py`

## 6. Важные детали для Developer

**Специфичные риски:**
- **Package location:** Пакет в `02_src/`, не в корне. Без корректного `package-dir` setuptools не найдет модуль
- **Editable install:** После `pip install -e .` изменения в коде сразу доступны без переустановки. Проверить что `egg-link` указывает на `02_src/vlm_ocr_doc_reader`
- **Circular imports:** При импорте в `__init__.py` избежать циклических зависимостей. Использовать `from .module import Class`, не `from .module.submodule import Class`

**OCRConfig/RenderConfig:**
- Проверить существуют ли эти классы в `schemas/config.py` перед экспортом
- Если отсутствуют - либо создать, либо не экспортировать

**README.md примеры:**
- Использовать реальные пути и имена классов
- Показать создание VLM client через `VLMConfig(api_key=...)`
- Показать использование .env файла: `load_dotenv()`

**Unit тест для API:**
- Тест должен проверять что все классы из `__all__` реально импортируются
- Использовать `pytest`, `importlib` для динамической проверки
- Тест location: `tests/test_public_api.py` (создать новую директорию tests/)

**Список экспортируемых классов должен совпадать с task_brief:**
- Core: DocumentProcessor, BaseVLMClient, GeminiVLMClient, VLMAgent, BaseOCRClient, QwenOCRClient, OCRTool
- Operations: BaseOperation, FullDescriptionOperation
- Schemas: ProcessorConfig, VLMConfig, OCRConfig, RenderConfig, DocumentData, HeaderInfo, TableInfo, PageInfo, ClusterInfo, TriageResult
