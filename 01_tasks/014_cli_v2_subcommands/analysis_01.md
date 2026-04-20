# Технический план: Task 014 — CLI v2 (scan/resolve/verify/full-description)

## 1. Анализ задачи

Реализовать CLI v2 с подкомандами `scan`, `resolve`, `verify`, `full-description` поверх `DocumentReader.open()`. Добавить `--workspace` и page filters (`--pages`). Режим `full-description` = scan + resolve(all). Обеспечить совместимость вывода с Windows (cp1251/UTF-8). Заменить старый entrypoint без легаси.

## 2. Текущее состояние

**cli.py:**
- Один entrypoint без подкоманд: `vlm-ocr-reader document.pdf [--output-dir, --dpi, --log-level, ...]`
- Использует `DocumentProcessor` + `FullDescriptionOperation` напрямую
- Создаёт timestamped run dir (`run_YYYY-MM-DD_HHMMSS/`), логи в `logs/run.log`
- `setup_logging()` — stream=sys.stdout, FileHandler с encoding="utf-8"
- `print()` для summary — без явной кодировки (на Windows cp1251 консоли Unicode может падать)
- `validate_arguments()` — проверка pdf_path, api_key
- `create_run_dir()` — создание run-директории

**reader.py (DocumentReader):**
- `open(pdf_path, workspace=None)` — factory
- `scan(pages=None)`, `resolve(pages=None)`, `verify(pages=None)`
- `page_status()`, `pending_entities(page=None)`, `get_document_data()`
- `_normalize_pages(pages)` — None → все страницы, иначе валидация и сортировка

**test_cli.py:**
- Тесты на `main`, `setup_logging`, `validate_arguments`, `create_output_directory` (имя функции устарело — в cli.py `create_run_dir`)
- Мокируют `DocumentProcessor`, `FullDescriptionOperation`
- Нужно адаптировать под новую структуру (subcommands, DocumentReader)

## 3. Предлагаемое решение

### 3.1. Общий подход

- Переход на `argparse` subparsers: `vlm-ocr-reader <subcommand> pdf_path [options]`
- Каждая подкоманда вызывает `DocumentReader.open(pdf_path, workspace)` и соответствующий метод
- Общие аргументы: `pdf_path`, `--workspace`, `--pages` (где релевантно), `--log-level`
- В начале `main()` — обёртка stdout/stderr для UTF-8 (Windows cp1251)
- `full-description` — scan() + resolve() по всем страницам; workspace опционален (memory mode при отсутствии)

### 3.2. Компоненты

#### 3.2.1. UTF-8 output wrapper

- **Назначение:** Избежать `UnicodeEncodeError` при выводе в Windows консоль (cp1251 по умолчанию)
- **Интерфейс:** Функция `ensure_utf8_stdio()` — вызывается в начале `main()` до любого print/log
- **Логика:**
  1. Проверить `sys.stdout.encoding` (или платформу)
  2. На Windows: если encoding не utf-8, заменить `sys.stdout` и `sys.stderr` на `io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')` (аналогично для stderr)
  3. На Unix — не трогать (обычно UTF-8)
- **Зависимости:** `sys`, `io`
- **Важно:** Вызывать до `setup_logging()`, т.к. logging использует sys.stdout

#### 3.2.2. parse_pages_arg(raw: str | None) -> list[int] | None

- **Назначение:** Парсинг строки `--pages "1,2,5-7"` в список номеров страниц
- **Интерфейс:** `parse_pages_arg(raw: str | None) -> list[int] | None`
- **Логика:**
  - `None` или пустая строка → `None` (все страницы)
  - Разделитель `,` — отдельные номера
  - Диапазон `N-M` — включительно
  - Дубликаты убрать, отсортировать
  - Некорректный формат → `ValueError` или возврат пустого списка (уточнить: лучше ValueError для явной ошибки)
- **Примеры:** `"1,2,5-7"` → `[1,2,5,6,7]`, `"3"` → `[3]`

#### 3.2.3. CLIArgs (dataclass или namespace)

- **Поля:** `pdf_path: Path`, `workspace: Path | None`, `pages: str | None`
- Использовать `argparse.Namespace` или простой dataclass — без лишней абстракции

#### 3.2.4. cmd_scan, cmd_resolve, cmd_verify, cmd_full_description

- **Сигнатура:** `cmd_*(args) -> int`
- **Общая логика:**
  1. `load_dotenv()`, проверка `GEMINI_API_KEY`
  2. `DocumentReader.open(args.pdf_path, args.workspace)`
  3. `pages = parse_pages_arg(args.pages)` (для scan/resolve/verify)
  4. Вызов `reader.scan(pages)` / `reader.resolve(pages)` / `reader.verify(pages)` / scan+resolve
  5. Вывод summary (краткий), return 0/1
- **full-description:** `reader.scan()` затем `reader.resolve()` без фильтра страниц (все)
- **verify:** stub — только вызов `reader.verify(pages)`, логирование (стратегия в 015)

#### 3.2.5. main()

- Вызов `ensure_utf8_stdio()`
- Парсинг с subparsers
- Диспетчеризация на `cmd_*`
- Обработка `KeyboardInterrupt`, общих исключений

### 3.3. Структуры данных

```
CLI subcommands:
  scan            Level 0, VLM-only
  resolve         Level 1, OCR по Registry
  verify          Level 2, stub
  full-description scan + resolve(all)
```

Общие опции для всех подкоманд:
- `pdf_path` (positional)
- `--workspace`, `-w` (optional, Path)
- `--log-level` (optional, default INFO)
- `--pages` (optional, для scan/resolve/verify) — строка "1,2,5-7"

