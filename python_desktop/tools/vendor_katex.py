"""Копирует KaTeX из node_modules в assets/katex (запускать из корня проекта: python python_desktop/tools/vendor_katex.py)."""
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
src = root / "node_modules" / "katex"
dst = Path(__file__).resolve().parents[1] / "assets" / "katex"

if not (src / "dist" / "katex.min.js").exists():
    sys.exit("Сначала выполните npm install в корне проекта.")

(dst / "fonts").mkdir(parents=True, exist_ok=True)
for name in ("katex.min.js", "katex.min.css"):
    shutil.copy2(src / "dist" / name, dst / name)
for font in (src / "dist" / "fonts").glob("*.woff2"):
    shutil.copy2(font, dst / "fonts" / font.name)
if (src / "LICENSE").exists():
    shutil.copy2(src / "LICENSE", dst / "LICENSE")
print(f"KaTeX скопирован в {dst}")
