import html
import json
import re
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional
import markdown as md_lib


def repair_corrupted_latex(text: str) -> str:
    if not text:
        return ""
    s = str(text)
    s = re.sub(r"\x0c(rac|orall|lat|rown|box|int)", r"\\f\1", s)
    s = s.replace("\x0c", "\\f")
    s = re.sub(r"\x08(eta|egin|inom|ar|f|ig|ullet|oxed|ot|ackslash|oldsymbol)", r"\\b\1", s)
    s = s.replace("\x08", "\\b")
    s = re.sub(r"\x09(heta|au|imes|ext|ilde|an|anh|op|riangle|o\b|herefore|iny)", r"\\t\1", s)
    s = re.sub(r"\x0d(ight|ightarrow|ho|angle|ceil|floor|ule|m)", r"\\r\1", s)
    s = re.sub(r"\n(abla|eq\b|u\b|ot\b|atural|exists|ewline|mid|parallel|otin|eg\b)", r"\\n\1", s)
    return s


def normalize_math_delimiters(text: str) -> str:
    text = re.sub(r"\\\[([\s\S]*?)\\\]", lambda m: f"\n$$\n{m.group(1).strip()}\n$$\n", text)
    return re.sub(r"\\\(([\s\S]*?)\\\)", lambda m: f"${m.group(1).strip()}$", text)


def unpack_raw_json_lecture_if_needed(lec: Dict[str, Any]) -> Dict[str, Any]:
    raw_text = (lec.get("text") or "").strip()
    if '"summaryMarkdown"' not in raw_text:
        return lec

    first = raw_text.find("{")
    last = raw_text.rfind("}")
    if first == -1 or last <= first:
        return lec

    candidate = raw_text[first : last + 1]
    fixed = re.sub(r'(?<!\\)\\(?![\\"/bfnrt]|u[0-9a-fA-F]{4})', r"\\\\", candidate)
    try:
        parsed = json.loads(fixed)
    except Exception:
        return lec
    if not isinstance(parsed, dict):
        return lec

    summary = parsed.get("summaryMarkdown")
    if isinstance(summary, str) and summary.strip():
        lec["text"] = repair_corrupted_latex(summary.strip())

    raw_items = parsed.get("actionItems") or parsed.get("tasks") or []
    if isinstance(raw_items, list) and raw_items and not lec.get("tasks"):
        lec["tasks"] = [
            {
                "id": f"{lec.get('id', 'lec')}-t-{i}",
                "task": item.get("task", "Повторить материал"),
                "deadline": item.get("deadline", "К следующему занятию"),
                "priority": item.get("priority", "medium"),
                "completed": bool(item.get("completed", False)),
            }
            for i, item in enumerate(raw_items)
            if isinstance(item, dict)
        ]

    raw_formulas = parsed.get("latexFormulas") or parsed.get("formulas") or []
    if isinstance(raw_formulas, list) and raw_formulas and not lec.get("formulas"):
        lec["formulas"] = [
            {
                "id": f"{lec.get('id', 'lec')}-f-{i}",
                "title": f.get("title", "Формула"),
                "latex": repair_corrupted_latex(f.get("latex", "")),
                "context": f.get("context", ""),
            }
            for i, f in enumerate(raw_formulas)
            if isinstance(f, dict)
        ]

    raw_segs = parsed.get("segments") or []
    if isinstance(raw_segs, list) and raw_segs and not lec.get("segments"):
        lec["segments"] = [
            {
                "start": float(idx * 30),
                "end": float((idx + 1) * 30),
                "time": s.get("time", f"{idx // 2:02d}:{(idx % 2) * 30:02d}"),
                "text": s.get("text", ""),
            }
            for idx, s in enumerate(raw_segs)
            if isinstance(s, dict) and s.get("text")
        ]
    return lec


