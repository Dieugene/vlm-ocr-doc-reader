# Промпт для запуска Analyst - Задача 004

Ты — агент Analyst (см. .agents/analyst.md).

Прочитай:
- .agents/analyst.md
- AGENTS.md
- 00_docs/architecture/overview.md
- Все файлы из 00_docs/standards/common/
- Все файлы из 00_docs/standards/analyst/
- 01_tasks/004_operations/task_brief_01.md

Задача: Создай техническое задание в 01_tasks/004_operations/analysis_01.md

После завершения сформируй промпт для Developer.

---
**ВАЖНО:**
- Все reference файлы доступны в 02_src/_reference/
- API ключ для Gemini: GEMINI_API_KEY (передается через .env)
- Будем работать с реальным Gemini API как можно скорее
- FullDescriptionOperation - контракт с проектом 07_agentic-doc-processing
- DocumentData должен соответствовать схеме из overview.md
- В v0.1.0 tables оставляем пустым (реализация в будущих версиях)
- Интеграционные тесты с реальным API обязательны
