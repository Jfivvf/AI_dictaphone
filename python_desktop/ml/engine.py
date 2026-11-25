import json
import os
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from audio_decode import decode_audio_16k
from paths import MODELS_DIR
from export.exporters import repair_corrupted_latex

ProgressCallback = Callable[[int, str], None]
CancelCallback = Callable[[], bool]


class AiUnavailableError(RuntimeError):
    pass


class NotEnoughTextError(RuntimeError):
    pass


MIN_TRANSCRIPT_CHARS = 300


class CancelledError(Exception):
    pass


@dataclass
class LectureContext:
    subject: str = ""
    title: str = ""
    lecturer: str = ""
    notes: str = ""

    def for_prompt(self) -> str:
        lines: List[str] = []
        if self.subject.strip():
            lines.append(f'Предмет: "{self.subject.strip()}"')
        if self.title.strip():
            lines.append(f'Тема лекции: "{self.title.strip()}"')
        if self.lecturer.strip():
            lines.append(f"Лектор: {self.lecturer.strip()}")
        if self.notes.strip():
            lines.append(
                "Справочник терминов, фамилий и обозначений от студента. Распознавание речи "
                "часто искажает такие слова: если в материале есть слово, похожее на одно из них "
                "по звучанию, пиши его так, как в справочнике. Очевидные опечатки в самом справочнике "
                "можно исправить. Обозначения, которых нет ни в справочнике, ни в материале, "
                "не придумывай:\n" + self.notes.strip()[:4000]
            )
        return "\n".join(lines)


def extract_terms(notes: str, limit: int = 25) -> List[str]:
    text = (notes or "").strip()
    if not text:
        return []
    parts = [p.strip(" .:-•*\t") for p in re.split(r"[,;\n•]+", text)]
    terms = [p for p in parts if 1 < len(p) <= 40]
    if not terms or len(terms) < len(parts) / 2:
        terms = re.findall(r"[^\W\d_]{6,}", text)
    seen: set = set()
    result: List[str] = []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            result.append(term)
        if len(result) >= limit:
            break
    return result


def build_asr_prompts(ctx: LectureContext) -> Tuple[str, str]:
    """Возвращает (initial_prompt, hotwords) для faster-whisper."""
    head = ". ".join(p.strip() for p in (ctx.subject, ctx.title) if p.strip())
    notes = re.sub(r"\s+", " ", ctx.notes or "").strip()
    initial = " ".join(p for p in (head + "." if head else "", notes) if p)[:600]
    hotwords = ", ".join(extract_terms(ctx.notes))[:250]
    return initial, hotwords


_LATEX_COLLIDING = (
    "frac", "forall", "flat", "theta", "tau", "times", "text", "tilde", "tan", "tanh",
    "top", "triangle", "to", "therefore", "beta", "begin", "binom", "bar", "bf", "big",
    "bullet", "boxed", "bot", "backslash", "boldsymbol", "rho", "right", "rightarrow",
    "rangle", "rceil", "rfloor", "nabla", "neq", "ne", "nu", "not", "natural",
    "nexists", "notin", "newline",
)
_COLLIDING_RE = re.compile(
    r"(?<!\\)\\(?!\\)(?=(?:%s)(?![A-Za-z]))"
    % "|".join(sorted(_LATEX_COLLIDING, key=len, reverse=True))
)
_STRAY_BACKSLASH_RE = re.compile(r'(?<!\\)\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})')


def _repair_strings(value: Any) -> Any:
    if isinstance(value, str):
        return repair_corrupted_latex(value)
    if isinstance(value, list):
        return [_repair_strings(v) for v in value]
    if isinstance(value, dict):
        return {k: _repair_strings(v) for k, v in value.items()}
    return value


