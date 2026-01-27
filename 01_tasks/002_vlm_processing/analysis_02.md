# Технический план: VLM Processing (критический путь)

**Версия:** 2.0
**Дата:** 2025-01-27
**Задача:** 002_vlm_processing

---

## 1. Анализ задачи

Необходимо исправить критические проблемы в реализации задачи 002 и добавить недостающие компоненты согласно отзыву Reviewer.

**Выявленные проблемы:**
1. **Retry логика** - выполняется retry на 400 статусе, хотя должна только на 429 и 500-599
2. **PageInfo несоответствие** - используется `page_num`, но схема определена с `index`
3. **Тесты DocumentProcessor** - некорректное мокание импортов
4. **Throttling тест** - не проверяется на стандартном значении 0.6s
5. **Интеграционные тесты** - отсутствуют, хотя требуются по ТЗ

---

## 2. Текущее состояние

### Существующая реализация

**Выполнено корректно:**
- VLM Agent - все 9 тестов проходят, tool calling loop работает для 1/2/10/max_iterations
- VLM Client базовая функциональность - запросы к Gemini API работают
- Retry на 429 и 503 - тесты проходят
- Throttling с `time.monotonic()` - реализовано правильно
- PDFRenderer - существует из задачи 001, работает корректно

**Критические проблемы:**
- `vlm_client.py:126` - неверная логика retry (повторяет на 400)
- `processor.py:121, 138` - создается PageInfo с `page_num` вместо `index`
- `test_processor.py` - неправильные patch пути для моков

### PageInfo из задачи 001

**Существующая схема в `schemas/common.py`:**
```python
@dataclass
class PageInfo:
    index: int  # 1-based
    image: bytes
```

**PDFRenderer возвращает:**
```python
List[Tuple[int, bytes]]  # (page_num, image_bytes) где page_num 1-based
```

**Вывод:** Использовать `PageInfo(index=page_num, image=img_bytes)` для согласованности.

---

## 3. Предлагаемое решение

### 3.1. Общий подход

**Исправления:**
1. Исправить логику retry в VLM Client - НЕ retry на 4xx (кроме 429)
2. Исправить DocumentProcessor - использовать `PageInfo(index=..., image=...)`
3. Исправить тесты DocumentProcessor - корректное мокание
4. Добавить тест throttling на стандартном значении 0.6s
5. Добавить интеграционные тесты (с пропуском если нет API ключа)

**Интеграционные тесты - решение:**
Создать базовые интеграционные тесты с реальным API, но с пропуском если GEMINI_API_KEY не задан. Это позволит:
- Проверить работу с реальным API
- Не блокировать CI/CD (тесты пропускаются если нет ключа)
- Дать разработчикам способ проверки локально

### 3.2. Компоненты

#### Компонент 1: Исправление VLM Client retry логики

**Файл:** `vlm_client.py:87-162`

**Проблема:** Текущая логика retry на строке 126:
```python
should_retry = status == 429 or (500 <= status < 600)
```

Это означает что при status=400 проверка `500 <= 400 < 600` = False, НО код продолжает выполняться и вызывает `response.raise_for_status()` только после проверки условия. Проблема в том, что при статусе 400-499 (кроме 429) код НЕ должен попадать в retry loop.

**Исправление:**
```python
# На строке 126
should_retry = status == 429 or (500 <= status < 600)

if should_retry and attempt < self.config.max_retries:
    # retry logic

# Для всех остальных статусов (включая 400-499 кроме 429)
response.raise_for_status()  # Это выбросит exception для 4xx
return response.json()
```

**Ключевое изменение:** Убедиться что при 4xx (кроме 429) код НЕ выполняет retry, а сразу вызывает `raise_for_status()`.

**Что проверить:**
- При status=400: НЕ должно быть retry, сразу exception
- При status=401: НЕ должно быть retry, сразу exception
- При status=429: ДОЛЖЕН быть retry (до 3 попыток)
- При status=503: ДОЛЖЕН быть retry (до 3 попыток)

#### Компонент 2: Исправление DocumentProcessor PageInfo

**Файл:** `processor.py:106-145`

**Проблема:** Создание PageInfo с несуществующим полем `page_num`:
```python
# Строка 121
PageInfo(page_num=page_num, image=img_bytes)  # WRONG - нет такого поля

# Строка 138
PageInfo(page_num=i + 1, image=img_bytes)  # WRONG - нет такого поля
```

