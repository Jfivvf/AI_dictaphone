import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QThread, Signal
from export.exporters import repair_corrupted_latex
from ml.engine import (
    AiUnavailableError,
    CancelledError,
    LectureContext,
    create_summarizer,
    create_transcriber,
)
from model_setup import SetupError, run_setup
from pdf_importer import DocumentError, keyword_tasks_and_formulas, read_document
from task_detection import extract_structured_tasks, extract_tasks, merge_tasks


class TranscriptionWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        audio_path: str,
        title: str = "",
        subject: str = "",
        lecturer: str = "",
        ai_context: str = "",
        settings: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.audio_path = audio_path
        self.title = title or "Запись"
        self.subject = subject or "Дисциплина"
        self.ctx = LectureContext(
            subject=subject, title=title, lecturer=lecturer, notes=ai_context
        )
        self.settings = settings or {}

    def _emit_progress(self, pct: int, msg: str) -> None:
        self.progress.emit(pct, msg)

    def run(self) -> None:
        cancel = self.isInterruptionRequested
        started = time.monotonic()
        try:
            self.progress.emit(8, "Подготовка...")

            try:
                transcriber = create_transcriber(self.settings)
                tr = transcriber.transcribe(
                    self.audio_path, self.ctx, progress_cb=self._emit_progress, cancel_cb=cancel
                )
            except CancelledError:
                self.error.emit("Обработка отменена. Аудиозапись сохранена.")
                return
            except AiUnavailableError as err:
                self.error.emit(f"{err}\nАудиозапись сохранена: {self.audio_path}")
                return
            except Exception as err:
                self.error.emit(f"Не удалось распознать речь: {err}\nАудиозапись сохранена: {self.audio_path}")
                return

            asr_done = time.monotonic()
            full_text = tr.get("full_text", "").strip()
            segments = tr.get("segments", [])

            summary_md = ""
            tasks: List[Dict[str, Any]] = []
            formulas: List[Dict[str, Any]] = []
            warning = ""

            if full_text:
                try:
                    summarizer = create_summarizer(self.settings)
                    res = summarizer.summarize_lecture(
                        full_text or self.ctx.notes,
                        self.ctx,
                        progress_cb=self._emit_progress,
                        cancel_cb=cancel,
                    )
                    summary_md = repair_corrupted_latex(res.get("summary_markdown", ""))
                    tasks = res.get("tasks", [])
                    formulas = res.get("formulas", [])
                except CancelledError:
                    warning = "Построение конспекта отменено. Сохранена только стенограмма."
                except AiUnavailableError as err:
                    warning = f"Конспект не построен: {err}"
                except Exception as err:
                    warning = f"Конспект не построен: {err}"

            if not summary_md:
                notes = f"\n\n### Контекст студента\n{self.ctx.notes}\n" if self.ctx.notes else ""
                summary_md = (
                    f"## {self.title}\n\n**Предмет:** {self.subject}{notes}\n\n"
                    f"### Стенограмма\n\n{full_text or 'Речь не распознана.'}"
                )
                if self.settings.get("auto_extract_tasks", True):
                    tasks = extract_tasks(full_text)

            finished_at = time.monotonic()
            self.progress.emit(100, "Готово!")
            self.finished.emit({
                "timing": {"asr_sec": asr_done - started, "summary_sec": finished_at - asr_done},
                "text": summary_md,
                "raw_transcript": full_text,
                "segments": segments,
                "tasks": tasks[:10],
                "formulas": formulas,
                "warning": warning,
            })
        except Exception as err:
            self.error.emit(str(err))


class ExpandLectureWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        title: str,
        subject: str,
        current_markdown: str,
        raw_transcript: str = "",
        ai_context: str = "",
        lecturer: str = "",
        settings: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.ctx = LectureContext(subject=subject, title=title, lecturer=lecturer, notes=ai_context)
        self.current_markdown = current_markdown
        self.raw_transcript = raw_transcript
        self.settings = settings or {}

    def run(self) -> None:
        try:
            self.progress.emit(8, "Анализ конспекта, стенограммы и контекста...")
            summarizer = create_summarizer(self.settings)
            expanded = summarizer.expand_lecture(
                self.current_markdown,
                self.raw_transcript,
                self.ctx,
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
                cancel_cb=self.isInterruptionRequested,
            )
            self.finished.emit(repair_corrupted_latex(expanded))
        except CancelledError:
            self.error.emit("Расширение отменено.")
        except AiUnavailableError as err:
            self.error.emit(str(err))
        except Exception as err:
            self.error.emit(str(err))


class ImportDocumentWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, file_path: str, settings: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.file_path = file_path
        self.settings = settings or {}

    def run(self) -> None:
        try:
            self.progress.emit(3, "Чтение документа...")
            doc = read_document(self.file_path)
            raw_text = doc["raw_text"].strip()
            if len(raw_text) < 50:
                self.error.emit(
                    "В документе нет текста. "
                    "Распознавание сканов пока не поддерживается."
                )
                return

            file_name = os.path.basename(self.file_path)
            ctx = LectureContext(title=doc["title"])
            summary_md = ""
            tasks: List[Dict[str, Any]] = []
            formulas: List[Dict[str, Any]] = []
            warning = ""

            self.progress.emit(5, "Построение конспекта...")
            try:
                summarizer = create_summarizer(self.settings)
                res = summarizer.summarize_lecture(
                    raw_text, ctx,
                    progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
                    cancel_cb=self.isInterruptionRequested,
                )
                summary_md = repair_corrupted_latex(res.get("summary_markdown", ""))
                tasks = res.get("tasks", [])
                formulas = res.get("formulas", [])
            except CancelledError:
                self.error.emit("Импорт отменён.")
                return
            except Exception as err:
                warning = f"Конспект не построен, сохранён исходный текст: {err}"

            if not summary_md:
                summary_md = f"## {doc['title']}\n\n{repair_corrupted_latex(raw_text)}"
                fallback = keyword_tasks_and_formulas(raw_text, file_name)
                tasks, formulas = fallback["tasks"], fallback["formulas"]

            if summary_md and not warning:
                tasks = merge_tasks(extract_structured_tasks(raw_text), tasks)
            self.finished.emit({
                "title": doc["title"],
                "subject": "Импортированные материалы",
                "lecturer": "Материалы курса",
                "date": datetime.now().strftime("%d.%m.%Y"),
                "duration_min": 60,
                "text": summary_md,
                "raw_transcript": raw_text,
                "tasks": tasks[:20],
                "formulas": formulas,
                "warning": warning,
            })
        except DocumentError as err:
            self.error.emit(str(err))
        except Exception as err:
            self.error.emit(str(err))


class SetupWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.settings = settings or {}

    def run(self) -> None:
        try:
            message = run_setup(
                self.settings,
                lambda pct, msg: self.progress.emit(pct, msg),
                self.isInterruptionRequested,
            )
            self.finished.emit(message)
        except CancelledError:
            self.error.emit("Установка отменена.")
        except SetupError as err:
            self.error.emit(str(err))
        except Exception as err:
            self.error.emit(f"Установка не удалась: {err}")
