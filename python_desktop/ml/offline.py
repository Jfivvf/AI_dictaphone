import os
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from audio_decode import decode_audio_16k
from paths import MODELS_DIR

SAMPLE_RATE = 16000
VAD_WINDOW = 512
VAD_FILE = "silero_vad.onnx"
SPEAKER_FILE = "wespeaker_resnet34.onnx"
ASR_FILES = ("encoder.onnx", "decoder.onnx", "joiner.onnx", "tokens.txt")


def asr_dir(lang: str) -> str:
    return os.path.join(MODELS_DIR, f"sherpa-{lang}")


def required_files(lang: str, diarization: bool = True) -> List[str]:
    files = [f"sherpa-{lang}/{name}" for name in ASR_FILES]
    files.append(VAD_FILE)
    if diarization:
        files.append(SPEAKER_FILE)
    return files


def offline_missing(lang: str, diarization: bool = True) -> List[str]:
    return [rel for rel in required_files(lang, diarization) if not os.path.isfile(os.path.join(MODELS_DIR, rel))]


_RECOGNIZERS: Dict[Tuple[str, int, str], Any] = {}
_EXTRACTORS: Dict[int, Any] = {}


def _import_sherpa():
    try:
        import sherpa_onnx
        return sherpa_onnx
    except ImportError as err:
        from ml.engine import AiUnavailableError
        raise AiUnavailableError(
            "Не установлен пакет sherpa-onnx. Выполните: pip install sherpa-onnx"
        ) from err


def _build_recognizer(sherpa, lang: str, threads: int, model_type: str):
    key = (lang, threads, model_type)
    if key in _RECOGNIZERS:
        return _RECOGNIZERS[key]
    d = asr_dir(lang)
    base = dict(
        encoder=os.path.join(d, "encoder.onnx"),
        decoder=os.path.join(d, "decoder.onnx"),
        joiner=os.path.join(d, "joiner.onnx"),
        tokens=os.path.join(d, "tokens.txt"),
        num_threads=threads,
        sample_rate=SAMPLE_RATE,
        decoding_method="greedy_search",
    )
    # Порядок попыток: явный тип из настроек, затем автоопределение, затем NeMo-трансдьюсер.
    attempts = [model_type] if model_type else ["", "nemo_transducer"]
    last_err: Optional[Exception] = None
    for mt in attempts:
        kwargs = dict(base)
        if mt:
            kwargs["model_type"] = mt
        if mt == "nemo_transducer":
            kwargs["feature_dim"] = 64
        try:
            rec = sherpa.OfflineRecognizer.from_transducer(**kwargs)
            _RECOGNIZERS[key] = rec
            return rec
        except TypeError:
            kwargs.pop("model_type", None)
            try:
                rec = sherpa.OfflineRecognizer.from_transducer(**kwargs)
                _RECOGNIZERS[key] = rec
                return rec
            except Exception as err:
                last_err = err
        except Exception as err:
            last_err = err
    raise RuntimeError(f"Не удалось загрузить офлайн-модель распознавания «sherpa-{lang}»: {last_err}")


def _build_vad(sherpa):
    cfg = sherpa.VadModelConfig()
    cfg.silero_vad.model = os.path.join(MODELS_DIR, VAD_FILE)
    cfg.silero_vad.threshold = 0.5
    cfg.silero_vad.min_silence_duration = 0.4
    cfg.silero_vad.min_speech_duration = 0.25
    cfg.silero_vad.window_size = VAD_WINDOW
    try:
        cfg.silero_vad.max_speech_duration = 20.0
    except Exception:
        pass
    cfg.sample_rate = SAMPLE_RATE
    return sherpa.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)


# Метаданные, без которых sherpa-onnx не принимает модель wespeaker (иначе пишет
# «No model_type in the metadata» и аварийно закрывает всё приложение).
_WESPEAKER_META = {
    "framework": "wespeaker",
    "language": "English",
    "comment": "WeSpeaker ResNet34",
    "sample_rate": "16000",
    "output_dim": "256",
    "normalize_samples": "0",
}


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _meta_entry(key: str, value: str) -> bytes:
    k, v = key.encode("utf-8"), value.encode("utf-8")
    inner = b"\x0a" + _varint(len(k)) + k + b"\x12" + _varint(len(v)) + v
    return b"\x72" + _varint(len(inner)) + inner  # ModelProto.metadata_props (поле 14)


def ensure_wespeaker_metadata(path: str) -> bool:
    """Дописывает в конец .onnx недостающие метаданные (формат protobuf это допускает:
    повторяющиеся поля просто дополняют друг друга). Возвращает True, если файл изменён."""
    with open(path, "rb") as f:
        data = f.read()
    if b"normalize_samples" in data and b"wespeaker" in data:
        return False
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        for key, value in _WESPEAKER_META.items():
            f.write(_meta_entry(key, value))
    os.replace(tmp, path)
    return True


def _build_extractor(sherpa, threads: int):
    if threads not in _EXTRACTORS:
        ensure_wespeaker_metadata(os.path.join(MODELS_DIR, SPEAKER_FILE))
        cfg = sherpa.SpeakerEmbeddingExtractorConfig(
            model=os.path.join(MODELS_DIR, SPEAKER_FILE), num_threads=threads, debug=False, provider="cpu",
        )
        _EXTRACTORS[threads] = sherpa.SpeakerEmbeddingExtractor(cfg)
    return _EXTRACTORS[threads]