**Исправление:**
```python
# В _init_from_pdf (строка 121)
self._pages = [
    PageInfo(index=page_num, image=img_bytes)
    for page_num, img_bytes in rendered
]

# В _init_from_png_array (строка 138)
self._pages = [
    PageInfo(index=i + 1, image=img_bytes)
    for i, img_bytes in enumerate(png_array)
]
```

**Зависимость:** `PageInfo` из `schemas/common.py` с полем `index` (задача 001).

#### Компонент 3: Исправление тестов DocumentProcessor

**Файл:** `tests/test_core/test_processor.py`

**Проблема:** Неправильный patch путь для моков:
```python
@patch('vlm_ocr_doc_reader.core.processor.os.getenv')
@patch('vlm_ocr_doc_reader.core.processor.load_dotenv')
```

**Почему это не работает:** В `processor.py` импорты `os` и `load_dotenv` находятся внутри функции `__init__` (строки 53-54), а не в начале файла.

**Решение 1 (предпочтительное):** Вынести импорты в начало файла
```python
# В начале processor.py
import os
from dotenv import load_dotenv

# В __init__ убрать локальные импорты
```

**Решение 2 (альтернативное):** Исправить patch путь
```python
# Патчить builtin модуль os
@patch('os.getenv')
@patch('vlm_ocr_doc_reader.core.processor.load_dotenv')
```

**Рекомендация:** Решение 1 - вынести импорты в начало файла для consistency с остальным кодом.

**Что нужно замокать в тестах:**
1. `os.getenv("GEMINI_API_KEY")` → вернуть тестовый API ключ
2. `load_dotenv()` → mock (нельзя вызывать в тестах)
3. `PDFRenderer.render_pdf()` → вернуть тестовые данные
4. `GeminiVLMClient.__init__` → mock (не создавать реальный клиент)

#### Компонент 4: Добавление теста throttling на стандартном значении

**Файл:** `tests/test_core/test_vlm_client.py`

**Текущий тест (строка ~152):** Использует `min_interval_s=0.2`

**Добавить тест:**
```python
def test_throttling_standard_interval(self):
    """Test throttling with standard min_interval_s=0.6."""
    config = VLMConfig(
        api_key="test_key",
        min_interval_s=0.6  # Standard value from task_brief
    )
    client = GeminiVLMClient(config)

    # Mock successful response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"text": "response"}

    with patch('requests.post', return_value=mock_response):
        start = time.monotonic()
        client.invoke("test", [])
        client.invoke("test", [])
        elapsed = time.monotonic() - start

        # Should be at least 0.6s between calls
        assert elapsed >= 0.6
```

#### Компонент 5: Интеграционные тесты

**Файл:** `tests/integration/test_vlm_client_real_api.py`

**Подход:** Тесты с реальным API, но с пропуском если нет ключа.

**Структура:**
```python
import os
import pytest

# Skip all tests if GEMINI_API_KEY not set
pytestmark = pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set"
)

class TestGeminiVLMClientRealAPI:
    """Integration tests with real Gemini API."""

    def test_simple_invoke(self):
        """Test simple text+image request."""
        api_key = os.getenv("GEMINI_API_KEY")
        config = VLMConfig(api_key=api_key)
        client = GeminiVLMClient(config)

        # Use small test image
        prompt = "What is in this image?"
        result = client.invoke(prompt, [])

        assert "text" in result
        assert isinstance(result["text"], str)

    def test_invoke_with_tools(self):
        """Test function calling with real API."""
        # Similar but with tools
```

**Важно:** Минимизировать количество запросов для экономии квоты.

### 3.3. Структуры данных

**Без изменений** - используются существующие схемы:
- `PageInfo(index: int, image: bytes)` из задачи 001
- `VLMConfig` с `min_interval_s=0.6`
- `ProcessorConfig` с `render_dpi=150`

### 3.4. Ключевые алгоритмы

**Retry логика - исправленная:**
```python
status = response.status_code

# Retry ТОЛЬКО на 429 и 500-599
should_retry = status == 429 or (500 <= status < 600)

if should_retry and attempt < max_retries:
    # Выполнить retry с exponential backoff
    # Не вызывать raise_for_status()

# Для всех остальных случаев (включая 400-499 кроме 429)
response.raise_for_status()  # Exception для 4xx
return response.json()       # Success для 2xx
```

