"""
Модуль извлечения текста и структуры из PDF файлов для Lectura AI.
Использует библиотеку pypdf для локального чтения без интернета.
"""
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List

def parse_pdf_document(file_path: str) -> Dict[str, Any]:
    """
    Извлекает текст из PDF, находит потенциальные формулы и домашние задания.
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        full_text = ""
        
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            full_text += f"\n\n### Страница {i + 1}\n" + page_text.strip()
    except Exception as e:
        full_text = f"Не удалось прочитать PDF файл: {str(e)}"

    file_name = os.path.basename(file_path)
    title = os.path.splitext(file_name)[0].replace("_", " ")

    # Поиск домашних заданий и дедлайнов по ключевым словам
    task_keywords = [
        "задание", "домашн", "сдать", "дедлайн", "подготовить", 
        "коллоквиум", "лабораторн", "контрольн", "экзамен", "контест"
    ]
    
    tasks: List[Dict[str, Any]] = []
    lines = full_text.split("\n")
    for idx, line in enumerate(lines):
        line_clean = line.strip()
        lower = line_clean.lower()
        if any(kw in lower for kw in task_keywords) and 10 < len(line_clean) < 180:
            tasks.append({
                "id": f"task-pdf-{idx}",
                "task": re.sub(r"^[-*•\d.)\s]+", "", line_clean),
                "deadline": "По графику учебного курса",
                "completed": False,
                "priority": "high" if "срочно" in lower or "коллоквиум" in lower else "medium"
            })

    if not tasks:
        tasks.append({
            "id": f"task-default-pdf",
            "task": f"Ознакомиться с материалами файла {file_name}",
            "deadline": "К следующему занятию",
            "completed": False,
            "priority": "medium"
        })

    return {
        "title": title,
        "subject": "Импортированные материалы",
        "lecturer": "Материалы курса (PDF)",
        "date": datetime.now().strftime("%d %B %Y"),
        "duration_min": 60,
        "text": full_text,
        "tasks": tasks[:8]
    }
