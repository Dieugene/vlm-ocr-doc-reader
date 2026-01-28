# Техническое задание: CLI интерфейс для распознавания документов

## 1. Анализ задачи

Создать CLI (Command Line Interface) для распознавания PDF документов через командную строку. CLI должен принимать путь к PDF, опциональные параметры (output-dir, dpi, log-level), выполнять `FullDescriptionOperation` и сохранять результаты через существующий `DiskStorage`. Регистрация CLI через `[project.scripts]` в pyproject.toml для глобальной доступности после `pip install -e .`.

## 2. Текущее состояние

**Существующие модули для переиспользования:**
- `core/processor.py` — `DocumentProcessor` с поддержкой PDF рендеринга и state management
- `core/state.py` — `DiskStorage` с сохранением в `state_dir/results/full_description.yaml`
- `operations/full_description.py` — `FullDescriptionOperation.execute()` возвращает `DocumentData`
- `schemas/config.py` — `ProcessorConfig` для настройки процессора
- `core/vlm_client.py` — `GeminiVLMClient` с throttling и retry

**Существующие паттерны:**
- Загрузка API ключа через `dotenv.load_dotenv()` и `os.getenv("GEMINI_API_KEY")`
- Логирование через модуль `logging` с уровнем из `config.log_level`
- State management через `StateManager` с `DiskStorage` backend

**Отсутствует:**
- Файл `cli.py` с entry point функцией
- `pyproject.toml` для packaging и регистрации CLI
- Unit тесты для CLI

## 3. Предлагаемое решение

### 3.1. Общий подход

CLI — это тонкая обертка вокруг существующего `DocumentProcessor` и `FullDescriptionOperation`. Основная логика:
1. Парсинг аргументов (argparse или click)
2. Валидация входных данных (существование PDF, наличие API ключа)
3. Создание `DocumentProcessor` с `state_dir=output_dir`
4. Выполнение `FullDescriptionOperation`
5. Вывод краткого резюме в stdout
6. Автосохранение результатов через `DiskStorage`

### 3.2. Компоненты

#### CLI Module (cli.py)
- **Назначение:** Entry point для командной строки
- **Интерфейс:** `main() -> int` или `main(argv: List[str]) -> int`
- **Логика:**
  1. Парсит аргументы командной строки
  2. Проверяет существование PDF файла
  3. Загружает `GEMINI_API_KEY` из окружения
  4. Создает `DocumentProcessor` с `state_dir=output_dir`
  5. Выполняет `FullDescriptionOperation`
  6. Сохраняет результаты через `StateManager.save_operation_result()`
  7. Выводит краткое резюме (количество страниц, путь к результатам)
  8. Возвращает 0 при успехе, 1 при ошибке

#### pyproject.toml
- **Назначение:** Packaging и регистрация CLI
- **Секции:**
  - `[project]` — metadata (name, version, dependencies)
  - `[project.scripts]` — entry point: `vlm-ocr-reader = "vlm_ocr_doc_reader.cli:main"`

#### Unit Tests (test_cli.py)
- **Назначение:** Проверка логики CLI без реальных API вызовов
- **Что тестировать:**
  - Успешное выполнение (мокануть VLM, проверить вызов operation.execute)
  - Обработка отсутствующего PDF файла (FileNotFoundError → exit 1)
  - Обработка отсутствующего API ключа (ValueError → exit 1)
  - Парсинг аргументов (output-dir, dpi, log-level)

### 3.3. Структуры данных

#### CLI Arguments
```
pdf_path (позиционный) — Path to PDF file
--output-dir, -o (опциональный) — Directory for results, default="./output"
--dpi (опциональный) — DPI for rendering, default=150
--log-level (опциональный) — Logging level, default="INFO"
```

#### Processor Config for CLI
```
ProcessorConfig(
    state_dir=Path(output_dir),
    auto_save=True,
    render_dpi=dpi,
    log_level=log_level
)
```

### 3.4. Ключевые алгоритмы

**Валидация аргументов:**
- Проверить существование PDF файла через `Path(pdf_path).exists()`
- Проверить наличие `GEMINI_API_KEY` через `os.getenv("GEMINI_API_KEY")`
- Создать output директорию через `Path(output_dir).mkdir(parents=True, exist_ok=True)`