**Критично:**
- 400 Bad Request → НЕ retry, сразу exception
- 401 Unauthorized → НЕ retry, сразу exception
- 429 Too Many Requests → retry (до 3 попыток)
- 503 Service Unavailable → retry (до 3 попыток)

**PageInfo создание:**
```python
# PDF рендеринг возвращает (page_num, image_bytes)
# Используем page_num как index
PageInfo(index=page_num, image=image_bytes)

# PNG массив - enumerate с 1-based
PageInfo(index=i + 1, image=img_bytes)
```

### 3.5. Изменения в существующем коде

**Изменения:**
1. `vlm_client.py:126-136` - исправить логику retry (НЕ retry на 400-499 кроме 429)
2. `processor.py:53-54` - вынести импорты os, load_dotenv в начало файла
3. `processor.py:121, 138` - исправить PageInfo(page_num=...) на PageInfo(index=...)
4. `tests/test_core/test_vlm_client.py` - добавить тест throttling на 0.6s
5. `tests/test_core/test_processor.py` - исправить patch пути для моков
6. `tests/integration/test_vlm_client_real_api.py` - создать новый файл

---

## 4. План реализации

### Шаг 1: Исправить VLM Client retry логику
1. Изучить текущую логику в `vlm_client.py:126-136`
2. Убедиться что при 4xx (кроме 429) код НЕ выполняет retry
3. Добавить явную проверку: если status в 400-499 и не 429 → сразу raise_for_status()
4. Добавить тест `test_no_retry_on_400_status` (уже существует, должен проходить)

### Шаг 2: Исправить DocumentProcessor PageInfo
1. Вынести импорты `os` и `load_dotenv` в начало `processor.py`
2. Исправить `_init_from_pdf`: PageInfo(page_num=...) → PageInfo(index=...)
3. Исправить `_init_from_png_array`: PageInfo(page_num=...) → PageInfo(index=...)
4. Убедиться что field name согласуется с `schemas/common.py`

### Шаг 3: Исправить тесты DocumentProcessor
1. Обновить patch пути в `test_processor.py`
2. Убедиться что mock правильно перехватывает os.getenv и load_dotenv
3. Проверить что mock PDFRenderer возвращает корректные данные
4. Запустить все тесты DocumentProcessor - должны проходить

### Шаг 4: Добавить тест throttling на стандартном значении
1. Создать тест `test_throttling_standard_interval` в `test_vlm_client.py`
2. Использовать `min_interval_s=0.6` (из task_brief)
3. Проверить что между двумя вызовами проходит ≥ 0.6s
4. Убедиться что тест проходит

### Шаг 5: Создать интеграционные тесты
1. Создать `tests/integration/test_vlm_client_real_api.py`
2. Добавить pytest mark для skip если GEMINI_API_KEY не задан
3. Создать тест `test_simple_invoke` - простой запрос без tools
4. Создать тест `test_invoke_with_tools` - запрос с function calling
5. Документировать запуск в README (экспорт GEMINI_API_KEY)

### Шаг 6: Обновить документацию
1. Обновить `README.md` или создать `docs/testing.md` с инструкциями по интеграционным тестам
2. Добавить пример .env файла (в .gitignore)

---

## 5. Технические критерии приемки

### VLM Client - исправления
- [TC-1.1] `test_no_retry_on_400_status` проходит - НЕ выполняется retry на 400
- [TC-1.2] Retry работает на 429 (существующий тест проходит)
- [TC-1.3] Retry работает на 503 (существующий тест проходит)
- [TC-1.4] `test_throttling_standard_interval` проходит (min_interval_s=0.6)

### DocumentProcessor - исправления
- [TC-2.1] `test_init_from_pdf` проходит - PageInfo создается с index
- [TC-2.2] `test_init_from_png_array` проходит - PageInfo создается с index
- [TC-2.3] `test_pages_property` проходит - возвращает список PageInfo
- [TC-2.4] `test_num_pages_property` проходит - возвращает int
- [TC-2.5] Все тесты DocumentProcessor проходят (моки работают корректно)

### Интеграционные тесты
- [TC-3.1] `test_simple_invoke` пропускается если нет GEMINI_API_KEY
- [TC-3.2] `test_simple_invoke` проходит с реальным API при наличии ключа
- [TC-3.3] `test_invoke_with_tools` пропускается если нет GEMINI_API_KEY
- [TC-3.4] `test_invoke_with_tools` проходит с реальным API при наличии ключа

