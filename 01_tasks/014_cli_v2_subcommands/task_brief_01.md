# Task 014: CLI v2 (scan/resolve/verify/full-description)

## Что нужно сделать
Реализовать CLI v2 с подкомандами `scan`, `resolve`, `verify`, `full-description` поверх `DocumentReader`. Добавить параметр `--workspace` и совместимый режим `full-description = scan + resolve(all)`.

## Зачем
CLI должен отражать новую архитектуру Resolution Levels и позволять инкрементальный запуск этапов по документу/страницам без ручного Python API.

## Acceptance Criteria
- [ ] AC-1: CLI поддерживает подкоманды `scan`, `resolve`, `verify`, `full-description`.
- [ ] AC-2: Каждая подкоманда использует `DocumentReader.open(...)`.
- [ ] AC-3: Поддержан `--workspace` и page filters (`--pages` где релевантно).
- [ ] AC-4: `full-description` выполняет `scan` + `resolve` по всем страницам.
- [ ] AC-5: Логи/stdout совместимы с Windows cp1251 ограничениями (вывод через UTF-8 writer).
- [ ] AC-6: Старый entrypoint заменен/обновлен без лишней легаси-логики.

## Контекст

**Релевантные части ADR (копия):**
- CLI целевой: `scan`, `resolve`, `verify`, `full-description`.
- Единая точка входа — `DocumentReader`.
- `full-description` остается для compatibility сценариев.

**Интерфейсы и контракты (полностью):**

```python
def main() -> int: ...

def cmd_scan(args) -> int: ...
def cmd_resolve(args) -> int: ...
def cmd_verify(args) -> int: ...
def cmd_full_description(args) -> int: ...
```

```python
class CLIArgs:
    pdf_path: str
    workspace: str | None
    pages: str | None  # "1,2,5-7"
```

```python
def parse_pages_arg(raw: str | None) -> list[int] | None:
    """Parse comma/range page specification."""
```

**Границы задачи 014:**
- Делает: CLI wiring на существующие `DocumentReader` методы.
- Не делает: новый verify algorithm (015), архитектурные изменения state/reader.

**Существующий код для reference:**
- `02_src/vlm_ocr_doc_reader/cli.py` - текущий CLI v1.
- `02_src/vlm_ocr_doc_reader/core/reader.py` - API для scan/resolve/verify.
- `00_docs/architecture/decision_001_resolution_levels.md`.
