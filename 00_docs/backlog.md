# Backlog

## Открытые

- **Параллельный resolve (этап 4).** Сейчас `_resolve_entities` обходит страницы и chunks последовательно. Завернуть в `ThreadPoolExecutor` — отдельные страницы и chunks параллельно, использовать `ProcessorConfig.max_tool_workers`. Прирост к multi-question даст ещё ×N по wall-time.
- **Level 2 `verify` с confidence scoring (этап 5).** Отдельный ADR (`decision_002_*`). Стратегия: для каждой сущности — N независимых прогонов по разным «осям» (chunk_size / DPI / temperature / модель), агрегация majority voting, поле `confidence` в `OCRRegistryEntry`. Решает наблюдавшуюся проблему «прочиталось — не знаем, насколько правильно».
- **Проверка на больших документах.** Текущая верификация — только на `03_data/test_document.pdf` (8 стр). Нужны 30–100+ стр., разные типы (регуляторные, финансовые, научные).

## Справочно

E2E на `03_data/test_document.pdf` (8 страниц): scan извлекает текст (~16K), headers (40+), OCR Registry (~30–40 атомарных записей с явным `context`). Resolve по multi-question (chunk_size=5) — 10 OCR-вызовов вместо 32, ~1 мин wall-time. Эмпирический GridSearch по `chunk_size` запускается через `scripts/ocr_chunk_grid.py`.