### 3.4. Ключевые алгоритмы

**parse_pages_arg:**
- Split по `,`, для каждого токена: если содержит `-`, split и взять range; иначе int()
- Собрать set, sorted, вернуть list

**ensure_utf8_stdio:**
- `if sys.platform == 'win32' and getattr(sys.stdout, 'encoding', None) != 'utf-8':`
- Перезаписать sys.stdout/stderr через TextIOWrapper над .buffer с encoding='utf-8', errors='replace'

### 3.5. Изменения в существующем коде

| Файл | Действие |
|------|----------|
| `cli.py` | Полная переработка: subparsers, cmd_*, parse_pages_arg, ensure_utf8_stdio, DocumentReader |
| `test_cli.py` | Адаптация: новые импорты, моки DocumentReader, тесты подкоманд; убрать create_output_directory (если удалена) |

**Удалить/заменить:**
- `create_run_dir`, `DEFAULT_OUTPUT_DIR` — не нужны в v2 (workspace от DocumentReader)
- Прямое использование `DocumentProcessor`, `FullDescriptionOperation` — только через DocumentReader
- `validate_arguments` — частично сохранить логику (pdf exists, api_key), интегрировать в cmd_* или общую pre-check

## 4. План реализации

1. Добавить `ensure_utf8_stdio()` в cli.py, вызвать в начале main()
2. Добавить `parse_pages_arg(raw) -> list[int] | None`
3. Переписать `main()`: subparsers для scan, resolve, verify, full-description
4. Реализовать `cmd_scan`, `cmd_resolve`, `cmd_verify`, `cmd_full_description`
5. Общие опции: pdf_path, --workspace, --pages, --log-level
6. Адаптировать `setup_logging()` — оставить stream=sys.stdout (после ensure_utf8_stdio он уже UTF-8)
7. Обновить test_cli.py под новую структуру (моки DocumentReader, тесты subcommands)
8. Удалить легаси: create_run_dir, DEFAULT_OUTPUT_DIR, прямые вызовы Processor/Operation

## 5. Технические критерии приемки

- [ ] TC-1: `vlm-ocr-reader scan doc.pdf --workspace ./ws` вызывает DocumentReader.open + scan()
- [ ] TC-2: `vlm-ocr-reader resolve doc.pdf --workspace ./ws --pages 1,3-5` вызывает resolve(pages=[1,3,4,5])
- [ ] TC-3: `vlm-ocr-reader verify doc.pdf` вызывает verify() (stub)
- [ ] TC-4: `vlm-ocr-reader full-description doc.pdf` выполняет scan() + resolve() по всем страницам
- [ ] TC-5: Без --workspace используется memory mode (DocumentReader.open(..., workspace=None))
- [ ] TC-6: На Windows с cp1251 консолью вывод не падает с UnicodeEncodeError (ensure_utf8_stdio)
- [ ] TC-7: `parse_pages_arg("1,2,5-7")` → `[1,2,5,6,7]`, `parse_pages_arg(None)` → `None`
- [ ] TC-8: Существующие unit-тесты в test_cli.py проходят после адаптации

## 6. Важные детали для Developer

### Windows cp1251 / UTF-8

- **Проблема:** В Windows консоли по умолчанию cp1251. При `print("Русский текст")` или `logger.info("...")` с Unicode может возникнуть `UnicodeEncodeError`.
- **Решение:** В самом начале `main()` вызвать `ensure_utf8_stdio()`, которая:
  - На Windows: заменяет `sys.stdout` и `sys.stderr` на `io.TextIOWrapper(encoding='utf-8', errors='replace')`
  - `errors='replace'` — невыводимые символы заменяются на `?`, без падения
  - На Linux/macOS обычно не требуется (консоль UTF-8), но проверка безвредна — если `sys.stdout.encoding == 'utf-8'`, ничего не менять

### Logging

- После `ensure_utf8_stdio()` `sys.stdout` уже UTF-8. `logging.basicConfig(stream=sys.stdout)` будет писать в UTF-8.
- FileHandler для логов: `encoding='utf-8'` — уже есть в cli. В v2 логи можно писать в workspace (если указан) или только в консоль при memory mode — на усмотрение, минимально — в консоль.

### Логи в v2

- task_brief не требует run_dir с timestamp. Workspace — это директория документа (DocumentReader сам создаёт поддиректорию по content_hash).
- Логи: можно писать в `workspace/<doc>/logs/` или только в stdout. Для простоты — только stdout при memory mode; при workspace — логи в консоль (без файла), чтобы не усложнять. Либо: при workspace — логи в `workspace/<doc>/run.log`. Уточнить в реализации: минимально — console only.

### parse_pages_arg

- При невалидном формате (например `"1-2-3"` или `"abc"`) — лучше `ValueError` с понятным сообщением, чтобы CLI мог вернуть 1 и exit.

### Тесты

- **Не создавать новые тестовые модули.** Адаптировать существующий `test_cli.py`:
  - Мокировать `DocumentReader.open` и возвращаемый reader
  - Тесты для subcommands: scan, resolve, full-description
  - Тесты для parse_pages_arg (можно добавить в test_cli или отдельный test_parse если нужно — без нового модуля, т.е. в том же файле)
  - Убрать/обновить тесты для create_output_directory (функция удалена)

### full-description и workspace

- При `full-description` без `--workspace`: memory mode, состояние не сохраняется. Обратная совместимость с текущим поведением.
