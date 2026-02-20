# Архитектура проекта vlm-ocr-doc-reader

**Версия:** 2.0
**Дата:** 2026-02-20
**Статус:** Фаза 1 реализована, Фаза 2 в проектировании

---

## 1. Концептуальная модель

### Разделение Agent vs Client

Модуль базируется на концептуальном разделении агентского и технического уровней:

- **VLM Agent** — агентская сущность (промпты, tool calling loop, conversation history, параллельное выполнение tools)
- **VLM Client** — техническая реализация (REST API Gemini, throttling, retry, conversation `contents`)
- **OCR Tool** — агентская сущность (получение image из StateManager, вызов OCR)
- **OCR Client** — техническая реализация OCR API (Qwen VL)

```mermaid
graph TB
    subgraph "CLI (cli.py)"
        CLI[CLI Entry Point]
    end

    subgraph "Operations"
        FD[FullDescriptionOperation]
    end

    subgraph "DocumentProcessor"
        DP[DocumentProcessor]
        SM[StateManager]

        subgraph "VLM Agent"
            Agent[VLM Agent]
            Messages["self.messages<br/>(conversation history)"]
            TPE["ThreadPoolExecutor<br/>max_workers=5"]
            Loop["Tool Calling Loop<br/>max 100 iterations"]
        end

        subgraph "VLM Client"
            VLMClient[GeminiVLMClient]
            VLM_API["REST API<br/>gemini-2.5-flash"]
            VLM_Throttle["Throttling 0.6s"]
            VLM_Retry["Retry 429/5xx"]
        end

        subgraph "OCR Tool"
            OCRTool["OCRTool<br/>(ask_ocr)"]
        end

        subgraph "OCR Client"
            OCRClient[QwenOCRClient]
            OCR_API["OpenAI-compatible API<br/>qwen-vl-plus"]
            OCR_Retry["Retry 429/5xx"]
        end
    end

    CLI --> FD
    FD --> DP
    DP --> SM
    DP --> Agent
    Agent --> Messages
    Agent --> TPE
    Agent --> Loop
    Agent -.uses.-> VLMClient
    VLMClient --> VLM_API
    VLMClient --> VLM_Throttle
    VLMClient --> VLM_Retry
    Agent -.contents=self.messages.-> VLMClient

    Loop -.calls.-> OCRTool
    TPE -.parallel.-> OCRTool
    OCRTool -.load_page.-> SM
    OCRTool -.uses.-> OCRClient
    OCRClient --> OCR_API
    OCRClient --> OCR_Retry
```

### Ключевые принципы

1. **Agent → Client relation**: VLM Agent использует VLM Client, OCR Tool использует OCR Client
2. **Conversation history**: VLM Agent хранит `self.messages`, передает `contents=self.messages` в VLM Client — полная история диалога
3. **Three-pass OCR strategy**: VLM читает текст → строит реестр OCR-сущностей → вызывает ask_ocr для каждой → подставляет результаты
4. **Параллельное выполнение tools**: ThreadPoolExecutor(max_workers=5) для одновременного выполнения нескольких ask_ocr вызовов
5. **OCR Tool самостоятелен**: получает image из StateManager по page_num, не зависит от VLM Agent для доступа к изображениям
6. **Uniform tool calling**: VLM Agent не знает про OCR — все tools вызываются одинаково через `handler(**func_args)`
7. **Все клиенты имеют retry-логику**: exponential backoff на 429/5xx
8. **Прямой вызов OCR не поддерживается**: только через VLM Agent via tool calling

---

## 2. Структура модулей (фактическая)

```
vlm_ocr_doc_reader/
├── __init__.py                    # Public API
├── cli.py                         # CLI entry point (argparse)
│
├── core/
│   ├── __init__.py
│   ├── processor.py               # DocumentProcessor
│   ├── vlm_agent.py               # VLMAgent (tool calling loop, ThreadPoolExecutor)
│   ├── vlm_client.py              # BaseVLMClient, GeminiVLMClient (contents support)
│   ├── ocr_tool.py                # OCRTool (state_manager, ask_ocr)
│   ├── ocr_client.py              # BaseOCRClient, QwenOCRClient
│   └── state.py                   # StateManager, MemoryStorage, DiskStorage
│
├── operations/
│   ├── __init__.py
│   ├── base.py                    # BaseOperation
│   └── full_description.py        # FullDescriptionOperation (three-pass prompts)
│
├── preprocessing/
│   ├── __init__.py
│   └── renderer.py                # PDFRenderer ([G{N}] page markers)
│
├── schemas/
│   ├── __init__.py
│   ├── document.py                # DocumentData, HeaderInfo, TableInfo
│   ├── common.py                  # PageInfo, ClusterInfo, TriageResult
│   └── config.py                  # ProcessorConfig, VLMConfig, OCRConfig
│
└── utils/
    ├── __init__.py
    └── normalization.py           # OCR normalization (raw values, no forced digits)
```

