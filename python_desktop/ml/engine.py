"""
Архитектурный слой ИИ для десктопного приложения AxAI (Python + PySide6).

Реализует рекомендации код-ревью:
1. Чёткое разделение интерфейсов `BaseTranscriber` (распознавание речи) и `BaseSummarizer` (генерация конспекта,
   выявление дедлайнов и формул LaTeX) с двумя реализациями для каждого:
   - Локальная: `FasterWhisperTranscriber` (с Silero VAD) + `LocalLlmSummarizer` (Ollama / llama.cpp Qwen 2.5 7B).
   - Облачная: `GeminiCloudTranscriber` + `GeminiCloudSummarizer` (Gemini 2.5 Flash с JSON Schema).
2. Map-Reduce обработка длинных лекций (>1–1.5 часа) для локальной 7B-модели:
   длинный транскрипт режется на смысловые блоки по ~10 000 символов, по каждому строится промежуточный
   разбор (Map), после чего собирается итоговый 6-раздельный университетский конспект (Reduce).
3. Строгая JSON-схема (`format: json` в Ollama / `response_schema` в Gemini) для извлечения дедлайнов и формул.
4. `HardwareInspector` — автоматическая проверка железа (CPU/RAM/CUDA/MPS/Ollama) и выбор оптимального размера модели.
"""
import os
import re
import json
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Callable, Dict, Any, List, Optional


ProgressCallback = Callable[[int, str], None]


