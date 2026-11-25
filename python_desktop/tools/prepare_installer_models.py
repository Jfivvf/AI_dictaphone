"""Готовит папку build/models для установщика: скачивает офлайн-модели из релиза,
проверяет контрольные суммы и раскладывает так, как их ждёт приложение.

Запуск (из корня репозитория):  python python_desktop/tools/prepare_installer_models.py
Переменные: AXAI_MODELS_URL — адрес релиза, OUT_DIR — куда класть (по умолчанию build/models).
Qwen и установщик Ollama сюда не входят: они слишком большие для одного файла релиза (лимит 2 ГиБ).
"""
import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile

RELEASE_URL = os.environ.get("AXAI_MODELS_URL", "https://github.com/Jfivvf/AI_dictaphone/releases/download/models-v1")
OUT_DIR = os.environ.get("OUT_DIR", os.path.join("build", "models"))
ASR_FILES = ("encoder.onnx", "decoder.onnx", "joiner.onnx", "tokens.txt")
ZIPS = ("sherpa-ru", "sherpa-en")
ONNX = ("silero_vad.onnx", "wespeaker_resnet34.onnx")


def fetch(name: str, dest: str) -> None:
    print(f"Скачивание {name}...", flush=True)
    with urllib.request.urlopen(f"{RELEASE_URL}/{name}", timeout=120) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out, 1024 * 1024)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_sums(tmp: str) -> dict:
    path = os.path.join(tmp, "SHA256SUMS")
    fetch("SHA256SUMS", path)
    sums = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            name = parts[1].lstrip("*").replace("\\", "/")
            while name.startswith("./"):
                name = name[2:]
            sums[name] = parts[0].lower()
    return sums


def main() -> int:
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(OUT_DIR)
    with tempfile.TemporaryDirectory() as tmp:
        sums = read_sums(tmp)
        for name in ONNX:
            dest = os.path.join(OUT_DIR, name)
            fetch(name, dest)
            if name in sums and sha256(dest) != sums[name]:
                print(f"Контрольная сумма {name} не совпала", file=sys.stderr)
                return 1
        for asset in ZIPS:
            zpath = os.path.join(tmp, f"{asset}.zip")
            fetch(f"{asset}.zip", zpath)
            extract = os.path.join(tmp, f"x-{asset}")
            with zipfile.ZipFile(zpath) as zf:
                zf.extractall(extract)
            src = next((root for root, _d, files in os.walk(extract) if ASR_FILES[0] in files), None)
            if src is None:
                print(f"В {asset}.zip нет {ASR_FILES[0]}", file=sys.stderr)
                return 1
            target = os.path.join(OUT_DIR, asset)
            os.makedirs(target)
            for name in ASR_FILES:
                shutil.copy2(os.path.join(src, name), os.path.join(target, name))
                expected = sums.get(f"{asset}/{name}")
                if expected and sha256(os.path.join(target, name)) != expected:
                    print(f"Контрольная сумма {asset}/{name} не совпала", file=sys.stderr)
                    return 1
    print("Готово:", OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
