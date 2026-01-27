# Промпт для запуска Analyst - Задача 002

Ты — агент Analyst (см. .agents/analyst.md).

Прочитай:
- .agents/analyst.md
- AGENTS.md
- 00_docs/architecture/overview.md
- Все файлы из 00_docs/standards/common/
- Все файлы из 00_docs/standards/analyst/
- 01_tasks/002_vlm_processing/task_brief_01.md

Задача: Создай техническое задание в 01_tasks/002_vlm_processing/analysis_01.md

После завершения сформируй промпт для Developer.

---
**ВАЖНО:**
- Все reference файлы доступны в 02_src/_reference/
- API ключ для Gemini: GEMINI_API_KEY (передается через .env)
- Будем работать с реальным Gemini API как можно скорее
- VLM Client должен поддерживать retry (429, 500-599) и throttling (min_interval_s=0.6)
- VLM Agent должен реализовывать tool calling loop (max 10 итераций)
- DocumentProcessor должен поддерживать PDF и массив PNG как входные данные