### Покрытие
- [TC-4.1] Все unit тесты VLM Client проходят (10/10)
- [TC-4.2] Все unit тесты VLM Agent проходят (9/9)
- [TC-4.3] Все unit тесты DocumentProcessor проходят
- [TC-4.4] Интеграционные тесты созданы и документированы

---

## 6. Важные детали для Developer

### Retry логика - как правильно

**Ключевой принцип:** Retry ТОЛЬКО на временных ошибках.

**Временные ошибки (retry):**
- 429 Too Many Requests - превысили rate limit, подождать и повторить
- 500-599 Server Errors - проблема на стороне сервера, может исправиться

**Постоянные ошибки (НЕ retry):**
- 400 Bad Request - проблема в запросе, повторение не поможет
- 401 Unauthorized - проблема с API ключом
- 403 Forbidden - нет прав доступа
- 404 Not Found - ресурс не найден
- 422 Unprocessable Entity - невалидные данные

**Паттерн реализации:**
```python
status = response.status_code

# Проверка на retryable ошибки
is_retryable = status == 429 or (500 <= status < 600)

if is_retryable and attempt < max_retries:
    # Retry with backoff
    # НЕ вызывать raise_for_status здесь
    time.sleep(backoff_base ** (attempt - 1))
    continue

# Для всех остальных случаев
response.raise_for_status()  # Exception для client errors
return response.json()       # Success
```

### PageInfo - единое поле index

**Правило:** Всегда использовать `PageInfo(index=..., image=...)`

**Почему index а не page_num:**
- Схема определена в задаче 001 с полем `index`
- PDFRenderer возвращает `Tuple[int, bytes]` где int - это page number (1-based)
- Мы используем этот int как index

**Примеры:**
```python
# Из PDF рендеринга
for page_num, img_bytes in rendered:
    PageInfo(index=page_num, image=img_bytes)

# Из PNG массива
for i, img_bytes in enumerate(png_array):
    PageInfo(index=i + 1, image=img_bytes)
```

### Мокание os.getenv и load_dotenv

**Проблема:** Локальные импорты внутри функции невозможно замокать через patch.

**Решение:** Вынести импорты в начало файла.

**До (неправильно):**
```python
def __init__(self, ...):
    import os  # Локальный импорт
    from dotenv import load_dotenv  # Локальный импорт
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
```

**После (правильно):**
```python
# В начале processor.py
import os
from dotenv import load_dotenv

def __init__(self, ...):
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
```

**Тест с моками:**
```python
@patch('vlm_ocr_doc_reader.core.processor.os.getenv')
@patch('vlm_ocr_doc_reader.core.processor.load_dotenv')
def test_init_creates_vlm_client(mock_load_dotenv, mock_getenv):
    mock_getenv.return_value = "test_api_key"
    # ... test code
```

### Интеграционные тесты - экономия квоты

**Принцип:** Минимум запросов к реальному API.

**Рекомендации:**
- 1-2 теста максимум
- Маленькие изображения или без изображений
- Промпты без tools для базового теста
- Один тест с tools для проверки function calling

**Skip если нет ключа:**
```python
pytestmark = pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set"
)
```

**Запуск:**
```bash
# Без API ключа - тесты skip
pytest tests/integration/

# С API ключом - тесты выполняются
export GEMINI_API_KEY=xxx
pytest tests/integration/
```

### Throttling - time.monotonic() vs time.time()

**Используй `time.monotonic()`:**
- Монотонные часы не зависят от системного времени
- Гарантируют корректную работу даже при изменении system time (NTP, manual correction)
- Уже реализовано правильно в коде

**НЕ используй `time.time()`:**
- Зависит от системного времени
- Может дать некорректные результаты если время изменится

### Логирование - что добавить

**Для retry логики:**
- Явно логировать когда НЕ выполняется retry (например, "status=400, not retrying")
- Это поможет при отладке понять почему запрос не был повторен

**Пример:**
```python
if not is_retryable:
    logger.info(f"Request failed with status={status}, not retrying (client error)")
    response.raise_for_status()
```

---

## История изменений

| Версия | Дата | Изменения | Автор |
|--------|------|-----------|-------|
| 1.0 | 2025-01-27 | Первая версия технического задания | Analyst |
| 2.0 | 2025-01-27 | Исправления по отзыву Reviewer: retry логика, PageInfo, тесты, интеграционные тесты | Analyst |
