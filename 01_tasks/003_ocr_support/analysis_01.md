# Технический план: OCR Support (Задача 003)

## 1. Анализ задачи

Реализовать поддержку OCR для точного извлечения числовых данных и идентификаторов из документов. Задача включает:
1. **OCR Client** - техническая реализация Qwen VL API клиента с retry logic
2. **OCR Tool** - агентская обертка для интеграции с VLM Agent через function calling

OCR используется VLM Agent через tools для точного извлечения данных, когда VLM вызывает tool `ask_ocr`.

## 2. Текущее состояние

### Reference код (доступен в 02_src/_reference/)
- **qwen_client.py** - рабочая реализация QwenClient из проекта 05_a_reports_ETL_02
- **tools.py** - реализация normalize_ocr_digits() и ask_qwen()

### Контракты из implementation_plan.md
- **OCRConfig** - конфигурация OCR клиента (api_key, model, timeout_sec, max_retries, backoff_base)
- **BaseOCRClient** - базовый интерфейс с методом extract()
- **QwenOCRClient** - конкретная реализация для Qwen VL API
- **OCRTool** - агентская обертка с методами to_tool_definition() и execute()

### Зависимости от параллельных задач
- **Задача 001** - normalize_ocr_digits() будет доступна в vlm_ocr_doc_reader/utils/normalization.py
- **Задача 002** - VLM Agent использует OCRTool через register_tool()

## 3. Предлагаемое решение

### 3.1. Общий подход

1. **Адаптировать qwen_client.py** из reference в архитектуру проекта (BaseOCRClient + QwenOCRClient)
2. **Сохранить retry logic** из reference (exponential backoff, retry на 429/500-599)
3. **Реализовать OCRTool** как агентскую обертку для function calling
4. **Интегрировать с VLM Agent** через to_tool_definition()

### 3.2. Компоненты

#### Модуль: 02_src/vlm_ocr_doc_reader/core/ocr_client.py

**Компонент: OCRConfig**
- **Назначение:** Конфигурация OCR клиента
- **Интерфейс:** dataclass с полями api_key, model, timeout_sec, max_retries, backoff_base
- **Зависимости:** os.getenv("QWEN_API_KEY") для дефолтного api_key

**Компонент: BaseOCRClient**
- **Назначение:** Базовый интерфейс для OCR клиентов
- **Интерфейс:**
  - extract(image: bytes, prompt: str, page_num: int) -> Dict[str, Any]
- **Возвращает:** {"status": "ok|no_data|error", "value": str, "context": str, "explanation": str}
- **Зависимости:** abc.ABC