def parse_json_with_latex_safe(raw_text: str) -> Dict[str, Any]:
    if not raw_text:
        return {}
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE).strip()
    first, last = stripped.find("{"), stripped.rfind("}")
    candidate = stripped[first : last + 1] if first != -1 and last > first else stripped

    fixed = _STRAY_BACKSLASH_RE.sub(r"\\\\", _COLLIDING_RE.sub(r"\\\\", candidate))
    for text in (fixed, candidate):
        try:
            data = json.loads(text)
        except ValueError:
            continue
        if isinstance(data, dict):
            return _repair_strings(data)
    return {}


def chunk_text(text: str, size: int) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            window = start + int(size * 0.7)
            cut = max(text.rfind(sep, window, end) for sep in ("\n\n", ". ", "? ", "! "))
            if cut != -1:
                end = cut + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end
    return chunks


def clean_model_markdown(text: str) -> str:
    t = (text or "").strip()
    fence = re.search(r"```[A-Za-z]*[ \t]*\n", t)
    if fence and not re.search(r"(?m)^#{1,3} \S", t[: fence.start()]):
        inner = t[fence.end():]
        end = inner.find("\n```")
        inner = inner if end == -1 else inner[:end]
        if re.search(r"(?m)^#{1,3} \S", inner):
            t = inner
    heading = re.search(r"(?m)^#{1,3} \S", t)
    if heading and heading.start() > 0:
        t = t[heading.start():]
    return t.strip()


def split_tasks_block(note: str) -> Tuple[str, str]:
    match = re.search(r"(?im)^\W*ЗАДАНИЯ\s*:\s*", note)
    if not match:
        return note.strip(), ""
    body = note[: match.start()].strip()
    tasks = note[match.end():].strip()
    return body, "" if tasks.lower().startswith("нет") else tasks


def _word_set(text: str) -> set:
    return {w.lower() for w in re.findall(r"\w{5,}", text)}


def relevant_excerpt(transcript: str, section: str, limit: int) -> str:
    transcript = (transcript or "").strip()
    if len(transcript) <= limit:
        return transcript
    pieces = chunk_text(transcript, 1500)
    words = _word_set(section)
    order = sorted(range(len(pieces)), key=lambda i: -len(words & _word_set(pieces[i])))
    chosen: List[int] = []
    total = 0
    for idx in order:
        if total + len(pieces[idx]) <= limit:
            chosen.append(idx)
            total += len(pieces[idx])
    return "\n".join(pieces[i] for i in sorted(chosen))


def split_sections(markdown: str, max_len: int) -> List[str]:
    parts = [p for p in re.split(r"(?m)^(?=## )", markdown or "") if p.strip()]
    result: List[str] = []
    for part in parts or [markdown or ""]:
        if len(part) <= max_len:
            result.append(part.strip())
        else:
            result.extend(chunk_text(part, max_len))
    return [r for r in result if r]


