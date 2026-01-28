# vlm-ocr-doc-reader

Universal Python package for document processing via Vision Language Models (VLM) and OCR. Hybrid approach — VLM for context understanding + OCR for precise data extraction.

## Overview

This package is designed for projects requiring:
- Extraction of structured data from PDFs/images
- Analysis of large documents (hundreds of pages)
- Precise extraction of numbers/identifiers (OCR)
- Universal interface for different VLM/OCR models

## Key Features

- **Hybrid Approach:** VLM for context understanding + OCR for precision
- **Universal Clients:** BaseVLMClient and BaseOCRClient with multiple implementations
- **Operations-based API:** Flexible operations for different document analysis tasks
- **State Management:** Automatic caching and result persistence
- **CLI Interface:** Quick document processing from command line

## Installation

### From GitHub

Clone the repository and install locally:

```bash
# Clone the repository
git clone https://github.com/your-org/vlm-ocr-doc-reader.git
cd vlm-ocr-doc-reader

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in editable mode
pip install -e .
```

### Dependencies

Core dependencies are installed automatically:
- requests>=2.31.0
- python-dotenv>=1.0.0
- Pillow>=10.0.0
- pymupdf>=1.23.0
- PyYAML>=6.0.0
- pydantic>=2.0.0

## Quick Start

### Basic Usage

```python
from pathlib import Path
from vlm_ocr_doc_reader import (
    GeminiVLMClient,
    VLMConfig,
    DocumentProcessor,
    ProcessorConfig,
    FullDescriptionOperation
)

# 1. Configure VLM client
vlm_config = VLMConfig(api_key="your-gemini-api-key")
vlm_client = GeminiVLMClient(vlm_config)

# 2. Create processor with PDF file
processor = DocumentProcessor(
    source=Path("report.pdf"),
    vlm_client=vlm_client
)

# 3. Create operation and execute
operation = FullDescriptionOperation(processor)
result = operation.execute()

# 4. Access results
print(f"Text length: {len(result.text)} chars")
print(f"Headers found: {len(result.structure['headers'])}")
for header in result.structure['headers'][:5]:
    print(f"  Level {header['level']}: {header['title']} (page {header['page']})")
```

### With State Persistence

```python
from pathlib import Path
from vlm_ocr_doc_reader import (
    GeminiVLMClient,
    VLMConfig,
    DocumentProcessor,
    ProcessorConfig,
    FullDescriptionOperation
)

# Configure with state directory for caching
vlm_config = VLMConfig(api_key="your-api-key")
processor_config = ProcessorConfig(
    state_dir=Path("./output"),
    render_dpi=150
)

processor = DocumentProcessor(
    source=Path("large_document.pdf"),
    vlm_client=vlm_client,
    config=processor_config
)

# Results will be automatically saved to ./output/results/
operation = FullDescriptionOperation(processor)
result = operation.execute()

# Output structure:
# ./output/
# ├── cache/
# │   ├── pages/page_001.png, page_002.png, ...
# │   └── vlm_responses/response_full_desc.json
# ├── results/
# │   └── full_description.yaml
# └── logs/
#     └── vlm_ocr.log
```

### From Array of PNG Images

```python
from pathlib import Path
from vlm_ocr_doc_reader import GeminiVLMClient, VLMConfig, DocumentProcessor, FullDescriptionOperation

# Load PNG images as bytes
images = [
    Path("page1.png").read_bytes(),
    Path("page2.png").read_bytes(),
    Path("page3.png").read_bytes(),
]

# Process from images
vlm_config = VLMConfig(api_key="your-api-key")
vlm_client = GeminiVLMClient(vlm_config)

processor = DocumentProcessor(source=images, vlm_client=vlm_client)
operation = FullDescriptionOperation(processor)
result = operation.execute()
```

### Using .env File

Create a `.env` file in your project root:

```env
GEMINI_API_KEY=your-gemini-api-key-here
QWEN_API_KEY=your-qwen-api-key-here
```

