# Тесты vlm-ocr-doc-reader

Смесь unit-тестов (мок-storage, парсинг, рендер) и интеграционных тестов с реальным API (Qwen VLM + Qwen OCR через DashScope).

## Структура

```
tests/
├── conftest.py                    # load .env + file logging в 04_logs/
├── test_core/                     # Unit + интеграции ядра
│   ├── test_state.py
│   ├── test_ocr_client.py
│   ├── test_ocr_integration.py
│   ├── test_ocr_tool.py
│   ├── test_processor.py
│   └── test_vlm_agent.py
├── test_integration/
│   ├── test_base_utilities.py
│   ├── test_full_description_with_processor.py
│   └── test_full_pipeline.py
├── test_preprocessing/
│   └── test_renderer.py
├── test_utils/
│   └── test_normalization.py
└── unit/
    └── test_cli.py
```

## API ключ

Тесты, зависящие от VLM/OCR, требуют `.env` в корне проекта:

```bash
DASHSCOPE_API_KEY=sk-...    # либо QWEN_API_KEY (алиас)
```

Тесты пропускаются (`pytest.skip`) если ключ не задан или это dummy (`test`, `test-key`, `test-api-key-123`).

## Запуск

```bash
pytest 02_src/tests/ -v
pytest 02_src/tests/test_integration/ -v              # только интеграции
pytest 02_src/tests/test_integration/test_full_pipeline.py -v
```
