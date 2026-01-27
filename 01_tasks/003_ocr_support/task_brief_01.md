# Задача 003: OCR support

## Что нужно сделать

Реализовать поддержку OCR для извлечения данных:
1. **OCR Client** - Qwen VL API клиент с retry logic
2. **OCR Tool** - агентская обертка для использования через VLM Agent

## Зачем

OCR Client обеспечивает точное извлечение числовых данных и идентификаторов, OCR Tool интегрирует его в agentic подход через function calling. Это позволяет VLM вызывать OCR для точного извлечения данных.

## Acceptance Criteria

- [ ] QwenOCRClient.extract() выполняет запросы к Qwen API с retry logic
- [ ] OCRTool.to_tool_definition() возвращает корректное tool definition для VLM
- [ ] OCRTool.execute() выполняет OCR запрос с пост-обработкой (нормализация)
- [ ] Unit тесты для OCR Client (mock API)

## Контекст

### Implementation Plan: Задача 3 (OCR support)

```python
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class OCRConfig:
    """Конфигурация OCR клиента."""
    api_key: str
    model: str = "qwen-vl-plus"
    timeout_sec: int = 60
    max_retries: int = 3
    backoff_base: float = 1.5

class BaseOCRClient:
    """Базовый интерфейс OCR клиента."""

    def extract(
        self,
        image: bytes,
        prompt: str,
        page_num: int
    ) -> Dict[str, Any]:
        """Извлечь данные с изображения.

        Returns:
            {
                "status": "ok" | "no_data" | "error",
                "value": str,  # Извлеченное значение
                "context": str,
                "explanation": str
            }
        """
        raise NotImplementedError

class QwenOCRClient(BaseOCRClient):
    """Qwen VL OCR клиент (OpenAI-compatible)."""
    pass
```

**Reference:** `02_src/_reference/qwen_client.py`

**Формат ответа:**
```
ЗНАЧЕНИЕ: <значение>
КОНТЕКСТ: <фрагмент текста>
ПОЯСНЕНИЕ: <объяснение>
```

### OCR Tool

```python
class OCRTool:
    """OCR Tool - агентская сущность для вызова OCR.

    Используется VLM Agent через tools.
    """

    def __init__(self, ocr_client: BaseOCRClient):
        self.ocr_client = ocr_client

    def to_tool_definition(self) -> Dict:
        """Определение tool для VLM."""
        return {
            "function_declarations": [
                {
                    "name": "ask_ocr",
                    "description": "Извлечь данные с изображения",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_num": {"type": "integer"},
                            "prompt": {"type": "string"}
                        },
                        "required": ["page_num", "prompt"]
                    }
                }
            ]
        }

    def execute(self, page_num: int, prompt: str, image: bytes) -> Dict:
        """Выполнить OCR запрос.

        Использует normalize_ocr_digits() для пост-обработки.
        """
        result = self.ocr_client.extract(image, prompt, page_num)

        # Пост-обработка для числовых полей
        if result["status"] == "ok":
            normalized = normalize_ocr_digits(result["value"])
            if normalized:
                result["value_normalized"] = normalized

        return result
```

**OCR нормализация (из Задачи 001):**
```python
def normalize_ocr_digits(raw: str, expected_length: Optional[int] = None) -> Optional[str]:
    """OCR нормализация для числовых полей."""
    cleaned = (
        str(raw)
        .replace("O", "0").replace("o", "0")
        .replace("l", "1").replace("I", "1")
        .replace("S", "5").replace("B", "8")
    )
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    if expected_length and len(digits) != expected_length:
        return None
    return digits or None
```

### Критерии готовности модуля:

- OCR Client возвращает валидные данные от Qwen API
- OCR Tool интегрируется с VLM Agent (через to_tool_definition)
- Пост-обработка (нормализация) работает корректно
- Интеграционные тесты проходят (с реальным API)
- Логирование настроено

### Существующий код для reference:

- `02_src/_reference/qwen_client.py` - Qwen OCR клиент из 05_a_reports_ETL_02
- `02_src/_reference/tools.py` - OCR нормализация (используется из Задачи 001)

### Другие ссылки:

- `00_docs/architecture/implementation_plan.md` - полный план реализации (см. Задачу 3)
- `00_docs/backlog.md` - реестр задач

### Конфигурация через .env

API ключ для Qwen API:
- `QWEN_API_KEY` - обязательно для тестов с реальным API

**ВАЖНО:** Все разработчики обязаны работать в виртуальном окружении. Установку библиотек выполнять через pip/poetry в venv.
