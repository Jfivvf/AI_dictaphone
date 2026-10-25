"""Чтение аудио в массив float32 (16 кГц, моно). Не зависит от версии PyAV, которую ставит faster-whisper."""
import shutil
import subprocess
import wave
from typing import List, Optional

import numpy as np

SAMPLE_RATE = 16000


class AudioDecodeError(RuntimeError):
    """Файл нельзя прочитать как аудио."""


def _read_plain_wav(path: str) -> Optional[np.ndarray]:
    """Быстрый путь для записей приложения: WAV 16 кГц, моно, 16 бит."""
    try:
        with wave.open(path, "rb") as wf:
            if wf.getsampwidth() != 2 or wf.getnchannels() != 1 or wf.getframerate() != SAMPLE_RATE:
                return None
            data = wf.readframes(wf.getnframes())
    except (wave.Error, EOFError, OSError):
        return None
    if not data:
        return None
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def _read_with_av(path: str) -> np.ndarray:
    import av

    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    parts: List[np.ndarray] = []

    def collect(result) -> None:
        if result is None:
            return
        frames = result if isinstance(result, (list, tuple)) else [result]
        for frame in frames:
            parts.append(frame.to_ndarray().reshape(-1))

    with av.open(path) as container:
        if not container.streams.audio:
            raise AudioDecodeError("В файле нет аудиодорожки.")
        frames = iter(container.decode(audio=0))
        while True:
            try:
                frame = next(frames)
            except StopIteration:
                break
            except av.error.InvalidDataError:
                continue
            collect(resampler.resample(frame))
        try:
            collect(resampler.resample(None))
        except Exception:
            pass

    if not parts:
        raise AudioDecodeError("Не удалось получить звук из файла.")
    return np.concatenate(parts).astype(np.float32) / 32768.0


def _read_with_ffmpeg(path: str) -> np.ndarray:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise AudioDecodeError("ffmpeg не найден.")
    proc = subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"],
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise AudioDecodeError(proc.stderr.decode("utf-8", errors="ignore").strip() or "ffmpeg не смог прочитать файл.")
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def decode_audio_16k(path: str) -> np.ndarray:
    """WAV приложения читается напрямую, остальное через PyAV, а при его сбое через ffmpeg, если он установлен."""
    audio = _read_plain_wav(path)
    if audio is not None:
        return audio

    errors: List[str] = []
    for reader in (_read_with_av, _read_with_ffmpeg):
        try:
            return reader(path)
        except Exception as err:
            errors.append(f"{reader.__name__.replace('_read_with_', '')}: {err}")
    raise AudioDecodeError("Не удалось прочитать аудиофайл. " + "; ".join(errors))
