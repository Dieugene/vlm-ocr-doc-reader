# Test Suite for VLM OCR Document Reader

## Structure

```
tests/
├── unit/                   # Unit tests (mock everything)
│   └── test_full_description.py
├── integration/            # Integration tests (real API)
│   └── test_full_description_api.py
└── README.md
```

## Running Tests

### Prerequisites

1. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env and add your GEMINI_API_KEY
   ```

### Run Unit Tests

Unit tests use mocks and don't require API keys:

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_full_description.py -v

# Run with coverage
pytest tests/unit/ --cov=vlm_ocr_doc_reader --cov-report=html
```

### Run Integration Tests

Integration tests require real API keys:

```bash
# Run all integration tests
pytest tests/integration/ -v -m integration

# Run specific integration test
pytest tests/integration/test_full_description_api.py -v -s
```

**Note:** Integration tests are skipped if `GEMINI_API_KEY` is not set in `.env`.

### Run All Tests

```bash
# Run everything (unit + integration)
pytest tests/ -v

# Skip integration tests
pytest tests/ -v -m "not integration"
```

## Test Coverage

- **Unit tests**: Cover logic with mocked dependencies
- **Integration tests**: Verify contract with real Gemini API
- **Contract tests**: Ensure compatibility with project 07

## Current Test Coverage

### Unit Tests (test_full_description.py)

- Initialization with/without DPI
- DocumentData return type
- Text extraction
- Structure extraction
- Page filtering
- JSON parsing with/without markdown fences
- Error handling (invalid JSON, malformed headers)
- Image extraction from PageInfo and bytes

### Integration Tests (test_full_description_api.py)

- Text extraction from real PDF
- Structure extraction from real PDF
- Page filtering
- Contract compliance with project 07
- Tables empty in v0.1.0

## Adding New Tests

When adding new operations:

1. Create unit test in `tests/unit/`
2. Create integration test in `tests/integration/`
3. Mock DocumentProcessor contract
4. Test both success and error cases
5. Verify contract compliance

## Troubleshooting

### Tests fail with import errors

Make sure `PYTHONPATH` includes `02_src`:

```bash
export PYTHONPATH="${PYTHONPATH}:02_src"
# Or on Windows:
set PYTHONPATH=%PYTHONPATH%;02_src
```

### Integration tests skipped

Check that `.env` file exists and contains valid `GEMINI_API_KEY`.

### PDF rendering fails

Integration tests create a simple test PDF automatically. If `reportlab` is not installed, tests will be skipped.

Install it manually if needed:

```bash
pip install reportlab
```