def _embedding(extractor, samples: np.ndarray) -> np.ndarray:
    stream = extractor.create_stream()
    stream.accept_waveform(sample_rate=SAMPLE_RATE, waveform=samples)
    stream.input_finished()
    vec = np.array(extractor.compute(stream), dtype=np.float32)
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm > 0 else vec


def assign_speakers(embeddings: List[Optional[np.ndarray]], threshold: float, max_speakers: int) -> List[int]:
    """Жадная кластеризация по косинусной близости к центроидам. Сегменты без эмбеддинга
    (слишком короткие) наследуют говорящего предыдущего сегмента."""
    centroids: List[np.ndarray] = []
    counts: List[int] = []
    labels: List[int] = []
    for emb in embeddings:
        if emb is None:
            labels.append(labels[-1] if labels else 0)
            continue
        sims = [float(np.dot(emb, c / (np.linalg.norm(c) or 1.0))) for c in centroids]
        best = int(np.argmax(sims)) if sims else -1
        if best >= 0 and (sims[best] >= threshold or len(centroids) >= max_speakers):
            counts[best] += 1
            centroids[best] = centroids[best] + emb
            labels.append(best)
        else:
            centroids.append(emb.copy())
            counts.append(1)
            labels.append(len(centroids) - 1)
    return labels


def _format_time(seconds: float) -> str:
    total = int(seconds)
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def transcribe_offline(
    audio_path: str,
    settings: Dict[str, Any],
    progress_cb=None,
    cancel_cb=None,
) -> Dict[str, Any]:
    from ml.engine import AiUnavailableError, CancelledError

    lang = settings.get("offline_language", "ru")
    diarize = bool(settings.get("diarization", True))
    missing = offline_missing(lang, diarize)
    if missing:
        raise AiUnavailableError(
            "Офлайн-модели не установлены (не найдено: " + ", ".join(missing) + "). "
            "Откройте Настройки → «Установить или проверить модели»."
        )
    sherpa = _import_sherpa()

    def report(pct: int, msg: str) -> None:
        if progress_cb:
            progress_cb(pct, msg)

    def check() -> None:
        if cancel_cb and cancel_cb():
            raise CancelledError()

    report(10, "Чтение аудиофайла...")
    audio = decode_audio_16k(audio_path)
    audio = np.asarray(audio, dtype=np.float32)
    total_sec = max(1.0, len(audio) / SAMPLE_RATE)

    threads = max(1, min(8, (os.cpu_count() or 4) // 2))
    report(12, f"Загрузка офлайн-модели (sherpa-{lang})...")
    recognizer = _build_recognizer(sherpa, lang, threads, str(settings.get("sherpa_model_type", "") or ""))
    vad = _build_vad(sherpa)

    report(20, "Поиск речи (Silero VAD)...")
    speech: List[Tuple[float, np.ndarray]] = []

    def drain() -> None:
        while not vad.empty():
            seg = vad.front
            samples = np.asarray(seg.samples, dtype=np.float32)
            if len(samples) >= SAMPLE_RATE * 0.1:
                speech.append((seg.start / SAMPLE_RATE, samples))
            vad.pop()

    step = VAD_WINDOW * 64
    for i in range(0, len(audio), step):
        check()
        chunk = audio[i:i + step]
        for j in range(0, len(chunk), VAD_WINDOW):
            vad.accept_waveform(chunk[j:j + VAD_WINDOW])
        drain()
        report(20 + int(10 * min(1.0, i / len(audio))), "Поиск речи (Silero VAD)...")
    vad.flush()
    drain()

    segments: List[Dict[str, Any]] = []
    kept: List[np.ndarray] = []
    for idx, (start, samples) in enumerate(speech):
        check()
        stream = recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        recognizer.decode_stream(stream)
        text = (stream.result.text or "").strip()
        if text:
            end = start + len(samples) / SAMPLE_RATE
            segments.append({
                "start": round(start, 1), "end": round(end, 1),
                "time": _format_time(start), "text": text,
            })
            kept.append(samples)
        ratio = (idx + 1) / max(1, len(speech))
        report(30 + int(ratio * 25), f"Распознавание речи: {int(ratio * 100)}%...")

    speakers_found = 0
    if diarize and segments:
        report(56, "Определение говорящих (wespeaker)...")
        extractor = _build_extractor(sherpa, threads)
        embeddings: List[Optional[np.ndarray]] = []
        for k, samples in enumerate(kept):
            check()
            if len(samples) < SAMPLE_RATE * 0.8:
                embeddings.append(None)
            else:
                embeddings.append(_embedding(extractor, samples[: SAMPLE_RATE * 10]))
        labels = assign_speakers(
            embeddings,
            float(settings.get("speaker_threshold", 0.5)),
            int(settings.get("max_speakers", 8)),
        )
        speakers_found = len(set(labels))
        for seg, label in zip(segments, labels):
            seg["speaker"] = f"Спикер {label + 1}"

    if speakers_found > 1:
        blocks: List[str] = []
        prev = None
        for seg in segments:
            if seg["speaker"] == prev:
                blocks[-1] += " " + seg["text"]
            else:
                blocks.append(f"{seg['speaker']}: {seg['text']}")
                prev = seg["speaker"]
        full_text = "\n\n".join(blocks)
    else:
        full_text = " ".join(s["text"] for s in segments)
    report(60, "Распознавание завершено.")
    return {"full_text": full_text.strip(), "segments": segments}
