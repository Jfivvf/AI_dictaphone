import os
import re
from typing import Any, Dict, List

TASK_KEYWORDS = (
    "задание", "домашн", "сдать", "дедлайн", "подготовить",
    "коллоквиум", "лабораторн", "контрольн", "экзамен", "контест",
)
URGENT_KEYWORDS = ("срочн", "коллоквиум", "экзамен", "контрольн")


class DocumentError(Exception):
def extract_raw_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as err:
            raise DocumentError("Не установлен пакет pypdf (pip install pypdf).") from err
        try:
            reader = PdfReader(file_path)
            pages = []
            for number, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    pages.append(f"### Страница {number}\n{text}")
        except Exception as err:
            raise DocumentError(f"Не удалось прочитать PDF: {err}") from err
        return "\n\n".join(pages)

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError as err:
        raise DocumentError(f"Не удалось прочитать файл: {err}") from err


def read_document(file_path: str) -> Dict[str, str]:
    file_name = os.path.basename(file_path)
    return {
        "title": os.path.splitext(file_name)[0].replace("_", " "),
        "raw_text": extract_raw_text(file_path),
    }


def keyword_tasks_and_formulas(raw_text: str, file_name: str) -> Dict[str, List[Dict[str, Any]]]:
    """Простой разбор без нейросети: строки с ключевыми словами заданий и строки с формулами."""
    tasks: List[Dict[str, Any]] = []
    formulas: List[Dict[str, Any]] = []
    for idx, line in enumerate(raw_text.split("\n")):
        clean = line.strip()
        lower = clean.lower()
        if 10 < len(clean) < 180 and any(kw in lower for kw in TASK_KEYWORDS):
            tasks.append({
                "id": f"task-doc-{idx}",
                "task": re.sub(r"^[-*•\d.)\s]+", "", clean),
                "deadline": "По графику курса",
                "completed": False,
                "priority": "high" if any(w in lower for w in URGENT_KEYWORDS) else "medium",
            })
        if len(clean) > 4 and ("$" in clean or any(c in clean for c in ("\\frac", "\\int", "\\sum"))):
            formulas.append({
                "id": f"f-doc-{idx}",
                "title": f"Формула из {file_name}",
                "latex": clean.strip("$ "),
                "context": "Извлечено из документа",
            })
    return {"tasks": tasks[:10], "formulas": formulas[:12]}
