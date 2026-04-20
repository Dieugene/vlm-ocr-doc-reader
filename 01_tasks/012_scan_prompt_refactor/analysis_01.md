# Технический план: Task 012 — Scan, рефакторинг промптов, Registry из VLM

## 1. Анализ задачи

Реализовать Level 0 (`scan`) в `DocumentReader`: VLM читает страницы и возвращает структурированные данные (текст, структура, OCR Registry candidates) **без вызовов OCR** и **без** `ask_ocr` tool-calling. Результат scan обновляет `page_states`, сохраняет OCR Registry, обеспечивает идемпотентность и совместимость `get_document_data()`.

---

## 2. Текущее состояние

### Существующий код

| Модуль | Релевантное |
|--------|-------------|
| `reader.py` | `scan()` — заглушка: обновляет page_states, OCR Registry пустой |
| `full_description.py` | `PROMPT_TEXT` — монолитный трёхпроходный промпт с ask_ocr в проходе 3 |
| `processor.py` | `DocumentProcessor` — инициализирует VLMAgent, OCRTool, рендерит страницы |
| `vlm_agent.py` | `invoke(prompt, images)` — tool calling loop; при `tools=None` возвращает только text |
| `state.py` | `upsert_ocr_entries()`, `save_ocr_registry()`, `set_page_resolution()`, `save_operation_result()` |
| `ocr_tool.py` | `ask_ocr` — регистрируется в VLMAgent; для Scan **не** регистрировать |

### Что переиспользовать

- `DocumentProcessor` — источник страниц и VLMAgent
- `StateManager.upsert_ocr_entries()`, `set_page_resolution()`, `save_operation_result()`
- `OCRRegistryEntry` — модель записи Registry
- `PDFRenderer` [G{N}] маркеры — уже в промпте
- `VLMAgent.invoke()` — вызывать **без tools** (или с пустым tools)

---

## 3. Предлагаемое решение

### 3.1. Общий подход

1. Создать **Scan-промпт** — урезанная версия PROMPT_TEXT: проходы 1 и 2 (текст + реестр), **без** прохода 3 (ask_ocr).
2. Вызывать VLM **без OCR tool** — добавить `VLMAgent.invoke_no_tools()` для вызова без tools.
3. Парсить ответ VLM в `ScanPayload` (text, structure, ocr_registry).
4. Нормализовать raw entries в `OCRRegistryEntry` через `normalize_scan_registry()`.
5. upsert в StateManager, обновить page_states, сохранить full_description-совместимый результат.

### 3.2. Компоненты

#### ScanPrompt (модуль `operations/scan.py`)

- **Назначение:** Текст промпта для Scan — извлечение текста, структуры, списка OCR-кандидатов.
- **Содержание:** Нумерация [G{N}], проход 1 (текст), проход 2 (реестр сущностей с page_num, prompt, context). Явно: **НЕ вызывай ask_ocr**.
- **Интерфейс:** Константа `SCAN_PROMPT_TEXT` + инструкция формата ответа (JSON).

#### ScanResponseParser

- **Назначение:** Парсинг текстового ответа VLM в структурированный payload.
- **Интерфейс:** `parse_scan_response(text: str) -> ScanPayload`
- **Логика:** Извлечь JSON из ответа (markdown fence, raw JSON), валидировать поля. Fallback: пустой payload при ошибке.

#### normalize_scan_registry

- **Назначение:** Преобразование raw dict из VLM в `List[OCRRegistryEntry]`.
- **Интерфейс:** `normalize_scan_registry(raw_entries: list[dict], fallback_page: int | None) -> list[OCRRegistryEntry]`
- **Логика:** Для каждой записи: page_num (обязательно), entity_id (генерировать из `f"scan_{page_num}_{hash(prompt)[:8]}"` если пусто), prompt, resolution=0. Пропускать записи без prompt или с невалидным page_num.

#### DocumentReader.scan()

- **Назначение:** Оркестрация Scan.
- **Логика:**
  1. `_normalize_pages(pages)`, `_ensure_pages_rendered()`
  2. Собрать images для страниц из `state_manager.load_page()`
  3. `vlm_agent.set_system_prompt(SCAN_PROMPT_TEXT)`; `invoke_no_tools(user_prompt, images)`
  4. `parse_scan_response(response["text"])` → ScanPayload
  5. `normalize_scan_registry(payload.ocr_registry, fallback_page)` → entries
  6. `state_manager.upsert_ocr_entries(entries)`
  7. Для каждой страницы: `state_manager.set_page_resolution(page_num, "scan")`
  8. `state_manager.save_operation_result("full_description", {text, structure, tables})` — для `get_document_data()`

#### VLMAgent.invoke_no_tools()

- **Назначение:** Вызов VLM без tool calling.
- **Логика:** Аналогично invoke(), но передаёт `tools=None` в vlm_client.invoke(). Гарантирует отсутствие OCR-вызовов.

