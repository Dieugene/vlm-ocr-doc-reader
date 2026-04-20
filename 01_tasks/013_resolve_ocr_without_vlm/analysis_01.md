# Технический план: Task 013 — Resolve OCR без VLM, page-based batching

## 1. Анализ задачи

Реализовать Level 1 (`resolve`) в `DocumentReader`: брать pending OCR entities из Registry, группировать по страницам, выполнять OCR напрямую (без VLM), записывать результаты в Registry. Обработка частичных ошибок: успешные сущности сохраняются, неудачные остаются pending для повторного resolve.

## 2. Текущее состояние

**Существующий код для переиспользования:**

- `02_src/vlm_ocr_doc_reader/core/reader.py` — `resolve()` уже фильтрует pending по pages, но не вызывает OCR (delegation point для 013).
- `02_src/vlm_ocr_doc_reader/core/ocr_tool.py` — `OCRTool.execute(page_num, prompt)` загружает страницу из StateManager и вызывает OCR Client. Идеально подходит для Resolve.
- `02_src/vlm_ocr_doc_reader/core/ocr_client.py` — `extract(image, prompt, page_num)` возвращает `{status, value, context, explanation}`. `status`: `"ok"` | `"no_data"` | `"error"`.
- `02_src/vlm_ocr_doc_reader/core/state.py` — `pending_entities(page_num)`, `upsert_ocr_entries()`, `set_page_resolution()`, `load_page()`. `OCRRegistryEntry` с полями `resolution`, `value`, `context`.

**Ограничение:** `DocumentProcessor` создаёт `OCRTool` внутри `__init__`, но не сохраняет его как атрибут — используется только для регистрации в VLMAgent. Для Resolve нужен доступ к OCR-исполнению.

## 3. Предлагаемое решение

### 3.1. Общий подход

1. `DocumentProcessor` сохраняет и экспонирует `ocr_tool` (если QWEN_API_KEY задан).
2. `DocumentReader.resolve()` получает pending entities, группирует по `page_num`, для каждой страницы загружает изображение один раз и последовательно вызывает OCR для каждой сущности на странице.
3. Результаты применяются через `apply_ocr_result()`: при `ok`/`no_data` — обновление entry и `resolution=1`; при `error` — entry не меняется (остаётся pending).
4. После обработки страницы обновляется `page_states` (resolved, если все сущности страницы обработаны; иначе — по фактическому состоянию).

### 3.2. Page-based batching

**Суть:** Группировка сущностей по `page_num` и обработка страница за страницей.

- **Зачем:** Один вызов `load_page(page_num)` на страницу вместо N вызовов для N сущностей. Изображение страницы загружается один раз и передаётся в OCR для каждой сущности на этой странице.
- **Алгоритм:**
  1. Получить pending entities, отфильтровать по `pages`.
  2. Сгруппировать по `page_num`: `{page_num: [entry1, entry2, ...]}`.
  3. Для каждой страницы (в порядке page_num):
     - Загрузить изображение `load_page(page_num)`.
     - Если изображения нет — залогировать, пропустить страницу, перейти к следующей.
     - Для каждой сущности на странице: вызвать `ocr_tool.execute(page_num, prompt)`.
     - Применить результат к entry (см. apply_ocr_result).
     - Сохранить обновлённые entries через `upsert_ocr_entries()`.
  4. Обновить `page_states` для страниц, где хотя бы одна сущность была успешно обработана.

**Порядок страниц:** Сортировка по `page_num` для предсказуемости и удобства логов.

### 3.3. Обработка partial failures

**Принцип:** Ошибка одной сущности не прерывает resolve остальных. Успешные результаты сохраняются сразу.

- **`status == "ok"`:** Записываем `value`, `context`, `resolution=1`. Entry считается resolved.
- **`status == "no_data"`:** Записываем `value=""`, `context` из explanation (или пусто), `resolution=1`. OCR отработал, данных нет — считаем resolved.
- **`status == "error"`:** Entry не обновляем. `resolution` остаётся 0. Логируем ошибку. Сущность останется в pending при следующем resolve.
- **Исключение при вызове OCR (QwenClientError и др.):** Ловить, логировать, не обновлять entry. Продолжать со следующей сущностью.
- **Страница не найдена (`load_page` вернул None):** Пропустить все сущности этой страницы, залогировать. Не обновлять entries.

**Персистенция:** После обработки каждой страницы вызывать `upsert_ocr_entries()` для обновлённых entries. Так при сбое в середине resolve уже обработанные страницы сохранены.

### 3.4. Компоненты

#### group_registry_by_page

- **Назначение:** Группировка entries по `page_num`.
- **Сигнатура:** `group_registry_by_page(entries: list[OCRRegistryEntry]) -> dict[int, list[OCRRegistryEntry]]`
- **Логика:** Итерировать entries, добавлять в `dict[page_num]`. Ключи — int, значения — списки. Страницы в произвольном порядке (сортировка при итерации в resolve).

#### apply_ocr_result