_FENCE_RE = re.compile(r"```.*?```", re.S)
_CODE_SPAN_RE = re.compile(r"`[^`\n]+`")
_BLOCK_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.S)
_INLINE_MATH_RE = re.compile(r"(?<![\\$])\$(?!\s)([^$\n]+?)(?<!\s)\$")
_BLOCK_TOKEN_RE = re.compile(r"(?:<p>\s*)?AXMB(\d+)X(?:\s*</p>)?")
_INLINE_TOKEN_RE = re.compile(r"AXMI(\d+)X")
_CODE_TOKEN_RE = re.compile(r"AXCD(\d+)X")


def _math_attr(latex: str) -> str:
    return html.escape(latex.strip(), quote=True)


def markdown_to_html(markdown_text: str) -> str:
    text = normalize_math_delimiters(repair_corrupted_latex(markdown_text or ""))
    code_parts: List[str] = []

    def stash_code(match: "re.Match[str]") -> str:
        code_parts.append(match.group(0))
        return f"AXCD{len(code_parts) - 1}X"

    text = _FENCE_RE.sub(stash_code, text)
    text = _CODE_SPAN_RE.sub(stash_code, text)
    blocks: List[str] = []
    inlines: List[str] = []

    def stash_block(match: "re.Match[str]") -> str:
        blocks.append(match.group(1))
        return f"\n\nAXMB{len(blocks) - 1}X\n\n"

    def stash_inline(match: "re.Match[str]") -> str:
        inlines.append(match.group(1))
        return f"AXMI{len(inlines) - 1}X"

    text = _BLOCK_MATH_RE.sub(stash_block, text)
    text = _INLINE_MATH_RE.sub(stash_inline, text)
    text = text.replace("<", "&lt;")
    text = _CODE_TOKEN_RE.sub(lambda m: code_parts[int(m.group(1))], text)
    out = md_lib.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])

    def block_html(match: "re.Match[str]") -> str:
        latex = blocks[int(match.group(1))]
        return f'<div class="math-block" data-latex="{_math_attr(latex)}">{html.escape(latex.strip())}</div>'

    def inline_html(match: "re.Match[str]") -> str:
        latex = inlines[int(match.group(1))]
        return f'<span class="math-inline" data-latex="{_math_attr(latex)}">{html.escape(latex.strip())}</span>'

    out = _BLOCK_TOKEN_RE.sub(block_html, out)
    return _INLINE_TOKEN_RE.sub(inline_html, out)


def bundled_katex_dir() -> Optional[Path]:
    """Папка с KaTeX, поставляемая вместе с приложением (assets/katex)."""
    path = Path(__file__).resolve().parent.parent / "assets" / "katex"
    return path if (path / "katex.min.js").exists() and (path / "katex.min.css").exists() else None


_THEMES = {
    "dark": {
        "bg": "#121215", "text": "#e4e4e7", "heading": "#ffffff", "accent": "#818cf8",
        "border": "#312e81", "panel": "#18181f", "muted": "#a1a1aa", "inline_bg": "#1e1b4b",
        "inline_fg": "#c7d2fe", "rule": "#27272a",
    },
    "light": {
        "bg": "#ffffff", "text": "#111827", "heading": "#0f172a", "accent": "#4338ca",
        "border": "#cbd5e1", "panel": "#f8fafc", "muted": "#475569", "inline_bg": "transparent",
        "inline_fg": "inherit", "rule": "#e2e8f0",
    },
}

