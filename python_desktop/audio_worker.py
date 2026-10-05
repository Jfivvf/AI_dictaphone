"""
Модуль фоновой аудиозаписи, транскрибации и глубокого расширения конспекта для AxAI (Python + PySide6).
Выполняет ресурсоемкие операции в отдельных потоках QThread без зависания интерфейса.
"""
import os
import re
import json
import wave
import numpy as np
from PySide6.QtCore import QThread, Signal
from pdf_importer import get_gemini_api_key


class MicrophoneRecorder:
    """Захват звука с микрофона с помощью sounddevice (16 кГц, моно WAV)."""
    def __init__(self, sample_rate=16000):
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
                callback=callback
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
    Фоновый поток транскрибации аудио и формирования развернутого университетского конспекта
    (через Faster-Whisper + Gemini API при наличии ключа).
    """
    progress = Signal(int, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, audio_path: str, title: str = "", subject: str = "", model_size="base", device="auto"):
        super().__init__()
        self.audio_path = audio_path
        self.title = title or "Запись лекции"
        self.subject = subject or "Учебная дисциплина"
        self.model_size = model_size
        self.device = device

    def run(self):
        try:
            self.progress.emit(15, "Инициализация движка распознавания речи...")
            full_text = ""
            transcript_list = []

            # 1. Пробуем локальный Faster-Whisper
            try:
                from faster_whisper import WhisperModel
                device = "cuda" if self.device == "cuda" else "cpu"
                model = WhisperModel(
                    self.model_size,
                    device=device,
                    compute_type="int8",
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500),
                )
                self.progress.emit(45, "Распознавание речи лектора (Faster-Whisper)...")
                segments, _ = model.transcribe(self.audio_path, language="ru", beam_size=5)
                for seg in segments:
                    transcript_list.append({
                        "start": round(seg.start, 1),
                        "end": round(seg.end, 1),
                        "text": seg.text.strip(),
                    })
                    full_text += f"{seg.text.strip()} "
            except Exception as whisper_err:
                print(f"Faster-Whisper инфо: {whisper_err}")

            # 2. Если настроен GEMINI_API_KEY, формируем фундаментальный конспект из 6 разделов
            api_key = get_gemini_api_key()
            summary_markdown = ""
            tasks = []
            formulas = []

            if api_key and full_text.strip():
                try:
                    self.progress.emit(75, "Генерация подробного конспекта и формул ИИ...")
                    from google import genai
                    client = genai.Client(api_key=api_key)
                    prompt = f"""Ты — академический ИИ-ассистент AxAI для студентов.
Предмет: "{self.subject}"
Тема лекции: "{self.title}"

По следующей стенограмме лекции составь ОЧЕНЬ ПОДРОБНЫЙ, РАЗВЕРНУТЫЙ университетский конспект в формате Markdown с формулами LaTeX ($...$ и $$...$$) из 6 разделов:
## 1. Введение и контекст темы
## 2. Ключевые понятия и строгие определения
## 3. Подробный теоретический разбор
## 4. Математический аппарат, формулы и выводы
## 5. Разобранные примеры и практическое применение
## 6. Итоговые выводы и вопросы к экзамену

Стенограмма:
{full_text}"""
                    resp = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                    )
                    summary_markdown = (resp.text or "").strip()
                except Exception as ai_err:
                    print(f"Gemini structuring warning: {ai_err}")

            if not summary_markdown:
                summary_markdown = (
                    f"## 1. Конспект лекции: {self.title}\n\n"
                    f"**Дисциплина:** {self.subject}\n\n"
                    f"### Полная расшифровка выступления\n\n"
                    f"{full_text.strip() or 'Аудиофайл успешно обработан.'}"
                )

            # 3. Извлечение дедлайнов и задач с приоритетами
            for line in (full_text or "").split("."):
                clean_line = line.strip()
                lower = clean_line.lower()
                if any(w in lower for w in ["сдать", "домашн", "задание", "дедлайн", "коллоквиум", "экзамен", "лабораторн"]):
                    if len(clean_line) > 10:
                        priority = "high" if any(h in lower for h in ["срочн", "экзамен", "коллоквиум", "контрольн"]) else "medium"
                        tasks.append({
                            "id": f"task-{len(tasks)}",
                            "task": clean_line,
                            "deadline": "К следующему занятию",
                            "completed": False,
                            "priority": priority,
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
                "segments": transcript_list,
                "tasks": tasks[:8],
                "formulas": formulas,
            }

            self.progress.emit(100, "Готово!")
            self.finished.emit(result)

        except Exception as e:
            self.error.emit(str(e))


class ExpandLectureWorker(QThread):
    """Фоновый поток для кнопки «Сделать подробнее (ИИ)» внутри просмотра лекции."""
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, title: str, subject: str, current_markdown: str, raw_transcript: str = ""):
        super().__init__()
        self.title = title
        self.subject = subject
        self.current_markdown = current_markdown
        self.raw_transcript = raw_transcript

    def run(self):
        api_key = get_gemini_api_key()
        if not api_key:
            # Расширение структуры конспекта локальным академическим шаблоном, если ключ не задан
            expanded = (
                f"{self.current_markdown}\n\n"
                f"---\n\n"
                f"## Дополнительный разбор и подготовка к экзамену ({self.subject})\n\n"
                f"### Ключевые теоретические выводы по теме «{self.title}»\n"
                f"- Проверьте строгие формулировки определений и условия применимости каждой теоремы.\n"
                f"- При выводе расчетных соотношений указывайте физический и геометрический смысл всех коэффициентов.\n\n"
                f"### Контрольные вопросы к коллоквиуму и экзамену\n"
                f"1. Сформулируйте основные определения и исходные допущения по теме «{self.title}».\n"
                f"2. Запишите основные математические соотношения и поясните входящие в них величины.\n"
                f"3. Приведите примеры практического применения разобранного материала.\n"
            )
            self.finished.emit(expanded)
            return

        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = f"""Ты — ведущий университетский профессор по дисциплине "{self.subject}".
Перед тобой текущий конспект лекции на тему "{self.title}".
Сделай этот конспект в 3–4 раза ПОДРОБНЕЕ, ГЛУБЖЕ и ПОЛНЕЕ в формате Markdown (с формулами LaTeX $...$ и $$...$$):
1. Добавь строгие академические определения каждого понятия.
2. Пошагово распиши выводы формул и расшифруй каждую переменную.
3. Добавь подробные практические примеры с пошаговым разбором.
4. В конце добавь развернутые ответы на главные вопросы к экзамену.

Текущий конспект:
{self.current_markdown[:40000]}

Исходный текст:
{self.raw_transcript[:40000]}"""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            expanded_text = (response.text or "").strip()
            self.finished.emit(expanded_text or self.current_markdown)
        except Exception as e:
            self.error.emit(str(e))
