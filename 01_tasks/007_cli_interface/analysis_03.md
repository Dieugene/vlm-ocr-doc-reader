# Техническое задание: CLI интерфейс для распознавания документов (v3)

## 1. Анализ задачи

Исправить последнюю оставшуюся проблему в тестах CLI интерфейса. Из 8 тестовых функций класса TestMainFunction только 6 были исправлены в предыдущей итерации. Функции `test_main_pdf_not_found` (строка 168) и `test_main_missing_api_key` (строка 185) все еще используют некорректное имя параметра `monkeybot` вместо `monkeypatch`, что вызывает ошибку `fixture 'monkeybot' not found` при выполнении тестов.

## 2. Текущее состояние

**Уже исправлено корректно (6 из 8 функций):**
1. ✅ `test_main_success` (строка 134) - использует `monkeypatch`
2. ✅ `test_main_custom_output_dir` (строка 208) - использует `monkeypatch`
3. ✅ `test_main_custom_dpi` (строка 257) - использует `monkeypatch`
4. ✅ `test_main_debug_logging` (строка 301) - использует `monkeypatch`
5. ✅ `test_main_keyboard_interrupt` (строка 340) - использует `monkeypatch`
6. ✅ `test_main_exception_handling` (строка 363) - использует `monkeypatch`

**Осталось исправить (2 из 8 функций):**
- ❌ `test_main_pdf_not_found` (строка 168) - использует `monkeybot` вместо `monkeypatch`
- ❌ `test_main_missing_api_key` (строка 185) - использует `monkeybot` вместо `monkeypatch`

**Что уже работает:**
- CLI полностью функционален, entry point зарегистрирован в pyproject.toml
- Логика CLI корректна, сохранение результатов работает
- Большинство тестов исправлено и проходят успешно

## 3. Предлагаемое решение

### 3.1. Общий подход

Исправить две оставшиеся тестовые функции путем замены параметра `monkeybot` на `monkeypatch`. Использовать grep для поиска всех вхождений `monkeybot` в файле теста перед началом работы.

### 3.2. Компоненты для изменения

#### test_cli.py
- **Файл:** `02_src/tests/unit/test_cli.py`
- **Назначение:** unit тесты для CLI
- **Изменения:** заменить `monkeybot` на `monkeypatch` в двух функциях

**Чеклист из 8 функций класса TestMainFunction:**

| # | Функция | Строка | Текущее состояние | Требуемое действие |
|---|---------|--------|-------------------|-------------------|
| 1 | `test_main_success` | 134 | ✅ `monkeypatch` | Без изменений |
| 2 | `test_main_pdf_not_found` | 168 | ❌ `monkeybot` | **ЗАМЕНИТЬ** на `monkeypatch` |
| 3 | `test_main_missing_api_key` | 185 | ❌ `monkeybot` | **ЗАМЕНИТЬ** на `monkeypatch` |
| 4 | `test_main_custom_output_dir` | 208 | ✅ `monkeypatch` | Без изменений |
| 5 | `test_main_custom_dpi` | 257 | ✅ `monkeypatch` | Без изменений |
| 6 | `test_main_debug_logging` | 301 | ✅ `monkeypatch` | Без изменений |
| 7 | `test_main_keyboard_interrupt` | 340 | ✅ `monkeypatch` | Без изменений |
| 8 | `test_main_exception_handling` | 363 | ✅ `monkeypatch` | Без изменений |

### 3.3. Детальное описание изменений

**Изменение 1: `test_main_pdf_not_found` (строка 168)**

Текущее состояние (строки 168-171):
```python
def test_main_pdf_not_found(self, mock_load_dotenv, monkeybot, tmp_path, capsys):
    """Test main function with non-existent PDF."""
    # Mock environment
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")  # ❌ Используется monkeypatch.setenv, но параметр называется monkeybot
```

Требуемое изменение:
```python
def test_main_pdf_not_found(self, mock_load_dotenv, monkeypatch, tmp_path, capsys):  # ✅ Заменить monkeybot → monkeypatch
    """Test main function with non-existent PDF."""
    # Mock environment
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")  # ✅ Теперь вызов корректен
```

**Изменение 2: `test_main_missing_api_key` (строка 185)**

Текущее состояние (строки 185-188):
```python
def test_main_missing_api_key(self, mock_load_dotenv, mock_pdf_path, monkeybot, capsys):
    """Test main function with missing API key."""
    # Ensure no API key is set
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)  # ❌ Используется monkeypatch.delenv, но параметр называется monkeybot
```

Требуемое изменение:
```python
def test_main_missing_api_key(self, mock_load_dotenv, mock_pdf_path, monkeypatch, capsys):  # ✅ Заменить monkeybot → monkeypatch
    """Test main function with missing API key."""
    # Ensure no API key is set
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)  # ✅ Теперь вызов корректен
```

### 3.4. Структуры данных

Изменений нет — используются существующие тестовые структуры.

### 3.5. Ключевые алгоритмы

Изменений нет — логика тестов остается прежней.

## 4. План реализации