_PAGE_TEMPLATE = Template("""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
$katex_css
<style>
  :root {
    --bg: $bg; --text: $text; --heading: $heading; --accent: $accent; --border: $border;
    --panel: $panel; --muted: $muted; --rule: $rule;
  }
  * { box-sizing: border-box; }
  html, body { background: var(--bg); }
  body {
    margin: 0; padding: $padding; color: var(--text);
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, "Noto Sans", "Helvetica Neue", Arial, sans-serif;
    font-size: $font_size; line-height: 1.6;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  h1 { color: var(--heading); font-size: 1.55em; margin: 0 0 0.4em; line-height: 1.25; }
  h2 { color: var(--accent); font-size: 1.2em; margin: 1.5em 0 0.5em; padding-bottom: 0.2em; border-bottom: 1px solid var(--border); break-after: avoid; }
  h3 { color: var(--heading); font-size: 1.05em; margin: 1.2em 0 0.4em; break-after: avoid; }
  p { margin: 0.5em 0 0.7em; orphans: 3; widows: 3; }
  ul, ol { margin: 0.4em 0 0.8em; padding-left: 1.6em; }
  li { margin-bottom: 0.25em; }
  strong { color: var(--heading); }
  hr { border: none; border-top: 1px solid var(--rule); margin: 1.2em 0; }
  code { font-family: "JetBrains Mono", Consolas, monospace; font-size: 0.9em; background: var(--panel); padding: 0.1em 0.35em; border-radius: 4px; }
  pre { background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; padding: 0.7em 0.9em; overflow-x: auto; break-inside: avoid; }
  pre code { background: none; padding: 0; }
  blockquote { margin: 0.8em 0; padding: 0.1em 1em; border-left: 3px solid var(--border); color: var(--muted); }
  table { border-collapse: collapse; margin: 0.8em 0; break-inside: avoid; }
  th, td { border: 1px solid var(--border); padding: 0.35em 0.7em; text-align: left; }
  th { background: var(--panel); color: var(--heading); }
  .doc-header { border-bottom: 2px solid var(--accent); padding-bottom: 0.7em; margin-bottom: 1.2em; }
  .doc-meta { color: var(--muted); font-size: 0.85em; }
  .math-inline { background: $inline_bg; color: $inline_fg; border-radius: 4px; padding: 0 0.15em; }
  .math-block { background: var(--panel); border-left: 3px solid var(--accent); border-radius: 6px; padding: 0.5em 1em; margin: 0.8em 0; text-align: center; overflow-x: auto; break-inside: avoid; }
  .katex-display { margin: 0.3em 0; }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 0.6em 1em; margin: 0.7em 0; break-inside: avoid; }
  .card-title { color: var(--accent); font-weight: 600; font-size: 0.95em; }
  .card-note { color: var(--muted); font-size: 0.85em; }
  .card .math-block { background: transparent; border: none; padding: 0.2em 0; margin: 0.2em 0; }
  .task { display: flex; gap: 0.6em; margin: 0.35em 0; break-inside: avoid; }
  .cb { flex: none; width: 0.9em; height: 0.9em; margin-top: 0.3em; border: 1.5px solid var(--muted); border-radius: 3px; }
  .cb.done { background: var(--accent); border-color: var(--accent); }
  .task.done .task-text { color: var(--muted); text-decoration: line-through; }
  .task-due { color: var(--muted); font-size: 0.85em; }
  .mark { margin: 0.25em 0; break-inside: avoid; }
  .mark-time { font-family: "JetBrains Mono", Consolas, monospace; color: var(--accent); margin-right: 0.6em; }
</style>
</head>
<body>
$header
<main>$body</main>
$katex_script
</body>
</html>
""")

_RENDER_SCRIPT = """<script src="$js_url"></script>
<script>
document.addEventListener("DOMContentLoaded", async function () {
  window.__axError = "";
  try {
    document.querySelectorAll("[data-latex]").forEach(function (el) {
      var display = el.classList.contains("math-block");
      try {
        katex.render(el.getAttribute("data-latex"), el, {
          displayMode: display, throwOnError: false, strict: "ignore", trust: false
        });
      } catch (e) {
        window.__axError += String(e) + "; ";
      }
    });
    void document.body.offsetHeight;
    if (document.fonts && document.fonts.ready) { await document.fonts.ready; }
  } catch (e) {
    window.__axError += String(e);
  }
  window.__axDone = true;
});
</script>"""