**Не реализовано в v0.1.0 (запланировано):**
- `operations/clustering.py` — ClusteringOperation (P1)
- `operations/triage.py` — TriageOperation (P2)
- `operations/extraction.py` — ExtractionOperation (P2)
- `preprocessing/page_numberer.py` — (не нужен, [G{N}] реализован в renderer.py)
- `utils/batching.py` — PageBatching (будет заменен page-based OCR batching)

---

## 3. Ключевые архитектурные решения

### 3.1. Operations Organization (без изменений)

Operations импортируются как самостоятельные классы:
```python
from vlm_ocr_doc_reader.operations import FullDescriptionOperation
op = FullDescriptionOperation(processor)
result = op.execute()
```

### 3.2. State Management (без изменений)

- **Memory** — если `state_dir` не указан
- **Disk** — если указан `state_dir`
- OCRTool обращается к StateManager.load_page(page_num) для получения изображений

### 3.3. Three-Pass OCR Strategy (НОВОЕ, реализовано 2026-02-09)

**Промпт PROMPT_TEXT в full_description.py содержит инструкцию для трёх проходов:**

1. **Проход 1 — Извлечение текста**: VLM читает все страницы по маркерам [G{N}], извлекает полный текст
2. **Проход 2 — Реестр OCR-сущностей**: VLM определяет precision-critical данные (URLs, IDs, имена, телефоны, адреса) и формирует реестр с указанием страницы и контекста
3. **Проход 3 — OCR верификация**: VLM вызывает ask_ocr для каждой сущности, получает точные значения, подставляет в текст (OCR имеет приоритет)

### 3.4. Parallel Tool Execution (НОВОЕ, реализовано 2026-02-09)

```python
# VLMAgent._execute_tool_calls()
if self.max_tool_workers <= 1:
    return [run_one(fc) for fc in function_calls]  # Sequential
with ThreadPoolExecutor(max_workers=self.max_tool_workers) as pool:
    return list(pool.map(run_one, function_calls))  # Parallel, order preserved
```

Gemini может вернуть 1-30 function calls за итерацию (недетерминированно). Все выполняются параллельно через ThreadPoolExecutor.

### 3.5. Conversation History (НОВОЕ, реализовано 2026-02-09)

VLM Client принимает `contents` — полная история сообщений Gemini. VLM Agent передает `contents=self.messages`. Это позволяет:
- Multi-turn dialogue (модель помнит предыдущие ходы)
- Three-pass strategy (промпт инструктирует делать несколько проходов в рамках одного invoke)
- OCR результаты видны модели при следующей итерации

### 3.6. Page Markers [G{N}] (НОВОЕ, реализовано 2026-02-09)

PDFRenderer штампует `[G1]`, `[G2]` и т.д. в верхнем левом углу каждой страницы. Это позволяет VLM точно идентифицировать страницы и указывать правильный `page_num` при вызове ask_ocr.

### 3.7. Init Order in Processor (уточнение)

```python
# Критический порядок инициализации:
1. StateManager (нужен OCRTool)
2. VLMClient (нужен VLMAgent)
3. OCRClient + OCRTool(ocr_client, state_manager)  # если QWEN_API_KEY задан
4. VLMAgent(vlm_client) + register_tool(ask_ocr, ocr_tool.execute)
5. Pages (render PDF + save to StateManager)
```

---

## 4. Интеграционные точки (без изменений)

### 4.1. Контракт с 07_agentic-doc-processing

```python
@dataclass
class DocumentData:
    text: str                          # Полный текст (с OCR-верифицированными данными)
    structure: Dict[str, Any]          # {"headers": [{"level": N, "title": "...", "page": N}]}
    tables: List[Dict[str, Any]]       # Пустой в v0.1.0
```

### 4.2. CLI

```bash
vlm-ocr-reader <pdf_path> [--output-dir DIR] [--dpi DPI] [--log-level LEVEL] \
    [--max-tool-workers N] [--max-iterations N]
```

---

## 5. Ограничения v0.1.0

### Технологические
- Только Gemini VLM (`gemini-2.5-flash`)
- Только Qwen OCR (`qwen-vl-plus`)
- API ключи через переменные окружения

### Функциональные
- Только FullDescriptionOperation (P0)
- Без классификации таблиц (NUMERIC/TEXT_MATRIX)
- Без расширения клиентов (нельзя добавить Claude VLM или Tesseract OCR)

### Производительность
- OCR вызывается по одной сущности (66 отдельных запросов)
- Gemini batching недетерминированен
- Общее время обработки 8-страничного документа: ~6 мин

**Планируемая оптимизация:** page-based OCR batching (задача 009, эскалация к Architect).

---

## История изменений

| Дата | Версия | Изменения | Автор |
|------|--------|-----------|-------|
| 2026-02-20 | 2.0 | Актуализация: фактическая архитектура (conversation history, parallel OCR, three-pass, [G{N}], init order), ограничения, Фаза 2 | Tech Lead |
| 2026-01-27 | 1.1 | Добавлены входные данные, auto-save, DPI иерархия, OCR формат, конфигурация | Architect |
| 2026-01-27 | 1.0 | Черновик архитектуры | Architect |
