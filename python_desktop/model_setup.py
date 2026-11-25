import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from typing import Any, Callable, Dict, List, Optional

from ml.engine import (
    CancelledError,
    HardwareInspector,
    check_ollama,
    find_local_whisper,
)
from ml.offline import ASR_FILES, SPEAKER_FILE, VAD_FILE, offline_missing
from paths import MODELS_DIR

RELEASE_URL = os.environ.get(
    "AXAI_MODELS_URL",
    "https://github.com/Jfivvf/AI_dictaphone/releases/download/models-v1",
)

# Примерный размер загрузки, МБ
WHISPER_SIZES_MB = {"tiny": 75, "base": 145, "small": 480, "medium": 1500, "large-v3-turbo": 1600, "large-v3": 3100}
LLM_SIZES_MB = {"qwen2.5:3b": 2100, "qwen2.5:7b": 4700}

# Языковая модель, которая входит в офлайн-пакет: файл GGUF лежит в релизе и импортируется в Ollama.
BUNDLED_LLM = "qwen2.5:3b"
BUNDLED_LLM_FILE = "qwen2.5-3b-instruct-q4_k_m.gguf"
_CHATML_TEMPLATE = (
    "{{ if .System }}<|im_start|>system\n{{ .System }}<|im_end|>\n{{ end }}"
    "{{ if .Prompt }}<|im_start|>user\n{{ .Prompt }}<|im_end|>\n{{ end }}"
    "<|im_start|>assistant\n{{ .Response }}<|im_end|>"
)
_STOP_TOKENS = ("<|im_start|>", "<|im_end|>")
OFFLINE_SIZES_MB = {"sherpa-ru": 233, "sherpa-en": 55, VAD_FILE: 3, SPEAKER_FILE: 26}

ProgressCb = Callable[[int, str], None]
CancelCb = Callable[[], bool]


class SetupError(RuntimeError):
    pass


def is_offline_mode(settings: Dict[str, Any]) -> bool:
    return settings.get("transcriber_backend") == "sherpa_offline"


def _targets(settings: Dict[str, Any]) -> Dict[str, Any]:
    hw = HardwareInspector.hardware()
    whisper = settings.get("whisper_model_size", "auto")
    if whisper == "auto":
        whisper = hw["recommended_whisper"]
    llm = settings.get("ollama_model") or hw["recommended_llm"]
    url = settings.get("ollama_url", "http://localhost:11434")
    return {
        "whisper": whisper, "llm": llm, "url": url,
        "lang": settings.get("offline_language", "ru"),
        "diarization": bool(settings.get("diarization", True)),
    }


def _offline_assets(missing: List[str]) -> List[str]:
    """Какие файлы релиза нужно скачать, чтобы закрыть недостающее."""
    assets: List[str] = []
    for rel in missing:
        if "/" in rel:
            asset = rel.split("/")[0]  # sherpa-ru, sherpa-en
        else:
            asset = rel
        if asset not in assets:
            assets.append(asset)
    return assets


def setup_status(settings: Dict[str, Any]) -> Dict[str, Any]:
    t = _targets(settings)
    needs: List[str] = []
    need_mb = 0

    if is_offline_mode(settings):
        missing = offline_missing(t["lang"], t["diarization"])
        for asset in _offline_assets(missing):
            label = {
                "sherpa-ru": "Офлайн-модель распознавания речи (русский)",
                "sherpa-en": "Офлайн-модель распознавания речи (английский)",
                VAD_FILE: "Офлайн-модель поиска речи (Silero VAD)",
                SPEAKER_FILE: "Офлайн-модель разделения по спикерам (wespeaker)",
            }.get(asset, asset)
            needs.append(label)
            need_mb += OFFLINE_SIZES_MB.get(asset, 100)
    elif not find_local_whisper(t["whisper"]):
        needs.append(f"Модель распознавания речи Whisper «{t['whisper']}»")
        need_mb += WHISPER_SIZES_MB.get(t["whisper"], 1000)

    online, installed = check_ollama(t["url"])
    if not online:
        needs.append("Ollama не запущена: установите её с ollama.com и запустите (нужна для конспектов)")
    elif not _has_model(t["llm"], installed):
        source = " (из офлайн-пакета)" if _from_release(settings, t["llm"]) else " (скачивается из интернета)"
        needs.append(f"Языковая модель Ollama «{t['llm']}»{source}")
        need_mb += LLM_SIZES_MB.get(t["llm"], 4700)

    return {"ready": not needs, "needs": needs, "need_mb": need_mb}