def parse_json_with_latex_safe(raw_text: str) -> Dict[str, Any]:
    """Безопасный парсинг JSON с формулами LaTeX (не портит двойные слэши \\\\equiv, \\\\frac, \\\\neg)."""
    if not raw_text:
        return {}
    stripped = re.sub(r"^```json\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE).strip()
    first = stripped.find("{")
    last = stripped.rfind("}")
    candidate = stripped[first : last + 1] if (first != -1 and last > first) else stripped

    try:
        return json.loads(candidate)
    except Exception:
        pass

    # Экранируем только одиночные обратные слэши перед LaTeX-командами
    fixed = re.sub(r'(?<!\\)\\(["\\/bfnrt]|u[0-9a-fA-F]{4})', r"\\\\\1", candidate)
    fixed = re.sub(r'(?<!\\)\\(?![\\"/bfnrt]|u[0-9a-fA-F]{4})', r"\\\\", fixed)
    try:
        return json.loads(fixed)
    except Exception:
        return {}


class HardwareInspector:
    """Определяет характеристики ПК (CPU, RAM, GPU CUDA/MPS, доступность Ollama) и рекомендует модели."""

    @staticmethod
    def inspect(ollama_url: str = "http://localhost:11434") -> Dict[str, Any]:
        cpu_cores = os.cpu_count() or 4
        ram_gb = 8.0

        # Определение объема ОЗУ кроссплатформенно
        try:
            import psutil
            ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
        except Exception:
            try:
                if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names and "SC_PHYS_PAGES" in os.sysconf_names:
                    ram_gb = round((os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")) / (1024 ** 3), 1)
            except Exception:
                pass

        has_cuda = False
        gpu_name = "Не обнаружена (режим CPU int8)"
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                has_cuda = True
                gpu_name = f"NVIDIA CUDA ({ctranslate2.get_cuda_device_count()} GPU)"
        except Exception:
            pass

        if not has_cuda:
            try:
                import torch
                if torch.cuda.is_available():
                    has_cuda = True
                    gpu_name = torch.cuda.get_device_name(0)
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    gpu_name = "Apple Silicon Metal (MPS)"
            except Exception:
                pass

        # Проверка локального сервера Ollama и установленных моделей
        ollama_online = False
        ollama_models: List[str] = []
        try:
            req = urllib.request.Request(f"{ollama_url.rstrip('/')}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                ollama_online = True
                ollama_models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception:
            pass

        # Рекомендация модели Whisper по железу
        if has_cuda or ram_gb >= 14:
            recommended_whisper = "large-v3-turbo"
        elif ram_gb >= 7.5:
            recommended_whisper = "small"
        else:
            recommended_whisper = "base"

        recommended_llm = "qwen2.5:7b" if (has_cuda or ram_gb >= 12) else "qwen2.5:3b"

        return {
            "cpu_cores": cpu_cores,
            "ram_gb": ram_gb,
            "has_cuda": has_cuda,
            "gpu_name": gpu_name,
            "ollama_online": ollama_online,
            "ollama_models": ollama_models,
            "recommended_whisper": recommended_whisper,
            "recommended_llm": recommended_llm,
        }


# =====================================================================
# 1. ИНТЕРФЕЙС РАСПОЗНАВАНИЯ РЕЧИ (TRANSCRIBER)
# =====================================================================

class BaseTranscriber(ABC):
    """Единый интерфейс распознавания аудиозаписи лекции."""

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        """
        Возвращает словарь:
        {
            "full_text": str,
            "segments": [{"start": float, "end": float, "text": str}]
        }
        """
        pass


class FasterWhisperTranscriber(BaseTranscriber):
    """
    Локальное распознавание речи через faster-whisper + фильтр тишины Silero VAD.
    Стабильно обрабатывает лекции >1–1.5 часа с поминутным обновлением прогресс-бара.
    """

    def __init__(self, model_size: str = "auto", use_vad: bool = True, accuracy_mode: str = "high"):
        self.model_size = model_size
        self.use_vad = use_vad
        self.accuracy_mode = accuracy_mode

    def transcribe(
        self,
        audio_path: str,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        from faster_whisper import WhisperModel

        hw = HardwareInspector.inspect()
        actual_model = hw["recommended_whisper"] if self.model_size == "auto" else self.model_size
        device = "cuda" if hw["has_cuda"] else "cpu"
        compute_type = "float16" if hw["has_cuda"] else "int8"

        # Режим максимальной точности по умолчанию: beam_size=5 для превосходного распознавания терминов и формул
        beam_size = 5

        if progress_cb:
            progress_cb(
                12,
                f"Загрузка локальной модели Faster-Whisper ({actual_model} на {device.upper()}, максимальная точность beam=5)...",
            )

        model = WhisperModel(
            actual_model,
            device=device,
            compute_type=compute_type,
            cpu_threads=max(2, hw["cpu_cores"] - 1),
        )

        if progress_cb:
            vad_status = "Silero VAD активен" if self.use_vad else "Фильтр шума отключен"
            progress_cb(22, f"Распознавание речи ({vad_status})...")

        segments_iter, info = model.transcribe(
            audio_path,
            language="ru",
            beam_size=beam_size,
            vad_filter=self.use_vad,
            vad_parameters=dict(min_silence_duration_ms=500),
            condition_on_previous_text=False,  # Предотвращает зацикливание на длинных лекциях >1 часа
        )

        total_duration = max(1.0, float(getattr(info, "duration", 0.0) or 1.0))
        segments: List[Dict[str, Any]] = []
        text_parts: List[str] = []

        for seg in segments_iter:
            clean_seg = (seg.text or "").strip()
            if not clean_seg:
                continue
            segments.append({
                "start": round(float(seg.start), 1),
                "end": round(float(seg.end), 1),
                "text": clean_seg,
            })
            text_parts.append(clean_seg)

            if progress_cb and total_duration > 1.0:
                ratio = min(1.0, float(seg.end) / total_duration)
                pct = 22 + int(ratio * 38)  # 22% -> 60%
                mins_done = int(seg.end // 60)
                mins_total = max(1, int(total_duration // 60))
                progress_cb(
                    pct,
                    f"Распознавание речи Faster-Whisper: {mins_done} из {mins_total} мин ({int(ratio * 100)}%)...",
                )

        return {
            "full_text": " ".join(text_parts).strip(),
            "segments": segments,
        }


class GeminiCloudTranscriber(BaseTranscriber):
    """Облачное распознавание аудио через Gemini File API (поддерживает лекции до 2+ часов)."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def transcribe(
        self,
        audio_path: str,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        from google import genai

        if progress_cb:
            progress_cb(18, "Загрузка аудиофайла в облачный движок Gemini File API...")

        client = genai.Client(api_key=self.api_key)
        uploaded = client.files.upload(file=audio_path)

        if progress_cb:
            progress_cb(45, "Распознавание речи и таймкодов лектора (Gemini)...")

        prompt = (
            "Расшифруй аудиозапись лекции на русском языке максимально подробно и точно. "
            "Верни строго JSON: {\"segments\": [{\"time\": \"00:00\", \"text\": \"...\"}]}"
        )
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[uploaded, prompt],
        )
        data = parse_json_with_latex_safe(resp.text or "")
        raw_segs = data.get("segments", [])
        segments = []
        full_parts = []
        for idx, s in enumerate(raw_segs):
            txt = (s.get("text") or "").strip()
            if txt:
                segments.append({
                    "start": float(idx * 30),
                    "end": float((idx + 1) * 30),
                    "time": s.get("time", f"{idx // 2:02d}:{(idx % 2) * 30:02d}"),
                    "text": txt,
                })
                full_parts.append(txt)

        if not full_parts and resp.text:
            full_parts = [resp.text.strip()]

        return {
            "full_text": " ".join(full_parts).strip(),
            "segments": segments,
        }


# =====================================================================
# 2. ИНТЕРФЕЙС ГЕНЕРАЦИИ КОНСПЕКТА И ДЕДЛАЙНОВ (SUMMARIZER)
# =====================================================================

class BaseSummarizer(ABC):
    """Единый интерфейс построения университетского конспекта, формул LaTeX и дедлайнов."""

    @abstractmethod
    def summarize_lecture(
        self,
        transcript_text: str,
        title: str,
        subject: str,
        ai_context: str = "",
        progress_cb: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        """Возвращает {"summary_markdown": str, "tasks": list, "formulas": list}."""
        pass

    @abstractmethod
    def expand_lecture(
        self,
        current_markdown: str,
        transcript_text: str,
        title: str,
        subject: str,
        ai_context: str = "",
        progress_cb: Optional[ProgressCallback] = None,
    ) -> str:
        """Расширяет конспект в 3–4 раза подробнее с выводом формул, примерами и вопросами к экзамену."""
        pass


class LocalLlmSummarizer(BaseSummarizer):
    """
    Локальный генератор конспектов через Ollama (Qwen 2.5 7B / 3B Instruct).
    - Использует Map-Reduce по кускам для длинных лекций (>1 часа), чтобы 7B-модель не теряла детали.
    - Использует JSON-схему (`format: "json"`) для надежного выделения дедлайнов и формул LaTeX.
    """

    def __init__(self, model_name: str = "qwen2.5:7b", ollama_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.ollama_url = ollama_url.rstrip("/")

    def _call_ollama(self, prompt: str, json_mode: bool = False, timeout: int = 180) -> str:
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.25,
                "num_ctx": 8192,
            },
        }
        if json_mode:
            payload["format"] = "json"

        req = urllib.request.Request(
            f"{self.ollama_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return (body.get("response") or "").strip()

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 10000) -> List[str]:
        text = (text or "").strip()
        if len(text) <= chunk_size:
            return [text] if text else []
        chunks = []
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            if end < len(text):
                dot = text.rfind(".", start + int(chunk_size * 0.7), end)
                if dot != -1:
                    end = dot + 1
            chunks.append(text[start:end].strip())
            start = end
        return chunks

    def summarize_lecture(
        self,
        transcript_text: str,
        title: str,
        subject: str,
        ai_context: str = "",
        progress_cb: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        chunks = self._chunk_text(transcript_text, chunk_size=10000)
        partial_notes: List[str] = []

        # Этап MAP (если лекция длинная — конспектируем по блокам)
        if len(chunks) > 1:
            for idx, ch in enumerate(chunks):
                if progress_cb:
                    pct = 62 + int(((idx + 1) / len(chunks)) * 18)
                    progress_cb(
                        pct,
                        f"Локальная LLM ({self.model_name}): Map-конспектирование блока {idx + 1} из {len(chunks)}...",
                    )
                map_prompt = f"""Ты — университетский лектор по предмету "{subject}". Тема: "{title}".
Контекст от студента: {ai_context or "не указан"}.
Извлеки из этого фрагмента лекции ВСЕ определения, теоремы, формулы LaTeX ($...$ и $$...$$) и примеры без сокращений:

{ch}"""
                part_summary = self._call_ollama(map_prompt, json_mode=False)
                if part_summary:
                    partial_notes.append(f"### Блок {idx + 1}\n{part_summary}")
            combined_source = "\n\n".join(partial_notes)
        else:
            combined_source = transcript_text

        # Этап REDUCE (сборка 6-раздельного конспекта)
        if progress_cb:
            progress_cb(84, f"Локальная LLM ({self.model_name}): сборка фундаментального конспекта из 6 разделов...")

        reduce_prompt = f"""Ты — профессор по предмету "{subject}". Тема лекции: "{title}".
Контекст студента: {ai_context or "не указан"}.
На основе материала ниже составь подробный, хорошо структурированный университетский конспект в формате Markdown с формулами LaTeX ($...$ и $$...$$) строго из 6 разделов:
## 1. Введение и контекст темы
## 2. Ключевые понятия и строгие определения
## 3. Подробный теоретический разбор
## 4. Математический аппарат, формулы и выводы
## 5. Разобранные примеры и практическое применение
## 6. Итоговые выводы и вопросы к экзамену

Материал:
{combined_source[:28000]}"""

        summary_md = self._call_ollama(reduce_prompt, json_mode=False)

        # Этап JSON-извлечения дедлайнов и карточек формул
        if progress_cb:
            progress_cb(93, f"Локальная LLM ({self.model_name}): извлечение дедлайнов и формул по JSON-схеме...")

        json_prompt = f"""Извлеки из конспекта и стенограммы лекции учебные задачи/дедлайны и ключевые формулы LaTeX.
Верни СТРОГО валидный JSON по следующей схеме:
{{
  "tasks": [
    {{"task": "Описание задачи или ДЗ", "deadline": "Срок сдачи", "priority": "high"}}
  ],
  "formulas": [
    {{"title": "Название формулы", "latex": "Формула без знаков $", "context": "Пояснение"}}
  ]
}}

Текст:
{summary_md[:12000]}"""

        meta_raw = self._call_ollama(json_prompt, json_mode=True)
        meta = parse_json_with_latex_safe(meta_raw)

        return {
            "summary_markdown": summary_md,
            "tasks": meta.get("tasks", []),
            "formulas": meta.get("formulas", []),
        }

    def expand_lecture(
        self,
        current_markdown: str,
        transcript_text: str,
        title: str,
        subject: str,
        ai_context: str = "",
        progress_cb: Optional[ProgressCallback] = None,
    ) -> str:
        if progress_cb:
            progress_cb(25, f"Локальная LLM ({self.model_name}): анализ конспекта и контекста...")

        prompt = f"""Ты — ведущий университетский профессор по дисциплине "{subject}".
Тема лекции: "{title}".
Дополнительный контекст студента: {ai_context or "углубить математический аппарат и доказательства"}.

Перед тобой текущий конспект. Сделай его в 3–4 раза ПОДРОБНЕЕ и ГЛУБЖЕ в формате Markdown с формулами LaTeX ($...$ и $$...$$):
1. Дай строгие академические определения каждого термина.
2. Пошагово выведи все формулы и объясни физический/математический смысл каждой переменной.
3. Добавь подробные практические примеры с пошаговым решением.
4. Добавь контрольные вопросы к экзамену с развернутыми ответами.

Текущий конспект:
{current_markdown[:18000]}

Стенограмма:
{transcript_text[:14000]}"""

        if progress_cb:
            progress_cb(60, f"Локальная LLM ({self.model_name}): генерация подробного конспекта и формул LaTeX...")

        expanded = self._call_ollama(prompt, json_mode=False, timeout=240)
        if progress_cb:
            progress_cb(100, "Готово!")
        return expanded or current_markdown


class GeminiCloudSummarizer(BaseSummarizer):
    """Облачный генератор конспектов на базе Gemini 2.5 Flash со строгой JSON-схемой и проверкой LaTeX."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def summarize_lecture(
        self,
        transcript_text: str,
        title: str,
        subject: str,
        ai_context: str = "",
        progress_cb: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        from google import genai
        from google.genai import types

        if progress_cb:
            progress_cb(68, "Генерация фундаментального конспекта и формул LaTeX (Gemini)...")

        client = genai.Client(api_key=self.api_key)
        prompt = f"""Ты — академический ИИ-ассистент AxAI для студентов.
Предмет: "{subject}"
Тема лекции: "{title}"
Контекст/заметки студента: "{ai_context or 'не указаны'}"

По следующей стенограмме составь ОЧЕНЬ ПОДРОБНЫЙ, РАЗВЕРНУТЫЙ университетский конспект в формате Markdown с формулами LaTeX ($...$ и $$...$$) из 6 разделов:
## 1. Введение и контекст темы
## 2. Ключевые понятия и строгие определения
## 3. Подробный теоретический разбор (с подпунктами ### 3.1, ### 3.2...)
## 4. Математический аппарат, формулы и выводы
## 5. Разобранные примеры и практическое применение
## 6. Итоговые выводы и вопросы к экзамену (с ответами)

Верни строго JSON с полями summaryMarkdown, tasks и formulas.

Стенограмма:
{transcript_text[:80000]}"""

        schema = types.Schema(
            type=types.Type.OBJECT,
            properties={
                "summaryMarkdown": types.Schema(type=types.Type.STRING),
                "tasks": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "task": types.Schema(type=types.Type.STRING),
                            "deadline": types.Schema(type=types.Type.STRING),
                            "priority": types.Schema(type=types.Type.STRING),
                        },
                        required=["task", "deadline", "priority"],
                    ),
                ),
                "formulas": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "title": types.Schema(type=types.Type.STRING),
                            "latex": types.Schema(type=types.Type.STRING),
                            "context": types.Schema(type=types.Type.STRING),
                        },
                        required=["title", "latex", "context"],
                    ),
                ),
            },
            required=["summaryMarkdown", "tasks", "formulas"],
        )

        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.2,
            ),
        )
        data = parse_json_with_latex_safe(resp.text or "")
        return {
            "summary_markdown": (data.get("summaryMarkdown") or "").strip(),
            "tasks": data.get("tasks", []),
            "formulas": data.get("formulas", []),
        }

    def expand_lecture(
        self,
        current_markdown: str,
        transcript_text: str,
        title: str,
        subject: str,
        ai_context: str = "",
        progress_cb: Optional[ProgressCallback] = None,
    ) -> str:
        from google import genai

        if progress_cb:
            progress_cb(20, "1. Анализ текущего конспекта, стенограммы и контекста лекции...")

        client = genai.Client(api_key=self.api_key)
        context_block = f"\nКонтекст и пожелания студента:\n{ai_context}\n" if ai_context.strip() else ""

        prompt = f"""Ты — ведущий университетский профессор по дисциплине "{subject}".
Перед тобой конспект лекции на тему "{title}".{context_block}
Сделай этот конспект в 3–4 раза ПОДРОБНЕЕ, ГЛУБЖЕ и ПОЛНЕЕ в формате чистого Markdown (с формулами LaTeX $...$ и $$...$$):
1. Добавь строгие академические определения каждого понятия и теоремы.
2. Пошагово распиши математические выводы формул и расшифруй каждую переменную.
3. Добавь подробные практические примеры с пошаговым решением.
4. В конце добавь контрольные вопросы к экзамену с развернутыми ответами.

Текущий конспект:
{current_markdown[:45000]}

Исходная стенограмма:
{transcript_text[:45000]}"""

        if progress_cb:
            progress_cb(55, "2. Вывод математических формул LaTeX, доказательств и примеров...")

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        expanded_text = (response.text or "").strip()
        if progress_cb:
            progress_cb(100, "Готово!")
        return expanded_text or current_markdown