def check_ollama(url: str, timeout: float = 1.5) -> Tuple[bool, List[str]]:
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return True, [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return False, []


_HW_CACHE: Optional[Dict[str, Any]] = None  # железо не меняется за время работы: определяем один раз

_PREFERRED_FAMILIES = ("qwen2.5", "qwen3", "llama3", "gemma", "mistral", "deepseek")


def pick_installed_model(wanted: str, installed: List[str]) -> Optional[str]:
    names = set(installed)
    if wanted in names or f"{wanted}:latest" in names:
        return wanted
    for family in _PREFERRED_FAMILIES:
        for name in installed:
            if name.startswith(family):
                return name
    return None


class HardwareInspector:
    @staticmethod
    def hardware() -> Dict[str, Any]:
        global _HW_CACHE
        if _HW_CACHE is None:
            _HW_CACHE = HardwareInspector._detect()
        return dict(_HW_CACHE)

    @staticmethod
    def _detect() -> Dict[str, Any]:
        cpu_cores = os.cpu_count() or 4
        physical_cores = max(1, cpu_cores // 2)
        ram_gb = 8.0
        try:
            import psutil
            ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
            physical_cores = psutil.cpu_count(logical=False) or physical_cores
        except Exception:
            try:
                ram_gb = round(
                    os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 ** 3), 1
                )
            except Exception:
                pass

        has_cuda = False
        gpu_name = "Не обнаружена (режим CPU int8)"
        try:
            import ctranslate2
            count = ctranslate2.get_cuda_device_count()
            if count > 0:
                has_cuda, gpu_name = True, f"NVIDIA CUDA ({count} GPU)"
        except ImportError:
            try:
                import torch
                if torch.cuda.is_available():
                    has_cuda, gpu_name = True, torch.cuda.get_device_name(0)
                elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                    gpu_name = "Apple Silicon Metal (MPS)"
            except Exception:
                pass
        except Exception:
            pass

        if has_cuda or ram_gb >= 14:
            whisper = "large-v3-turbo"
        elif ram_gb >= 7.5:
            whisper = "small"
        else:
            whisper = "base"

        return {
            "cpu_cores": cpu_cores,
            "physical_cores": physical_cores,
            "ram_gb": ram_gb,
            "has_cuda": has_cuda,
            "gpu_name": gpu_name,
            "recommended_whisper": whisper,
            "recommended_llm": "qwen2.5:7b" if (has_cuda or ram_gb >= 12) else "qwen2.5:3b",
        }

    @staticmethod
    def inspect(ollama_url: str = "http://localhost:11434") -> Dict[str, Any]:
        info = HardwareInspector.hardware()
        online, models = check_ollama(ollama_url)
        info["ollama_online"] = online
        info["ollama_models"] = models
        return info


class BaseTranscriber(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        ctx: LectureContext,
        progress_cb: Optional[ProgressCallback] = None,
        cancel_cb: Optional[CancelCallback] = None,
    ) -> Dict[str, Any]:
        """Возвращает {"full_text": str, "segments": [{"start", "end", "time", "text"}]}."""


def _format_time(seconds: float) -> str:
    total = int(seconds)
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


_WHISPER_CACHE: Dict[Tuple[str, str, str, int], Any] = {}

SPEED_PRESETS = {
    "fast": {"beam_size": 1, "batch_size": 8},
    "balanced": {"beam_size": 2, "batch_size": 8},
    "accurate": {"beam_size": 5, "batch_size": 0},
}


def find_local_whisper(name: str) -> Optional[str]:
    if os.path.isdir(name):
        return name
    try:
        from faster_whisper.utils import download_model
    except ImportError:
        return None
    for cache_dir in (MODELS_DIR, None):
        try:
            return download_model(name, cache_dir=cache_dir, local_files_only=True)
        except Exception:
            continue
    return None


def _load_whisper(model_name: str, device: str, compute_type: str, cpu_threads: int):
    key = (model_name, device, compute_type, cpu_threads)
    if key not in _WHISPER_CACHE:
        from faster_whisper import WhisperModel
        source = find_local_whisper(model_name) or model_name
        _WHISPER_CACHE[key] = WhisperModel(
            source, device=device, compute_type=compute_type, cpu_threads=cpu_threads,
            download_root=MODELS_DIR,
        )
    return _WHISPER_CACHE[key]


def _call_with_supported_options(func, audio, options: Dict[str, Any]):
    opts = dict(options)
    for _ in range(len(opts) + 1):
        try:
            return func(audio, **opts)
        except TypeError as err:
            match = re.search(r"unexpected keyword argument '(\w+)'", str(err))
            if not match or match.group(1) not in opts:
                raise
            opts.pop(match.group(1))
    raise RuntimeError("Не удалось вызвать распознавание речи.")


class FasterWhisperTranscriber(BaseTranscriber):
    def __init__(self, model_size: str = "auto", use_vad: bool = True, beam_size: int = 2, batch_size: int = 8):
        self.model_size = model_size
        self.use_vad = use_vad
        self.beam_size = beam_size
        self.batch_size = batch_size

    def transcribe(self, audio_path, ctx, progress_cb=None, cancel_cb=None):
        if progress_cb:
            progress_cb(10, "Чтение аудиофайла...")
        audio = decode_audio_16k(audio_path)

        hw = HardwareInspector.hardware()
        model_name = hw["recommended_whisper"] if self.model_size == "auto" else self.model_size
        device = "cuda" if hw["has_cuda"] else "cpu"
        compute_type = "float16" if hw["has_cuda"] else "int8"
        threads = min(8, max(2, hw["physical_cores"]))

        if progress_cb:
            progress_cb(12, f"Загрузка модели Whisper ({model_name}, {device.upper()})...")
        model = _load_whisper(model_name, device, compute_type, threads)

        initial_prompt, hotwords = build_asr_prompts(ctx)
        options: Dict[str, Any] = {
            "language": "ru",
            "beam_size": self.beam_size,
            "vad_filter": True if self.batch_size > 0 else self.use_vad,
            "vad_parameters": {"min_silence_duration_ms": 500},
            "condition_on_previous_text": False,
        }
        if initial_prompt:
            options["initial_prompt"] = initial_prompt
        if hotwords:
            options["hotwords"] = hotwords

        runner = model.transcribe
        batched = False
        if self.batch_size > 0 and self.use_vad:
            try:
                from faster_whisper import BatchedInferencePipeline
                runner = BatchedInferencePipeline(model=model).transcribe
                options["batch_size"] = self.batch_size
                batched = True
            except ImportError:
                pass

        if progress_cb:
            note = " с учётом контекста" if hotwords or initial_prompt else ""
            progress_cb(22, f"Распознавание речи{note}{' (пакетный режим)' if batched else ''}...")
        segments_iter, info = _call_with_supported_options(runner, audio, options)

        total = max(1.0, float(getattr(info, "duration", 0.0) or 1.0))
        segments: List[Dict[str, Any]] = []
        parts: List[str] = []
        for seg in segments_iter:
            if cancel_cb and cancel_cb():
                raise CancelledError()
            text = (seg.text or "").strip()
            if not text:
                continue
            segments.append({
                "start": round(float(seg.start), 1),
                "end": round(float(seg.end), 1),
                "time": _format_time(seg.start),
                "text": text,
            })
            parts.append(text)
            if progress_cb and total > 1.0:
                ratio = min(1.0, float(seg.end) / total)
                progress_cb(
                    22 + int(ratio * 38),
                    f"Распознавание речи: {int(seg.end // 60)} из {max(1, int(total // 60))} мин ({int(ratio * 100)}%)...",
                )
        return {"full_text": " ".join(parts).strip(), "segments": segments}


class BaseSummarizer(ABC):
    @abstractmethod
    def summarize_lecture(
        self,
        transcript_text: str,
        ctx: LectureContext,
        progress_cb: Optional[ProgressCallback] = None,
        cancel_cb: Optional[CancelCallback] = None,
    ) -> Dict[str, Any]:
        """Возвращает {"summary_markdown": str, "tasks": list, "formulas": list}."""

    @abstractmethod
    def expand_lecture(
        self,
        current_markdown: str,
        transcript_text: str,
        ctx: LectureContext,
        progress_cb: Optional[ProgressCallback] = None,
        cancel_cb: Optional[CancelCallback] = None,
    ) -> str:
        """Возвращает подробную версию конспекта."""


_META_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "deadline": {"type": "string"},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["task", "deadline", "priority"],
            },
        },
        "formulas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "latex": {"type": "string"},
                    "context": {"type": "string"},
                },
                "required": ["title", "latex", "context"],
            },
        },
    },
    "required": ["tasks", "formulas"],
}


