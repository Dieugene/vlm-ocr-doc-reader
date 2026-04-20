# Технический план: Task 015 — Verify interface only

## 1. Анализ задачи

Зафиксировать публичный API Level 2 (`verify`) в DocumentReader без реализации стратегии majority voting. Стратегия верификации **отложена** (ADR-001). Задача — стабильный интерфейс, контракты, безопасная заглушка для последующих экспериментов.

**Границы:**
- Делает: API verify, обработка пустых/невалидных страниц, подготовительные поля в state, явные TODO об отложенной стратегии.
- Не делает: N-параллельные OCR-вызовы, voting algorithm, новые тестовые модули.

## 2. Текущее состояние

### reader.py
- `verify(pages=None)` уже есть (строки 253–256): вызывает `_normalize_pages`, логирует, возвращает.
- Docstring ссылается на "011" вместо "015".
- `_normalize_pages` обрабатывает пустые/невалидные диапазоны (возвращает `[]`, логирует предупреждения).

### state.py
- `OCRRegistryEntry` уже содержит `verified: bool = False` и `confidence: Optional[str] = None`.
- `PageResolution` включает `"verified"`.
- Сериализация/десериализация registry поддерживает эти поля.

### Чего нет
- `VerifyResult` TypedDict из task_brief.
- Явного TODO/ограничения о том, что voting strategy отложена.
- Обновлённого docstring для `verify()` по ADR-001.

## 3. Предлагаемое решение

### 3.1. Общий подход

Оставить `verify()` как заглушку с чётким контрактом: принимает страницы, нормализует их, при пустом списке — ранний выход без изменения состояния. Добавить `VerifyResult` как контракт для будущей реализации. Явно задокументировать отложенную стратегию.

### 3.2. Компоненты

#### DocumentReader.verify()
- **Назначение:** Публичный метод Level 2. В v0.2.0 — только интерфейс, без вызовов OCR.
- **Интерфейс:** `verify(pages: Optional[Iterable[int]] = None) -> None`
- **Логика:**
  1. Нормализовать страницы через `_normalize_pages(pages)`.
  2. Если `page_list` пуст — логировать, выйти.
  3. Иначе — логировать страницы и выйти (заглушка). Состояние не менять.
- **Зависимости:** `_normalize_pages`, logger.

#### VerifyResult (TypedDict)
- **Назначение:** Контракт результата верификации для будущей реализации.
- **Расположение:** `state.py` или `schemas/` (рядом с другими типами).
- **Поля:** `page_num`, `entity_id`, `verified`, `confidence` (все optional через `total=False`).

### 3.3. Структуры данных

```
VerifyResult (TypedDict, total=False):
  - page_num: int
  - entity_id: str
  - verified: bool
  - confidence: str
```

### 3.4. Изменения в существующем коде

| Файл | Изменение |
|------|-----------|
| `reader.py` | Обновить docstring `verify()`, добавить TODO о voting strategy |
| `state.py` или `schemas/` | Добавить `VerifyResult` TypedDict |

### 3.5. Явные ограничения (AC-5)

В docstring `verify()` и/или в комментарии в теле метода:
- Указать, что majority voting / confidence scoring отложены до экспериментов (ADR-001).
- Ссылка на задачу 015.

## 4. План реализации

1. Добавить `VerifyResult` TypedDict в `state.py` (экспорт в `__init__.py` при необходимости).
2. Обновить `DocumentReader.verify()` в `reader.py`:
   - Docstring: Level 2 interface only, no majority-voting strategy in v0.2.0.
   - При пустом `page_list` после нормализации — ранний выход.
   - TODO-комментарий о том, что voting strategy отложена (ADR-001, Task 015).
3. Убедиться, что `verify()` не изменяет state (уже так — только логирование).

## 5. Технические критерии приемки

- [ ] TC-1: `DocumentReader.verify(pages=...)` — публичный метод с корректной сигнатурой.
- [ ] TC-2: Пустой/невалидный диапазон страниц — ранний выход, state не меняется.
- [ ] TC-3: `verify()` не ломает scan/resolve (не изменяет registry, page_states).
- [ ] TC-4: Поля `verified`, `confidence` в `OCRRegistryEntry` остаются доступны (уже есть).
- [ ] TC-5: В коде есть явный TODO/ограничение о том, что voting strategy отложена.

## 6. Важные детали для Developer

- **Не создавать** новые тестовые модули. Использовать существующие тесты при необходимости.
- **VerifyResult** — только объявление типа, не используется в логике verify() в этой задаче.
- `_normalize_pages` уже обрабатывает `None` (все страницы), невалидные значения (skip + warning), выход за диапазон (skip + warning).
- Стратегия verify (N параллельных OCR, majority voting) **отложена** — не реализовывать.
