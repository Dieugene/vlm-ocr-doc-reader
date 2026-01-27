# Промпт для запуска Analyst - Задача 003

Ты — агент Analyst (см. .agents/analyst.md).

Прочитай:
- .agents/analyst.md
- AGENTS.md
- 00_docs/architecture/overview.md
- Все файлы из 00_docs/standards/common/
- Все файлы из 00_docs/standards/analyst/
- 01_tasks/003_ocr_support/task_brief_01.md

Задача: Создай техническое задание в 01_tasks/003_ocr_support/analysis_01.md

После завершения сформируй промпт для Developer.

---
**ВАЖНО:**
- Все reference файлы доступны в 02_src/_reference/
- API ключ для Qwen: QWEN_API_KEY (передается через .env)
- Будем работать с реальным Qwen API как можно скорее
- OCR Client должен поддерживать retry logic
- OCR Tool должен интегрироваться с VLM Agent (через function calling)
- Используй normalize_ocr_digits() из Задачи 001 для пост-обработки