### 3.3. Структуры данных

```python
# ScanPayload (TypedDict или dataclass)
ScanPayload:
  text: str
  structure: dict  # {"headers": [...]}
  ocr_registry: list[dict]  # [{"page_num": int, "entity_id"?: str, "prompt": str, "context"?: str}]
```

Формат ответа VLM (в промпте):

```json
{
  "text": "полный текст документа...",
  "structure": {"headers": [{"level": 1, "title": "...", "page": 1}]},
  "ocr_registry": [
    {"page_num": 5, "prompt": "найди ОГРН организации", "context": "рядом с реквизитами"},
    {"page_num": 5, "entity_id": "ogrn_p5", "prompt": "извлеки ИНН"}
  ]
}
```

### 3.4. Ключевые алгоритмы

**Идемпотентность scan:** `upsert_ocr_entries` по entity_id. Повторный scan тех же страниц — новые/обновлённые записи мержатся, дублей нет. page_states перезаписываются в "scan" — допустимо.

**Генерация entity_id:** Если VLM не вернул entity_id — `entity_id = f"scan_{page_num}_{hashlib.sha256(prompt.encode()).hexdigest()[:8]}"`.

**Порядок сохранения:** Сначала upsert_ocr_entries (Registry), затем set_page_resolution (page_states), затем save_operation_result (для get_document_data).

### 3.5. Изменения в существующем коде

| Файл | Изменения |
|------|-----------|
| `operations/scan.py` (новый) | `SCAN_PROMPT_TEXT`, `ScanPayload`, `parse_scan_response()`, `normalize_scan_registry()` |
| `core/vlm_agent.py` | Добавить `invoke_no_tools(prompt, images)` — вызов vlm_client с tools=None |
| `core/reader.py` | Реализовать `scan()`: invoke_no_tools, парсинг, upsert, set_page_resolution, save_operation_result |

---

## 4. План реализации

1. **Добавить `invoke_no_tools()` в VLMAgent** — вызов vlm_client.invoke с tools=None.
2. **Создать `operations/scan.py`** — SCAN_PROMPT_TEXT, ScanPayload, parse_scan_response(), normalize_scan_registry().
3. **Реализовать `DocumentReader.scan()`** — собрать images, вызвать invoke_no_tools, парсить, upsert, set_page_resolution, save_operation_result.

---

## 5. Технические критерии приемки

- [ ] TC-1: `DocumentReader.scan(pages=...)` не вызывает OCR (нет обращений к OCRClient/OCRTool).
- [ ] TC-2: VLM-ответ парсится в ScanPayload; ocr_registry нормализуется в `List[OCRRegistryEntry]` с resolution=0.
- [ ] TC-3: После scan: page_states обновлены в "scan", OCR Registry сохранён в state.
- [ ] TC-4: Повторный scan тех же страниц — upsert без дублей по entity_id.
- [ ] TC-5: `get_document_data()` возвращает актуальные text и structure после scan.
- [ ] TC-6: Не создавать новые тестовые модули (использовать существующие тесты при наличии).

---

## 6. Важные детали для Developer

- **VLMAgent.invoke_no_tools()** — при вызове передавать в vlm_client `tools=None` или пустой список, чтобы Gemini не предлагал function calls.
- **Gemini JSON mode:** Fallback: парсить JSON из markdown ```json ... ```. Использовать `_clean_json_fence` из full_description.py.
- **entity_id пустой:** normalize_scan_registry обязан сгенерировать уникальный id (например `scan_{page_num}_{hash8}`), иначе upsert пропустит запись (пустой entity_id скипается в upsert_ocr_entries).
- **StateManager.save_operation_result** — ключ "full_description" для совместимости с `get_document_data()`. Формат: `{text, structure, tables}` (tables=[]).
- **Не создавать новые тестовые модули** — по требованию задачи.

---

## 7. Граница 012 vs 013

| Аспект | Задача 012 (Scan) | Задача 013 (Resolve) |
|--------|-------------------|----------------------|
| **Роль** | Создаёт OCR Registry | Потребляет и заполняет Registry |
| **VLM** | Участвует (читает, формирует кандидатов) | Не участвует |
| **OCR** | Не вызывается | Вызывается напрямую (OCR Client) |
| **Registry** | Заполняется entries с resolution=0, value=null | Обновляет value, context, resolution=1 |
| **Вход** | PDF pages | Pending entities из Registry |
| **Выход** | text, structure, ocr_registry (candidates) | Заполненные value/context в Registry |
| **Идемпотентность** | upsert по entity_id, page_states="scan" | Пропуск уже resolved (resolution≥1) |

**Кратко:** 012 производит Registry (VLM решает *что* извлекать), 013 исполняет Registry (OCR извлекает *значения*).
