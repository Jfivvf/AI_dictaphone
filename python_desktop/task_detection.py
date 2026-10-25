"""Поиск заданий и сроков в тексте без нейросети (запасной вариант, когда Ollama недоступна)."""
import re
from typing import Any, Dict, List, Optional

_MONTHS = r"(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)"
_WEEKDAYS = (
    r"(?:понедельник\w*|вторник\w*|сред[ауеы]\w*|четверг\w*|пятниц\w*|суббот\w*|воскресень\w*)"
)
_ORDINAL = (
    r"(?:перв|втор|трет|четвёрт|четверт|пят|шест|седьм|восьм|девят|десят|одиннадцат|двенадцат|"
    r"тринадцат|четырнадцат|пятнадцат|шестнадцат|семнадцат|восемнадцат|девятнадцат|двадцат|тридцат)\w*"
)

# Фразы со сроком: берём первую найденную как значение дедлайна.
_DEADLINE_RE = re.compile(
    "|".join([
        rf"(?:до|к)\s+(?:конца\s+)?(?:следующ\w+\s+)?{_WEEKDAYS}(?:\s*,?\s*\d{{1,2}}\s+{_MONTHS})?",
        rf"(?:до|к|на)\s+\d{{1,2}}(?:[.:]\d{{2}})?(?:\s+{_MONTHS}|\s*числа|\s*час\w*)?",
        rf"(?:до|к)\s+(?:конца\s+)?(?:(?:двадцать|тридцать)\s+)?{_ORDINAL}\s+{_MONTHS}",
        rf"\d{{1,2}}\s+{_MONTHS}",
        rf"(?:(?:двадцать|тридцать)\s+)?{_ORDINAL}\s+{_MONTHS}",
        r"\b\d{1,2}\.\d{2}(?:\.\d{2,4})?\b",
        r"(?:до|к|на)\s+следующ\w+\s+(?:занят\w+|пар\w+|лекци\w+|семинар\w+|неделе|неделю|практик\w+)",
        r"(?:до|к)\s+(?:конца\s+)?(?:недели|месяца|семестра|сессии|зачётной\s+недели)",
        r"через\s+(?:\d+|дв[ае]|три|четыре|пять|недел\w+)\s*\w*",
        r"на\s+этой\s+неделе|на\s+той\s+неделе",
        r"\b(?:сегодня|завтра|послезавтра)\b",
        rf"\b(?:в|на)\s+{_WEEKDAYS}",
    ]),
    re.IGNORECASE,
)

# Достаточно одного такого слова, чтобы считать фразу заданием.
_STRONG_RE = re.compile(
    r"домашн|\bдз\b|задани|задал|задам|задаёт|задает|задаётся|"
    r"\bсда(?:ть|йте|ёте|ете|ём|ем|ча|чи|вать)|дедлайн|срок\s+сдачи|"
    r"коллоквиум|контрольн|лабораторн|летучк|самостоятельн\w+\s+работ|типов\w+\s+расч[её]т|"
    r"курсов\w+\s+(?:работ|проект)",
    re.IGNORECASE,
)

# Эти слова считаются заданием только вместе с фразой о сроке.
_WEAK_RE = re.compile(
    r"подготов(?:ить|ьте|иться)|решить|решите|выучить|выучите|прочита(?:ть|йте)|прочесть|"
    r"повтор(?:ить|ите)|принести|принесите|напис(?:ать|ите)|выполн(?:ить|ите)|оформ(?:ить|ите)|"
    r"разобрать|разберите|доказать|докажите|реферат|доклад|отч[её]т|контест|проект|экзамен|зач[её]т",
    re.IGNORECASE,
)

_URGENT_RE = re.compile(r"срочн|обязательн|коллоквиум|контрольн|экзамен|зач[её]т|завтра|сегодня", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")

DEFAULT_DEADLINE = "К следующему занятию"


def _find_deadline(text: str) -> Optional[str]:
    match = _DEADLINE_RE.search(text)
    return re.sub(r"\s+", " ", match.group(0)).strip(" ,") if match else None


def extract_tasks(text: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Находит в тексте задания. Срок берётся из самой фразы или из следующего предложения."""
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text or "") if s and s.strip()]
    tasks: List[Dict[str, Any]] = []
    seen = set()
    skip_next = False

    for idx, sentence in enumerate(sentences):
        if skip_next:
            skip_next = False
            continue
        if not 12 <= len(sentence) <= 400:
            continue

        deadline = _find_deadline(sentence)
        is_task = bool(_STRONG_RE.search(sentence)) or (bool(_WEAK_RE.search(sentence)) and deadline is not None)
        if not is_task:
            continue

        task_text = re.sub(r"^[-*•\d.)\s]+", "", sentence)
        if deadline is None and idx + 1 < len(sentences):
            following_deadline = _find_deadline(sentences[idx + 1])
            if following_deadline:
                deadline = following_deadline
                task_text = f"{task_text} {sentences[idx + 1]}"
                skip_next = True

        key = task_text.lower()
        if key in seen:
            continue
        seen.add(key)
        tasks.append({
            "id": f"task-kw-{len(tasks)}",
            "task": task_text,
            "deadline": deadline or DEFAULT_DEADLINE,
            "completed": False,
            "priority": "high" if _URGENT_RE.search(task_text) else "medium",
        })
        if len(tasks) >= limit:
            break
    return tasks
