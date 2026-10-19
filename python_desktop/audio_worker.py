"""
Модуль фоновой аудиозаписи, транскрибации и глубокого расширения конспекта для AxAI (Python + PySide6).
Работает поверх архитектурных интерфейсов `BaseTranscriber` и `BaseSummarizer` (`ml/engine.py`),
выполняя ресурсоемкие задачи в потоках `QThread` с пошаговым индикатором прогресса (`progress(int, str)`).
"""
import os
import wave
from typing import Dict, Any, Optional
import numpy as np
from PySide6.QtCore import QThread, Signal

from pdf_importer import get_gemini_api_key, repair_corrupted_latex
from ml.engine import create_transcriber, create_summarizer


class MicrophoneRecorder:
    """Захват звука с микрофона с помощью sounddevice (16 кГц, моно WAV)."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.is_recording = False
        self.frames = []

    def start(self):
        try:
            import sounddevice as sd
            self.is_recording = True
            self.frames = []

            def callback(indata, frames, time, status):
                if self.is_recording:
                    self.frames.append(indata.copy())

            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                callback=callback,
            )
            self.stream.start()
        except Exception as e:
            print(f"Ошибка захвата звука с микрофона: {e}")

    def stop(self, output_path: str) -> str:
        self.is_recording = False
        if hasattr(self, "stream"):
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass

        if not self.frames:
            return ""

        audio_data = np.concatenate(self.frames, axis=0)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data.tobytes())

        return output_path


class TranscriptionWorker(QThread):
    """
    Фоновый поток транскрибации и построения конспекта через `BaseTranscriber` + `BaseSummarizer`.
    Поддерживает:
    - Локальный `FasterWhisperTranscriber` (с Silero VAD) и облачный `GeminiCloudTranscriber`.
    - Локальный `LocalLlmSummarizer` (Ollama Qwen 2.5 7B с Map-Reduce для лекций >1 часа) и `GeminiCloudSummarizer`.
    - Передачу пользовательского контекста (`ai_context`).
    """
    progress = Signal(int, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        audio_path: str,
        title: str = "",
        subject: str = "",
        ai_context: str = "",
        settings: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.audio_path = audio_path
        self.title = title or "Запись лекции"
        self.subject = subject or "Учебная дисциплина"
        self.ai_context = ai_context or ""
        self.settings = settings or {}

    def run(self):
        try:
            self.progress.emit(8, "Инициализация пайплайна распознавания речи...")
            api_key = get_gemini_api_key()

            # 1. Вызов Transcriber (Faster-Whisper + VAD или Gemini Cloud)
            transcriber = create_transcriber(self.settings, api_key=api_key)
            full_text = ""
            segments = []

            try:
                tr_res = transcriber.transcribe(
                    self.audio_path,
                    progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
                )
                full_text = tr_res.get("full_text", "")
                segments = tr_res.get("segments", [])
            except Exception as tr_err:
                print(f"Предупреждение Transcriber: {tr_err}")

            # 2. Вызов Summarizer (Локальная LLM с Map-Reduce или Gemini Cloud)
            summary_markdown = ""
            tasks = []
            formulas = []

            summarizer = create_summarizer(self.settings, api_key=api_key)
            if summarizer and (full_text.strip() or self.ai_context.strip()):
                try:
                    sum_res = summarizer.summarize_lecture(
                        transcript_text=full_text or self.ai_context,
                        title=self.title,
                        subject=self.subject,
                        ai_context=self.ai_context,
                        progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
                    )
                    summary_markdown = repair_corrupted_latex(sum_res.get("summary_markdown", ""))
                    tasks = sum_res.get("tasks", [])
                    formulas = sum_res.get("formulas", [])
                except Exception as sum_err:
                    print(f"Предупреждение Summarizer: {sum_err}")

            if not summary_markdown:
                ctx_note = f"\n\n### Контекст и заметки студента\n{self.ai_context}\n" if self.ai_context else ""
                summary_markdown = (
                    f"## 1. Конспект лекции: {self.title}\n\n"
                    f"**Дисциплина:** {self.subject}{ctx_note}\n\n"
                    f"### Полная расшифровка выступления\n\n"
                    f"{full_text.strip() or 'Аудиофайл успешно сохранен.'}"
                )

            # 3. Резервное извлечение дедлайнов по ключевым словам, если Summarizer не вернул задачи
            if not tasks and self.settings.get("auto_extract_tasks", True):
                for line in (full_text or "").split("."):
                    clean_line = line.strip()
                    lower = clean_line.lower()
                    if any(w in lower for w in ["сдать", "домашн", "задание", "дедлайн", "коллоквиум", "экзамен", "лабораторн"]):
                        if len(clean_line) > 10:
                            prio = "high" if any(h in lower for h in ["срочн", "экзамен", "коллоквиум", "контрольн"]) else "medium"
                            tasks.append({
                                "id": f"task-{len(tasks)}",
                                "task": clean_line,
                                "deadline": "К следующему занятию",
                                "completed": False,
                                "priority": prio,
                            })

            if not tasks:
                tasks.append({
                    "id": "task-default-0",
                    "task": f"Повторить конспект по теме «{self.title}»",
                    "deadline": "К следующему семинару",
                    "completed": False,
                    "priority": "medium",
                })

            result = {
                "text": summary_markdown,
                "raw_transcript": full_text.strip(),
                "segments": segments,
                "tasks": tasks[:10],
                "formulas": formulas,
            }

            self.progress.emit(100, "Готово!")
            self.finished.emit(result)

        except Exception as e:
            self.error.emit(str(e))


class ExpandLectureWorker(QThread):
    """
    Фоновый поток для кнопки «✨ Сделать подробнее (ИИ)» с передачей пошагового прогресса (`progress(int, str)`).
    Работает как с облачным Gemini, так и с локальной моделью Qwen 2.5 через Ollama.
    """
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
        settings: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.title = title
        self.subject = subject
        self.current_markdown = current_markdown
        self.raw_transcript = raw_transcript
        self.ai_context = ai_context
        self.settings = settings or {}

    def run(self):
        try:
            self.progress.emit(12, "1. Анализ исходного конспекта, стенограммы и контекста лекции...")
            api_key = get_gemini_api_key()
            summarizer = create_summarizer(self.settings, api_key=api_key)

            if summarizer is not None:
                expanded = summarizer.expand_lecture(
                    current_markdown=self.current_markdown,
                    transcript_text=self.raw_transcript,
                    title=self.title,
                    subject=self.subject,
                    ai_context=self.ai_context,
                    progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
                )
                self.progress.emit(100, "Готово!")
                self.finished.emit(repair_corrupted_latex(expanded))
                return

            # Локальное академическое расширение шаблоном, если не запущен Ollama и нет GEMINI_API_KEY
            self.progress.emit(65, "3. Добавление контрольных вопросов и структуры подготовки к экзамену...")
            ctx_section = (
                f"\n### Разбор по контексту студента\n{self.ai_context}\n"
                if self.ai_context.strip()
                else ""
            )
            expanded = (
                f"{self.current_markdown}\n\n"
                f"---\n\n"
                f"## Дополнительный разбор и подготовка к экзамену ({self.subject})\n"
                f"{ctx_section}\n"
                f"### Ключевые теоретические выводы по теме «{self.title}»\n"
                f"- Проверьте строгие формулировки определений и условия применимости каждой теоремы.\n"
                f"- При выводе расчетных соотношений указывайте физический и математический смысл всех коэффициентов.\n\n"
                f"### Контрольные вопросы к коллоквиуму и экзамену\n"
                f"1. Сформулируйте основные определения и исходные допущения по теме «{self.title}».\n"
                f"2. Запишите основные математические соотношения и поясните входящие в них величины.\n"
                f"3. Приведите примеры практического применения разобранного материала.\n"
            )
            self.progress.emit(100, "Готово!")
            self.finished.emit(expanded)
        except Exception as e:
            self.error.emit(str(e))
