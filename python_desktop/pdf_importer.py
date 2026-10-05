"""
Модуль интеллектуального импорта PDF и Markdown файлов для AxAI (Python + PySide6).
Автоматически определяет: перед нами готовая лекция или «сырой» документ,
и при необходимости формирует подробный академический конспект из 6 разделов через Gemini API (либо локально через pypdf).
"""
import os
import re
import json
from datetime import datetime
from typing import Dict, Any, List


def repair_corrupted_latex(text: str) -> str:
    """Восстанавливает LaTeX-команды (\frac, \beta, \theta, \times, \right, \nabla), если они были искажены."""
    if not text:
        return ""
    s = str(text)
    s = re.sub(r"\x0c(rac|orall|lat|rown|box|int)", r"\\f\1", s)
    s = s.replace("\x0c", "\\f")
    s = re.sub(r"\x08(eta|egin|inom|ar|f|ig|ullet|oxed|ot|ackslash|oldsymbol)", r"\\b\1", s)
    s = s.replace("\x08", "\\b")
    s = re.sub(r"\x09(heta|au|imes|ext|ilde|an|anh|op|riangle|o\b|herefore|iny)", r"\\t\1", s)
    s = re.sub(r"\x0d(ight|ightarrow|ho|angle|ceil|floor|ule|m)", r"\\r\1", s)
    s = re.sub(r"\n(abla|eq\b|u\b|ot\b|atural|exists|ewline|mid|parallel|otin)", r"\\n\1", s)
    return s


def extract_raw_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            pages = []
            for i, page in enumerate(reader.pages):
                page_text = (page.extract_text() or "").strip()
                if page_text:
                    pages.append(f"### Страница {i + 1}\n{page_text}")
            return "\n\n".join(pages)
        except Exception as e:
            return f"Не удалось прочитать PDF через pypdf: {e}"
    else:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            return f"Ошибка чтения файла: {e}"


def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key and key != "MY_GEMINI_API_KEY":
        return key
    for env_path in [
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
    ]:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val and val != "MY_GEMINI_API_KEY":
                                return val
            except Exception:
                pass
    return ""


def parse_pdf_document(file_path: str) -> Dict[str, Any]:
    """
    Читает PDF/MD/TXT файл, автоматически анализирует его структуру через Gemini API (если задан GEMINI_API_KEY)
    или локальным парсером, возвращая полный структурированный конспект, формулы и дедлайны.
    """
    raw_text = extract_raw_text(file_path)
    file_name = os.path.basename(file_path)
    clean_title = os.path.splitext(file_name)[0].replace("_", " ")

    api_key = get_gemini_api_key()
    if api_key and len(raw_text.strip()) > 10:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = f"""Ты — профессор и составитель фундаментальных университетских конспектов AxAI.
Пользователь загрузил файл: "{file_name}".

Определи состояние документа ("isAlreadyStructured"):
- Если это УЖЕ аккуратный, структурированный конспект -> сохрани авторский текст без сокращений, поправив переносы строк и формулы LaTeX ($...$ и $$...$$).
- Если это «сырой» текст из PDF, слайды или заметки -> преобразуй ВЕСЬ материал в подробный, фундаментальный университетский конспект ("summaryMarkdown") из 6 разделов:
  ## 1. Введение и ключевая идея темы
  ## 2. Фундаментальные понятия и строгие определения
  ## 3. Детальный теоретический разбор по разделам (### 3.1, ### 3.2...)
  ## 4. Математический аппарат, вывод формул и расшифровка переменных
  ## 5. Подробный разбор практических примеров и задач
  ## 6. Тонкости и развернутые ответы на вопросы к экзамену

Верни строго JSON:
{{
  "isAlreadyStructured": false,
  "title": "Тема лекции",
  "subject": "Название предмета",
  "lecturer": "Преподаватель или Материалы курса",
  "summaryMarkdown": "Полный подробный конспект...",
  "actionItems": [{{"task": "...", "deadline": "...", "priority": "high"}}],
  "latexFormulas": [{{"title": "...", "latex": "...", "context": "..."}}]
}}

Текст документа:
{raw_text[:60000]}"""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            resp_text = (response.text or "").strip()
            resp_text = re.sub(r"^```json\s*|\s*```$", "", resp_text, flags=re.MULTILINE).strip()
            data = json.loads(resp_text)

            tasks = []
            for idx, item in enumerate(data.get("actionItems", [])):
                tasks.append({
                    "id": f"task-ai-{idx}-{int(datetime.now().timestamp())}",
                    "task": item.get("task", "Повторить материал лекции"),
                    "deadline": item.get("deadline", "К следующему занятию"),
                    "completed": False,
                    "priority": item.get("priority", "medium") if item.get("priority") in ("high", "medium", "low") else "medium",
                })

            formulas = []
            for idx, f_item in enumerate(data.get("latexFormulas", [])):
                formulas.append({
                    "id": f"f-ai-{idx}",
                    "title": f_item.get("title", "Формула"),
                    "latex": repair_corrupted_latex(f_item.get("latex", "")),
                    "context": f_item.get("context", ""),
                })

            return {
                "title": data.get("title") or clean_title,
                "subject": data.get("subject") or "Учебная дисциплина",
                "lecturer": data.get("lecturer") or "Материалы курса",
                "date": datetime.now().strftime("%d.%m.%Y"),
                "duration_min": 60,
                "text": repair_corrupted_latex(data.get("summaryMarkdown") or raw_text),
                "raw_transcript": raw_text,
                "tasks": tasks,
                "formulas": formulas,
            }
        except Exception as e:
            print(f"Интеллектуальная структуризация через Gemini недоступна, используем локальный парсер: {e}")

    # Локальный разбор задач и формул
    task_keywords = [
        "задание", "домашн", "сдать", "дедлайн", "подготовить",
        "коллоквиум", "лабораторн", "контрольн", "экзамен", "контест"
    ]

    tasks: List[Dict[str, Any]] = []
    formulas: List[Dict[str, Any]] = []
    lines = raw_text.split("\n")

    for idx, line in enumerate(lines):
        line_clean = line.strip()
        lower = line_clean.lower()
        if any(kw in lower for kw in task_keywords) and 10 < len(line_clean) < 180:
            priority = "high" if any(w in lower for w in ["срочн", "коллоквиум", "экзамен", "контрольн"]) else "medium"
            tasks.append({
                "id": f"task-pdf-{idx}",
                "task": re.sub(r"^[-*•\d.)\s]+", "", line_clean),
                "deadline": "По графику учебного курса",
                "completed": False,
                "priority": priority,
            })

        if ("$" in line_clean or "\\frac" in line_clean or "\\int" in line_clean or "\\sum" in line_clean) and len(line_clean) > 4:
            formulas.append({
                "id": f"f-pdf-{idx}",
                "title": f"Формула из {file_name}",
                "latex": line_clean.strip("$ "),
                "context": "Извлечено из документа",
            })

    if not tasks:
        tasks.append({
            "id": "task-default-pdf",
            "task": f"Ознакомиться с материалами файла {file_name}",
            "deadline": "К следующему занятию",
            "completed": False,
            "priority": "medium",
        })

    return {
        "title": clean_title,
        "subject": "Импортированные материалы",
        "lecturer": "Материалы курса",
        "date": datetime.now().strftime("%d.%m.%Y"),
        "duration_min": 60,
        "text": f"## {clean_title}\n\n{repair_corrupted_latex(raw_text)}",
        "raw_transcript": raw_text,
        "tasks": tasks[:10],
        "formulas": formulas[:12],
    }
