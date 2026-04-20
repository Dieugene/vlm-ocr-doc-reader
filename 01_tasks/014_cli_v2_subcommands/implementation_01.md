# Отчет о реализации: Task 014 — CLI v2 (scan/resolve/verify/full-description)

## Что реализовано

CLI v2 с подкомандами `scan`, `resolve`, `verify`, `full-description` поверх `DocumentReader`. Добавлены `--workspace`, `--pages`, обёртка UTF-8 для Windows (cp1251→utf-8). Режим `full-description` выполняет scan + resolve по всем страницам.

## Файлы

**Измененные:**
- `02_src/vlm_ocr_doc_reader/cli.py` — полная переработка: subparsers, `ensure_utf8_stdio`, `parse_pages_arg`, `cmd_scan`/`cmd_resolve`/`cmd_verify`/`cmd_full_description`, использование `DocumentReader.open()`
- `02_src/tests/unit/test_cli.py` — адаптация под новую структуру: моки `DocumentReader`, тесты subcommands и `parse_pages_arg`, удалены тесты `create_output_directory`

## Особенности реализации

### SystemExit в main()

**Причина:** `_check_api_key` и `_check_pdf_path` вызывают `sys.exit(1)`, что поднимает `SystemExit`. Тесты ожидают `main()` возвращает 1, а не исключение.
**Решение:** В `main()` добавлен `except SystemExit as e: return int(e.code) if e.code is not None else 1`.

### logging.basicConfig(force=True)

**Причина:** В тестах `setup_logging` вызывается многократно; `basicConfig` по умолчанию не перезаписывает уже настроенный root logger.
**Решение:** Добавлен `force=True` (Python 3.8+), чтобы тесты могли переключать уровень логирования.

### validate_arguments сохранён

**Причина:** Тесты импортируют и проверяют `validate_arguments`.
**Решение:** Функция оставлена для совместимости с тестами; внутренняя логика дублирует `_check_pdf_path` и `_check_api_key`.

## Известные проблемы

Нет
