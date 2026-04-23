# Архитектура

Python-пакет для обработки документов через VLM и OCR — оба провайдера сейчас Qwen через DashScope (`qwen3-vl-flash` для чтения структуры, `qwen-vl-plus` для точечного OCR). Ключевой приём — разделение по уровням детальности (Resolution Levels): VLM быстро читает структуру и текст, OCR точечно извлекает критичные идентификаторы.

## Resolution Levels

Обработка страницы проходит один из трёх уровней. Уровень привязан к странице, а не к отдельной сущности.

| Level | Команда | Кто работает | Что делает |
|-------|---------|--------------|------------|
| 0 | `scan` | VLM | Читает страницы, возвращает текст + структуру + OCR Registry (что извлекать точно) |
| 1 | `resolve` | OCR | Выполняет OCR по записям Registry для страниц |
| 2 | `verify` | — | Интерфейс есть, стратегия majority voting не реализована |

`resolve` не вызывает VLM: `DocumentReader` группирует Registry по страницам, для каждой страницы отправляет OCR одну картинку + список вопросов (multi-question, размер чанка задаётся параметром `chunk_size` или env `OCR_CHUNK_SIZE`, по умолчанию 5).

Обоснование выбора — см. [ADR 001](decision_001_resolution_levels.md).

## OCR Registry

Персистентный список целей извлечения. Запись:

```
page_num    — номер страницы (1-based)
entity_id   — уникальный ключ для upsert
prompt      — что искать ("ОГРН организации")
resolution  — 0 (создано при scan), 1 (resolved), 2 (verified)
value       — извлечённое значение (null до resolve)
context     — ориентир рядом (опционально)
verified    — прошла ли верификация
confidence  — результат верификации (например "3/3")
```

Создаётся при `scan`, пополняется при `resolve`, обновляется при `verify`.

## Workspace

Директория для персистентного состояния. Документы живут в поддиректориях `{stem}_{hash6}/`, где `hash6` — первые 6 символов SHA256 содержимого файла.

```
workspace/
├── contract_a1b2c3/
│   ├── pages/             рендеры страниц (PNG)
│   ├── state.json         page_states + metadata + ocr_registry
│   ├── registry.json      дубликат ocr_registry (для удобства)
│   ├── vlm_responses/     сырые VLM-ответы
│   └── results/           YAML с DocumentData
```

Следствия идентификации по содержимому:

- Файл переместили → хэш тот же → состояние подхватывается.
- Файл изменили → другой хэш → новая поддиректория, чистый старт.
- Без `workspace` — `MemoryStorage`, ничего не персистируется.

## Модули

```
vlm_ocr_doc_reader/
├── core/
│   ├── reader.py            DocumentReader — публичный API (scan/resolve/verify)
│   ├── processor.py         DocumentProcessor — рендер + VLM agent (используется при scan)
│   ├── vlm_agent.py         VLMAgent — conversation + tool-calling loop (OpenAI-style messages)
│   ├── vlm_client.py        BaseVLMClient — провайдер-нейтральный контракт
│   ├── qwen_vlm_client.py   QwenVLMClient (DashScope OpenAI-compatible endpoint)
│   ├── ocr_tool.py          OCRTool — tool для VLM agent (ask_ocr)
│   ├── ocr_client.py        QwenOCRClient
│   └── state.py             StateManager + WorkspaceStorage + OCRRegistryEntry
├── operations/
│   ├── base.py              BaseOperation
│   ├── full_description.py  FullDescriptionOperation — монолитный three-pass (legacy API)
│   └── scan.py              SCAN_PROMPT_TEXT + parser/нормализатор scan-ответа
├── preprocessing/
│   └── renderer.py          PDFRenderer (маркеры [G{N}] в левом верхнем углу)
├── schemas/
│   ├── config.py            ProcessorConfig, VLMConfig, OCRConfig
│   ├── document.py          DocumentData, HeaderInfo, TableInfo
│   └── common.py            PageInfo
├── utils/
│   └── normalization.py     нормализация цифр OCR (O→0 и т.п.)
└── cli.py                   subcommands: scan, resolve, verify, full-description
```

Внутренний формат сообщений в `VLMAgent` — OpenAI-style (`messages` с `role`/`content`, `tool_calls`, `tool_call_id`). Это продуктовый контракт, а не проекция конкретного провайдера; `QwenVLMClient` — тонкий pass-through, т.к. DashScope принимает этот формат натив. Новые провайдеры должны конвертировать свой формат в/из этого внутри своего клиента.

## Публичный API

Главный вход:

```python
from vlm_ocr_doc_reader import DocumentReader

reader = DocumentReader.open(pdf_path, workspace=None)  # workspace=None → memory mode
reader.scan(pages=None)                                  # None → все страницы
reader.resolve(pages=None, chunk_size=None)             # multi-question OCR; chunk_size override
reader.verify(pages=None)                                # stub
reader.page_status()                                     # {page_num: "scan"|"resolved"|"verified"}
reader.pending_entities(page=None)                       # список OCRRegistryEntry с resolution < 1
reader.get_document_data() -> DocumentData
```

Legacy-путь (монолитный VLM invoke с tool calling OCR):

```python
from vlm_ocr_doc_reader import DocumentProcessor, FullDescriptionOperation

processor = DocumentProcessor(source=Path("doc.pdf"))
data = FullDescriptionOperation(processor).execute()
```

## Контракт с agentic-doc-processing

`reader.get_document_data()` возвращает `DocumentData(text, structure, tables)` — стабильный контракт для соседнего подпроекта `01_projects/agentic-doc-processing`. Поле `tables` всегда пусто в текущей реализации.

## Известные ограничения

- VLM и OCR: только Qwen (`qwen3-vl-flash` и `qwen-vl-plus` соответственно), оба через DashScope и единый API-ключ. `BaseVLMClient`/`BaseOCRClient` оставляют место для других провайдеров, но реализаций нет.
- `verify()` не реализует стратегию — лишь нормализует диапазон страниц и логирует.
- DPI рендеринга жёстко 150 (`render_dpi` в `ProcessorConfig`, не используется как переменная через CLI).
- `DocumentData.tables` всегда пуст.
- `ClusterInfo` и `TriageResult` — зарезервированные типы, соответствующих операций нет.
