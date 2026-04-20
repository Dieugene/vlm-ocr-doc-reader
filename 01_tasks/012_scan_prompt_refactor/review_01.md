# Review отчет: Task 012 — Scan (рефакторинг промптов, Registry из VLM)

## Общая оценка

**Статус:** Принято

**Краткий вывод:** Реализация соответствует ТЗ. Scan выполняется VLM-only без OCR, результат парсится в ScanPayload, нормализуется в OCRRegistryEntry, сохраняется через upsert. AC и TC выполнены.

## Проверка соответствия ТЗ

**Технические критерии (analysis_01.md):**
- [x] TC-1: `DocumentReader.scan(pages=...)` не вызывает OCR — ✅ `invoke_no_tools()` передаёт `tools=None` в vlm_client
- [x] TC-2: VLM-ответ парсится в ScanPayload, ocr_registry → `List[OCRRegistryEntry]` с resolution=0 — ✅ `parse_scan_response()`, `normalize_scan_registry()`
- [x] TC-3: page_states обновлены в "scan", OCR Registry сохранён — ✅ `set_page_resolution()`, `upsert_ocr_entries()`
- [x] TC-4: Повторный scan — upsert без дублей по entity_id — ✅ `upsert_ocr_entries()` мержит по entity_id
- [x] TC-5: `get_document_data()` возвращает актуальные text/structure — ✅ `save_operation_result("full_description", ...)` + `load_operation_result()`
- [x] TC-6: Не создавать новые тестовые модули — ✅ Соблюдено

**Acceptance Criteria (task_brief_01.md):**
- [x] AC-1: scan запускает VLM-only обработку, OCR не вызывается — ✅
- [x] AC-2: VLM-ответ трансформируется в OCR Registry entries — ✅
- [x] AC-3: page_states → "scan", OCR Registry в state — ✅
- [x] AC-4: Идемпотентность (upsert, без дублей) — ✅
- [x] AC-5: `get_document_data()` отражает данные после scan — ✅
- [x] AC-6: Resolve/Verify/CLI вне scope — ✅

## Проблемы

Проблем не обнаружено.

## Рекомендации (не блокирующие)

- **entity_id не-str:** В `normalize_scan_registry` при `entity_id` не-str (например, число от VLM) сейчас передаётся как есть. `OCRRegistryEntry.entity_id` ожидает `str`. Рекомендация: `entity_id = str(entity_id)` при непустом не-str значении для устойчивости.

## Решение

**Действие:** Принять

**Обоснование:** Все AC и TC выполнены, реализация соответствует analysis и task_brief. Блокеров нет.
