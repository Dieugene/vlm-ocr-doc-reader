# Технический план: Base utilities (PDF Renderer, OCR нормализация, State Manager)

## 1. Анализ задачи

Реализовать три независимых базовых компонента модуля:
1. **PDFRenderer** - рендеринг PDF страниц в PNG изображения с настраиваемым DPI
2. **normalize_ocr_digits()** - утилита для исправления типичных OCR ошибок (O→0, l→1, S→5, B→8)
3. **StateManager** - управление состоянием с двумя backend'ами (Memory и Disk)

Эти компоненты - фундамент для всего модуля. PDF Renderer используется для подготовки документов для VLM, OCR нормализация улучшает качество извлечения числовых данных, State Manager обеспечивает персистентность для разработки и тестирования пайплайнов.

## 2. Текущее состояние

**Существующий код (reference implementations):**
- `02_src/_reference/pdf_utils.py` - рабочая реализация рендеринга из 05_a_reports_ETL_02 ( pymupdf/fitz, PIL, JPEG формат)
- `02_src/_reference/tools.py` - рабочая реализация нормализации из 05_a_reports_ETL_02

**Что нужно адаптировать:**
- PDFRenderer из reference использует JPEG, нужен PNG
- Reference код не имеет структуры модуля (просто функции)
- State Manager - новая разработка, нет reference

**Архитектура:**
- Модульная структура в `02_src/vlm_ocr_doc_reader/` с подпапками
- См. `00_docs/architecture/overview.md` раздел 2

## 3. Предлагаемое решение

### 3.1. Общий подход

**PDF Renderer:**
- Адаптировать `pdf_utils.py` из reference
- Использовать pymupdf (fitz) для рендеринга, PIL для конвертации
- Поддерживать два режима: render_pdf() все страницы, render_page() одна страница
- Возвращать PNG bytes (не JPEG как в reference)

**OCR нормализация:**
- Перенести функцию `_normalize_digits()` из tools.py с минимальными изменениями
- Сделать публичной функцией в модуле normalization.py

**State Manager:**
- Создать протокол StorageBackend с двумя реализациями
- MemoryStorage - in-memory dict
- DiskStorage - файловая система с каталогами cache/, results/, logs/
- StateManager агрегирует StorageBackend и DocumentState

### 3.2. Компоненты

#### PDFRenderer
- **Назначение:** Рендеринг PDF страниц в PNG изображения
- **Интерфейс:**
  - `__init__(config: RenderConfig)` - конструктор с конфигурацией
  - `render_pdf(pdf_path: Path, page_indices: Optional[List[int]]) -> List[Tuple[int, bytes]]` - рендеринг списка страниц (0-based), возвращает (page_num, png_bytes)
  - `render_page(pdf_path: Path, page_num: int, dpi: Optional[int]) -> bytes` - рендеринг одной страницы с переопределением DPI
- **Зависимости:** pymupdf (fitz), PIL, io, dataclasses
- **Логика:** Открыть PDF через fitz, для каждой страницы создать pixmap с нужным DPI, конвертировать в PIL Image, сохранить как PNG bytes

#### normalize_ocr_digits
- **Назначение:** Исправление OCR ошибок в числовых строках
- **Интерфейс:** `normalize_ocr_digits(raw: str, expected_length: Optional[int]) -> Optional[str]`
- **Зависимости:** typing
- **Логика:** Удалить пробелы/неразрывные пробелы/дефисы, заменить O→0, l→1, I→1, S→5, B→8, оставить только цифры, проверить длину если указана

#### StorageBackend (Protocol)
- **Назначение:** Абстракция хранилища для StateManager
- **Интерфейс:**
  - `save(key: str, value: Any) -> None`
  - `load(key: str, default: Any) -> Any`
  - `exists(key: str) -> bool`
- **Зависимости:** typing.Protocol

#### MemoryStorage
- **Назначение:** In-memory хранилище для экспериментов
- **Интерфейс:** Реализация StorageBackend
- **Логика:** Обертка вокруг dict[str, Any]
- **Зависимости:** typing.Dict

#### DiskStorage
- **Назначение:** Файловое хранилище для персистентности
- **Интерфейс:** Реализация StorageBackend
- **Логика:**
  - При init: создать каталоги cache/, results/, logs/ в state_dir
  - save/load работают с JSON для технических данных, YAML для результатов operations
  - Формат ключей: "pages/001", "vlm_responses/full_desc", "results/clustering"
