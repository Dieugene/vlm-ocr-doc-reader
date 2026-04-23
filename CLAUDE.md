# CLAUDE.md — vlm-ocr-doc-reader

Этот файл — оперативный контекст для работы агента над данным подпроектом. Источники истины — код в `02_src/` и `00_docs/architecture/overview.md`. Сюда вынесено то, чего нет в коде и доках: история решений, эмпирика, подводные камни, открытые задачи.

## Моя роль

Я — Tech Lead этого подпроекта. Полное описание роли в `D:\_workspace\docs-processing\.agents\tech-lead.md`. Архитектурные решения принимаю не я — они в `00_docs/architecture/overview.md` и ADR. Реализация — моя.

## Что за проект

Python-пакет (v0.1.0) для чтения документа через Vision Language Model + точечный OCR. Public API — `DocumentReader.open(pdf, workspace=...)`. Три уровня детальности по ADR-001 (`scan` / `resolve` / `verify`). Workspace identifies документ по `{stem}_{sha256[:6]}/`. Подробная архитектура — `00_docs/architecture/overview.md`. Список открытых задач — `00_docs/backlog.md`.

## Текущая конфигурация (на момент написания)

- **VLM (scan):** `qwen3-vl-flash` через `QwenVLMClient` (DashScope OpenAI-compat endpoint).
- **OCR (resolve):** `qwen-vl-ocr-2025-11-20` (специализированная Qwen3-VL OCR модель) через `QwenOCRClient`.
- **Endpoint:** `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` (Singapore, intl).
- **API ключ:** один общий — `DASHSCOPE_API_KEY` (или alias `QWEN_API_KEY`) в `.env` корня подпроекта.
- **Default resolve:** `chunk_size=5`, `max_workers=5` (env `OCR_CHUNK_SIZE`, `OCR_MAX_WORKERS`).
- **Default scan batch:** 2 страницы на VLM-запрос (env `VLM_SCAN_BATCH_SIZE`).
- **Render DPI:** 150 захардкожен (`render_dpi` в `ProcessorConfig` есть, но через CLI не пробрасывается).

## История ключевых решений (этой сессии)

1. **Gemini убран полностью.** Причина: с 2026-04-15 у `gemini-2.5-flash` и `gemini-3-flash-preview` массовые 503 «high demand» (подтверждено множеством источников — `discuss.ai.google.dev`, `googleapis/python-genai#1373`). Не наш баг, не временная перегрузка модели — capacity issue Google. Дальше работаем только с Qwen.
2. **Внутренний формат сообщений — OpenAI-style** (`messages` с `role`/`content`/`tool_calls`/`tool_call_id`). Это **продуктовый контракт**, а не «угоди OpenAI». Раньше `VLMAgent` хранил Gemini-specific `parts/inline_data/functionCall` — это была проекция исчезающего провайдера. Теперь любой новый клиент конвертирует свой формат в/из OpenAI на своей стороне. `QwenVLMClient` — pass-through (DashScope принимает OpenAI натив).
3. **OCR-модель: `qwen-vl-plus` → `qwen-vl-ocr-2025-11-20`.** Изначально (с самого первого коммита) на OCR-слое стояла **общая VL-модель**, а не OCR-специализированная. Пользователь обнаружил это ретроспективно — никем не менялось, просто исторический выбор. Заменили на специализированную OCR-модель Qwen3-VL — точнее на длинных URL/кодах, дешевле в 3 раза (input $0.07/1M vs ~$0.21/1M).
4. **`structured_output` (Pydantic-схемы) НЕ используем для OCR.** Пользователь раньше пробовал — были проблемы валидности. Парсим текстовые блоки `[ЗАДАЧА N] / ЗНАЧЕНИЕ: / КОНТЕКСТ: / ПОЯСНЕНИЕ:` через regex.
5. **Multi-question OCR.** В одном запросе картинка + список из N вопросов. Парсер `parse_multi_task_response` ищет блоки `[ЗАДАЧА N]` и для каждого вытаскивает значение/контекст/пояснение. Дефолт `chunk_size=5`. `extract()` оставлен как обёртка над `extract_batch([prompt])[0]` для обратной совместимости.
6. **Параллельный resolve через `ThreadPoolExecutor`.** Все (page × chunk) задачи собираются в плоский список, идут в пул `max_workers`, результаты группируются по странице, persist пер страница. Дефолт 5 worker'ов.
7. **Scan-промпт переписан с тремя жёсткими критериями для записей `ocr_registry`:** атомарность (одно значение в строку), конкретность («другой человек должен суметь найти, не видя страницу»), обоснованность (`context` 5–15 слов реального текста). Плюс явный image-to-page mapping в user-промпте каждого батча. Это убрало мусорные сущности и misattribution между страницами в batch.

