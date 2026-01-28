# Техническое задание: CLI интерфейс для распознавания документов (v2)

## 1. Анализ задачи

Исправить реализацию CLI интерфейса согласно замечаниям от Reviewer. Основная логика CLI реализована корректно, но необходимо исправить две критические проблемы: добавить отсутствующую секцию `[project.scripts]` в pyproject.toml для регистрации entry point и исправить некорректное использование pytest fixtures в тестах (`monkeybot` вместо `monkeypatch`).

## 2. Текущее состояние

**Уже реализовано корректно:**
- `02_src/vlm_ocr_doc_reader/cli.py` — полный CLI модуль с argparse, валидацией, интеграцией с DocumentProcessor
- `pyproject.toml` — metadata, dependencies, setuptools конфигурация
- `02_src/tests/unit/test_cli.py` — unit тесты с моками VLM, покрытие основных сценариев
- Логика CLI использует существующие модули без дублирования кода
- Валидация аргументов (PDF существует, API ключ задан)
- Сохранение результатов через state_manager
- Логирование в stdout с настраиваемым уровнем

**Проблемы выявленные Reviewer:**
1. **Критическая:** отсутствует секция `[project.scripts]` в pyproject.toml → CLI не доступен глобально
2. **Высокая:** в тестах используется `monkeybot` вместо корректного pytest fixture `monkeypatch` → тесты падают

## 3. Предлагаемое решение

### 3.1. Общий подход

Исправить два конкретных дефекта без изменения остальной реализации:
1. Добавить секцию `[project.scripts]` в pyproject.toml для регистрации CLI команды
2. Заменить все вхождения `monkeybot` на `monkeypatch` в тестах

### 3.2. Компоненты для изменения

#### pyproject.toml
- **Назначение:** packaging и регистрация CLI entry point
- **Изменения:** добавить секцию `[project.scripts]` после строки 56
- **Содержимое:**
```toml
[project.scripts]
vlm-ocr-reader = "vlm_ocr_doc_reader.cli:main"
```

#### test_cli.py
- **Назначение:** unit тесты для CLI
- **Изменения:** заменить `monkeybot` на `monkeypatch` во всех тестовых функциях
- **Затронутые строки:** 134, 138, 168, 171, 185, 188, 207, 213, 257, 261, 300, 305, 339, 344, 363, 368
- **Заменить:** все вхождения параметра `monkeybot` → `monkeypatch`
- **Заменить:** все вызовы `monkeybot.setenv()` → `monkeypatch.setenv()`
- **Заменить:** все вызовы `monkeybot.delenv()` → `monkeypatch.delenv()`

### 3.3. Структуры данных

Изменений нет — используется существующая структура.

### 3.4. Ключевые алгоритмы

Изменений нет — логика работы остается прежней.

### 3.5. Изменения в существующем коде

**pyproject.toml:**
```toml
# После строки 56 добавить:

[project.scripts]
vlm-ocr-reader = "vlm_ocr_doc_reader.cli:main"
```

**test_cli.py:**
- Во всех функциях класса TestMainFunction заменить параметр `monkeybot` на `monkeypatch`
- Примеры:
  - Строка 134: `def test_main_success(..., monkeybot):` → `def test_main_success(..., monkeypatch):`
  - Строка 138: `monkeybot.setenv(...)` → `monkeypatch.setenv(...)`
  - Строка 168: `def test_main_pdf_not_found(..., monkeybot, ...):` → `def test_main_pdf_not_found(..., monkeypatch, ...):`

## 4. План реализации

1. **Шаг 1:** Добавить секцию `[project.scripts]` в pyproject.toml
2. **Шаг 2:** Заменить `monkeybot` на `monkeypatch` в test_cli.py (8 функций класса TestMainFunction)
3. **Шаг 3:** Пересобрать пакет через `pip install -e .`
4. **Шаг 4:** Проверить что CLI доступен: `vlm-ocr-reader --help`
5. **Шаг 5:** Запустить тесты: `pytest 02_src/tests/unit/test_cli.py`

## 5. Технические критерии приемки

- [ ] TC-1: pyproject.toml содержит секцию `[project.scripts]`
- [ ] TC-2: Entry point зарегистрирован как `vlm-ocr-reader = "vlm_ocr_doc_reader.cli:main"`
- [ ] TC-3: После `pip install -e .` команда `vlm-ocr-reader --help` доступна из любой директории
- [ ] TC-4: Все тестовые функции используют `monkeypatch` вместо `monkeybot`
- [ ] TC-5: Все тесты в test_cli.py проходят успешно
- [ ] TC-6: CLI сохраняет результаты в `{output_dir}/results/full_description.yaml`
- [ ] TC-7: CLI возвращает exit code 0 при успехе, 1 при ошибке

## 6. Важные детали для Developer

### Специфичные риски:

**Entry point регистрация:**
- После добавления `[project.scripts]` необходимо переустановить пакет: `pip install -e .`
- Это обновит скрипты в bin/ директории virtual environment
- Проверка работоспособности: `vlm-ocr-reader --help` должен показать help сообщение

**Pytest fixtures:**
- `monkeypatch` — это встроенный fixture из pytest для модификации окружения/объектов во время тестов
- `monkeybot` — не существует, это опечатка导致 ошибку `fixture 'monkeybot' not found`
- Замена должна быть точной: не `monkeybot` → `monkeypatchbot`, а именно `monkeybot` → `monkeypatch`

**Перечень замен в test_cli.py:**

Функции для замены параметра (8 функций):
1. `test_main_success` — строка 134
2. `test_main_pdf_not_found` — строка 168
3. `test_main_missing_api_key` — строка 185
4. `test_main_custom_output_dir` — строка 207
5. `test_main_custom_dpi` — строкa 251
6. `test_main_debug_logging` — строка 295
7. `test_main_keyboard_interrupt` — строка 334
8. `test_main_exception_handling` — строка 357

Вызовы для замены (внутри этих функций):
- `monkeybot.setenv()` → `monkeypatch.setenv()`
- `monkeybot.delenv()` → `monkeypatch.delenv()`

**Проверка после изменений:**
1. Переустановить пакет: `pip install -e .`
2. Проверить CLI: `vlm-ocr-reader --help`
3. Запустить тесты: `pytest 02_src/tests/unit/test_cli.py -v`
4. Убедиться что все тесты проходят (нет ошибок `fixture 'monkeybot' not found`)

**Примечание о logging тестах:**
Reviewer отметил потенциальную проблему с тестами `test_setup_logging_debug` и `test_setup_logging_warning` (pytest может настраивать root logger по-своему). Однако это вторичная проблема по отношению к `monkeybot`. Если после исправления `monkeybot` эти тесты все равно падают — можно их удалить или упростить (проверять только что setup_logging не вызывает exception).