1. **Шаг 1: Поиск всех вхождений `monkeybot`**
   - Выполнить: `grep -n "monkeybot" 02_src/tests/unit/test_cli.py`
   - Убедиться что найдены ровно 2 вхождения (строки 168 и 185)
   - Это гарантирует что не пропущены ни одна функция

2. **Шаг 2: Замена в `test_main_pdf_not_found`**
   - Открыть файл `02_src/tests/unit/test_cli.py`
   - Перейти к строке 168
   - Заменить параметр `monkeybot` на `monkeypatch`

3. **Шаг 3: Замена в `test_main_missing_api_key`**
   - Перейти к строке 185
   - Заменить параметр `monkeybot` на `monkeypatch`

4. **Шаг 4: Проверка после изменений**
   - Выполнить: `grep -n "monkeybot" 02_src/tests/unit/test_cli.py`
   - Убедиться что найдено 0 вхождений (все заменены)

5. **Шаг 5: Запуск тестов**
   - Выполнить: `pytest 02_src/tests/unit/test_cli.py -v`
   - Убедиться что все 8 тестовых функций класса TestMainFunction проходят успешно

## 5. Технические критерии приемки

- [ ] TC-1: Команда `grep -n "monkeybot" 02_src/tests/unit/test_cli.py` возвращает пустой результат (0 вхождений)
- [ ] TC-2: Параметр `monkeybot` заменен на `monkeypatch` в функции `test_main_pdf_not_found` (строка 168)
- [ ] TC-3: Параметр `monkeybot` заменен на `monkeypatch` в функции `test_main_missing_api_key` (строка 185)
- [ ] TC-4: Все 8 тестовых функций класса TestMainFunction используют `monkeypatch`
- [ ] TC-5: Все тесты в test_cli.py проходят успешно без ошибок `fixture 'monkeybot' not found`
- [ ] TC-6: CLI остается функциональным (`vlm-ocr-reader --help` работает)

## 6. Важные детали для Developer

### Специфичные риски:

**Использование grep для проверки:**
- **ВАЖНО:** Перед началом работы выполнить `grep -n "monkeybot" 02_src/tests/unit/test_cli.py`
- Это покажет точное количество и расположение всех вхождений
- После замены выполнить grep снова — должно быть 0 результатов
- Это гарантирует что ни одна функция не пропущена

**Почему `monkeybot` вызывает ошибку:**
- `monkeypatch` — это встроенный pytest fixture для модификации окружения/объектов
- `monkeybot` — не существует, pytest ищет fixture с таким именем и не находит
- Когда параметр называется `monkeybot`, pytest пытается найти `@pytest.fixture` с именем `monkeybot`
- Так как такого fixture нет, pytest падает с ошибкой: `fixture 'monkeybot' not found`
- Внутри функций используется `monkeypatch.setenv()` или `monkeypatch.delenv()`, но переменная называется `monkeybot` → `AttributeError: 'None' has no attribute 'setenv'`

**Признаки правильной замены:**
1. Параметр функции называется `monkeypatch` (не `monkeypatchbot`, не `monkeybot`)
2. Вызовы внутри функции используют `monkeypatch.setenv()` или `monkeypatch.delenv()`
3. Grep по `monkeybot` возвращает 0 результатов

**Чеклист для проверки:**

После внесения изменений проверить каждую из 8 функций:
```
1. test_main_success (строка 134) - параметр monkeypatch ✅
2. test_main_pdf_not_found (строка 168) - параметр monkeypatch [ИСПРАВИТЬ]
3. test_main_missing_api_key (строка 185) - параметр monkeypatch [ИСПРАВИТЬ]
4. test_main_custom_output_dir (строка 208) - параметр monkeypatch ✅
5. test_main_custom_dpi (строка 257) - параметр monkeypatch ✅
6. test_main_debug_logging (строка 301) - параметр monkeypatch ✅
7. test_main_keyboard_interrupt (строка 340) - параметр monkeypatch ✅
8. test_main_exception_handling (строка 363) - параметр monkeypatch ✅
```

**Команды для проверки:**

```bash
# До начала работы: показать все вхождения monkeybot
grep -n "monkeybot" 02_src/tests/unit/test_cli.py
# Ожидается: 2 строки (168, 185)

# После замены: проверить что все заменено
grep -n "monkeybot" 02_src/tests/unit/test_cli.py
# Ожидается: 0 результатов

# Проверить что monkeypatch используется в тестах
grep -n "monkeypatch" 02_src/tests/unit/test_cli.py | grep "def test_main"
# Ожидается: 8 строк (все 8 функций)

# Запустить тесты
pytest 02_src/tests/unit/test_cli.py -v
# Ожидается: все тесты PASS
```

**Вторичная проблема (logging тесты):**
Как отмечено в review_02.md, тесты `test_setup_logging_debug` и `test_setup_logging_warning` могут падать из-за того, что pytest переопределяет root logger. Это вторичная проблема по сравнению с `monkeybot`. Если после исправления `monkeybot` эти тесты все еще падают — можно их удалить или упростить (проверять только что setup_logging не вызывает exception).
