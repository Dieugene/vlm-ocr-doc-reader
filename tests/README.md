# Тесты vlm-ocr-doc-reader

Все тесты в этом проекте - **интеграционные с реальным API**.

## Структура

```
tests/
├── integration/                    # Интеграционные тесты с реальным API
│   ├── test_full_description_api.py
│   ├── test_full_description_with_processor.py
│   └── test_vlm_client_real_api.py
└── test_core/                      # Unit тесты для модулей
    ├── test_preprocessing.py
    ├── test_state.py
    ├── test_vlm_client.py
    ├── test_vlm_agent.py
    ├── test_ocr_client.py
    ├── test_ocr_tool.py
    └── test_processor.py
```

## Интеграционные тесты

Требуют `.env` файл с API ключами:
```bash
GEMINI_API_KEY=your_key_here
```

### Запуск интеграционных тестов:

```bash
# Все интеграционные тесты
pytest tests/integration/ -v

# Только с DocumentProcessor
pytest tests/integration/test_full_description_with_processor.py -v

# Только VLM клиент
pytest tests/integration/test_vlm_client_real_api.py -v
```

## Сквозной тест

Для быстрой проверки всего пайплайна:

```bash
python run_e2e_test.py
```

Этот скрипт:
1. Создает тестовый PDF
2. Обрабатывает через DocumentProcessor
3. Выполняет FullDescriptionOperation
4. Показывает результаты