def _has_model(wanted: str, installed: List[str]) -> bool:
    """Точное совпадение: запасная подстановка другой модели здесь не годится,
    иначе при установленной 7B «установка» 3B считалась бы уже выполненной."""
    names = set(installed)
    return wanted in names or f"{wanted}:latest" in names


def _from_release(settings: Dict[str, Any], llm: str) -> bool:
    """Модель берём из релиза (без интернета-реестра Ollama), если это 3B и включён офлайн-режим."""
    return is_offline_mode(settings) and llm == BUNDLED_LLM


def _check_cancel(cancel_cb: Optional[CancelCb]) -> None:
    if cancel_cb and cancel_cb():
        raise CancelledError()


# ----------------------------- Whisper / Ollama -----------------------------

def _download_whisper(name: str, progress_cb: ProgressCb, cancel_cb: CancelCb) -> None:
    try:
        from faster_whisper.utils import download_model
    except ImportError as err:
        raise SetupError("Не установлен пакет faster-whisper. Выполните: pip install -r requirements.txt") from err
    progress_cb(5, f"Скачивание Whisper «{name}» (может занять несколько минут)...")
    _check_cancel(cancel_cb)
    try:
        download_model(name, cache_dir=MODELS_DIR)
    except Exception as err:
        raise SetupError(f"Не удалось скачать Whisper «{name}»: {err}") from err
    progress_cb(50, "Whisper установлен.")