- **Назначение:** Создать обновлённый entry по результату OCR.
- **Сигнатура:** `apply_ocr_result(entry: OCRRegistryEntry, value: str | None, context: str | None, resolution: int) -> OCRRegistryEntry`
- **Логика:** Вернуть новый `OCRRegistryEntry` с теми же `page_num`, `entity_id`, `prompt`, но обновлёнными `value`, `context`, `resolution`. Остальные поля (`verified`, `confidence`) не менять.
- **Использование:** Вызывать только при `status in ("ok", "no_data")`. При `"error"` не вызывать.

#### DocumentReader._resolve_entities

- **Назначение:** Внутренняя логика resolve: итерация по страницам, вызов OCR, применение результатов.
- **Зависимости:** `_state_manager`, `_processor.ocr_tool` (через новый атрибут processor).
- **Логика:** См. разделы 3.2 и 3.3. Вызывается из `resolve()` после фильтрации pending.

#### DocumentProcessor.ocr_tool

- **Назначение:** Экспозиция OCRTool для Resolve.
- **Изменение:** В `__init__` после создания `ocr_tool` сохранять `self.ocr_tool = ocr_tool`. Если QWEN_API_KEY не задан — `self.ocr_tool = None`.

### 3.5. Структуры данных

Используются существующие:

- `OCRRegistryEntry` — без изменений.
- Результат `OCRTool.execute` / `OCRClient.extract`: `{status, value, context, explanation}`.

### 3.6. Изменения в существующем коде

| Файл | Изменение |
|------|-----------|
| `processor.py` | Сохранять `self.ocr_tool = ocr_tool` (или `None` при отсутствии QWEN_API_KEY) |
| `reader.py` | Реализовать `resolve()`: вызов `_resolve_entities()`, проверка `ocr_tool is not None` |
| `reader.py` или `state.py` | Добавить `group_registry_by_page`, `apply_ocr_result` (см. task_brief — можно в state или отдельный модуль) |

### 3.7. Идемпотентность

- `pending_entities()` уже возвращает только `resolution < 1`. Повторный `resolve(pages)` не затронет уже resolved entries.
- После успешного применения результата entry получает `resolution=1` и больше не попадёт в pending.

## 4. План реализации

1. **DocumentProcessor:** Сохранить `self.ocr_tool = ocr_tool` в `__init__` (при создании) или `None`.
2. **group_registry_by_page:** Добавить в `state.py` (рядом с OCRRegistryEntry) или в `reader.py` как приватную функцию. Рекомендация: `state.py` — утилита для работы с Registry.
3. **apply_ocr_result:** Добавить в `state.py` (рядом с OCRRegistryEntry).
4. **DocumentReader._resolve_entities:** Реализовать в `reader.py` — группировка, цикл по страницам, вызов OCR, применение результатов, upsert, обновление page_states.
5. **DocumentReader.resolve:** Вызвать `_resolve_entities(pending)` после фильтрации; при `ocr_tool is None` — залогировать и выйти (или поднять понятную ошибку).

## 5. Технические критерии приемки

- [ ] TC-1: `resolve(pages=...)` не вызывает VLM (нет обращений к vlm_agent).
- [ ] TC-2: Pending entities фильтруются по `pages`; при `pages=None` — все страницы.
- [ ] TC-3: Сущности группируются по `page_num`; каждая страница обрабатывается с одним `load_page`.
- [ ] TC-4: При `status in ("ok", "no_data")` entry обновляется (`value`, `context`, `resolution=1`) и сохраняется.
- [ ] TC-5: При `status == "error"` или исключении entry не обновляется; resolve продолжается.
- [ ] TC-6: Повторный `resolve(pages)` не меняет уже resolved entries (идемпотентность).
- [ ] TC-7: При `ocr_tool is None` resolve завершается без падения (логирование или явная ошибка).

## 6. Важные детали для Developer

- **QWEN_API_KEY:** Если не задан, `DocumentProcessor` создаётся с `ocr_tool=None`. В этом случае `resolve` должен завершаться с понятным сообщением (логирование + return или ValueError).
- **WorkspaceBackend vs DiskStorage:** `load_page` использует ключ `pages/{page_num:03d}`. WorkspaceBackend маппит на `pages_dir/page_{name}.png`. Убедиться, что ключи совместимы (в state.py `save_page` использует `f"pages/{page_num:03d}"`).
- **OCRClient.extract:** При `no_data` возвращает `value=""`, `status="no_data"`. Считаем это успешным вызовом — записываем resolution=1 с пустым value.
- **page_states:** После resolve страницы обновлять `set_page_resolution(page_num, "resolved")` только для страниц, где хотя бы одна сущность была успешно обработана. Если на странице все сущности в error — page_state можно оставить "scan" или не менять (уточнить по контексту ADR: при Resolve страницы — все сущности на ней; если часть в error — страница частично resolved; для простоты: ставить "resolved" если хотя бы одна сущность обновлена).
- **Не создавать новые тестовые модули** — использовать существующие тесты или добавлять тесты в текущие модули по необходимости.