def _clean_meta(meta: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    tasks = []
    for item in meta.get("tasks") or []:
        if not isinstance(item, dict) or not str(item.get("task", "")).strip():
            continue
        priority = item.get("priority")
        tasks.append({
            "task": str(item["task"]).strip(),
            "deadline": str(item.get("deadline") or "К следующему занятию").strip(),
            "priority": priority if priority in ("high", "medium", "low") else "medium",
        })
    formulas = []
    for item in meta.get("formulas") or []:
        if not isinstance(item, dict):
            continue
        latex = str(item.get("latex", "")).strip().strip("$").strip()
        if latex:
            formulas.append({
                "title": str(item.get("title") or "Формула").strip(),
                "latex": latex,
                "context": str(item.get("context") or "").strip(),
            })
    return tasks, formulas


class LocalLlmSummarizer(BaseSummarizer):
    CHUNK_CHARS = 9000
    INPUT_BUDGET = 20000
    SECTION_CHARS = 8000

    DETAIL = {
        "fast": {
            "map": 600, "reduce": 2500, "meta": 1200,
            "map_hint": "Не более 250 слов, только тезисы.",
            "reduce_hint": "Объём: примерно 1200–1800 слов, по существу, без воды.",
        },
        "full": {
            "map": 2048, "reduce": 6144, "meta": 2048,
            "map_hint": "Без сокращений.",
            "reduce_hint": "Объём: максимально подробно.",
        },
    }
    STRICT_RULES = (
        "Используй только факты из материала ниже, ничего не выдумывай и не додумывай. "
        "Если для раздела в материале нет сведений, напиши «В записи не освещено». "
        "Начни ответ сразу с заголовка «## 1.» без вступлений и пояснений, не оборачивай ответ в блок кода."
    )

    def __init__(
        self,
        model_name: str = "qwen2.5:7b",
        ollama_url: str = "http://localhost:11434",
        num_ctx: int = 16384,
        read_timeout: int = 600,
        detail: str = "fast",
        requested_model: str = "",
    ):
        self.detail = self.DETAIL.get(detail, self.DETAIL["fast"])
        self.model_name = model_name
        self.requested_model = requested_model or model_name
        self.ollama_url = ollama_url.rstrip("/")
        self.num_ctx = num_ctx
        self.read_timeout = read_timeout

    def _call(
        self,
        prompt: str,
        num_predict: int = 4096,
        schema: Optional[Any] = None,
        cancel_cb: Optional[CancelCallback] = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": 0.25, "num_ctx": self.num_ctx, "num_predict": num_predict},
        }
        if schema is not None:
            payload["format"] = schema
        try:
            return self._stream(payload, cancel_cb)
        except urllib.error.HTTPError as err:
            if err.code == 400 and isinstance(schema, dict):
                payload["format"] = "json"
                return self._stream(payload, cancel_cb)
            raise
        except urllib.error.URLError as err:
            raise AiUnavailableError(f"Нет связи с Ollama ({self.ollama_url}): {err.reason}") from err

    def _stream(self, payload: Dict[str, Any], cancel_cb: Optional[CancelCallback]) -> str:
        req = urllib.request.Request(
            f"{self.ollama_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        parts: List[str] = []
        with urllib.request.urlopen(req, timeout=self.read_timeout) as resp:
            for raw in resp:
                if cancel_cb and cancel_cb():
                    raise CancelledError()
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                chunk = json.loads(line)
                if chunk.get("error"):
                    raise RuntimeError(chunk["error"])
                parts.append(chunk.get("response", ""))
                if chunk.get("done"):
                    break
        return "".join(parts).strip()

    @property
    def label(self) -> str:
        """Название модели для сообщений; если вместо выбранной взята другая, это видно."""
        if self.requested_model and self.requested_model != self.model_name:
            return f"{self.model_name} вместо {self.requested_model}: её нет в Ollama"
        return self.model_name

    @staticmethod
    def _report(cb: Optional[ProgressCallback], pct: int, msg: str) -> None:
        if cb:
            cb(pct, msg)

    def _compress(self, notes: List[str], ctx: LectureContext, cancel_cb) -> str:
        prompt = (
            f"{ctx.for_prompt()}\n\n"
            "Ниже конспекты подряд идущих фрагментов одной лекции. Объедини их в один связный "
            "конспект без повторов. Сохрани все определения, теоремы, формулы LaTeX ($...$ и $$...$$) "
            "и примеры.\n\n" + "\n\n".join(notes)
        )
        return self._call(prompt, num_predict=self.detail["map"] * 2, cancel_cb=cancel_cb) or "\n\n".join(notes)

    def _fit_notes(self, notes: List[str], ctx: LectureContext, progress_cb, cancel_cb) -> str:
        for _ in range(4):
            if len("\n\n".join(notes)) <= self.INPUT_BUDGET or len(notes) < 2:
                break
            self._report(progress_cb, 82, "Сжатие промежуточных конспектов...")
            groups: List[List[str]] = []
            current: List[str] = []
            size = 0
            for note in notes:
                if current and size + len(note) > self.INPUT_BUDGET:
                    groups.append(current)
                    current, size = [], 0
                current.append(note)
                size += len(note)
            if current:
                groups.append(current)
            notes = [self._compress(g, ctx, cancel_cb) for g in groups]
        return "\n\n".join(notes)[: self.INPUT_BUDGET]

    def summarize_lecture(self, transcript_text, ctx, progress_cb=None, cancel_cb=None):
        text = (transcript_text or "").strip()
        if len(text) < MIN_TRANSCRIPT_CHARS:
            raise NotEnoughTextError(
                f"Распознано слишком мало текста ({len(text)} символов). Конспект не был построен. "
                "Проверьте стенограмму и качество записи."
            )
        header = ctx.for_prompt()
        task_notes: List[str] = []

        if len(text) <= self.INPUT_BUDGET:
            source = text
            task_source = text
        else:
            chunks = chunk_text(text, self.CHUNK_CHARS)
            notes: List[str] = []
            for idx, chunk in enumerate(chunks):
                self._report(
                    progress_cb,
                    62 + int((idx + 1) / len(chunks) * 18),
                    f"Локальная LLM ({self.label}): блок {idx + 1} из {len(chunks)}...",
                )
                raw = self._call(
                    f"{header}\n\nИзвлеки из фрагмента лекции определения, ключевые мысли, формулы LaTeX "
                    f"($...$ и $$...$$) и примеры. {self.detail['map_hint']} Без вступлений. "
                    "В конце отдельной строкой «ЗАДАНИЯ:» перечисли всё, что лектор задал студентам, "
                    "со сроками. Если заданий не было, напиши «ЗАДАНИЯ: нет».\n\n" + chunk,
                    num_predict=self.detail["map"],
                    cancel_cb=cancel_cb,
                )
                body, tasks = split_tasks_block(raw)
                if body:
                    notes.append(f"### Фрагмент {idx + 1}\n{body}")
                if tasks:
                    task_notes.append(tasks)
            source = self._fit_notes(notes, ctx, progress_cb, cancel_cb)
            task_source = "\n".join(task_notes)

        self._report(progress_cb, 84, f"Локальная LLM ({self.label}): сборка конспекта...")
        summary_md = self._call(
            f"{header}\n\nНа основе материала составь университетский конспект в Markdown "
            f"с формулами LaTeX ($...$ и $$...$$). {self.detail['reduce_hint']}\n{self.STRICT_RULES}\n"
            "Строго 6 разделов:\n"
            "## 1. Введение и контекст темы\n"
            "## 2. Ключевые понятия и строгие определения\n"
            "## 3. Подробный теоретический разбор\n"
            "## 4. Математический аппарат, формулы и выводы\n"
            "## 5. Разобранные примеры и практическое применение\n"
            "## 6. Итоговые выводы\n\n"
            f"Материал:\n{source}",
            num_predict=self.detail["reduce"],
            cancel_cb=cancel_cb,
        )
        summary_md = clean_model_markdown(summary_md)

        self._report(progress_cb, 93, "Поиск заданий и формул...")
        meta_text = f"{task_source}\n\nКонспект:\n{summary_md[:8000]}".strip()
        meta_raw = self._call(
            "Найди в тексте учебные задания, домашние работы и дедлайны, названные лектором, "
            "и ключевые формулы LaTeX. Не выдумывай задания: если их нет, верни пустой массив tasks. "
            'Ответ строго JSON с ключами "tasks" (task, deadline, priority: high|medium|low) '
            'и "formulas" (title, latex без знаков $, context).\n\n' + meta_text,
            num_predict=self.detail["meta"],
            schema=_META_SCHEMA,
            cancel_cb=cancel_cb,
        )
        tasks, formulas = _clean_meta(parse_json_with_latex_safe(meta_raw))
        return {"summary_markdown": summary_md, "tasks": tasks, "formulas": formulas}

    def expand_lecture(self, current_markdown, transcript_text, ctx, progress_cb=None, cancel_cb=None):
        sections = split_sections(current_markdown, self.SECTION_CHARS)
        if not sections:
            return current_markdown
        header = ctx.for_prompt()
        result: List[str] = []
        for idx, section in enumerate(sections):
            self._report(
                progress_cb,
                12 + int(idx / len(sections) * 82),
                f"Локальная LLM ({self.label}): раздел {idx + 1} из {len(sections)}...",
            )
            excerpt = relevant_excerpt(transcript_text, section, 6000)
            piece = self._call(
                f"{header}\n\nРасширь этот раздел конспекта в 3–4 раза: строгие определения, "
                "пошаговый вывод формул с расшифровкой переменных, примеры с решением. "
                "Сохрани заголовок раздела и формулы LaTeX ($...$ и $$...$$). "
                "Добавляй только то, что следует из стенограммы, ничего не выдумывай. "
                "Верни только текст раздела в Markdown, без вступлений и без блока кода.\n\n"
                f"Раздел:\n{section}\n\nФрагменты стенограммы:\n{excerpt}",
                num_predict=4096,
                cancel_cb=cancel_cb,
            )
            piece = clean_model_markdown(piece)
            heading = section.splitlines()[0] if section.startswith("#") else ""
            if piece and heading and not piece.lstrip().startswith("#"):
                piece = f"{heading}\n\n{piece}"
            result.append(piece or section)
        self._report(progress_cb, 100, "Готово!")
        return "\n\n".join(result)


class SherpaOfflineTranscriber(BaseTranscriber):
    """Офлайн-распознавание: sherpa-onnx + Silero VAD + разделение по спикерам (wespeaker)."""

    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings

    def transcribe(self, audio_path, ctx, progress_cb=None, cancel_cb=None):
        from ml.offline import transcribe_offline
        return transcribe_offline(audio_path, self.settings, progress_cb, cancel_cb)


def create_transcriber(settings: Dict[str, Any]) -> BaseTranscriber:
    if settings.get("transcriber_backend") == "sherpa_offline":
        return SherpaOfflineTranscriber(settings)
    preset = SPEED_PRESETS.get(settings.get("whisper_speed", "balanced"), SPEED_PRESETS["balanced"])
    return FasterWhisperTranscriber(
        model_size=settings.get("whisper_model_size", "auto"),
        use_vad=bool(settings.get("silero_vad", True)),
        beam_size=preset["beam_size"],
        batch_size=preset["batch_size"],
    )


def create_summarizer(settings: Dict[str, Any]) -> BaseSummarizer:
    url = settings.get("ollama_url", "http://localhost:11434")
    wanted = settings.get("ollama_model", "qwen2.5:3b")
    online, installed = check_ollama(url)
    if not online:
        raise AiUnavailableError(f"Сервер Ollama не запущен на {url}. Запустите Ollama и повторите.")
    model = pick_installed_model(wanted, installed)
    if not model:
        raise AiUnavailableError(f"В Ollama нет модели {wanted}. Установите её командой: ollama pull {wanted}")
    return LocalLlmSummarizer(
        model_name=model,
        ollama_url=url,
        num_ctx=int(settings.get("ollama_num_ctx", 16384)),
        read_timeout=int(settings.get("ollama_timeout", 600)),
        detail=settings.get("summary_detail", "fast"),
        requested_model=wanted,
    )
