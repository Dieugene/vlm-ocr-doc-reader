# Эскалация к Architect: Оптимизация OCR — page-based batching

**Дата:** 2026-02-20
**От:** Tech Lead
**Задача:** 009 (backlog.md)
**Приоритет:** High

---

## 1. Контекст проблемы

### Текущая архитектура OCR (Variant 1 — действующая)

VLM Agent использует three-pass стратегию:
1. VLM читает текст со страниц самостоятельно
2. VLM строит реестр OCR-сущностей (precision-critical данные)
3. VLM вызывает `ask_ocr(page_num, prompt)` для каждой сущности **по одной**

Gemini возвращает function calls батчами (недетерминированно: 1/16/29/30 за итерацию).
VLM Agent выполняет их параллельно через ThreadPoolExecutor (5 workers).

### Наблюдаемые данные (test_document.pdf, 8 страниц)

**Распределение OCR-вызовов по страницам (run_193215, 65 calls):**
- Страницы 1-5: единичные вызовы (IDs, названия)
- Страница 6: ~15 вызовов (URLs-источники)
- Страница 7: ~25 вызовов (URLs-источники)
- Страница 8: ~25 вызовов (URLs-источники)

**Latency одного OCR-вызова (Qwen):** 5-35 сек, медиана ~7 сек.

**Производительность по запускам:**

| Запуск | OCR calls | Workers | Время OCR | Общее время |
|--------|-----------|---------|-----------|-------------|
| run_174559 | 66 | 1 (sequential) | ~8 мин | 12 мин |
| run_193215 | 65 | 5 (parallel) | ~3 мин | 6 мин |

### Узкое место

Даже с 5 параллельными воркерами, 65 OCR-вызовов = ~13 "волн" по 5, каждая ~7 сек = ~90 сек.
Но Gemini batching недетерминированен: если в одной итерации придет 29 вызовов, а в другой 1, то "хвост" из одиночных вызовов сводит параллелизацию на нет.

---

## 2. Предлагаемое решение: Variant 2 — Page-based OCR Batching

### Идея

Когда от Gemini приходит батч function calls (например, 29 ask_ocr вызовов), **перед выполнением**:

1. Сгруппировать вызовы по `page_num`
2. Для каждой страницы составить ОДИН объединённый OCR-запрос
3. Отправить один Qwen-запрос на страницу
4. Распарсить ответ обратно на индивидуальные результаты
5. Вернуть каждому оригинальному function call его индивидуальный результат

### Ожидаемый эффект

```
Variant 1: 65 calls → 65 Qwen requests → ~3 мин (5 workers)
Variant 2: 65 calls → ~8 Qwen requests → ~30-40 сек (один на страницу)
```

### Требования от пользователя

1. **Переключаемость:** Variant 1 (по одному), Variant 2 (page-batched), или ОБА параллельно для сравнения
2. **Прозрачность для VLM:** tool definition ask_ocr не меняется, VLM по-прежнему запрашивает по одному
3. **Точность:** каждый оригинальный function call получает свой индивидуальный результат

---

## 3. Архитектурные вопросы

### Вопрос 1: Где разместить логику батчинга?

**Вариант A: В VLMAgent._execute_tool_calls()**

```python
def _execute_tool_calls(self, function_calls):
    if self.batching_mode == "page":
        return self._execute_batched(function_calls)
    else:
        return self._execute_individual(function_calls)
```

- Плюс: VLM Agent уже оркестрирует tool calls
- Минус: VLM Agent знает про семантику page_num (нарушает uniform tool calling)

**Вариант B: В OCRTool (новый BatchingOCRTool или режим)**

```python
class OCRTool:
    def __init__(self, ocr_client, state_manager, batching=False):
        self.batching = batching
        self._pending_batch = []

    def execute(self, page_num, prompt):
        if self.batching:
            return self._execute_batched(page_num, prompt)
        return self._execute_individual(page_num, prompt)
```

- Плюс: батчинг инкапсулирован в OCR-слое
- Минус: OCRTool вызывается по одному из ThreadPoolExecutor — нет "момента батча"