def _format_mmss(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _formulas_html(formulas: List[Dict[str, Any]]) -> str:
    if not formulas:
        return ""
    parts = ["<h2>Ключевые формулы</h2>"]
    for f in formulas:
        latex = repair_corrupted_latex(str(f.get("latex", ""))).strip().strip("$").strip()
        if not latex:
            continue
        note = html.escape(str(f.get("context", "")))
        parts.append(
            '<div class="card">'
            f'<div class="card-title">{html.escape(str(f.get("title", "Формула")))}</div>'
            f'<div class="math-block" data-latex="{_math_attr(latex)}">{html.escape(latex)}</div>'
            + (f'<div class="card-note">{note}</div>' if note else "")
            + "</div>"
        )
    return "\n".join(parts)


def _tasks_html(tasks: List[Dict[str, Any]]) -> str:
    if not tasks:
        return ""
    parts = ["<h2>Задачи и дедлайны</h2>"]
    for t in tasks:
        done = bool(t.get("completed"))
        parts.append(
            f'<div class="task{" done" if done else ""}"><span class="cb{" done" if done else ""}"></span>'
            f'<div><span class="task-text">{html.escape(str(t.get("task", "")))}</span> '
            f'<span class="task-due">— срок: {html.escape(str(t.get("deadline", "")))}</span></div></div>'
        )
    return "\n".join(parts)


def _bookmarks_html(bookmarks: List[Dict[str, Any]]) -> str:
    if not bookmarks:
        return ""
    parts = ["<h2>Важные моменты записи</h2>"]
    for b in bookmarks:
        note = html.escape(str(b.get("note", ""))) or "Метка"
        parts.append(
            f'<div class="mark"><span class="mark-time">{_format_mmss(int(b.get("time_sec", 0)))}</span>{note}</div>'
        )
    return "\n".join(parts)


def render_lecture_html(
    lecture: Dict[str, Any],
    katex_dir: Optional[Path] = None,
    dark_mode: bool = True,
    with_header: bool = False,
) -> str:
    """Собирает страницу конспекта. Для PDF: dark_mode=False, with_header=True."""
    theme = _THEMES["dark" if dark_mode else "light"]
    header = ""
    if with_header:
        meta = " · ".join(
            html.escape(str(p))
            for p in (lecture.get("subject"), lecture.get("lecturer"), lecture.get("date"))
            if p
        )
        header = (
            f'<header class="doc-header"><h1>{html.escape(str(lecture.get("title", "Лекция")))}</h1>'
            f'<div class="doc-meta">{meta}</div></header>'
        )

    body = markdown_to_html(lecture.get("text", ""))
    body += _formulas_html(lecture.get("formulas") or [])
    body += _tasks_html(lecture.get("tasks") or []) if with_header else ""
    body += _bookmarks_html(lecture.get("bookmarks") or []) if with_header else ""

    katex_css = katex_script = ""
    if katex_dir is not None:
        base = Path(katex_dir).resolve()
        katex_css = f'<link rel="stylesheet" href="{(base / "katex.min.css").as_uri()}">'
        katex_script = Template(_RENDER_SCRIPT).substitute(js_url=(base / "katex.min.js").as_uri())

    return _PAGE_TEMPLATE.safe_substitute(
        **theme,
        padding="20px 26px" if dark_mode else "0",
        font_size="14px" if dark_mode else "11pt",
        katex_css=katex_css,
        katex_script=katex_script,
        header=header,
        body=body,
    )


def markdown_to_latex_body(raw_markdown: str) -> str:
    clean_md = normalize_math_delimiters(repair_corrupted_latex(raw_markdown))
    lines = clean_md.split("\n")
    out: List[str] = []
    state = {"ul": False, "ol": False}
    in_block_math = False
    math_buf: List[str] = []

    def close_lists() -> None:
        if state["ul"]:
            out.append("\\end{itemize}")
            state["ul"] = False
        if state["ol"]:
            out.append("\\end{enumerate}")
            state["ol"] = False

    def format_inline(text: str) -> str:
        parts = re.split(r"(\$[^$]+\$)", text)
        res = []
        for part in parts:
            if part.startswith("$") and part.endswith("$") and len(part) > 2:
                res.append(part)
            else:
                s = part.replace("%", "\\%").replace("&", "\\&").replace("#", "\\#").replace("_", "\\_")
                s = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", s)
                s = re.sub(r"\*([^*]+)\*", r"\\textit{\1}", s)
                s = re.sub(r"`([^`]+)`", r"\\texttt{\1}", s)
                res.append(s)
        return "".join(res)

    for line in lines:
        trimmed = line.strip()
        if trimmed.startswith("$$") and trimmed.endswith("$$") and len(trimmed) > 4:
            close_lists()
            out += ["\\begin{equation*}", trimmed[2:-2].strip(), "\\end{equation*}"]
            continue
        if trimmed == "$$":
            close_lists()
            if not in_block_math:
                in_block_math, math_buf = True, []
            else:
                in_block_math = False
                out += ["\\begin{equation*}", *math_buf, "\\end{equation*}"]
            continue
        if in_block_math:
            math_buf.append(line)
            continue

        for prefix, command in (("### ", "subsubsection*"), ("## ", "subsection*"), ("# ", "section*")):
            if trimmed.startswith(prefix):
                close_lists()
                out.append(f"\\{command}{{{format_inline(trimmed[len(prefix):])}}}")
                break
        else:
            if trimmed.startswith("- ") or trimmed.startswith("* "):
                if state["ol"]:
                    out.append("\\end{enumerate}")
                    state["ol"] = False
                if not state["ul"]:
                    out.append("\\begin{itemize}")
                    state["ul"] = True
                out.append(f"  \\item {format_inline(trimmed[2:])}")
                continue
            m = re.match(r"^(\d+)\.\s+(.*)", trimmed)
            if m:
                if state["ul"]:
                    out.append("\\end{itemize}")
                    state["ul"] = False
                if not state["ol"]:
                    out.append("\\begin{enumerate}")
                    state["ol"] = True
                out.append(f"  \\item {format_inline(m.group(2))}")
                continue
            close_lists()
            out.append("" if not trimmed else format_inline(line))

    close_lists()
    return "\n".join(out)


def export_lecture_to_markdown(lec: Dict[str, Any], save_path: str) -> None:
    body = repair_corrupted_latex(lec.get("text", ""))
    md = f"# {lec.get('title', '')}\n\n"
    md += f"- **Предмет:** {lec.get('subject', '')}\n"
    md += f"- **Преподаватель:** {lec.get('lecturer', '')}\n"
    md += f"- **Дата:** {lec.get('date', '')}\n\n---\n\n{body}\n\n"

    tasks = lec.get("tasks", [])
    if tasks:
        md += "---\n\n## Задачи и дедлайны\n\n"
        for t in tasks:
            mark = "x" if t.get("completed") else " "
            md += f"- [{mark}] **{t.get('task', '')}** *(Срок: {t.get('deadline', '')})*\n"

    with open(save_path, "w", encoding="utf-8-sig") as f:
        f.write(md)


def export_lecture_to_latex(lec: Dict[str, Any], save_path: str) -> None:
    body_tex = markdown_to_latex_body(lec.get("text", ""))
    tex = (
        "\\documentclass[12pt,a4paper]{article}\n"
        "\\usepackage[utf8]{inputenc}\n"
        "\\usepackage[T2A]{fontenc}\n"
        "\\usepackage[russian]{babel}\n"
        "\\usepackage{amsmath,amssymb,amsfonts}\n"
        "\\usepackage[margin=2cm]{geometry}\n"
        "\\usepackage{hyperref}\n\n"
        f"\\title{{{lec.get('title', '')}}}\n"
        f"\\author{{{lec.get('lecturer', '')} \\\\ \\small {lec.get('subject', '')}}}\n"
        f"\\date{{{lec.get('date', '')}}}\n\n"
        "\\begin{document}\n\\maketitle\n\n"
        f"{body_tex}\n\n"
    )
    tasks = lec.get("tasks", [])
    if tasks:
        tex += "\\section*{Задачи и дедлайны}\n\\begin{itemize}\n"
        for t in tasks:
            tex += f"  \\item \\textbf{{{t.get('task', '')}}} --- \\textit{{Срок: {t.get('deadline', '')}}}\n"
        tex += "\\end{itemize}\n\n"
    tex += "\\end{document}\n"

    with open(save_path, "w", encoding="utf-8-sig") as f:
        f.write(tex)
