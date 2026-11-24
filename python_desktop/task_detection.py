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

_STRONG_RE = re.compile(
    r"домашн|\bдз\b|задани|задал|задам|задаёт|задает|задаётся|"
    r"\bсда(?:ть|йте|ёте|ете|ём|ем|ча|чи|вать)|дедлайн|срок\s+сдачи|"
    r"коллоквиум|контрольн|лабораторн|летучк|самостоятельн\w+\s+работ|типов\w+\s+расч[её]т|"
    r"курсов\w+\s+(?:работ|проект)",
    re.IGNORECASE,
)

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
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text or "") if s and s.strip()]
    tasks: List[Dict[str, Any]] = []
    seen = set()
    skip_next = False

    for idx, sentence in enumerate(sentences):
        if skip_next:
            skip_next = False
            continue
        if not 12 <= len(sentence) <= 400 or sentence.lstrip().startswith("#") or len(sentence.split()) < 3:
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


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_TASK_HEAD_RE = re.compile(r"задани|домашн|\bд/з\b|\bдз\b|упражнени|практическ\w+\s+работ", re.IGNORECASE)
_ITEM_RE = re.compile(r"^\s{0,3}(?:\d+[.)]|[-*+])\s+(.*)$")
_OPTIONAL_RE = re.compile(r"по\s+желанию|необязательн|дополнительн", re.IGNORECASE)


def _plain(text: str) -> str:
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"[^\w\s.,:;!?()\[\]{}<>/\\+\-–—=«»\"'$^|%№…→←↔]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_structured_tasks(text: str, limit: int = 20) -> List[Dict[str, Any]]:
    lines = (text or "").splitlines()
    heads: List[Any] = []
    in_fence = False
    fence_rows = set()
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            fence_rows.add(i)
            continue
        if in_fence:
            fence_rows.add(i)
            continue
        m = _HEADING_RE.match(line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2)))

    tasks: List[Dict[str, Any]] = []
    for n, (start, level, title) in enumerate(heads):
        if not _TASK_HEAD_RE.search(title):
            continue
        end = len(lines)
        for nxt_start, nxt_level, _t in heads[n + 1:]:
            if nxt_level <= level:
                end = nxt_start
                break
        body = [
            ln for j, ln in enumerate(lines[start + 1:end], start + 1)
            if not re.fullmatch(r"\s*(?:-{3,}|\*{3,}|_{3,})\s*", ln) and not ln.strip().startswith("```")
        ]
        head_deadline = _find_deadline(_plain(title))

        items: List[List[str]] = []
        after_blank = False
        for ln in body:
            if not ln.strip():
                after_blank = True
                continue
            m = _ITEM_RE.match(ln)
            if m:
                items.append([m.group(1)])
            elif items and items[-1][-1] != "" and after_blank and not ln.startswith("  "):
                break  # абзац после списка («Совет: …») к заданиям не относится
            elif items and ln.strip():
                items[-1].append(ln)
            elif not items and ln.strip():
                items.append([ln])
                items[-1].append("")  # метка: абзац без списка, дальше дописываем в него же
            after_blank = False
        if items and all(it[-1] == "" for it in items):
            # абзацы без списка: склеиваем в одну задачу
            items = [[ln for it in items for ln in it if ln]]
        else:
            items = [[ln for ln in it if ln] for it in items]

        for it in items:
            task_text = _plain(" ".join(it))
            if len(task_text) < 12:
                continue
            tasks.append({
                "id": f"task-md-{len(tasks)}",
                "task": task_text,
                "deadline": _find_deadline(task_text) or head_deadline or DEFAULT_DEADLINE,
                "completed": False,
                "priority": "low" if _OPTIONAL_RE.search(task_text) or _OPTIONAL_RE.search(title)
                else ("high" if _URGENT_RE.search(task_text) else "medium"),
            })
            if len(tasks) >= limit:
                return tasks
    return tasks


def _words(text: str) -> set:
    return {w.lower() for w in re.findall(r"\w{4,}", text)}


def merge_tasks(primary: List[Dict[str, Any]], extra: List[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
    result = list(primary)
    known = [_words(t.get("task", "")) for t in result]
    for task in extra:
        words = _words(task.get("task", ""))
        if not words:
            continue
        if any(k and len(words & k) / min(len(words), len(k)) >= 0.5 for k in known):
            continue
        result.append(task)
        known.append(words)
    return result[:limit]