**Вариант C: Новый middleware-слой между VLMAgent и OCRTool**

```python
class OCRBatchProxy:
    """Прозрачная прокси, накапливает вызовы и отправляет батчем."""
    def __init__(self, ocr_tool):
        self.ocr_tool = ocr_tool

    def execute(self, page_num, prompt):
        # Вызывается из ThreadPoolExecutor
        # Нужен механизм "подождать остальных из батча"
```

- Плюс: не трогает ни VLMAgent, ни OCRTool
- Минус: сложная синхронизация (barrier pattern)

### Вопрос 2: Формат объединённого промпта для Qwen

Один Qwen-запрос должен извлечь N значений с одной страницы. Как структурировать?

**Вариант A: Нумерованный список**

```
Найди на изображении следующие значения:

1. URL источника, ориентир: "Bank of England, 2018"
2. URL источника, ориентир: "OECD Capital Market Review"
3. URL источника, ориентир: "ASX Listing Rules"

Для каждого верни:
N. ЗНАЧЕНИЕ: <...> | КОНТЕКСТ: <...>
```

**Вариант B: JSON-запрос → JSON-ответ**

```json
{"items": [
  {"id": 1, "prompt": "URL источника, ориентир: 'Bank of England'"},
  {"id": 2, "prompt": "URL источника, ориентир: 'OECD Capital Market Review'"}
]}
```

Ответ:
```json
{"results": [
  {"id": 1, "status": "ok", "value": "https://...", "context": "..."},
  {"id": 2, "status": "ok", "value": "https://...", "context": "..."}
]}
```

**Вариант C: Markdown-таблица**

```
| # | Что найти | Ориентир |
|---|-----------|----------|
| 1 | URL       | Bank of England, 2018 |
| 2 | URL       | OECD Capital Market Review |
```

### Вопрос 3: Как парсить ответ Qwen при partial failure?

Qwen может не найти часть значений. Как обрабатывать:

- Если 1 из 20 не найден → вернуть `{"status": "no_data"}` для этого элемента?
- Если Qwen вернул ответ в неожиданном формате (не все элементы) → fallback на Variant 1 для missing?
- Нужен ли retry для отдельных элементов?

### Вопрос 4: Максимальный размер батча

Qwen имеет ограничения на длину промпта/ответа. Если на одной странице 25 OCR-сущностей:

- Все 25 в один запрос? Или разбить на суб-батчи (например, по 10)?
- Как определить оптимальный размер? Эмпирически?

### Вопрос 5: Режим сравнения V1 vs V2

Пользователь хочет запускать оба варианта параллельно и сравнивать результаты. Как реализовать:

- Отдельный ComparisonMode, который запускает оба и diff'ит?
- Или просто два запуска с разными конфигурациями?
- Формат отчёта сравнения?

---

## 4. Влияние на архитектуру

### Что точно меняется

- **OCRTool или новый компонент** — логика объединения/разделения запросов
- **ProcessorConfig** — новый параметр `ocr_batching_mode: "individual" | "page" | "both"`
- **CLI** — новый аргумент `--ocr-batching`

### Что НЕ должно меняться

- **VLM Agent** — uniform tool calling (в идеале)
- **VLM Client** — не затрагивается
- **ask_ocr tool definition** — VLM видит тот же интерфейс
- **QwenOCRClient.extract()** — базовый метод одного вызова сохраняется

### Новые компоненты (предварительно)

- `QwenOCRClient.extract_batch()` — новый метод для batch-запросов
- Или `OCRBatchProxy` / `BatchingOCRTool` — middleware

---

## 5. Предложение Tech Lead

Исходя из анализа, мне кажется наиболее чистым **Вариант A (в VLMAgent)** для размещения и **Вариант B (JSON)** для формата, но это требует архитектурного решения, потому что:

1. Variant A нарушает принцип uniform tool calling — Agent начинает знать семантику конкретного tool
2. JSON-формат ответа от Qwen менее надёжен чем структурированный текст (текущий ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ)

Прошу Architect принять решение по вопросам 1-5 и при необходимости создать ADR.

