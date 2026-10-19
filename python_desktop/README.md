# AxAI — Нативное десктопное приложение на Python + PySide6

Проект организован по модульной архитектуре (в соответствии с архитектурным ревью):

## Структура пакетов `python_desktop/`
- **`main.py`** — главное окно нативного десктопного приложения (`PySide6.QtWidgets` + встроенный рендерер формул `LatexLecturePreview`).
- **`db/repositories.py`** — слой репозиториев SQLite (`DatabaseManager`, `LectureRepository`, `TaskRepository`, `RevisionRepository`, `ProfileRepository`, `SettingsRepository`):
  - Точечные транзакционные `INSERT ... ON CONFLICT(id) DO UPDATE` вместо полного `DELETE FROM lectures/tasks`.
  - Полнотекстовый поиск **SQLite FTS5** (`lectures_fts`) по заголовкам, предметам и конспектам.
  - Таблица `lecture_revisions` для сохранения истории версий конспекта при каждом нажатии **«✨ Сделать подробнее (ИИ)»** и возврата к лаконичной версии в 1 клик.
  - Отдельное хранение сжатой квадратной аватарки пользователя (`256×256 PNG` в `student_profile.avatar_blob`), не затрагивающее системную иконку приложения AxAI.
- **`ml/engine.py`** — единые интерфейсы `BaseTranscriber` и `BaseSummarizer` с двумя реализациями:
  - **Локальная (100% офлайн):** `FasterWhisperTranscriber` (с Silero VAD и поддержкой лекций >1.5 ч) + `LocalLlmSummarizer` (Ollama `qwen2.5:7b` с **Map-Reduce** конспектированием по блокам и строгой JSON-схемой для дедлайнов и формул).
  - **Облачная:** `GeminiCloudTranscriber` + `GeminiCloudSummarizer` (`gemini-2.5-flash` со строгой `response_schema`).
  - **`HardwareInspector`** — автопроверка CPU, RAM, NVIDIA CUDA / Apple Metal (MPS) и локального сервера Ollama с рекомендацией оптимальной модели.
- **`export/exporters.py`** — рендеринг формул $\LaTeX$ (поддержка локального KaTeX в `~/AxAI_Storage/katex/` без CDN + встроенный 100% офлайн математический типограф), экспорт в `.PDF`, `.MD` (UTF-8 BOM) и `.TEX`.
- **`ui/latex_preview.py`** — виджет `LatexLecturePreview` (`QWebEngineView` с автоматическим откатом на `QTextBrowser`), генератор неизменной иконки приложения `draw_fixed_app_icon_pixmap()` и функция обрезки пользовательской аватарки `crop_and_compress_avatar_square(256)`.

## Запуск нативного десктопного приложения
```bash
cd python_desktop
pip install -r requirements.txt
python main.py
```
