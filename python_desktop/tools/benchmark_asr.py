"""Замер скорости распознавания на вашем компьютере.

Берёт первые N минут вашей записи и прогоняет через разные настройки, чтобы выбрать быстрые и при этом точные.
Запуск из папки python_desktop:
    python tools/benchmark_asr.py "C:\\путь\\к\\записи.m4a" --minutes 5
    python tools/benchmark_asr.py запись.m4a --minutes 3 --models small,large-v3-turbo --speeds fast,balanced
Тексты для сравнения качества сохраняются в папку benchmark_out рядом с запуском.
RTF = время обработки / длительность звука. Меньше 1 значит быстрее реального времени.
"""
import argparse
import os
import sys
import tempfile
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from audio_decode import SAMPLE_RATE, decode_audio_16k
from ml.engine import (
    SPEED_PRESETS, FasterWhisperTranscriber, HardwareInspector, LectureContext, _load_whisper,
)


def write_wav(path: str, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio")
    parser.add_argument("--minutes", type=float, default=5.0, help="сколько минут записи взять (по умолчанию 5)")
    parser.add_argument("--models", default="small,large-v3-turbo", help="через запятую: tiny,base,small,medium,large-v3-turbo")
    parser.add_argument("--speeds", default="fast,balanced,accurate", help="через запятую: fast,balanced,accurate")
    args = parser.parse_args()

    audio = decode_audio_16k(args.audio)
    audio = audio[: int(args.minutes * 60 * SAMPLE_RATE)]
    seconds = len(audio) / SAMPLE_RATE
    hw = HardwareInspector.hardware()
    threads = min(8, max(2, hw["physical_cores"]))
    device = "cuda" if hw["has_cuda"] else "cpu"
    compute = "float16" if hw["has_cuda"] else "int8"
    print(f"Звук: {seconds / 60:.1f} мин | CPU: {hw['cpu_cores']} потоков, {hw['physical_cores']} ядер, "
          f"ОЗУ {hw['ram_gb']} ГБ | ускоритель: {hw['gpu_name']} | потоков Whisper: {threads}\n")

    out_dir = os.path.abspath("benchmark_out")
    os.makedirs(out_dir, exist_ok=True)
    tmp_wav = os.path.join(tempfile.gettempdir(), "axai_bench.wav")
    write_wav(tmp_wav, audio)

    rows = []
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"Загрузка модели {model}...", flush=True)
        _load_whisper(model, device, compute, threads)
        for speed in [s.strip() for s in args.speeds.split(",") if s.strip()]:
            preset = SPEED_PRESETS[speed]
            transcriber = FasterWhisperTranscriber(model, True, preset["beam_size"], preset["batch_size"])
            started = time.monotonic()
            result = transcriber.transcribe(tmp_wav, LectureContext())
            elapsed = time.monotonic() - started
            words = len(result["full_text"].split())
            name = f"{model}_{speed}.txt"
            with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
                f.write(result["full_text"])
            rows.append((model, speed, elapsed, elapsed / seconds, words, name))
            print(f"  {model:16} {speed:9} {elapsed:7.1f} с   RTF {elapsed / seconds:5.2f}   слов {words}", flush=True)

    print("\nИтог (чем меньше RTF, тем быстрее):")
    for model, speed, elapsed, rtf, words, name in sorted(rows, key=lambda r: r[3]):
        est = rtf * 64
        print(f"  {model:16} {speed:9} RTF {rtf:5.2f}  примерно {est:5.0f} мин на 64 мин лекции  ({name})")
    print(f"\nТексты для сравнения качества: {out_dir}")


if __name__ == "__main__":
    main()