def _pull_ollama(url: str, model: str, progress_cb: ProgressCb, cancel_cb: CancelCb) -> None:
    body = json.dumps({"name": model, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        f"{url.rstrip('/')}/api/pull", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for raw in resp:
                _check_cancel(cancel_cb)
                if not raw.strip():
                    continue
                chunk = json.loads(raw.decode("utf-8"))
                if chunk.get("error"):
                    raise SetupError(f"Ollama: {chunk['error']}")
                total, done = chunk.get("total") or 0, chunk.get("completed") or 0
                if total:
                    pct = 50 + int(done / total * 49)
                    progress_cb(min(pct, 99), f"Скачивание {model}: {done // (1024 * 1024)} из {total // (1024 * 1024)} МБ")
                else:
                    progress_cb(50, f"Ollama: {chunk.get('status', '...')}")
    except (SetupError, CancelledError):
        raise
    except Exception as err:
        raise SetupError(f"Не удалось скачать модель {model} через Ollama: {err}") from err


# ----------------------------- Офлайн-пакет -----------------------------

def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _pack_dirs() -> List[str]:
    """Папки, где может лежать локальный комплект (файлы релиза, скопированные заранее):
    переменная AXAI_PACK, затем `models_pack` рядом с приложением, рядом с его папкой и рядом с хранилищем."""
    here = os.path.dirname(os.path.abspath(__file__))
    dirs = [
        os.environ.get("AXAI_PACK", ""),
        os.path.join(os.path.dirname(sys.executable), "models_pack") if getattr(sys, "frozen", False) else "",
        os.path.join(here, "models_pack"),
        os.path.join(os.path.dirname(here), "models_pack"),
        os.path.join(os.path.dirname(MODELS_DIR), "models_pack"),
    ]
    return [d for d in dirs if d and os.path.isdir(d)]


def _local_file(name: str) -> Optional[str]:
    for d in _pack_dirs():
        path = os.path.join(d, name)
        if os.path.isfile(path):
            return path
    return None


def _fetch_sums() -> Dict[str, str]:
    """Контрольные суммы: из локального комплекта, а если его нет — из релиза.
    Ключи — путь из файла без ведущих «./» и «models/»."""
    local = _local_file("SHA256SUMS")
    if local:
        with open(local, "r", encoding="utf-8", errors="replace") as f:
            return _parse_sums(f.read())
    try:
        with urllib.request.urlopen(f"{RELEASE_URL}/SHA256SUMS", timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as err:
        raise SetupError(f"Не удалось получить список контрольных сумм ({RELEASE_URL}): {err}") from err
    return _parse_sums(text)


def _parse_sums(text: str) -> Dict[str, str]:
    sums: Dict[str, str] = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            continue
        name = parts[1].lstrip("*").replace("\\", "/")
        while name.startswith("./"):
            name = name[2:]
        if name.startswith("models/"):
            name = name[len("models/"):]
        sums[name] = parts[0].lower()
    return sums


def _download_file(url: str, dest: str, label: str, lo: int, hi: int, progress_cb: ProgressCb, cancel_cb: CancelCb) -> None:
    try:
        with urllib.request.urlopen(url, timeout=60) as resp, open(dest, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                _check_cancel(cancel_cb)
                block = resp.read(1024 * 256)
                if not block:
                    break
                out.write(block)
                done += len(block)
                pct = lo + int((hi - lo) * (done / total)) if total else lo
                progress_cb(min(pct, hi), f"Скачивание {label}: {done // (1024 * 1024)} из {total // (1024 * 1024) if total else '?'} МБ")
    except (CancelledError, SetupError):
        raise
    except Exception as err:
        raise SetupError(f"Не удалось скачать {label} ({url}): {err}") from err


def _install_offline(missing: List[str], progress_cb: ProgressCb, cancel_cb: CancelCb) -> List[str]:
    assets = _offline_assets(missing)
    progress_cb(2, "Получение контрольных сумм...")
    try:
        sums = _fetch_sums()
    except SetupError:
        # без интернета можно обойтись, если все файлы лежат в локальном комплекте
        if not all(_local_file(f"{a}.zip" if not a.endswith(".onnx") else a) for a in assets):
            raise
        sums = {}
    installed: List[str] = []
    os.makedirs(MODELS_DIR, exist_ok=True)

    weights = {a: OFFLINE_SIZES_MB.get(a, 50) for a in assets}
    total_w = sum(weights.values()) or 1
    cursor = 3
    for asset in assets:
        span = max(3, int(95 * weights[asset] / total_w))
        lo, hi = cursor, min(98, cursor + span)
        cursor = hi
        is_zip = not asset.endswith(".onnx")
        file_name = f"{asset}.zip" if is_zip else asset

        tmp_dir = tempfile.mkdtemp(prefix="axai_dl_", dir=MODELS_DIR)
        try:
            part = os.path.join(tmp_dir, file_name)
            dl_hi = lo + int((hi - lo) * 0.85)
            local = _local_file(file_name)
            if local:
                part = local  # файл из локального комплекта: интернет не нужен, исходный файл не трогаем
                progress_cb(lo, f"Найден локальный файл {file_name}")
            else:
                _download_file(f"{RELEASE_URL}/{file_name}", part, file_name, lo, dl_hi, progress_cb, cancel_cb)

            progress_cb(dl_hi, f"Проверка {file_name}...")
            expected = sums.get(file_name)
            if expected and _sha256(part) != expected:
                raise SetupError(f"Контрольная сумма {file_name} не совпала — файл повреждён. Повторите установку.")

            if is_zip:
                extract_dir = os.path.join(tmp_dir, "x")
                try:
                    with zipfile.ZipFile(part) as zf:
                        zf.extractall(extract_dir)
                except zipfile.BadZipFile as err:
                    raise SetupError(f"Архив {file_name} повреждён: {err}") from err
                src = None
                for root, _dirs, files in os.walk(extract_dir):
                    if ASR_FILES[0] in files:
                        src = root
                        break
                if src is None:
                    raise SetupError(f"В архиве {file_name} не найден {ASR_FILES[0]}.")
                for name in ASR_FILES:
                    if not os.path.isfile(os.path.join(src, name)):
                        raise SetupError(f"В архиве {file_name} не хватает файла {name}.")
                target = os.path.join(MODELS_DIR, asset)
                if os.path.isdir(target):
                    shutil.rmtree(target)
                shutil.move(src, target)
                for name in ASR_FILES:  # контрольные суммы распакованных файлов, если они есть в списке
                    exp = sums.get(f"{asset}/{name}")
                    if exp and _sha256(os.path.join(target, name)) != exp:
                        shutil.rmtree(target, ignore_errors=True)
                        raise SetupError(f"Файл {asset}/{name} повреждён (контрольная сумма не совпала).")
            else:
                (shutil.copy2 if local else shutil.move)(part, os.path.join(MODELS_DIR, file_name))
            installed.append(asset)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    return installed


def _import_gguf(url: str, model: str, gguf_path: str, progress_cb: ProgressCb, cancel_cb: CancelCb) -> None:
    """Создаёт в Ollama модель `model` из локального файла GGUF.

    Сначала пробуем команду `ollama create` (она работает во всех версиях), затем — HTTP API.
    Шаблон ChatML и стоп-токены задаём явно: приложение шлёт «сырые» запросы в /api/generate.
    """
    progress_cb(90, "Импорт модели в Ollama...")
    errors: List[str] = []

    exe = shutil.which("ollama")
    if exe:
        tmp = tempfile.mkdtemp(prefix="axai_modelfile_", dir=MODELS_DIR)
        try:
            modelfile = os.path.join(tmp, "Modelfile")
            with open(modelfile, "w", encoding="utf-8") as f:
                f.write(f"FROM {gguf_path}\n")
                f.write(f'TEMPLATE """{_CHATML_TEMPLATE}"""\n')
                for stop in _STOP_TOKENS:
                    f.write(f'PARAMETER stop "{stop}"\n')
            env = dict(os.environ)
            if url.rstrip("/") != "http://localhost:11434":
                env["OLLAMA_HOST"] = url.rstrip("/")
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.run(
                [exe, "create", model, "-f", modelfile],
                capture_output=True, text=True, timeout=1800, env=env, creationflags=flags,
            )
            if proc.returncode == 0:
                return
            errors.append((proc.stderr or proc.stdout or "").strip()[-300:])
        except Exception as err:
            errors.append(str(err))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    _check_cancel(cancel_cb)

    try:
        digest = _sha256(gguf_path)
        size = os.path.getsize(gguf_path)
        with open(gguf_path, "rb") as blob:
            req = urllib.request.Request(
                f"{url.rstrip('/')}/api/blobs/sha256:{digest}", data=blob, method="POST",
                headers={"Content-Length": str(size), "Content-Type": "application/octet-stream"},
            )
            urllib.request.urlopen(req, timeout=1800).read()
        body = json.dumps({
            "model": model, "files": {os.path.basename(gguf_path): f"sha256:{digest}"},
            "template": _CHATML_TEMPLATE, "parameters": {"stop": list(_STOP_TOKENS)}, "stream": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{url.rstrip('/')}/api/create", data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=1800) as resp:
            for raw in resp:
                _check_cancel(cancel_cb)
                if raw.strip():
                    chunk = json.loads(raw.decode("utf-8"))
                    if chunk.get("error"):
                        raise SetupError(str(chunk["error"]))
        return
    except CancelledError:
        raise
    except Exception as err:
        errors.append(str(err))
    raise SetupError(f"Не удалось импортировать модель {model} в Ollama: " + "; ".join(e for e in errors if e))


def _install_bundled_llm(url: str, model: str, progress_cb: ProgressCb, cancel_cb: CancelCb) -> None:
    """Скачивает GGUF из релиза, проверяет SHA256 (если сумма есть) и импортирует в Ollama."""
    try:
        sums = _fetch_sums()
    except SetupError:
        sums = {}
    os.makedirs(MODELS_DIR, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="axai_dl_", dir=MODELS_DIR)
    try:
        part = _local_file(BUNDLED_LLM_FILE)  # из локального комплекта, если он есть
        if part:
            progress_cb(5, f"Найден локальный файл {BUNDLED_LLM_FILE}")
        else:
            part = os.path.join(tmp, BUNDLED_LLM_FILE)
            _download_file(f"{RELEASE_URL}/{BUNDLED_LLM_FILE}", part, BUNDLED_LLM_FILE, 3, 85, progress_cb, cancel_cb)
        progress_cb(86, "Проверка файла модели...")
        expected = sums.get(BUNDLED_LLM_FILE)
        if expected and _sha256(part) != expected:
            raise SetupError("Контрольная сумма файла модели не совпала — файл повреждён. Повторите установку.")
        _import_gguf(url, model, part, progress_cb, cancel_cb)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # Ollama уже скопировал модель к себе, файл больше не нужен


# ----------------------------- Точка входа -----------------------------

def run_setup(settings: Dict[str, Any], progress_cb: ProgressCb, cancel_cb: CancelCb) -> str:
    t = _targets(settings)
    done: List[str] = []
    notes: List[str] = []

    progress_cb(1, "Проверка установленных моделей...")
    if is_offline_mode(settings):
        missing = offline_missing(t["lang"], t["diarization"])
        if missing:
            done.extend(f"офлайн: {a}" for a in _install_offline(missing, progress_cb, cancel_cb))
    elif not find_local_whisper(t["whisper"]):
        _download_whisper(t["whisper"], progress_cb, cancel_cb)
        done.append(f"Whisper «{t['whisper']}»")

    _check_cancel(cancel_cb)
    online, installed = check_ollama(t["url"])
    if not online:
        setup_exe = _local_file("OllamaSetup.exe")
        where = f"установщик лежит здесь: {setup_exe}" if setup_exe else "скачайте её с ollama.com"
        notes.append(f"Ollama не запущена — {where}, запустите её и повторите установку (нужна для конспектов).")
    elif not _has_model(t["llm"], installed):
        if _from_release(settings, t["llm"]):
            _install_bundled_llm(t["url"], t["llm"], progress_cb, cancel_cb)
        else:
            _pull_ollama(t["url"], t["llm"], progress_cb, cancel_cb)
        done.append(f"модель Ollama «{t['llm']}»")

    progress_cb(100, "Готово.")
    parts = []
    if done:
        parts.append("Установлено: " + ", ".join(done) + ".")
    else:
        parts.append("Все модели, которые можно скачать, уже установлены.")
    parts.extend(notes)
    return "\n".join(parts)