**Выполнение операции:**
- Создать `DocumentProcessor(source=Path(pdf_path), config=ProcessorConfig(...))`
- Создать `FullDescriptionOperation(processor)`
- Вызвать `operation.execute()`
- Сохранить результат через `processor.state_manager.save_operation_result("full_description", result)`

**Логирование:**
- Настроить логирование через `logging.basicConfig(level=log_level, format=...)`
- Использовать существующие логеры из модулей (`logger.info()`)

**Обработка ошибок:**
- FileNotFoundError → error message + `sys.exit(1)`
- ValueError (no API key) → error message + `sys.exit(1)`
- Exception during processing → error message + `sys.exit(1)`

### 3.5. Изменения в существующем коде

**Не требуется изменений** — CLI использует существующие модули как есть.

**Новые файлы:**
- `02_src/vlm_ocr_doc_reader/cli.py`
- `pyproject.toml` (в корне проекта)
- `02_src/tests/unit/test_cli.py`

## 4. План реализации

1. **Шаг 1:** Создать `pyproject.toml` с metadata и `[project.scripts]`
2. **Шаг 2:** Создать `cli.py` с функцией `main()` и парсингом аргументов
3. **Шаг 3:** Реализовать валидацию (PDF существует, API ключ задан)
4. **Шаг 4:** Интегрировать `DocumentProcessor` и `FullDescriptionOperation`
5. **Шаг 5:** Добавить сохранение результатов и вывод резюме
6. **Шаг 6:** Создать unit тесты с моками VLM
7. **Шаг 7:** Проверить установку через `pip install -e .` и вызов CLI

## 5. Технические критерии приемки

- [ ] TC-1: CLI принимает позиционный аргумент `pdf_path`
- [ ] TC-2: CLI принимает опциональные флаги `--output-dir`, `--dpi`, `--log-level`
- [ ] TC-3: CLI возвращает exit code 0 при успехе, 1 при ошибке
- [ ] TC-4: CLI сохраняет результаты в `{output_dir}/results/full_description.yaml`
- [ ] TC-5: CLI логирует прогресс в stdout (INFO уровень по умолчанию)
- [ ] TC-6: CLI доступен глобально после `pip install -e .`
- [ ] TC-7: Unit тесты мокают VLM вызовы и проверяют логику CLI
- [ ] TC-8: CLI обрабатывает ошибки (нет PDF, нет API ключа)

## 6. Важные детали для Developer

### Специфичные риски:

**API Key загрузка:**
- `DocumentProcessor` уже загружает `.env` через `load_dotenv()` в `__init__`
- В CLI НЕ нужно дублировать загрузку, просто проверить `os.getenv("GEMINI_API_KEY")` до создания процессора
- Если ключа нет → вывести ошибку и `sys.exit(1)` ДО создания процессора

**State management:**
- CLI должен передать `state_dir` в `ProcessorConfig`
- `DocumentProcessor` автоматически создаст `DiskStorage` и сохранит страницы
- Результат операции нужно сохранить явно через `processor.state_manager.save_operation_result("full_description", result)`

**Выбор библиотеки для CLI:**
- `argparse` — стандартный, в stdlib, достаточно для этой задачи
- `click` — более удобный, но требует дополнительной зависимости
- **Рекомендация:** использовать `argparse` (нет новых зависимостей)

**Формат логирования:**
- Использовать существующие логеры из модулей (они уже настроены)
- Дополнительный вывод в stdout: краткое резюме после выполнения
- Пример резюме: `"Processed 10 pages. Results saved to ./output/results/full_description.yaml"`

**Структура pyproject.toml:**
```toml
[project]
name = "vlm-ocr-doc-reader"
version = "0.1.0"
dependencies = [
    "pymupdf>=1.23.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0.0",
    "requests>=2.31.0",
]

[project.scripts]
vlm-ocr-reader = "vlm_ocr_doc_reader.cli:main"
```

**Unit тесты:**
- Использовать `unittest.mock` для моканья VLM
- Мокать `FullDescriptionOperation.execute` для проверки логики CLI
- НЕ вызывать реальные VLM API в тестах

**Exit codes:**
- 0 — успех
- 1 — ошибка (нет файла, нет API ключа, ошибка обработки)

**Интеграционное тестирование (опционально):**
- После unit тестов можно проверить CLI с реальным PDF (если есть API ключ)
- Это НЕ обязательно для приемки задачи, но полезно для проверки
