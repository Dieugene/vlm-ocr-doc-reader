---
# Промпт для запуска Developer

Скопируй этот текст и вставь в новый чат Claude:

---

Ты — агент Developer (см. .agents/developer.md).

Прочитай:
- .agents/developer.md
- AGENTS.md
- Все файлы из 00_docs/standards/common/
- Все файлы из 00_docs/standards/developer/
- 01_tasks/002_vlm_processing/task_brief_01.md
- 01_tasks/002_vlm_processing/analysis_02.md
- 01_tasks/002_vlm_processing/review_01.md

Задача: Реализуй исправления согласно техническому заданию analysis_02.md.

Ключевые исправления:
1. VLM Client retry логика - НЕ выполнять retry на 4xx (кроме 429)
2. DocumentProcessor PageInfo - использовать поле index вместо page_num
3. Тесты DocumentProcessor - исправить мокание os.getenv и load_dotenv
4. Добавить тест throttling на стандартном значении 0.6s
5. Создать интеграционные тесты с реальным API (с пропуском если нет ключа)

После завершения сформируй промпт для Reviewer.

---
