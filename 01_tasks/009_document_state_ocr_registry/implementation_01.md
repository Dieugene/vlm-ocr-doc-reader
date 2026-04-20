# Отчет о реализации: DocumentState + OCR Registry (Задача 009)

## Что реализовано

Введена модель состояния документа для Resolution Levels (ADR-001): `ResolutionDocumentState` с `page_states`, `metadata` и персистентным `ocr_registry`. Реализован API StateManager для сохранения/загрузки состояния и OCR Registry, upsert по `entity_id`, `pending_entities`, `page_status`, `set_page_resolution`. DiskStorage расширен ключами `document_state/state` и `ocr_registry/registry`.

## Файлы

**Измененные:**
- `02_src/vlm_ocr_doc_reader/core/state.py` — добавлены `ResolutionLevel`, `PageResolution`, `OCRRegistryEntry`, `DocumentMetadata`, `ResolutionDocumentState`; функции сериализации; расширен `DiskStorage._get_file_path`; расширен `StateManager` (8 новых методов, `_resolution_state`)
- `02_src/vlm_ocr_doc_reader/core/__init__.py` — экспорт новых типов

## Особенности реализации

Реализовано согласно техническому плану (analysis_01.md).

- **Ключи int в JSON:** `page_states` сериализуется с ключами-строками, при загрузке конвертируются в `int`.
- **Файлы в корне state_dir:** `state.json` и `registry.json` — в `state_dir`, не в `cache_dir`.

## Известные проблемы

Нет

---

## Доработка по code-quality review

### C1 (обязательный): Синхронизация state.json и registry.json

- **Проблема:** `save_ocr_registry` обновлял только `registry.json`, `state.json` расходился.
- **Решение:** `state.json` — единый source of truth. `save_ocr_registry` вызывает `save_document_state()` перед записью `registry.json`. `load_ocr_registry` сначала читает из `document_state/state`, при отсутствии — из `ocr_registry/registry`.

### H1 (желательный): Валидация при десериализации

- `resolution`: приведение к 0|1|2, невалидные значения → 0.
- `page_states`: значения должны быть в `{"none","scan","resolved","verified"}`, невалидные пропускаются с warning.
- `page_num`: отрицательные/нечисловые пропускаются.

### H2 (желательный): Пустой entity_id

- В `upsert_ocr_entries` записи с пустым `entity_id` пропускаются с warning (избежание коллизий).
