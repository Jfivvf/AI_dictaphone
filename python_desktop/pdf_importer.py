import os
from typing import Any, Dict, List
from task_detection import extract_structured_tasks, extract_tasks, merge_tasks

class DocumentError(Exception):
    pass

def extract_raw_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as err:
            raise DocumentError("Не установлен пакет pypdf") from err
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
    formulas: List[Dict[str, Any]] = []
    for idx, line in enumerate(raw_text.split("\n")):
        clean = line.strip()
        if len(clean) > 4 and ("$" in clean or any(c in clean for c in ("\\frac", "\\int", "\\sum"))):
            formulas.append({
                "id": f"f-doc-{idx}",
                "title": f"Формула из {file_name}",
                "latex": clean.strip("$ "),
                "context": "Извлечено из документа",
            })
    tasks = merge_tasks(extract_structured_tasks(raw_text), extract_tasks(raw_text))
    return {"tasks": tasks, "formulas": formulas[:12]}
