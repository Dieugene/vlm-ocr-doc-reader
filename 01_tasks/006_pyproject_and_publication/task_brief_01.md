# pyproject.toml и подготовка к публикации (GitHub)

## Что нужно сделать

Создать современную конфигурацию Python-пакета через `pyproject.toml` для удобного использования после клонирования из GitHub. Настроить публичный API через `__init__.py`, обеспечить корректную локальную установку через `pip install -e .`, обновить README с примерами использования.

**ВАЖНО:** Глобальная публикация на PyPI НЕ планируется. Модуль будет доступен через GitHub, пользователи клонируют репозиторий и устанавливают локально.

## Зачем

**Бизнес-цель:** Сделать модуль удобным для интеграции в другие проекты (включая проект 07_agentic-doc-processing) после клонирования из GitHub.

**Ценность для пользователя:**
- Клонирование: `git clone <repo-url>`
- Локальная установка: `pip install -e .`
- Понятный публичный API
- Примеры использования в README
- Максимально удобный интерфейс

**Сценарий использования:**
```bash
# Пользователь клонирует репозиторий
git clone https://github.com/your-org/vlm-ocr-doc-reader.git
cd vlm-ocr-doc-reader

# Устанавливает в editable режиме
pip install -e .

# Использует в своем коде
python -c "from vlm_ocr_doc_reader import DocumentProcessor; print('OK')"
```

## Acceptance Criteria

- [ ] AC-1: `pyproject.toml` создан с metadata (name, version, dependencies)
- [ ] AC-2: `pip install -e .` выполняется успешно из корня проекта
- [ ] AC-3: Публичный API экспортируется через `vlm_ocr_doc_reader/__init__.py`
- [ ] AC-4: README.md обновлен с инструкцией по клонированию и установке
- [ ] AC-5: README.md содержит примеры использования (создание клиентов, процессора, операций)
- [ ] AC-6: `.gitignore` исключает артефакты сборки (build/, dist/, *.egg-info/)
- [ ] AC-7: Unit тесты для публичного API (проверка импортов из `vlm_ocr_doc_reader`)

## Контекст

**Релевантные части ADR:**

ADR-001: Python Packaging Standards
- Использовать pyproject.toml (PEP 517/518)
- Локальная установка через pip install -e .
- Зависимости: requests, python-dotenv, Pillow, pymupdf, PyYAML, pydantic
- Python version: >=3.10
- НЕ требуется настройка publish на PyPI

**Интерфейсы и контракты:**

### Требования к pyproject.toml

Файл должен содержать:
- `[build-system]` с setuptools
- `[project]` секцию с metadata:
  - name: "vlm-ocr-doc-reader"
  - version: "0.1.0"
  - dependencies (из requirements.txt)
  - requires-python: ">=3.10"
- `[tool.setuptools.package-dir]` — **ВАЖНО**: пакет в `02_src/vlm_ocr_doc_reader`, не в корне
- `[project.optional-dependencies]` с dev зависимостями (pytest, pytest-mock, pytest-cov)

### Требования к публичному API (__init__.py)

Файл `02_src/vlm_ocr_doc_reader/__init__.py` должен экспортировать:

**Core классы:**
- DocumentProcessor
- BaseVLMClient, GeminiVLMClient
- VLMAgent
- BaseOCRClient, QwenOCRClient
- OCRTool

**Operations:**
- BaseOperation
- FullDescriptionOperation

**Schemas:**
- ProcessorConfig, VLMConfig, OCRConfig, RenderConfig
- DocumentData, HeaderInfo, TableInfo
- PageInfo, ClusterInfo, TriageResult

**Version:**
- `__version__ = "0.1.0"`

### Требования к README.md

README должен содержать:

1. **Краткое описание** модуля и возможностей
2. **Инструкция по установке:**
   - Клонирование из GitHub
   - Создание venv
   - Установка зависимостей
   - Опционально: `pip install -e .`

3. **Примеры использования:**
   - Базовое использование (создание VLM client → processor → operation)
   - С сохранением состояния (ProcessorConfig с state_dir)
   - Из массива изображений
   - С использованием .env файла

4. **Ссылки на документацию:**
   - Архитектура (00_docs/architecture/overview.md)
   - Implementation Plan

**Критерии готовности модуля:**
- Корректная локальная установка через pip install -e .
- Все публичные классы импортируются из `vlm_ocr_doc_reader`
- README содержит инструкцию по клонированию и установке
- README содержит понятные примеры использования
- Unit тесты проверяют импорты

**Существующий код для reference:**
- `02_src/vlm_ocr_doc_reader/__init__.py` — текущий (пустой) файл
- `requirements.txt` — список зависимостей
- `README.md` — текущий (устаревший) файл

**Другие ссылки:**
- [PEP 517/518](https://peps.python.org/pep-0517/) — спецификация pyproject.toml
- [Python Packaging Tutorial](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
- [Setuptools Package Discovery](https://setuptools.pypa.io/en/latest/userguide/package_discovery.html) — про package-dir