**Компонент: QwenOCRClient**
- **Назначение:** Qwen VL API клиент с retry logic
- **Интерфейс:** Наследует BaseOCRClient
- **Логика:**
  1. Конвертировать image в base64 PNG
  2. Построить request для OpenAI-compatible endpoint (https://dashscope-intl.aliyuncs.com/compatible-mode/v1)
  3. Retry с exponential backoff на 429 (rate limit) и 500-599 (server errors)
  4. Парсить ответ в формате ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ
- **Зависимости:** requests, PIL (Image), base64, json, re
- **Retry параметры:** max_retries=3, backoff_base=1.5

#### Модуль: 02_src/vlm_ocr_doc_reader/core/ocr_tool.py

**Компонент: OCRTool**
- **Назначение:** Агентская обертка для вызова OCR через VLM Agent
- **Интерфейс:**
  - __init__(ocr_client: BaseOCRClient)
  - to_tool_definition() -> Dict (tool definition для Gemini function calling)
  - execute(page_num: int, prompt: str, image: bytes) -> Dict
- **Логика execute():**
  1. Вызвать ocr_client.extract(image, prompt, page_num)
  2. Если status=="ok", применить normalize_ocr_digits() к value
  3. Добавить value_normalized в результат
- **Зависимости:** vlm_ocr_doc_reader.utils.normalization.normalize_ocr_digits (из Задачи 001)

### 3.3. Структуры данных

**Результат OCR extraction:**
```python
{
    "status": "ok" | "no_data" | "error",
    "value": str,              # Сырое значение из Qwen (цифры)
    "context": str,            # Фрагмент текста где найдено
    "explanation": str,        # Объяснение от Qwen
    "value_normalized": str    # Пост-обработка через normalize_ocr_digits (если status=="ok")
}
```

**Tool definition format (для Gemini function calling):**
```python
{
    "function_declarations": [
        {
            "name": "ask_ocr",
            "description": "Извлечь данные с изображения",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_num": {"type": "integer"},
                    "prompt": {"type": "string"}
                },
                "required": ["page_num", "prompt"]
            }
        }
    ]
}
```

### 3.4. Ключевые алгоритмы

**Retry logic (из reference qwen_client.py):**
- Retry на HTTP статусах: 429 (rate limit), 500-599 (server errors)
- Exponential backoff: sleep_s = backoff_base ** (attempt - 1)
- Максимум попыток: max_retries (обычно 3)
- Логирование каждой попытки

**Парсинг ответа Qwen (формат ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ):**
- Извлечь VALUE через regex `r"ЗНАЧЕНИЕ:\s*(\S+)"`
- Извлечь CONTEXT через regex `r"КОНТЕКСТ:\s+(.+?)(?=\nПОЯСНЕНИЕ:|$)"`
- Извлечь EXPLANATION через regex `r"ПОЯСНЕНИЕ:\s+(.+)"`
- Если VALUE == "НЕТ" или "-", то status = "no_data"
- Иначе извлечь цифры из VALUE через `re.sub(r"[^\d]", "", value_raw)`
- Fallback: если ничего не распарсилось, найти любые цифры в ответе (минимум 10 для ОГРН/ОРНЗ)

**Пост-обработка через normalize_ocr_digits():**
- Замены: O→0, o→0, l→1, I→1, S→5, B→8
- Удалить пробелы, \xa0, дефисы
- Оставить только цифры
- Если expected_length указан, проверить длину

### 3.5. Изменения в существующем коде

Новые модули (изменения существующего кода не требуются):
- `02_src/vlm_ocr_doc_reader/core/ocr_client.py` - новый файл
- `02_src/vlm_ocr_doc_reader/core/ocr_tool.py` - новый файл

Интеграция с VLM Agent (будет в Задаче 002):
```python
# В VLM Agent.register_tool():
ocr_tool = OCRTool(qwen_client)
agent.register_tool(ocr_tool.to_tool_definition(), ocr_tool.execute)
```

## 4. План реализации

### Шаг 1: Создать структуру модулей
- Создать `02_src/vlm_ocr_doc_reader/core/__init__.py`
- Создать `02_src/vlm_ocr_doc_reader/core/ocr_client.py`
- Создать `02_src/vlm_ocr_doc_reader/core/ocr_tool.py`

### Шаг 2: Реализовать OCR Client
- Реализовать OCRConfig dataclass
- Реализовать BaseOCRClient (abc)
- Адаптировать QwenClient из reference в QwenOCRClient
  - __init__ с OCRConfig
  - extract() с retry logic
  - _image_to_base64() helper
  - _build_url() helper

### Шаг 3: Реализовать парсинг ответа Qwen
- Адаптировать parse_qwen_text_response() из reference
- Поддержать формат ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ
- Реализовать fallback для extraction цифр

### Шаг 4: Реализовать OCR Tool
- Реализовать OCRTool.__init__()
- Реализовать to_tool_definition() (Gemini format)
- Реализовать execute() с вызовом ocr_client.extract()
- Интегрировать normalize_ocr_digits() (импортировать из vlm_ocr_doc_reader.utils.normalization)

### Шаг 5: Настроить логирование
- Логировать попытки retry
- Логировать статусы ответов (ok/no_data/error)
- Логировать время выполнения запросов

### Шаг 6: Unit тесты
- Тесты для QwenOCRClient.extract() с mock responses
- Тесты для retry logic (429, 500)
- Тесты для парсинга ответа (формат ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ)
- Тесты для OCRTool.execute() с нормализацией
- Тесты для to_tool_definition() (проверка структуры)

### Шаг 7: Интеграционные тесты (с реальным API)
- Тест с реальным Qwen API (требуется QWEN_API_KEY)
- Проверка извлечения числовых данных с тестового изображения
- Проверка normalize_ocr_digits() на реальных данных

## 5. Технические критерии приемки

- [ ] TC-1: QwenOCRClient.extract() выполняет запрос к Qwen API с retry logic (max_retries=3, backoff_base=1.5)
- [ ] TC-2: Retry срабатывает на HTTP 429 и 500-599 с exponential backoff
- [ ] TC-3: QwenOCRClient.extract() парсит ответ в формате ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ
- [ ] TC-4: OCRTool.to_tool_definition() возвращает валидную tool definition для Gemini function calling
- [ ] TC-5: OCRTool.execute() применяет normalize_ocr_digits() к value при status=="ok"
- [ ] TC-6: Unit тесты покрывают retry logic (mock responses для 429, 500)
- [ ] TC-7: Unit тесты покрывают парсинг ответа (валидный формат, fallback)
- [ ] TC-8: Интеграционный тест с реальным Qwen API проходит (требует QWEN_API_KEY)
- [ ] TC-9: Логирование запросов включает attempt, status, latency
- [ ] TC-10: QwenOCRClient использует QWEN_API_KEY из переменной окружения

## 6. Важные детали для Developer

### API Endpoint и аутентификация
- **Endpoint:** https://dashscope-intl.aliyuncs.com/compatible-mode/v1 (OpenAI-compatible)
- **API Key:** передается через header `Authorization: Bearer {api_key}`
- **Переменная окружения:** QWEN_API_KEY (обязательно для тестов с реальным API)
- **Timeout:** 60 секунд по умолчанию

### Retry logic детали
- **Retry на:** HTTP статус 429 (rate limit), 500-599 (server errors)
- **Не retry на:** 4xx (кроме 429), 200-299
- **Backoff формула:** sleep_s = backoff_base ** (attempt - 1)
  - attempt 1: sleep 0s (первая попытка сразу)
  - attempt 2: sleep 1s (backoff_base=1.5)
  - attempt 3: sleep 1.5s
- **Максимум попыток:** max_retries (по умолчанию 3)

### Формат ответа Qwen (ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ)
- **ЗНАЧЕНИЕ:** сырое значение (может содержать буквы O, l, I, S, B)
- **КОНТЕКСТ:** фрагмент текста где найдено значение
- **ПОЯСНЕНИЕ:** объяснение от Qwen (где искал, что нашел/не нашел)
- **Спец-значения:** "НЕТ", "-" означают отсутствие данных (status="no_data")

### Пост-обработка normalize_ocr_digits()
- **Вызывается только при** status=="ok"
- **Замены:** O→0, o→0, l→1, I→1, S→5, B→8
- **Удаление:** пробелы, \xa0 (non-breaking space), дефисы
- **Результат:** только цифры или None
- **Сохранение:** добавляется в result["value_normalized"]

### Работа с изображениями
- **Input:** bytes (PNG/JPEG)
- **Конвертация:** в base64 PNG перед отправкой (через PIL для избежания JPEG артефактов)
- **Format:** data:image/png;base64,{b64_string}

### Тестирование с реальным API
- **Переменная окружения:** QWEN_API_KEY должна быть установлена
- **Проверка:** если QWEN_API_KEY не задан, интеграционные тесты пропускаются (pytest.mark.skipif)
- **WARNING:** не коммитить API ключи в код

### Интеграция с VLM Agent (будет в Задаче 002)
OCRTool регистрируется как tool:
```python
ocr_tool = OCRTool(qwen_client)
agent.register_tool(ocr_tool.to_tool_definition(), ocr_tool.execute)
```

Когда VLM вызывает `ask_ocr(page_num=5, prompt="найди ОГРН")`:
1. VLM Agent передает вызов в OCRTool.execute()
2. OCRTool получает image из DocumentProcessor.pages[5]
3. Вызывает qwen_client.extract(image, prompt, 5)
4. Нормализует значение через normalize_ocr_digits()
5. Возвращает результат в VLM Agent

### Логирование
- **Структурированные логи:** JSON format
- **Поля:** timestamp, attempt, status, latency_ms, page_num, value_length
- **Уровни:** INFO для успешных запросов, WARN для retry, ERROR для неудач
- **Вывод:** stdout по умолчанию, дополнительно в state_dir/logs/vlm_ocr.log если задан state_dir

### Конфигурация через OCRConfig
```python
config = OCRConfig(
    api_key=os.getenv("QWEN_API_KEY"),  # обязательно
    model="qwen-vl-plus",
    timeout_sec=60,
    max_retries=3,
    backoff_base=1.5
)
client = QwenOCRClient(config)
```

### Зависимость от Задачи 001
- **Модуль:** vlm_ocr_doc_reader/utils/normalization.py
- **Функция:** normalize_ocr_digits(raw: str, expected_length: Optional[int] = None) -> Optional[str]
- **Импорт:** from vlm_ocr_doc_reader.utils.normalization import normalize_ocr_digits
- **Примечание:** если Задача 001 еще не завершена, временно скопировать функцию в ocr_tool.py с комментарием "TODO: move to utils/normalization.py (Задача 001)"

### Обработка ошибок
- **QwenClientError:** поднимается при неуспешных всех попыток retry
- **TimeoutError:** от requests если timeout_sec превышен
- **ValueError:** если api_key не задан (ни в параметрах, ни в переменной окружения)
- **Все ошибки** логируются перед поднятием exception

### Reference код注意事项 (внимание)
- **qwen_client.py** использует `ask_number()` - переименовать в `extract()` для соответствия интерфейсу
- **parse_qwen_text_response()** - перенести как helper метод или функцию
- **System prompt** из reference (lines 119-133) - использовать для построения messages
- **Старый JSON формат** (закомментирован) - не использовать, только текстовый формат ЗНАЧЕНИЕ/КОНТЕКСТ/ПОЯСНЕНИЕ
