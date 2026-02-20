# Decision 001: Resolution Levels, DocumentReader, Workspace

## Контекст

Текущая архитектура FullDescriptionOperation выполняет все три прохода (чтение текста, построение реестра OCR-сущностей, вызов OCR) в рамках одного монолитного invoke. Для тестового документа (8 страниц) это занимает 6 минут при 65 OCR-вызовах. При масштабировании до сотен страниц подход нежизнеспособен.

Корневая проблема — не скорость OCR, а отсутствие разделения фаз обработки документа по уровню детальности. OCR нужен не всегда и не для всех страниц.

Tech Lead эскалировал тактический вопрос (page-based OCR batching, задача 009). При обсуждении с пользователем принято решение рассмотреть задачу на стратегическом уровне, что привело к серии взаимосвязанных архитектурных решений.

---

## Решение 1: Resolution Levels

Три уровня детальности обработки страниц документа:

**Level 0 — Scan**
- Только VLM, без вызовов OCR.
- VLM читает страницы, извлекает текст, структуру, заголовки.
- Побочный продукт: OCR Registry — персистентный список сущностей, требующих точного извлечения (page_num, prompt). OCR не вызывается.
- Применение: быстрый первый проход по всему документу.

**Level 1 — Resolve**
- OCR вызывается по записям из OCR Registry для указанных страниц.
- Может быть запущен для всего документа или для выбранных страниц.
- Результаты записываются обратно в Registry.
- **VLM не участвует.** Resolve — механическое исполнение по готовому Registry (см. Решение 5).
- Батчинг OCR-запросов (page-based batching) — оптимизация внутри этого уровня.

**Level 2 — Verify**
- Повторный OCR с дополнительными проверками для критических данных.
- Механизм: N параллельных вызовов (разные DPI, промпты), majority voting / confidence scoring.
- Применяется точечно — для критических данных (суммы, ИНН, даты контрактов).
- В текущей версии фиксируется только интерфейс. Реализация стратегии верификации откладывается до экспериментов.

### Гранулярность

Resolution level привязан к **странице**, не к отдельной сущности. При Resolve страницы резолвятся все OCR-сущности на ней.

### Связь с Operations

Operations (FullDescription, Triage, Extraction) и Resolution Levels — ортогональные оси. Не каждая операция требует всех уровней. Каждая операция определяет resolution по умолчанию, вызывающий может переопределить.

### Идемпотентность

Каждый вызов проверяет текущее состояние Registry и выполняет только то, что ещё не сделано.

---

## Решение 2: OCR Registry

Персистентный артефакт в StateManager. Создаётся при Scan, заполняется при Resolve, верифицируется при Verify.

Структура записи:

```
page_num: int           # Номер страницы
entity_id: str          # Уникальный идентификатор сущности
prompt: str             # Запрос на извлечение (как если бы VLM вызывал ask_ocr)
resolution: 0|1|2       # Текущий уровень обработки
value: str | null       # Извлечённое значение (null до Resolve)
context: str | null     # Контекст (null до Resolve)
verified: bool          # Прошла ли верификация (Level 2)
confidence: str | null  # Результат верификации (например, "3/3")
```

Registry хранится в StateManager рядом с page images. При Scan VLM возвращает список сущностей как структурированные данные (не через tool calling).

---

## Решение 3: DocumentReader — публичный API

Вводится `DocumentReader` — единственная точка входа для работы с документом. CLI, программный API, интеграция с 07_agentic-doc-processing — все работают через него.

### Внутренняя структура

```
DocumentReader                          # Public API
├── state: DocumentState                # Модель знаний о документе
│   ├── pages: Dict[int, PageState]     # page_num → {resolution, text, headers}
│   ├── ocr_registry: OCRRegistry       # Все OCR-сущности
│   └── metadata: DocumentMetadata      # Общая информация, content_hash
├── processor: DocumentProcessor        # Оркестратор VLM/OCR (существующий, рефакторится)
│   ├── vlm_agent: VLMAgent
│   ├── state_manager: StateManager
│   └── tools: [OCRTool, ...]
└── operations: Dict[str, Operation]    # Зарегистрированные операции
```

Разделение ответственности:
- **DocumentReader** — публичный API, lifecycle документа, делегирует работу
- **DocumentState** — модель данных (что мы знаем о документе)
- **DocumentProcessor** — оркестрация VLM/OCR (как мы работаем)
- **Operations** — конкретные стратегии (FullDescription, Triage, Extraction)

### Публичный интерфейс

```python
reader = DocumentReader.open("contract.pdf", workspace="./workspace")

reader.scan()                          # Level 0, все страницы
reader.scan(pages=[1, 2, 3])           # Level 0, выбранные страницы
reader.resolve(pages=[48, 49])         # Level 1, выбранные страницы
reader.verify(pages=[48])              # Level 2

reader.page_status()                   # {1: "scan", 48: "resolved", ...}
reader.pending_entities(page=48)       # Список нерезолвленных сущностей

reader.get_document_data()             # DocumentData (итоговый результат)
```

### CLI

```bash
vlm-ocr-reader scan contract.pdf --workspace ./workspace
vlm-ocr-reader resolve contract.pdf --workspace ./workspace --pages 48,49
vlm-ocr-reader full-description contract.pdf   # scan + resolve all (обратная совместимость)
```

### Без workspace

