"""
Модуль фоновой аудиозаписи и офлайн транскрибации для PySide6.
Выполняет ресурсоемкие операции в отдельном потоке QThread.
"""
import os
import wave
import numpy as np
from PySide6.QtCore import QThread, Signal

class MicrophoneRecorder:
    """Захват звука с микрофона с помощью sounddevice"""
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
            print(f"Ошибка захвата звука: {e}")

    def stop(self, output_path: str) -> str:
        self.is_recording = False
        if hasattr(self, 'stream'):
            self.stream.stop()
            self.stream.close()

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
    """Фоновый поток транскрибации через Faster-Whisper"""
    progress = Signal(int, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, audio_path: str, model_size="large-v3-turbo", device="auto"):
        super().__init__()
        self.audio_path = audio_path
        self.model_size = model_size
        self.device = device

    def run(self):
        try:
            self.progress.emit(20, "Загрузка модели распознавания...")
            from faster_whisper import WhisperModel

            # Автоопределение GPU (CUDA) или CPU
            device = "cuda" if self.device == "cuda" else "cpu"
            compute_type = "int8"

            model = WhisperModel(
                self.model_size,
                device=device,
                compute_type=compute_type,
                vad_filter=True, # Встроенный Silero VAD для очистки пауз
                vad_parameters=dict(min_silence_duration_ms=500)
            )

            self.progress.emit(50, "Распознавание речи лектора...")
            segments, info = model.transcribe(
                self.audio_path,
                language="ru",
                beam_size=5
            )

            transcript_list = []
            full_text = ""
            for seg in segments:
                transcript_list.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text
                })
                full_text += f"{seg.text} "

            self.progress.emit(85, "Форматирование конспекта и формул...")
            
            # Базовое извлечение задач по ключевым словам
            tasks = []
            for line in full_text.split("."):
                lower = line.lower()
                if any(w in lower for w in ["сдать", "домашн", "задание", "дедлайн", "коллоквиум"]):
                    if len(line.strip()) > 10:
                        tasks.append({
                            "task": line.strip(),
                            "deadline": "К следующей паре",
                            "completed": False
                        })

            result = {
                "text": full_text.strip(),
                "segments": transcript_list,
                "tasks": tasks[:5]
            }

            self.progress.emit(100, "Готово!")
            self.finished.emit(result)

        except Exception as e:
            self.error.emit(str(e))