- **Зависимости:** pathlib, json, yaml (PyYAML)

#### DocumentState
- **Назначение:** Контейнер состояния документа
- **Интерфейс:** dataclass с полями pages, vlm_responses, operation_results
- **Зависимости:** dataclasses

#### StateManager
- **Назначение:** Менеджер состояния документа
- **Интерфейс:**
  - `__init__(storage: StorageBackend)` - конструктор с backend'ом
  - `save_page(page_num: int, image: bytes) -> None`
  - `load_page(page_num: int) -> Optional[bytes]`
  - `save_vlm_response(operation: str, response: Dict) -> None`
  - `save_operation_result(operation: str, result: Any) -> None` - в YAML формат
  - `save_state() -> None` - явное сохранение всего состояния
  - `load_state() -> None` - загрузка состояния из storage
- **Логика:** Делегирует save/load в storage backend, форматирует ключи
- **Зависимости:** typing, DocumentState

### 3.3. Структуры данных

**RenderConfig:**
```python
@dataclass
class RenderConfig:
    dpi: int = 150           # DPI для рендеринга
    quality: int = 85        # Качество (не используется для PNG)
    format: str = "PNG"      # Формат изображения
```

**DocumentState:**
```python
@dataclass
class DocumentState:
    pages: Dict[int, bytes]              # page_num → image_bytes
    vlm_responses: Dict[str, Any]        # operation → response
    operation_results: Dict[str, Any]    # operation → result
```

**Структура state_dir при DiskStorage:**
```
state_dir/
├── cache/
│   ├── pages/              # page_001.png, page_002.png, ...
│   └── vlm_responses/      # response_full_desc.json, ...
├── results/                # full_description.yaml, ...
├── logs/                   # vlm_ocr.log
└── state.json              # metadata (auto_save, DPI, etc.)
```

### 3.4. Ключевые алгоритмы

**PDF Renderer:**
1. Открыть PDF через `fitz.open(pdf_path)`
2. Для каждой страницы из page_indices (или всех страниц):
   - Загрузить страницу через `doc.load_page(idx)`
   - Создать pixmap: `page.get_pixmap(dpi=config.dpi)`
   - Определить режим: RGB если alpha=0 иначе RGBA
   - Создать PIL Image: `Image.frombytes(mode, [width, height], pix.samples)`
   - Конвертировать RGBA→RGB если нужно
   - Сохранить в BytesIO как PNG
   - Вернуть (page_num, bytes)

**OCR нормализация:**
1. Привести к строке: `str(raw)`
2. Удалить пробелы, \xa0, -
3. Заменить O→0, o→0, l→1, I→1, S→5, B→8
4. Оставить только цифры через `ch.isdigit()`
5. Проверить длину если expected_length указан
6. Вернуть строку или None если пусто

**DiskStorage.save():**
1. Разобрать ключ на части ("pages/001" → type, name)
2. Определить подкаталог (cache/pages, cache/vlm_responses, results)
3. Определить формат (PNG для страниц, JSON для VLM ответов, YAML для результатов)
4. Создать подкаталоги если нет
5. Сохранить в файл

**StateManager.save_operation_result():**
1. Сериализовать result в YAML (человеко-читаемый формат)
2. Вызвать `storage.save(f"results/{operation}", yaml_str)`
3. Обновить `state.operation_results[operation]`

### 3.5. Изменения в существующем коде

Ничего не меняется - это новая разработка. Reference код только для изучения паттернов.

## 4. План реализации

1. **Создать структуру модулей:**
   - `02_src/vlm_ocr_doc_reader/__init__.py` - пустой (пока)
   - `02_src/vlm_ocr_doc_reader/preprocessing/__init__.py`
   - `02_src/vlm_ocr_doc_reader/preprocessing/renderer.py` - PDFRenderer
   - `02_src/vlm_ocr_doc_reader/utils/__init__.py`
   - `02_src/vlm_ocr_doc_reader/utils/normalization.py` - normalize_ocr_digits
   - `02_src/vlm_ocr_doc_reader/core/__init__.py`
   - `02_src/vlm_ocr_doc_reader/core/state.py` - StateManager и все компоненты

2. **Реализовать PDFRenderer:**
   - Создать RenderConfig dataclass
   - Создать класс PDFRenderer с методами render_pdf(), render_page()
   - Добавить типизацию и docstrings
   - Логировать количество рендеримых страниц

