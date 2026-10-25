"""Запись звука с микрофона: данные пишутся на диск по ходу записи, есть закладки."""
import os
import queue
import threading
import wave
from typing import Any, Dict, List, Optional


class MicrophoneRecorder:
    """Захват 16 кГц моно через sounddevice с потоковой записью в WAV."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.is_recording = False
        self.bookmarks: List[Dict[str, Any]] = []
        self._queue: "queue.Queue[Optional[Any]]" = queue.Queue()
        self._writer: Optional[threading.Thread] = None
        self._wav: Optional[wave.Wave_write] = None
        self._stream = None
        self._path = ""
        self._frames_written = 0

    @property
    def elapsed_seconds(self) -> float:
        return self._frames_written / self.sample_rate

    def start(self, output_path: str) -> None:
        try:
            import sounddevice as sd
        except ImportError as err:
            raise RuntimeError("Не установлен пакет sounddevice (pip install sounddevice).") from err

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        self._path = output_path
        self._frames_written = 0
        self.bookmarks = []
        self._queue = queue.Queue()

        self._wav = wave.open(output_path, "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(self.sample_rate)

        def callback(indata, frames, time_info, status):
            if self.is_recording:
                self._queue.put(indata.copy())

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate, channels=1, dtype="int16", callback=callback
            )
            self.is_recording = True
            self._writer = threading.Thread(target=self._write_loop, daemon=True)
            self._writer.start()
            self._stream.start()
        except Exception as err:
            self.is_recording = False
            self._close_wav()
            raise RuntimeError(f"Не удалось открыть микрофон: {err}") from err

    def _write_loop(self) -> None:
        while True:
            block = self._queue.get()
            if block is None:
                break
            self._wav.writeframes(block.tobytes())
            self._frames_written += len(block)

    def _close_wav(self) -> None:
        if self._wav is not None:
            self._wav.close()
            self._wav = None

    def add_bookmark(self, note: str = "") -> Dict[str, Any]:
        mark = {"time_sec": int(self.elapsed_seconds), "note": note.strip()}
        self.bookmarks.append(mark)
        return mark

    def stop(self) -> str:
        """Останавливает запись и возвращает путь к файлу или пустую строку, если звука не было."""
        self.is_recording = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._writer is not None:
            self._queue.put(None)
            self._writer.join()
            self._writer = None
        self._close_wav()
        return self._path if self._frames_written > 0 else ""


def recover_wav_header(path: str) -> bool:
    """Чинит заголовок WAV, оставшийся нулевым после аварийного завершения записи."""
    size = os.path.getsize(path)
    if size <= 44:
        return False
    with open(path, "r+b") as f:
        if f.read(4) != b"RIFF":
            return False
        data_size = size - 44
        f.seek(4)
        f.write((36 + data_size).to_bytes(4, "little"))
        f.seek(40)
        f.write(data_size.to_bytes(4, "little"))
    return True