## Эмпирика на тестовом документе (`03_data/test_document.pdf`, 8 стр.)

После всех фиксов: `scan` → 32 атомарных registry-записи, распределение `{p1:1, p2:4, p3:7, p4:3, p5:7, p6:2, p7:5, p8:3}`.

Grid `chunk_size × max_workers` (sequential vs parallel):

| chunk | workers | time | ok | no_data | unres | consistency vs (1,1) |
|---|---|---|---|---|---|---|
| 1 | 1 | 184s | 31 | 1 | 0 | BASELINE |
| **1** | **5** | **48s** | **31** | **1** | **0** | **31/32 (97%)** |
| 5 | 1 | 65s | 29 | 2 | 1 | 17/32 |
| 5 | 5 | 19s | 29 | 2 | 1 | 18/32 |
| 8 | 1 | 53s | 29 | 2 | 1 | 16/32 |
| 8 | 5 | 13s | 29 | 2 | 1 | 16/32 |

**Ключевые выводы:**
- Параллель даёт чистый ×3.5–4 без потери качества.
- Качество (ok) зависит **только** от `chunk_size`, не от concurrency.
- **Multi-question ломает consistency:** при chunk≥3 ровно ~50% значений отличаются от chunk=1. Какие из них правильные — без эталона не знаем (это и есть задача Level 2).
- Одна и та же сущность `scan_8_d89286a4` (URL на p8) стабильно падает в `error` на chunk≥3 (модель не выводит блок `[ЗАДАЧА N]` для неё).

Дампы grid — `04_logs/chunk_grid_results.json`, `04_logs/chunk_workers_grid.json` (gitignored).

## Что сделано / не сделано

**Сделано в текущей сессии (закоммичено `e9ae0f2`):**
- Замена Gemini → Qwen (VLM + OCR, новая OCR-модель, удаление GeminiVLMClient + Gemini-mock тестов)
- BaseVLMClient + VLMAgent на OpenAI-формат
- SCAN_PROMPT_TEXT с критериями атомарности
- E2E baseline 38 entries / 37 ok / 1 no_data

**Сделано после `e9ae0f2`, ещё не закоммичено (этапы 3+4):**
- `extract_batch(image, prompts, page_num)` в BaseOCRClient + Qwen реализация
- Парсер `parse_multi_task_response` для блоков `[ЗАДАЧА N]`
- `DocumentReader.resolve(chunk_size, max_workers)` через ThreadPoolExecutor
- CLI: `--chunk-size`, `--max-workers`
- env: `OCR_CHUNK_SIZE`, `OCR_MAX_WORKERS`
- `scripts/ocr_chunk_grid.py` — grid `chunks × workers`
- Обновления `overview.md` и `backlog.md`

**Открыто (`backlog.md`):**
- **Этап 5: Level 2 `verify` с confidence scoring.** Самый назревший пункт. Решает прямо наблюдаемую проблему: при multi-question ~50% ответов отличаются от baseline, но мы не знаем какие правильные. Стратегия: для каждой сущности — N независимых прогонов по разным «осям» (chunk_size / DPI / temperature / модель), majority voting, поле `confidence` в `OCRRegistryEntry`. Заслуживает отдельного ADR (`decision_002_*`). Возможно частично «бесплатно» из grid-данных.
- **Тест на больших документах** (30–100+ страниц, разные типы — регуляторные/финансовые/научные).

## Структура и важные пути

```
01_projects/vlm-ocr-doc-reader/
├── 00_docs/                    # архитектура, ADR, backlog
├── 01_tasks/                   # пусто (без формального task-фолдера)
├── 02_src/
│   ├── vlm_ocr_doc_reader/     # пакет
│   │   ├── core/
│   │   │   ├── reader.py       # public API DocumentReader
│   │   │   ├── processor.py    # рендер + VLMAgent + OCRTool
│   │   │   ├── vlm_agent.py    # OpenAI-style messages, tool loop
│   │   │   ├── vlm_client.py   # BaseVLMClient (контракт)
│   │   │   ├── qwen_vlm_client.py
│   │   │   ├── ocr_client.py   # OCRConfig + Base + QwenOCRClient (multi-question)
│   │   │   ├── ocr_tool.py     # ask_ocr tool для VLMAgent (legacy путь)
│   │   │   └── state.py        # StateManager + Workspace + OCRRegistryEntry
│   │   ├── operations/
│   │   │   ├── scan.py         # SCAN_PROMPT_TEXT + parser
│   │   │   └── full_description.py  # legacy three-pass
│   │   ├── preprocessing/renderer.py
│   │   ├── schemas/{config,document,common}.py
│   │   └── cli.py
│   ├── _reference/             # старые исторические клиенты, не часть пакета
│   └── tests/
├── 03_data/                    # gitignored, тестовые PDF
├── 04_logs/                    # gitignored, логи и grid-дампы
├── scripts/
│   ├── qwen_vlm_probe.py       # connectivity test разных Qwen3-VL моделей
│   └── ocr_chunk_grid.py       # эмпирический grid chunk × workers
├── venv/                       # gitignored, см. ниже
└── CLAUDE.md                   # этот файл
```

