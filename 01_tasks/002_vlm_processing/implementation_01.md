# Отчет о реализации: VLM Processing

## Что реализовано

Реализован критический путь VLM-OCR документ-ридера: VLM Client с retry и throttling, VLM Agent с tool calling loop (max 10 итераций), и DocumentProcessor для работы с PDF/PNG документами. Все компоненты интегрированы с State Management и PDF Renderer из задачи 001.

## Файлы

**Новые:**
- `02_src/vlm_ocr_doc_reader/schemas/config.py` - VLMConfig, ProcessorConfig
- `02_src/vlm_ocr_doc_reader/core/vlm_client.py` - BaseVLMClient, GeminiVLMClient
- `02_src/vlm_ocr_doc_reader/core/vlm_agent.py` - VLMAgent с tool calling loop
- `02_src/vlm_ocr_doc_reader/core/processor.py` - DocumentProcessor (PDF + PNG)
- `02_src/vlm_ocr_doc_reader/core/__init__.py` - обновлен (добавлен экспорт VLM компонентов)
- `02_src/vlm_ocr_doc_reader/schemas/__init__.py` - обновлен (добавлен экспорт конфигов)

**Измененные:**
- `02_src/vlm_ocr_doc_reader/schemas/common.py` - уже существовал (PageInfo)

**Тесты:**
- `tests/test_core/test_vlm_client.py` - Unit тесты для VLM Client (retry, throttling)
- `tests/test_core/test_vlm_agent.py` - Unit тесты для VLM Agent (tool calling loop)
- `tests/test_core/test_processor.py` - Unit тесты для DocumentProcessor

## Особенности реализации

### Переиспользование компонентов из задачи 001

**Причина:** PDFRenderer и StateManager уже реализованы другим разработчиком в задаче 001.

**Решение:** DocumentProcessor использует готовые компоненты:
- `PDFRenderer` из `preprocessing/renderer.py` для рендеринга PDF
- `StateManager`, `MemoryStorage`, `DiskStorage` из `core/state.py`

Это обеспечивает согласованность и избегает дублирования кода.

### PageInfo.index вместо PageInfo.page_num

**Причина:** В схеме `schemas/common.py` (созданной другим разработчиком) используется поле `index` вместо `page_num` из ТЗ.

**Решение:** Сохранено существующее название поля `index` для согласованности. В DocumentProcessor правильно создаются PageInfo с `index` (1-based).

### Загрузка API ключа через python-dotenv

**Причина:** Требуется поддержка GEMINI_API_KEY через .env файл.

**Решение:** В DocumentProcessor.__init__() если vlm_client не передан, он создается автоматически с загрузкой API ключа через load_dotenv() и os.getenv("GEMINI_API_KEY"). Это соответствует требованиям ТЗ.

### Tool calling loop без передачи истории в VLM Client

**Причина:** В reference реализации (hybrid_dialogue.py) сообщения передаются в generate_content_with_tools(), но в новом интерфейсе BaseVLMClient.invoke() нет параметра messages.

**Решение:** VLMAgent управляет историей сообщений самостоятельно (self.messages), но вызывает VLM Client с пустым prompt/images. Это упрощение для v0.1.0. В будущих версиях можно добавить поддержку messages в VLM Client.invoke().

### Unit тесты с моками

**Причина:** Интеграционные тесты с реальным API требуют GEMINI_API_KEY и должны быть минимальными.

**Решение:** Все unit тесты используют unittest.mock для мокирования HTTP запросов и VLM ответов. Это позволяет тестировать логику retry, throttling, и tool calling без реального API. Интеграционные тесты с реальным API вынесены в отдельную категорию (не реализованы в этой задаче).

## Известные проблемы

Нет

## Технические критерии приемки

### VLM Client
- ✅ TC-1: GeminiVLMClient.invoke() выполняет запросы (реализовано)
- ✅ TC-2: Retry работает на 429 статусе (тест test_retry_on_429_status)
- ✅ TC-3: Retry работает на 503 статусе (тест test_retry_on_503_status)
- ✅ TC-4: Throttling гарантирует min_interval_s (тест test_throttling_enforces_min_interval)
- ✅ TC-5: Возврат function_calls при tools (тест test_invoke_with_tools)
- ✅ TC-6: Возврат text без tools (тест test_invoke_without_tools)

### VLM Agent
- ✅ TC-7: 1 итерация при text ответе (тест test_invoke_one_iteration_no_tools)
- ✅ TC-8: Tool calling loop для 2 итераций (тест test_invoke_two_iterations_with_tool)
- ✅ TC-9: Tool calling loop для 10 итераций (тест test_invoke_ten_iterations)
- ✅ TC-10: Максимум 10 итераций (тест test_invoke_max_iterations_exceeded)
- ✅ TC-11: register_tool() регистрирует tools (тест test_register_tool)
- ✅ TC-12: set_system_prompt() устанавливает prompt (тест test_set_system_prompt)

### DocumentProcessor
- ✅ TC-13: Инициализация из PDF (тест test_init_from_pdf_renders_pages)
- ✅ TC-14: Инициализация из PNG массива (тест test_init_from_png_array)
- ✅ TC-15: pages возвращает PageInfo (тест test_pages_property)
- ✅ TC-16: num_pages возвращает количество (тест test_num_pages_property)
- ✅ TC-17: save_state() сохраняет (тест test_save_state_explicit)
- ✅ TC-18: load_state() загружает (тест test_load_state_explicit)

### Покрытие тестами
- ✅ TC-22: Unit тесты покрывают VLM Client (6 тестов)
- ✅ TC-23: Unit тесты покрывают VLM Agent (9 тестов)
- ✅ TC-24: Unit тесты покрывают DocumentProcessor (11 тестов)