Then use in your code:

```python
from pathlib import Path
from dotenv import load_dotenv
from vlm_ocr_doc_reader import DocumentProcessor, ProcessorConfig, FullDescriptionOperation

# Load environment variables
load_dotenv()

# API key will be automatically loaded from GEMINI_API_KEY
# No need to pass vlm_client - it's created automatically!
processor = DocumentProcessor(
    source=Path("document.pdf"),
    config=ProcessorConfig(state_dir=Path("./output"))
)

operation = FullDescriptionOperation(processor)
result = operation.execute()
```

## CLI Interface

Quick document processing from command line:

```bash
# Basic usage
python -m vlm_ocr_doc_reader.cli document.pdf

# With custom output directory
python -m vlm_ocr_doc_reader.cli document.pdf --output-dir ./my_results

# With custom DPI for rendering
python -m vlm_ocr_doc_reader.cli document.pdf --dpi 200 --output-dir ./output

# With debug logging
python -m vlm_ocr_doc_reader.cli document.pdf --log-level DEBUG
```

**Note:** Make sure `GEMINI_API_KEY` is set in `.env` file or environment variables before running CLI.

## Module Structure

```
vlm_ocr_doc_reader/
├── core/              # Core processing components
│   ├── processor.py   # DocumentProcessor
│   ├── vlm_client.py  # VLM clients (Gemini)
│   ├── vlm_agent.py   # VLMAgent with tool calling
│   ├── ocr_client.py  # OCR clients (Qwen)
│   ├── ocr_tool.py    # OCRTool wrapper
│   └── state.py       # State persistence (Memory/Disk)
├── operations/        # Document operations
│   ├── base.py        # BaseOperation abstract class
│   └── full_description.py  # FullDescriptionOperation
├── schemas/           # Data schemas
│   ├── config.py      # Config classes (VLMConfig, ProcessorConfig, etc.)
│   ├── document.py    # DocumentData, HeaderInfo, TableInfo
│   └── common.py      # PageInfo, ClusterInfo, TriageResult
├── preprocessing/     # Preprocessing utilities
│   └── renderer.py    # PDF to PNG renderer
├── utils/             # Utilities
│   └── normalization.py  # OCR digit normalization
└── cli.py             # Command-line interface
```

## Public API

### Core Classes
- `DocumentProcessor` - Main document processor
- `BaseVLMClient`, `GeminiVLMClient` - VLM clients
- `VLMAgent` - VLM agent with tool calling loop
- `BaseOCRClient`, `QwenOCRClient` - OCR clients
- `OCRTool` - OCR tool wrapper

### Operations
- `BaseOperation` - Base operation class
- `FullDescriptionOperation` - Extract full text and structure

### Schemas
- `ProcessorConfig`, `VLMConfig`, `OCRConfig`, `RenderConfig` - Configuration
- `DocumentData`, `HeaderInfo`, `TableInfo` - Document data
- `PageInfo`, `ClusterInfo`, `TriageResult` - Common data structures

## Documentation

- [Architecture Overview](00_docs/architecture/overview.md) - System architecture and design
- [Implementation Plan](00_docs/architecture/implementation_plan.md) - Implementation details
- [Backlog](00_docs/backlog.md) - Development tasks and status

## Development Status

:warning: **Version 0.1.0** - Early release with core functionality

**Implemented:**
- ✅ FullDescriptionOperation (text + structure extraction)
- ✅ State management (Memory + Disk backends)
- ✅ CLI interface
- ✅ PDF rendering and OCR normalization

**Planned:**
- ⏳ ClusteringOperation (semantic page grouping)
- ⏳ TriageOperation (find pages by criteria)
- ⏳ ExtractionOperation (field extraction)
- ⏳ Table classification (NUMERIC vs TEXT_MATRIX)

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! This project uses AI-assisted development with clear agent roles. See `.agents/` directory for details.

---

[Русская версия](README.md)
