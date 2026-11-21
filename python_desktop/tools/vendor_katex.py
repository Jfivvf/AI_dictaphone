import re
import shutil
import sys
import urllib.request
from pathlib import Path

VERSION = "0.16.11"
BASE = f"https://cdn.jsdelivr.net/npm/katex@{VERSION}"
DST = Path(__file__).resolve().parents[1] / "assets" / "katex"
NODE_SRC = Path(__file__).resolve().parents[2] / "node_modules" / "katex"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "AxAI-vendor-katex"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    if not data:
        raise RuntimeError(f"Пустой ответ: {url}")
    return data


def from_node_modules() -> None:
    (DST / "fonts").mkdir(parents=True, exist_ok=True)
    for name in ("katex.min.js", "katex.min.css"):
        shutil.copy2(NODE_SRC / "dist" / name, DST / name)
    for font in (NODE_SRC / "dist" / "fonts").glob("*.woff2"):
        shutil.copy2(font, DST / "fonts" / font.name)
    if (NODE_SRC / "LICENSE").exists():
        shutil.copy2(NODE_SRC / "LICENSE", DST / "LICENSE")


def from_cdn() -> None:
    (DST / "fonts").mkdir(parents=True, exist_ok=True)
    (DST / "katex.min.js").write_bytes(fetch(f"{BASE}/dist/katex.min.js"))
    css = fetch(f"{BASE}/dist/katex.min.css")
    (DST / "katex.min.css").write_bytes(css)
    fonts = sorted(set(re.findall(rb"fonts/(KaTeX_[A-Za-z0-9_-]+\.woff2)", css)))
    if not fonts:
        raise RuntimeError("В katex.min.css не найдены шрифты.")
    for i, name in enumerate(fonts, 1):
        text = name.decode("ascii")
        (DST / "fonts" / text).write_bytes(fetch(f"{BASE}/dist/fonts/{text}"))
        print(f"  шрифт {i}/{len(fonts)}: {text}")
    try:
        (DST / "LICENSE").write_bytes(fetch(f"{BASE}/LICENSE"))
    except Exception:
        pass


def main() -> None:
    try:
        if (NODE_SRC / "dist" / "katex.min.js").exists():
            from_node_modules()
        else:
            from_cdn()
    except Exception as err:
        sys.exit(f"Не удалось установить KaTeX: {err}\nПроверьте интернет и повторите.")
    print(f"KaTeX {VERSION} установлен в {DST}")


if __name__ == "__main__":
    main()