Если workspace не указан — Memory storage, состояние не сохраняется. Обратная совместимость с текущим поведением.

---

## Решение 4: Workspace

### Организация

`workspace` — директория, внутри которой каждый документ получает свою поддиректорию автоматически. Путь к workspace всегда явный (задаётся пользователем).

```
workspace/
├── contract_a1b2c3/                   # документ 1
│   ├── pages/                         # отрендеренные страницы
│   ├── registry.json                  # OCR Registry
│   └── state.json                     # page states, metadata
├── annual_report_d4e5f6/              # документ 2
│   ├── pages/
│   ├── registry.json
│   └── state.json
└── index.json                         # реестр документов (опционально)
```

### Идентификация документа по содержимому

Имя поддиректории: `{stem}_{content_hash6}`, где `content_hash6` — первые 6 символов SHA256 от содержимого файла.

Следствия:
- **Файл переместили** → хеш тот же → состояние подхватывается, перечитывать не нужно.
- **Файл изменили** (новая версия) → хеш другой → новая поддиректория, чистый старт.
- **Два файла с одинаковым именем, разным содержимым** → разные поддиректории, без коллизий.

Стоимость хеширования при каждом `open()` — доли секунды даже для больших PDF.

### state.json

```json
{
  "source_path": "/data/contracts/contract.pdf",
  "content_hash": "a1b2c3d4e5f6...",
  "created_at": "2026-02-20T14:30:00",
  "pages_total": 48,
  "page_states": {"1": "scan", "2": "scan", "48": "resolved"}
}
```

`source_path` — справочное поле, обновляется при каждом open. Не используется для идентификации.

### Логика DocumentReader.open()

```
open(pdf_path, workspace=None):
    1. Если workspace=None → Memory mode, без персистенции
    2. Вычислить content_hash от pdf_path
    3. subdir = f"{pdf_path.stem}_{content_hash[:6]}"
    4. Если workspace/subdir/ существует → загрузить состояние
    5. Если нет → создать, инициализировать пустое состояние
```

### Поддержка нескольких документов

Один workspace обслуживает документы из любых директорий:

```python
reader1 = DocumentReader.open("/data/contracts/a.pdf", workspace="./workspace")
reader2 = DocumentReader.open("/archive/reports/b.pdf", workspace="./workspace")
```

---

## Решение 5: Resolve без VLM

На этапе Resolve VLM Agent не участвует. DocumentReader сам итерирует OCR Registry, группирует сущности по страницам и вызывает OCR Client напрямую.

### Поток

```
Scan:    DocumentReader → VLM Agent → читает текст, строит Registry (VLM решает ЧТО извлекать)
Resolve: DocumentReader → итерирует Registry → OCR Client напрямую (механическое исполнение)
Verify:  DocumentReader → итерирует Registry → N параллельных OCR-вызовов → сравнение
```

### Обоснование

- На этапе Scan VLM уже выполнил интеллектуальную работу — определил сущности и сформулировал запросы.
- Resolve — механическое исполнение по готовому списку. Повторный вызов VLM — лишний расход токенов и времени.
- Без VLM в цикле Resolve батчинг OCR-запросов становится тривиальным: DocumentReader сам контролирует группировку, без зависимости от недетерминированного batching Gemini.
- Если OCR вернул `no_data` или сомнительный результат — обработка на уровне DocumentReader (retry с изменённым prompt, эскалация на Verify).

### Влияние на задачу 009 (OCR batching)

Вопросы Tech Lead по батчингу полностью переосмысляются:
- **Где размещать батчинг** → в DocumentReader (не в VLMAgent, не в OCRTool). Снимается.
- **Формат промпта** → тактическое решение при реализации Resolve. Откладывается.
- **Partial failure** → тактическое решение при реализации Resolve. Откладывается.
- **Размер батча** → тактическое решение при реализации Resolve. Откладывается.
- **Режим сравнения V1/V2** → снимается. Individual vs batched — конфигурационный параметр.

---

## Обоснование (общее)

- Разделение по уровням детальности позволяет обрабатывать большие документы (сотни страниц) поэтапно, без обязательного OCR для каждой страницы.
- DocumentReader как единственная точка входа упрощает интеграцию для всех потребителей (CLI, API, пайплайны).
- OCR Registry как персистентный артефакт даёт инкрементальную обработку: scan всего документа → resolve только нужных страниц.
- Workspace с идентификацией по content hash обеспечивает изоляцию документов и устойчивость к перемещению файлов.
- Resolve без VLM устраняет зависимость от недетерминированного поведения Gemini и делает батчинг тривиальным.

## Последствия

- Вводится новый публичный класс `DocumentReader` — единственная точка входа в модуль.
- Вводится `DocumentState` с `OCRRegistry` — персистентная модель знаний о документе.
- `DocumentProcessor` рефакторится в оркестратор, подчинённый DocumentReader.
- Текущий монолитный PROMPT_TEXT в full_description.py разделяется на промпты по resolution levels.
- StateManager расширяется для хранения OCR Registry и page states.
- CLI расширяется командами `scan`, `resolve`, `verify`. Команда `full-description` сохраняется для обратной совместимости.
- Тактические решения по батчингу OCR (формат, размер, ошибки) откладываются до реализации Resolve в DocumentReader.

## Связанные решения

- Задача 009 (backlog.md) — переосмыслена в контексте данного ADR.
