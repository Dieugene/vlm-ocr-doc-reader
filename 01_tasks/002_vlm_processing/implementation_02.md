# Отчет о реализации: VLM Processing (исправления)

## Что реализовано

Исправлены критические проблемы в реализации задачи 002 согласно отзыву Reviewer:
1. VLM Client retry логика - НЕ выполняется retry на 4xx (кроме 429)
2. DocumentProcessor PageInfo - используется поле index вместо page_num
3. Тесты DocumentProcessor - исправлено мокание os.getenv и load_dotenv
4. Добавлен тест throttling на стандартном значении 0.6s
5. Созданы интеграционные тесты с реальным API (с пропуском если нет ключа)

## Файлы

**Измененные:**
- `02_src/vlm_ocr_doc_reader/core/vlm_client.py` - исправлена логика retry (НЕ retry на 400-499 кроме 429)
- `02_src/vlm_ocr_doc_reader/core/processor.py` - импорты вынесены в начало файла, PageInfo использует index

**Измененные тесты:**
- `tests/test_core/test_vlm_client.py` - добавлен тест test_throttling_standard_interval (0.6s)

**Новые тесты:**
- `tests/integration/test_vlm_client_real_api.py` - интеграционные тесты с реальным API

## Особенности реализации

### Исправлена retry логика для 4xx ошибок

**Причина:** Reviewer обнаружил что при status=400 выполняется 3 попытки вместо немедленного возврата ошибки. Ошибка 400 означает проблему с запросом (Bad Request), повторение не поможет.

**Решение:** Добавлена явная проверка: retry ТОЛЬКО на 429 и 500-599. Для всех остальных ошибок (включая 400-499 кроме 429) вызов raise_for_status() происходит немедленно без retry. Логика теперь корректно обрабатывает три случая:
1. Retryable ошибки с оставшимися попытками → retry с backoff
2. Retryable ошибки без оставшихся попыток → raise immediately
3. Non-retryable ошибки (4xx кроме 429) → raise immediately

### PageInfo использует поле index

**Причина:** Схема PageInfo из задачи 001 имеет поле `index`, но DocumentProcessor создавал PageInfo с несуществующим полем `page_num`.

**Решение:** DocumentProcessor теперь создает PageInfo с полем `index`:
- Из PDF: `PageInfo(index=page_num, image=img_bytes)`
- Из PNG массива: `PageInfo(index=i + 1, image=img_bytes)`

### Вынесены импорты в processor.py

**Причина:** Локальные импорты внутри `__init__()` невозможно замокать через `@patch` в тестах.

**Решение:** Импорты `os` и `load_dotenv` вынесены в начало файла `processor.py`. Тесты теперь правильно мокают `vlm_ocr_doc_reader.core.processor.os.getenv` и `vlm_ocr_doc_reader.core.processor.load_dotenv`.

### Добавлен тест throttling на стандартном значении

**Причина:** Reviewer отметил что throttling проверяется только на 0.2s вместо стандартного 0.6s из ТЗ.

**Решение:** Добавлен тест `test_throttling_standard_interval` который проверяет что между двумя вызовами проходит ≥ 0.6s при `min_interval_s=0.6` (стандартное значение из task_brief).

### Созданы интеграционные тесты

**Причина:** analysis.md требовал интеграционные тесты с реальным API, но они отсутствовали в implementation_01.md.

**Решение:** Создан `tests/integration/test_vlm_client_real_api.py` с 4 тестами:
- `test_simple_invoke_no_images` - простой запрос без изображений
- `test_invoke_with_tools` - запрос с function calling
- `test_invoke_error_handling_invalid_key` - проверка обработки невалидного ключа
- `test_throttling_with_real_api` - проверка throttling с реальным API

Все тесты пропускаются если `GEMINI_API_KEY` не задан в environment, что позволяет запускать их в CI/CD без блокировки.

## Известные проблемы

Нет

## Технические критерии приемки

### VLM Client - исправления
- ✅ TC-1.1: test_no_retry_on_400_status проходит - НЕ выполняется retry на 400
- ✅ TC-1.2: Retry работает на 429 (существующий тест проходит)
- ✅ TC-1.3: Retry работает на 503 (существующий тест проходит)
- ✅ TC-1.4: test_throttling_standard_interval проходит (min_interval_s=0.6)

### DocumentProcessor - исправления
- ✅ TC-2.1: test_init_from_pdf проходит - PageInfo создается с index
- ✅ TC-2.2: test_init_from_png_array проходит - PageInfo создается с index
- ✅ TC-2.3: test_pages_property проходит - возвращает список PageInfo
- ✅ TC-2.4: test_num_pages_property проходит - возвращает int
- ✅ TC-2.5: Все тесты DocumentProcessor проходят (моки работают корректно, 12/12)

### Интеграционные тесты
- ✅ TC-3.1: test_simple_invoke_no_images пропускается если нет GEMINI_API_KEY
- ✅ TC-3.2: test_invoke_with_tools пропускается если нет GEMINI_API_KEY
- ✅ TC-3.3: test_invoke_error_handling_invalid_key пропускается если нет GEMINI_API_KEY
- ✅ TC-3.4: test_throttling_with_real_api пропускается если нет GEMINI_API_KEY

### Покрытие
- ✅ TC-4.1: Все unit тесты VLM Client проходят (11/11)
- ✅ TC-4.2: Все unit тесты VLM Agent проходят (9/9)
- ✅ TC-4.3: Все unit тесты DocumentProcessor проходят (12/12)
- ✅ TC-4.4: Интеграционные тесты созданы и документированы (4 теста)

**Итого:** 60 unit тестов проходят, 4 интеграционных теста созданы (пропускаются без API ключа)