## Workflow

- **Виртуальное окружение:** `./venv/Scripts/python.exe`. Создан `python -m venv venv` из `C:\Python313`. Команды через `./venv/Scripts/vlm-ocr-reader.exe ...` или `./venv/Scripts/python.exe -m vlm_ocr_doc_reader.cli ...`.
- **E2E:** `./venv/Scripts/vlm-ocr-reader.exe scan 03_data/test_document.pdf --workspace 04_logs/<run> --log-level INFO`, потом `... resolve ... --chunk-size 5 --max-workers 5`.
- **Grid:** `./venv/Scripts/python.exe scripts/ocr_chunk_grid.py --pdf 03_data/test_document.pdf --workspace 04_logs/<run> --chunks 1,5,8 --workers 1,5`.
- **Unit-тесты:** `./venv/Scripts/python.exe -m pytest 02_src/tests/unit/ 02_src/tests/test_utils/ 02_src/tests/test_preprocessing/ 02_src/tests/test_core/test_state.py 02_src/tests/test_core/test_ocr_*.py -q`. Тесты с `pytestmark.skipif` пропускаются без API-ключа.

## Подводные камни

- **`D:\_storage_cbr\020_docs_vision\08_vlm-ocr-doc-reader\` — это бэкап до переезда репозитория**, оставлен пользователем намеренно. **Не трогать.** Старый venv там работает с устаревшим editable install из старого пути — если что-то странное с импортами, проверь `vlm_ocr_doc_reader.__file__`. Текущий рабочий путь — `D:\_workspace\docs-processing\01_projects\vlm-ocr-doc-reader`.
- **Тесты `test_vlm_agent.py` и `test_full_pipeline.py` требуют `DASHSCOPE_API_KEY`** — без ключа skipped. CI без ключа покажет «X passed, Y skipped».
- **`02_src/_reference/` — старые исторические референсы** вне пакета. Не часть `vlm_ocr_doc_reader.*`. Туда не лезть без причины.
- **`03_data/` и `04_logs/` gitignored** — экспериментальные артефакты не утекут в коммит, но не пушь оттуда что-то важное.
- **Когда меняешь промпт, проверяй на конкретном документе через E2E** — никакие unit-тесты качество промпта не покрывают.

## Принципы работы (из feedback пользователя)

- **Код — источник истины, не доки.** Начинать всегда с `02_src/`. Доки могут отставать.
- **Доки описывают current state**, не историю задач/фаз/статусов. ADR — исключение (исторические по природе).
- **Не дробить большие WIP-коммиты на «чистые» по задачам ради истории** — это не даёт ценности пользователю.
- **Не писать тесты «для метрики»** и не докладывать «X/X passed» как доказательство работоспособности. Зелёный тест = механика крутится, не качество.
- **VL-модели плохо играют в OCR** — пользователь предпочитает специализированные OCR-модели для OCR-задач.
- **Не использовать `structured_output`/Pydantic-схемы для OCR** — раньше валилось.
- **Не предлагать гранулярные раскладки коммитов** без явного запроса.
- **Не предлагать брать VL-модели для OCR-замены.** Если выбираем OCR-модель — это должна быть OCR-специализированная.
- **Не имитировать архитектурные решения** — эскалировать к Architect через `_questions_architect.md` (стандарт tech-lead). На текущем этапе отдельного Architect нет, эскалация — пользователю.

## Что можно делать без согласований

Пользователь явно дал автономию по этапам 3–5: «общую логику и цели ты понял, я не вижу теперь необходимости согласовывать со мной каждый шаг». Согласовывать только: смену провайдера, удаление кода, изменение public API без явной мотивации, действия с git/push.
