# vlm-ocr-doc-reader

Python package for document processing via Vision Language Models and OCR. VLM reads structure and text; OCR extracts identifiers and numbers with precision.

## Installation

```bash
git clone https://github.com/your-org/vlm-ocr-doc-reader.git
cd vlm-ocr-doc-reader
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

API keys via `.env` at project root:

```
GEMINI_API_KEY=...
QWEN_API_KEY=...
```

## Usage

### API

`DocumentReader` is the single entry point. Workspace mode persists state under `{stem}_{hash6}/` (filename + 6 hex SHA256 of content); memory mode persists nothing.

```python
from vlm_ocr_doc_reader import DocumentReader

reader = DocumentReader.open("contract.pdf", workspace="./workspace")

reader.scan()                       # Level 0 — VLM: text + structure + OCR Registry
reader.resolve(pages=[5, 7])        # Level 1 — OCR from Registry entries
# reader.verify(pages=[5])          # Level 2 — interface stub

data = reader.get_document_data()   # DocumentData(text, structure, tables)
```

Without workspace:

```python
reader = DocumentReader.open("document.pdf")
reader.scan()
reader.resolve()
print(reader.get_document_data().text)
```

Legacy API (monolithic three-pass via VLM tool calling):

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

`--pages` accepts ranges: `1,2,5-7`. Without `--workspace` — memory mode.

## Resolution Levels

| Level | Command | VLM | OCR | Note |
|-------|---------|-----|-----|------|
| 0 | `scan` | yes | no | VLM returns text + OCR Registry as structured data |
| 1 | `resolve` | no | yes | `DocumentReader` iterates Registry and calls OCR directly |
| 2 | `verify` | — | — | Interface exists; majority-voting strategy not implemented |

`OCR Registry` is a persistent list of extraction targets (`page_num`, `entity_id`, `prompt`, `value`, `resolution`). Created during `scan`, populated during `resolve`.

Details — [overview.md](00_docs/architecture/overview.md), [ADR 001](00_docs/architecture/decision_001_resolution_levels.md).

## Limitations

- VLM: Gemini only; OCR: Qwen only.
- `verify()` is an interface stub without strategy.
- Rendering DPI is hardcoded to 150.
- `DocumentData.tables` is always empty.

## License

MIT. See `LICENSE`.

[Russian version](README.md)
