# CLI интерфейс для распознавания документов

## Что нужно сделать

Создать CLI (Command Line Interface) для удобного распознавания PDF документов из командной строки. CLI должен использовать `FullDescriptionOperation` под капотом, принимать путь к PDF и опциональный путь для сохранения результатов.

## Зачем

**Бизнес-цель:** Обеспечить быстрый способ распознать документ без написания Python кода. Полезно для:
- Быстрого тестирования модуля
- Использования в shell скриптах
- Пользователей, которым не нужно программировать

**Ценность для пользователя:**
- Простая команда: `vlm-ocr-reader document.pdf --output-dir ./results`
- Автоматическое сохранение результатов
- Прогресс-бар и логирование в stdout

## Acceptance Criteria

- [ ] AC-1: CLI принимает путь к PDF как позиционный аргумент
- [ ] AC-2: CLI принимает опциональный `--output-dir` для сохранения результатов
- [ ] AC-3: CLI принимает опциональный `--dpi` для настройки качества рендеринга
- [ ] AC-4: CLI использует `FullDescriptionOperation` под капотом
- [ ] AC-5: CLI сохраняет результаты через существующий `DiskStorage`
- [ ] AC-6: CLI показывает прогресс (логирование в stdout)
- [ ] AC-7: CLI зарегистрирован в `pyproject.toml` как `[project.scripts]`
- [ ] AC-8: Unit тесты для CLI (мокованное выполнение, без реальных API вызовов)

## Контекст

**Релевантные части ADR:**

ADR-002: CLI Interface Design
- Использовать argparse или click для CLI
- Entry point через `[project.scripts]` в pyproject.toml
- Логирование в stdout (INFO уровень по умолчанию)
- Файловое сохранение через существующий `DiskStorage`

**Интерфейсы и контракты:**

### CLI Интерфейс

Базовый синтаксис:
```bash
vlm-ocr-reader <pdf_path> [--output-dir DIR] [--dpi DPI] [--log-level LEVEL]
```

**Аргументы:**
- `pdf_path` (позиционный) — путь к PDF файлу
- `--output-dir`, `-o` (опциональный) — директория для сохранения результатов, default="./output"
- `--dpi` (опциональный) — DPI для рендеринга, default=150
- `--log-level` (опциональный) — уровень логирования (DEBUG/INFO/WARNING/ERROR), default="INFO"

**Примеры использования:**
```bash
vlm-ocr-reader document.pdf
vlm-ocr-reader document.pdf --output-dir ./results
vlm-ocr-reader document.pdf -o ./output --dpi 200
```

### Регистрация в pyproject.toml

Добавить секцию:
```toml
[project.scripts]
vlm-ocr-reader = "vlm_ocr_doc_reader.cli:main"
```

После установки через `pip install -e .` команда станет доступна в системе.

### Требования к реализации

**Структура:**
- Создать файл `02_src/vlm_ocr_doc_reader/cli.py`
- Функция `main() -> int` — entry point
- Возвращает 0 при успехе, 1 при ошибке

**Логика работы:**
1. Парсинг аргументов командной строки
2. Проверка существования PDF файла
3. Создание output директории если не существует
4. Загрузка GEMINI_API_KEY из переменных окружения (через dotenv)
5. Создание VLM client, DocumentProcessor с state_dir=output_dir
6. Выполнение FullDescriptionOperation
7. Вывод результатов в stdout (краткое резюме)
8. Логирование прогресса в stdout

**Использование state management:**
- Создать ProcessorConfig с state_dir=output_dir
- DocumentProcessor автоматически сохранит результаты через DiskStorage
- Структура сохранения: `{output_dir}/results/full_description.yaml`

**Обработка ошибок:**
- PDF файл не найден → error + exit 1
- GEMINI_API_KEY не задан → error + exit 1
- Ошибка при распознавании → exception + exit 1

### Unit тесты

**Файл:** `02_src/tests/unit/test_cli.py`

**Что тестировать:**
- Успешное выполнение (мокануть VLM, проверить что operation.execute вызван)
- Обработка отсутствующего API ключа
- Обработка отсутствующего PDF файла
- Проверка аргументов (output-dir, dpi)

**НЕ тестировать:**
- Реальные API вызовы (должны быть замоканы)
- Реальное распознавание PDF

**Критерии готовности модуля:**
- CLI вызывается из любой директории после pip install -e .
- CLI корректно обрабатывает аргументы
- CLI сохраняет результаты через DiskStorage
- CLI показывает прогресс в stdout
- Unit тесты мокают VLM вызовы и проверяют логику CLI

**Существующий код для reference:**
- `02_src/vlm_ocr_doc_reader/core/state.py` — DiskStorage реализация
- `02_src/vlm_ocr_doc_reader/operations/full_description.py` — FullDescriptionOperation
- `02_src/vlm_ocr_doc_reader/core/processor.py` — DocumentProcessor
- `02_src/vlm_ocr_doc_reader/schemas/config.py` — ProcessorConfig

**Другие ссылки:**
- [argparse documentation](https://docs.python.org/3/library/argparse.html)
- [click documentation](https://click.palletsprojects.com/) — альтернатива argparse
- [Python CLI Best Practices](https://clinteastwood.dev/)