3. **Реализовать normalize_ocr_digits:**
   - Перенести логику из reference/tools.py
   - Добавить type hints и docstring
   - Сделать публичной функцией

4. **Реализовать State Manager:**
   - Создать протокол StorageBackend
   - Создать MemoryStorage
   - Создать DiskStorage с созданием каталогов
   - Создать DocumentState dataclass
   - Создать StateManager с методами save/load

5. **Написать unit тесты:**
   - Тесты для PDFRenderer: проверка размера изображений, DPI, количества страниц
   - Тесты для normalize_ocr_digits: все замены, проверка длины
   - Тесты для MemoryStorage: save/load/exists
   - Тесты для DiskStorage: создание файлов, структура каталогов
   - Тесты для StateManager: сохранение/загрузка страниц, VLM ответов, результатов

6. **Интеграционные тесты:**
   - PDF → рендеринг всех страниц
   - StateManager с DiskStorage: полный цикл save/load

7. **Настроить логирование:**
   - Добавить логгеры в каждый модуль (renderer.py, state.py)
   - Использовать setup_logger из utils/logging.py (если есть)

## 5. Технические критерии приемки

- [ ] TC-1: PDFRenderer.render_pdf() рендерит все страницы PDF в PNG bytes (проверить размер > 0, формат PNG)
- [ ] TC-2: PDFRenderer.render_pdf() с page_indices рендерит только указанные страницы (0-based)
- [ ] TC-3: PDFRenderer.render_page() с переопределением DPI использует кастомный DPI
- [ ] TC-4: normalize_ocr_digits выполняет все замены (O→0, l→1, S→5, B→8)
- [ ] TC-5: normalize_ocr_digits возвращает None если expected_length не совпадает
- [ ] TC-6: MemoryStorage.save/load сохраняют и загружают данные в памяти
- [ ] TC-7: DiskStorage создает структуру каталогов cache/, results/, logs/
- [ ] TC-8: DiskStorage.save_page() сохраняет PNG в cache/pages/page_XXX.png
- [ ] TC-9: DiskStorage.save_operation_result() сохраняет YAML в results/
- [ ] TC-10: StateManager.save_state() / load_state() сохраняют и загружают все состояние
- [ ] TC-11: Unit тесты покрывают все компоненты (> 80% coverage)
- [ ] TC-12: Интеграционный тест PDF → страницы → StateManager проходит

## 6. Важные детали для Developer

### pymupdf (fitz) специфика:
- PDF страницы индексируются с 0, но в методах render_pdf() возвращать page_num с 1 (для удобства пользователей)
- `page.get_pixmap(dpi=150)` создает pixmap с указанным DPI
- Проверять `pix.alpha` для определения режима (RGB/RGBA)
- Всегда закрывать doc через `doc.close()` в finally блоке

### PIL Image:
- `Image.frombytes(mode, [width, height], pix.samples)` создает изображение из pixmap
- PNG не использует параметр quality (в отличие от JPEG), но оставим в конфиге для совместимости

### OCR нормализация:
- Замена I→1 важна для capitalized текстов (например, "I234" → "1234")
- Удалять неразрывные пробелы (\xa0) - они часто встречаются в PDF
- Возвращать None если после очистки нет цифр

### State Manager:
- DiskStorage должен создавать каталоги при инициализации (`mkdir(exist_ok=True)`)
- YAML формат для результатов operations - человеко-читаемый, JSON для VLM ответов - технический
- Ключи формируются как "pages/001", "vlm_responses/full_desc", "results/clustering"
- При save_operation_result() сериализовать в YAML, не JSON

### Логирование:
- Использовать logger.info() для начала/конца операций
- Логировать количество рендеримых страниц, пути к файлам
- Добавить logger.exception() в exception handlers

### Тестирование:
- Использовать pytest для тестов
- Создать фикстуру с тестовым PDF (минимум 2-3 страницы)
- Для тестов DiskStorage использовать temporary directory (tmp_path от pytest)
- Проверять не только успешные пути, но и error cases (невалидные пути, пустые данные)

### Зависимости:
- pymupdf (pip install pymupdf)
- PyYAML (pip install pyyaml)
- pytest (pip install pytest) для тестов

### Каталоги:
- 02_src/vlm_ocr_doc_reader/ - основной модуль
- tests/test_preprocessing/test_renderer.py - тесты renderer
- tests/test_utils/test_normalization.py - тесты нормализации
- tests/test_core/test_state.py - тесты state manager
- 03_data/test_documents/ - тестовые PDF для тестов
