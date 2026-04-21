# vlm-ocr-doc-reader

Python-пакет для обработки документов через Vision Language Model и OCR. VLM (Qwen `qwen3-vl-flash` через DashScope) читает структуру и текст; OCR (Qwen `qwen-vl-plus`) точечно извлекает идентификаторы и числа. Оба канала используют один API-ключ DashScope.

## Установка

```bash
git clone https://github.com/your-org/vlm-ocr-doc-reader.git
cd vlm-ocr-doc-reader
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

Ключи API через `.env` в корне проекта (VLM и OCR работают через один DashScope-ключ):

```
DASHSCOPE_API_KEY=...
# либо эквивалент
QWEN_API_KEY=...
```

## Использование

### API

`DocumentReader` — единая точка входа. Workspace mode персистит состояние в `{stem}_{hash6}/` (имя файла + 6 hex SHA256 содержимого); memory mode ничего не сохраняет.

```python
from vlm_ocr_doc_reader import DocumentReader

reader = DocumentReader.open("contract.pdf", workspace="./workspace")

reader.scan()                       # Level 0 — VLM: текст + структура + OCR Registry
reader.resolve(pages=[5, 7])        # Level 1 — OCR по записям Registry
# reader.verify(pages=[5])          # Level 2 — интерфейс-заглушка

data = reader.get_document_data()   # DocumentData(text, structure, tables)
```

Без workspace:

```python
reader = DocumentReader.open("document.pdf")
reader.scan()
reader.resolve()
print(reader.get_document_data().text)
```

Legacy API (монолитный three-pass через VLM tool calling):

```python
from pathlib import Path
from vlm_ocr_doc_reader import DocumentProcessor, FullDescriptionOperation

processor = DocumentProcessor(source=Path("document.pdf"))
data = FullDescriptionOperation(processor).execute()
```

### CLI

```bash
vlm-ocr-reader scan document.pdf --workspace ./ws
vlm-ocr-reader resolve document.pdf --workspace ./ws --pages 1,3-5
vlm-ocr-reader verify document.pdf --workspace ./ws      # stub
vlm-ocr-reader full-description document.pdf            # scan + resolve all
```

`--pages` принимает диапазоны: `1,2,5-7`. Без `--workspace` — memory mode.

## Resolution Levels

| Level | Команда | VLM | OCR | Примечание |
|-------|---------|-----|-----|------------|
| 0 | `scan` | да | нет | VLM отдаёт текст + OCR Registry как структурированные данные |
| 1 | `resolve` | нет | да | `DocumentReader` сам итерирует Registry и вызывает OCR |
| 2 | `verify` | — | — | Интерфейс есть, стратегия majority voting не реализована |

`OCR Registry` — персистентный список целей извлечения (`page_num`, `entity_id`, `prompt`, `value`, `resolution`). Создаётся при `scan`, заполняется при `resolve`.

Подробнее — [overview.md](00_docs/architecture/overview.md), [ADR 001](00_docs/architecture/decision_001_resolution_levels.md).

## Ограничения

- VLM только Qwen (`qwen3-vl-flash`), OCR только Qwen (`qwen-vl-plus`). Базовые классы `BaseVLMClient`/`BaseOCRClient` допускают другие провайдеры, но реализаций нет.
- `verify()` — интерфейс без стратегии majority voting.
- DPI рендеринга жёстко 150.
- `DocumentData.tables` всегда пуст.

## Лицензия

MIT. См. `LICENSE`.

[English version](README_EN.md)
