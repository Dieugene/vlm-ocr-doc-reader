# Промпт для Reviewer: Проверка исправления MockVLMAgent

## Контекст

Вы — агент Reviewer (см. .agents/reviewer.md). Ваша задача — провести техническую ревизию исправления бага в тестах.

## Задача

Проверить исправление ошибки в MockVLMAgent (tests/unit/test_full_description.py, строки 50-56).

## Описание проблемы

**Исходная проблема:** В MockVLMAgent порядок проверки промптов был неправильным — проверка "текст" срабатывала для PROMPT_STRUCTURE из-за того, что слово "структура" содержит подстроку "текст".

**Ожидаемое поведение:** MockVLMAgent должен возвращать разные ответы в зависимости от типа промпта:
- Для PROMPT_TEXT → text_response
- Для PROMPT_STRUCTURE → structure_response

## Что проверено

### Изменения в коде

**Файл:** `D:\_storage_cbr\020_docs_vision\08_vlm-ocr-doc-reader\tests\unit\test_full_description.py`

**Строки 50-56 (было):**
```python
# Return different responses based on prompt
if "plain text" in prompt.lower() or "текст" in prompt.lower():
    return {"text": self.text_response}
elif "structure" in prompt.lower() or "структура" in prompt.lower():
    return {"text": self.structure_response}
else:
    return {"text": ""}
```

**Строки 50-56 (стало):**
```python
# Return different responses based on prompt
# Check structure first before text (текст is contained in структура)
if "structure" in prompt.lower() or "структура" in prompt.lower():
    return {"text": self.structure_response}
elif "plain text" in prompt.lower() or "текст" in prompt.lower():
    return {"text": self.text_response}
else:
    return {"text": ""}
```

### Обоснование изменения

1. **Проблема:** Слово "структура" содержит подстроку "текст", поэтому проверка `if "текст" in prompt.lower()` срабатывала первой для PROMPT_STRUCTURE
2. **Решение:** Изменен порядок проверки — сначала проверяется более специфичное условие "structure"/"структура", затем более общее "plain text"/"текст"
3. **Добавлен комментарий:** "# Check structure first before text (текст is contained in структура)" объясняет причину порядка проверки

### Тестирование

**Команда для запуска тестов:**
```bash
pytest tests/unit/test_full_description.py -v
```

**Ожидаемый результат:** Все 16 тестов должны пройти успешно:
- test_initialization
- test_initialization_with_dpi
- test_execute_returns_document_data
- test_execute_extracts_text
- test_execute_extracts_structure
- test_execute_with_page_filter
- test_execute_tables_empty_in_v0_1_0
- test_parse_valid_json_structure
- test_parse_json_with_markdown_fence
- test_handle_invalid_json
- test_handle_malformed_headers
- test_filter_pages_with_pageinfo_objects
- test_filter_pages_returns_all_when_none
- test_extract_images_from_pageinfo
- test_extract_images_from_bytes
- test_clean_json_fence

## Что нужно проверить Reviewer

### 1. Корректность исправления
- [ ] Правильно ли определена причина проблемы?
- [ ] Корректно ли изменен порядок проверки?
- [ ] Достаточно ли добавленного комментария для понимания логики?
- [ ] Есть ли edge cases, которые не учтены?

### 2. Качество кода
- [ ] Следует ли код стандартам из 00_docs/standards/common/?
- [ ] Понятен ли код для будущей поддержки?
- [ ] Нет ли дублирования или избыточности?

### 3. Полнота тестирования
- [ ] Покрывают ли тесты все сценарии использования MockVLMAgent?
- [ ] Проверяют ли тесты оба типа промптов (PROMPT_TEXT и PROMPT_STRUCTURE)?
- [ ] Есть ли тесты, которые могут сломаться из-за этого изменения?

### 4. Документация
- [ ] Достаточно ли обновлен implementation_01.md?
- [ ] Понятно ли описание проблемы и решения?
- [ ] Есть ли неточности или упущения?

### 5. Риски
- [ ] Есть ли риск, что изменение сломает другие тесты?
- [ ] Есть ли риск, что изменение повлияет на интеграционные тесты?
- [ ] Нужно ли дополнительное тестирование?

## Формат отчета

Пожалуйста, предоставьте отчет в формате:

### Критерии приемки
- [Пройден/Не пройден] Критерий 1
- [Пройден/Не пройден] Критерий 2
...

### Найденные проблемы
1. **[Критичность]** Описание проблемы
   - Детали
   - Рекомендация

### Рекомендации
1. Рекомендация по улучшению
...

### Итог
[Готово к мержу/Требуются исправления/Требуется дополнительная ревизия]

## Дополнительная информация

**Связанные файлы:**
- `.agents/reviewer.md` — стандарты ревизии
- `00_docs/standards/common/` — общие стандарты кода
- `00_docs/standards/developer/` — стандарты разработки
- `01_tasks/004_operations/task_brief_01.md` — техническое задание
- `01_tasks/004_operations/analysis_01.md` — анализ задачи
- `01_tasks/004_operations/review_01.md` — результаты предыдущей ревизии
- `01_tasks/004_operations/implementation_01.md` — отчет о реализации (обновлен)
