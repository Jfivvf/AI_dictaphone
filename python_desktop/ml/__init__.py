"""Пакет ИИ-движков AxAI: интерфейсы Transcriber и Summarizer (локальные и облачные реализации) + инспектор железа."""
from .engine import (
    HardwareInspector,
    BaseTranscriber,
    FasterWhisperTranscriber,
    GeminiCloudTranscriber,
    BaseSummarizer,
    LocalLlmSummarizer,
    GeminiCloudSummarizer,
    create_transcriber,
    create_summarizer,
)

__all__ = [
    "HardwareInspector",
    "BaseTranscriber",
    "FasterWhisperTranscriber",
    "GeminiCloudTranscriber",
    "BaseSummarizer",
    "LocalLlmSummarizer",
    "GeminiCloudSummarizer",
    "create_transcriber",
    "create_summarizer",
]
