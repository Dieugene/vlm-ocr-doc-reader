# Backlog: vlm-ocr-doc-reader

**Версия:** 5.0
**Дата:** 2026-02-20
**Владелец:** Tech Lead

---

## Задачи

| ID | Название | Приоритет | Статус | Дата начала | Дата завершения | Зависимости |
|----|----------|-----------|--------|-------------|-----------------|-------------|
| 001 | Base utilities | High | Выполнена | 2026-01-27 | 2026-01-27 | — |
| 002 | VLM processing | High | Выполнена | 2026-01-27 | 2026-01-27 | 001 |
| 003 | OCR support | Medium | Выполнена | 2026-01-27 | 2026-01-27 | 001 |
| 004 | High-level operations | High | Выполнена | 2026-01-27 | 2026-01-27 | 002 |
| 005 | Критические баги | Critical | Выполнена | 2026-01-27 | 2026-01-28 | 001-004 |
| 006 | pyproject.toml и публикация | High | Выполнена | 2026-01-28 | 2026-01-28 | — |
| 007 | CLI интерфейс | High | Выполнена | 2026-01-28 | 2026-01-28 | — |
| 008 | Рефакторинг и отладка | Critical | Выполнена | 2026-02-09 | 2026-02-09 | 001-007 |
| 009 | DocumentState + OCR Registry | High | Не начата | - | - | 008 |
| 010 | Workspace (DiskStorage рефакторинг) | High | Не начата | - | - | 009 |
| 011 | DocumentReader (публичный API) | High | Не начата | - | - | 009, 010 |
| 012 | Scan — рефакторинг промптов, Registry из VLM | High | Не начата | - | - | 009, 011 |
| 013 | Resolve — OCR без VLM, page-based batching | High | Не начата | - | - | 009, 011 |
| 014 | CLI v2 (scan/resolve/verify/full-description) | Medium | Не начата | - | - | 011 |
| 015 | Verify — интерфейс (стратегия отложена) | Low | Не начата | - | - | 013 |

---

## Фаза 1: v0.1.0 (ЗАВЕРШЕНА)

Задачи 001-008. Подробности по задаче 008 см. `implementation_plan.md` (результаты тестирования).

---

## Фаза 2: v0.2.0 — Resolution Levels (ADR 001)

**Основание:** `decision_001_resolution_levels.md`

### Задача 009: DocumentState + OCR Registry

Новая модель данных: DocumentState с page states и OCR Registry. Registry хранит сущности (page_num, entity_id, prompt, resolution, value, context, verified, confidence). Создаётся при Scan, заполняется при Resolve.

### Задача 010: Workspace

Рефакторинг DiskStorage → Workspace: директория с поддиректориями `{stem}_{content_hash6}/`. Идентификация документа по содержимому (SHA256). Поддержка нескольких документов в одном workspace.

### Задача 011: DocumentReader

Новый публичный API: `DocumentReader.open(pdf, workspace=...)`. Методы `scan()`, `resolve()`, `verify()`, `page_status()`, `get_document_data()`. DocumentProcessor подчиняется DocumentReader.

### Задача 012: Scan (рефакторинг)

Разделение PROMPT_TEXT: Scan-промпт возвращает текст + OCR Registry как структурированные данные. VLM определяет ЧТО извлекать, но НЕ вызывает ask_ocr. OCR Registry персистируется.

### Задача 013: Resolve (OCR без VLM)

DocumentReader итерирует OCR Registry, группирует по page_num, вызывает OCR Client напрямую. Page-based batching — тактическое решение внутри этой задачи. VLM не участвует.

### Задача 014: CLI v2

Субкоманды: `scan`, `resolve`, `verify`, `full-description` (обратная совместимость = scan + resolve all). Параметр `--workspace`.

### Задача 015: Verify (интерфейс)

Только интерфейс: N параллельных OCR-вызовов, majority voting / confidence scoring. Реализация стратегии верификации откладывается до экспериментов.

---

## История изменений

| Дата | Версия | Изменения | Автор |
|------|--------|-----------|-------|
| 2026-02-20 | 5.0 | Фаза 2 по ADR 001: задача 009 переформулирована, добавлены 010-015 | Tech Lead |
| 2026-02-20 | 4.0 | Задачи 008-009, убран дубликат 007 | Tech Lead |
| 2026-01-28 | 3.0 | Задачи 006-007 | Tech Lead |
| 2026-01-27 | 2.0 | Укрупненные задачи (4 вместо 37) | Tech Lead |
| 2026-01-27 | 1.0 | Первая версия | Architect |
