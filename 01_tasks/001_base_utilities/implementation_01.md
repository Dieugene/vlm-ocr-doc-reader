# Отчет о реализации: Base utilities

## Что реализовано

Реализованы базовые утилиты модуля vlm-ocr-doc-reader согласно техническому заданию:
1. **PDFRenderer** - рендеринг PDF страниц в PNG изображения с настраиваемым DPI
2. **normalize_ocr_digits()** - утилита для исправления типичных OCR ошибок (O→0, l→1, S→5, B→8)
3. **StateManager** - управление состоянием с двумя backend'ами (Memory и Disk)

## Файлы

**Новые:**
- `02_src/vlm_ocr_doc_reader/preprocessing/__init__.py` - модуль preprocessing
- `02_src/vlm_ocr_doc_reader/preprocessing/renderer.py` - PDFRenderer и RenderConfig
- `02_src/vlm_ocr_doc_reader/utils/__init__.py` - модуль utils
- `02_src/vlm_ocr_doc_reader/utils/normalization.py` - normalize_ocr_digits функция
- `02_src/vlm_ocr_doc_reader/core/__init__.py` - обновлен (экспорт state компонентов)
- `02_src/vlm_ocr_doc_reader/core/state.py` - StorageBackend, MemoryStorage, DiskStorage, DocumentState, StateManager

**Тесты:**
- `tests/test_preprocessing/test_renderer.py` - 11 тестов для PDFRenderer
- `tests/test_utils/test_normalization.py` - 17 тестов для normalize_ocr_digits
- `tests/test_core/test_state.py` - 26 тестов для State Manager
- `tests/test_integration/test_base_utilities.py` - 3 интеграционных теста

## Особенности реализации

### PDF Renderer
- Адаптирован из `02_src/_reference/pdf_utils.py` с изменениями:
  - Возвращаемый формат изменен с JPEG на PNG (согласно ТЗ)
  - Добавлена поддержка RenderConfig dataclass
  - Метод `render_pdf()` принимает 0-based индексы, возвращает 1-based номера страниц
  - Метод `render_page()` позволяет переопределять DPI при вызове
  - Логирование количества рендеримых страниц и размеров файлов

### OCR нормализация
- Перенесена из `02_src/_reference/tools.py` без изменений логики
- Сделана публичной функцией в модуле `utils/normalization.py`
- Добавлены type hints и детальная документация
- Поддерживает валидацию длины (expected_length параметр)

### State Manager
- Полностью новая разработка (не было в reference)
- **StorageBackend Protocol** - абстракция для разных хранилищ
- **MemoryStorage** - in-memory хранилище на основе dict
- **DiskStorage** - файловое хранилище с автоматическим созданием структуры каталогов:
  - `cache/pages/` - PNG изображения страниц (page_001.png, page_002.png, ...)
  - `cache/vlm_responses/` - JSON ответы VLM (response_operation.json)
  - `results/` - YAML результаты operations (operation.yaml)
  - `logs/` - логи (для будущего использования)
- **StateManager** - агрегирует StorageBackend и DocumentState
- Форматирование ключей: "pages/001", "vlm_responses/operation", "results/operation"
- Поддержка zero-padding для номеров страниц (001, 002, ..., 010, ..., 100)

## Отклонения от плана

Нет. Реализовано полностью согласно `analysis_01.md`.

## Известные проблемы

Нет. Все компоненты работают корректно, все тесты проходят.

## Результаты тестирования

**Unit тесты (54 теста):**
- ✅ 17 тестов для normalize_ocr_digits - все проходят
- ✅ 11 тестов для PDFRenderer - все проходят
- ✅ 26 тестов для State Manager - все проходят

**Интеграционные тесты (3 теста):**
- ✅ Полный цикл PDF → рендеринг → StateManager с DiskStorage
- ✅ Выборочный рендеринг страниц
- ✅ Кастомный DPI для разных сценариев

**Технические критерии приемки (TC):**
- ✅ TC-1: render_pdf() рендерит все страницы в PNG
- ✅ TC-2: render_pdf() с page_indices рендерит только указанные страницы
- ✅ TC-3: render_page() с переопределением DPI использует кастомный DPI
- ✅ TC-4: normalize_ocr_digits выполняет все замены
- ✅ TC-5: normalize_ocr_digits возвращает None если expected_length не совпадает
- ✅ TC-6: MemoryStorage.save/load сохраняют и загружают данные
- ✅ TC-7: DiskStorage создает структуру каталогов
- ✅ TC-8: DiskStorage.save_page() сохраняет PNG в cache/pages/
- ✅ TC-9: DiskStorage.save_operation_result() сохраняет YAML в results/
- ✅ TC-10: StateManager.save_state() / load_state() работают
- ✅ TC-11: Unit тесты покрывают все компоненты (54 теста > 80%)
- ✅ TC-12: Интеграционный тест PDF → страницы → StateManager проходит