# =====================================================================
# 3. ФАБРИКИ ВЫБОРА ДВИЖКА ПО НАСТРОЙКАМ
# =====================================================================

def create_transcriber(settings: Dict[str, Any], api_key: str = "") -> BaseTranscriber:
    backend = settings.get("transcriber_backend", "auto")
    model_size = settings.get("whisper_model_size", "auto")
    use_vad = bool(settings.get("silero_vad", True))
    accuracy_mode = settings.get("accuracy_mode", "high")

    if backend == "gemini_cloud" and api_key:
        return GeminiCloudTranscriber(api_key=api_key)
    return FasterWhisperTranscriber(model_size=model_size, use_vad=use_vad, accuracy_mode=accuracy_mode)


def create_summarizer(settings: Dict[str, Any], api_key: str = "") -> Optional[BaseSummarizer]:
    backend = settings.get("summarizer_backend", "auto")
    ollama_url = settings.get("ollama_url", "http://localhost:11434")
    ollama_model = settings.get("ollama_model", "qwen2.5:7b")

    if backend == "local_ollama":
        return LocalLlmSummarizer(model_name=ollama_model, ollama_url=ollama_url)
    if backend == "gemini_cloud" and api_key:
        return GeminiCloudSummarizer(api_key=api_key)

    # Режим "auto": сначала проверяем наличие ключа Gemini, затем локальный Ollama
    if api_key:
        return GeminiCloudSummarizer(api_key=api_key)

    hw = HardwareInspector.inspect(ollama_url=ollama_url)
    if hw["ollama_online"]:
        chosen_model = ollama_model
        if hw["ollama_models"] and ollama_model not in hw["ollama_models"]:
            chosen_model = hw["ollama_models"][0]
        return LocalLlmSummarizer(model_name=chosen_model, ollama_url=ollama_url)

    return None
