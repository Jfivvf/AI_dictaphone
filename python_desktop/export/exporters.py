"""
Модуль экспорта (.PDF, .MD, .TEX) и офлайн-рендеринга математических формул LaTeX для AxAI (Python + PySide6).

Реализует рекомендации код-ревью:
1. Полноценный рендеринг формул LaTeX ($...$ и $$...$$) в нативном приложении и при экспорте в PDF:
   - Поддерживает локально закэшированный KaTeX в `~/AxAI_Storage/katex/` (без зависимости от CDN).
   - Имеет встроенный автономный математический типограф `format_latex_math_offline()`, который
     мгновенно превращает выражения LaTeX (`\\frac{a}{b}`, `\\neg x \\equiv x \\to 0`, `S_1`, `x^2`,
     греческие буквы, интегралы, суммы, кванторы, штрих Шеффера, стрелку Пирса) в чистую математическую
     HTML-верстку — работает 100% офлайн и в `QWebEngineView`, и в `QTextBrowser`, и в `QPrinter` PDF!
2. Автоматическая распаковка «сырого» JSON (`{"summaryMarkdown": ...}`), если нейросеть вернула JSON-строку.
"""
import os
import re
import html
import json
import urllib.request
from typing import Dict, Any, List, Optional


def repair_corrupted_latex(text: str) -> str:
    """Восстанавливает LaTeX-команды (\\frac, \\beta, \\theta, \\times, \\right, \\nabla, \\equiv)."""
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


def unpack_raw_json_lecture_if_needed(lec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Если в поле `text` лекции случайно сохранился сырой JSON (`{"summaryMarkdown": "...", ...}`),
    автоматически распаковывает конспект, задачи, формулы и сегменты стенограммы.
    """
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

    if isinstance(parsed.get("summaryMarkdown"), str) and parsed["summaryMarkdown"].strip():
        lec["text"] = repair_corrupted_latex(parsed["summaryMarkdown"].strip())

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


# Таблица математических символов LaTeX -> Unicode для 100% офлайн-рендеринга
LATEX_SYMBOLS = {
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ", r"\epsilon": "ε",
    r"\varepsilon": "ε", r"\zeta": "ζ", r"\eta": "η", r"\theta": "θ", r"\vartheta": "ϑ",
    r"\iota": "ι", r"\kappa": "κ", r"\lambda": "λ", r"\mu": "μ", r"\nu": "ν",
    r"\xi": "ξ", r"\pi": "π", r"\rho": "ρ", r"\sigma": "σ", r"\tau": "τ",
    r"\upsilon": "υ", r"\phi": "φ", r"\varphi": "ϕ", r"\chi": "χ", r"\psi": "ψ",
    r"\omega": "ω", r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ",
    r"\Xi": "Ξ", r"\Pi": "Π", r"\Sigma": "Σ", r"\Phi": "Φ", r"\Psi": "Ψ", r"\Omega": "Ω",
    r"\equiv": "≡", r"\approx": "≈", r"\neq": "≠", r"\ne": "≠", r"\leq": "≤", r"\le": "≤",
    r"\geq": "≥", r"\ge": "≥", r"\ll": "≪", r"\gg": "≫", r"\pm": "±", r"\mp": "∓",
    r"\times": "×", r"\cdot": "·", r"\div": "÷", r"\ast": "∗", r"\star": "⋆",
    r"\circ": "∘", r"\bullet": "•", r"\oplus": "⊕", r"\otimes": "⊗",
    r"\neg": "¬", r"\lnot": "¬", r"\land": "∧", r"\wedge": "∧", r"\lor": "∨", r"\vee": "∨",
    r"\to": "→", r"\rightarrow": "→", r"\leftarrow": "←", r"\leftrightarrow": "↔",
    r"\Rightarrow": "⇒", r"\Leftarrow": "⇐", r"\Leftrightarrow": "⇔", r"\iff": "⟺",
    r"\implies": "⟹", r"\downarrow": "↓", r"\uparrow": "↑", r"\mid": "∣",
    r"\forall": "∀", r"\exists": "∃", r"\nexists": "∄", r"\in": "∈", r"\notin": "∉",
    r"\subset": "⊂", r"\subseteq": "⊆", r"\supset": "⊃", r"\supseteq": "⊇",
    r"\cup": "∪", r"\cap": "∩", r"\setminus": "∖", r"\emptyset": "∅", r"\varnothing": "∅",
    r"\infty": "∞", r"\partial": "∂", r"\nabla": "∇", r"\int": "∫", r"\iint": "∬",
    r"\iiint": "∭", r"\oint": "∮", r"\sum": "∑", r"\prod": "∏", r"\sqrt": "√",
    r"\propto": "∝", r"\angle": "∠", r"\perp": "⊥", r"\parallel": "∥",
    r"\dots": "…", r"\ldots": "…", r"\cdots": "⋯", r"\quad": "  ", r"\qquad": "    ",
    r"\{": "{", r"\}": "}",
}


def format_latex_math_offline(expr: str) -> str:
    """
    Преобразует LaTeX-формулу в красивую математическую HTML-верстку (дроби, степени, индексы,
    греческие символы и логические операторы), которая работает 100% офлайн и в QPrinter PDF.
    """
    s = repair_corrupted_latex(expr).strip().strip("$").strip()
    s = html.escape(s)

    # \text{...} и \mathrm{...}
    s = re.sub(r"\\(?:text|mathrm|mathbf)\{([^{}]*)\}", r'<span style="font-style:normal;">\1</span>', s)
    s = re.sub(r"\\mathbb\{([^{}]*)\}", r'<b>\1</b>', s)

    # \sqrt{...}
    s = re.sub(r"\\sqrt\{([^{}]*)\}", r"√(\1)", s)

    # \overline{...} / \bar{...}
    s = re.sub(r"\\(?:overline|bar)\{([^{}]*)\}", r'<span style="text-decoration:overline;">\1</span>', s)

    # Дроби \frac{a}{b} (включая вложенные 2 уровня)
    for _ in range(2):
        s = re.sub(
            r"\\frac\{([^{}]+)\}\{([^{}]+)\}",
            r'<span class="math-frac"><span class="num">(\1)</span>⁄<span class="den">(\2)</span></span>',
            s,
        )

    # Замена команд LaTeX на математические символы Unicode (сначала длинные команды)
    for cmd in sorted(LATEX_SYMBOLS.keys(), key=len, reverse=True):
        s = s.replace(cmd, LATEX_SYMBOLS[cmd])

    # Удаляем служебные \left и \right
    s = re.sub(r"\\(?:left|right)\b", "", s)

    # Степени ^{...} и ^x
    s = re.sub(r"\^\{([^{}]+)\}", r"<sup>\1</sup>", s)
    s = re.sub(r"\^([a-zA-Z0-9+\-∗′])", r"<sup>\1</sup>", s)

    # Нижние индексы _{...} и _x
    s = re.sub(r"_\{([^{}]+)\}", r"<sub>\1</sub>", s)
    s = re.sub(r"_([a-zA-Z0-9+\-])", r"<sub>\1</sub>", s)

    return s


def ensure_local_katex_assets(storage_path: str) -> Dict[str, str]:
    """
    Проверяет наличие локальных файлов KaTeX в `~/AxAI_Storage/katex/`.
    Если интернет есть при первом вызове — скачивает `katex.min.css` и `katex.min.js` на диск,
    чтобы все последующие запуски `QWebEngineView` рендерили KaTeX полностью локально без CDN.
    """
    katex_dir = os.path.join(storage_path, "katex")
    os.makedirs(katex_dir, exist_ok=True)
    css_path = os.path.join(katex_dir, "katex.min.css")
    js_path = os.path.join(katex_dir, "katex.min.js")

    if not (os.path.exists(css_path) and os.path.exists(js_path)):
        try:
            urllib.request.urlretrieve(
                "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css", css_path
            )
            urllib.request.urlretrieve(
                "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js", js_path
            )
        except Exception:
            pass

    return {
        "css_path": css_path if os.path.exists(css_path) else "",
        "js_path": js_path if os.path.exists(js_path) else "",
    }


def _render_inline_markdown_and_math(line: str) -> str:
    """Рендерит строчные формулы $...$, жирный шрифт, курсив и код внутри строки Markdown."""
    parts = re.split(r"(\$[^$]+\$)", line)
    out = []
    for part in parts:
        if part.startswith("$") and part.endswith("$") and len(part) > 2:
            raw_tex = part[1:-1]
            offline_rendered = format_latex_math_offline(raw_tex)
            escaped_attr = html.escape(raw_tex, quote=True)
            out.append(
                f'<span class="math-inline" data-latex="{escaped_attr}">{offline_rendered}</span>'
            )
        else:
            escaped = html.escape(part)
            escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
            escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
            escaped = re.sub(r"`([^`]+)`", r'<code class="inline-code">\1</code>', escaped)
            out.append(escaped)
    return "".join(out)


def render_lecture_html_with_math(
    markdown_text: str,
    title: str = "",
    subject: str = "",
    lecturer: str = "",
    date: str = "",
    formulas: Optional[List[Dict[str, Any]]] = None,
    dark_mode: bool = True,
    storage_path: str = "",
) -> str:
    """
    Генерирует полноценный HTML-документ конспекта с рендерингом Markdown и формул LaTeX.
    - Внутри `QWebEngineView` автоматически активирует локальный KaTeX (если скачан в `~/AxAI_Storage/katex/`).
    - Внутри `QTextBrowser` и `QPrinter` (при экспорте PDF) сразу отображает отформатированные
      математические формулы через `format_latex_math_offline`.
    """
    clean_md = repair_corrupted_latex(markdown_text or "")
    lines = clean_md.split("\n")

    body_parts: List[str] = []
    in_ul = False
    in_ol = False
    in_block_math = False
    math_buf: List[str] = []

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            body_parts.append("</ul>")
            in_ul = False
        if in_ol:
            body_parts.append("</ol>")
            in_ol = False

    for line in lines:
        trimmed = line.strip()

        # Однострочная блочная формула $$ ... $$
        if trimmed.startswith("$$") and trimmed.endswith("$$") and len(trimmed) > 4:
            close_lists()
            raw_tex = trimmed[2:-2].strip()
            offline_html = format_latex_math_offline(raw_tex)
            escaped_attr = html.escape(raw_tex, quote=True)
            body_parts.append(
                f'<div class="math-block" data-latex="{escaped_attr}">{offline_html}</div>'
            )
            continue

        # Многострочная блочная формула $$
        if trimmed == "$$":
            close_lists()
            if not in_block_math:
                in_block_math = True
                math_buf = []
            else:
                in_block_math = False
                raw_tex = "\n".join(math_buf).strip()
                offline_html = format_latex_math_offline(raw_tex)
                escaped_attr = html.escape(raw_tex, quote=True)
                body_parts.append(
                    f'<div class="math-block" data-latex="{escaped_attr}">{offline_html}</div>'
                )
            continue

        if in_block_math:
            math_buf.append(line)
            continue

        if trimmed in ("---", "***"):
            close_lists()
            body_parts.append("<hr/>")
            continue

        if trimmed.startswith("### "):
            close_lists()
            body_parts.append(f"<h3>{_render_inline_markdown_and_math(trimmed[4:])}</h3>")
            continue
        if trimmed.startswith("## "):
            close_lists()
            body_parts.append(f"<h2>{_render_inline_markdown_and_math(trimmed[3:])}</h2>")
            continue
        if trimmed.startswith("# "):
            close_lists()
            body_parts.append(f"<h1>{_render_inline_markdown_and_math(trimmed[2:])}</h1>")
            continue

        if trimmed.startswith("- ") or trimmed.startswith("* "):
            if in_ol:
                body_parts.append("</ol>")
                in_ol = False
            if not in_ul:
                body_parts.append("<ul>")
                in_ul = True
            body_parts.append(f"<li>{_render_inline_markdown_and_math(trimmed[2:])}</li>")
            continue

        m = re.match(r"^(\d+)\.\s+(.*)", trimmed)
        if m:
            if in_ul:
                body_parts.append("</ul>")
                in_ul = False
            if not in_ol:
                body_parts.append("<ol>")
                in_ol = True
            body_parts.append(f"<li>{_render_inline_markdown_and_math(m.group(2))}</li>")
            continue

        if not trimmed:
            close_lists()
            continue

        close_lists()
        body_parts.append(f"<p>{_render_inline_markdown_and_math(line)}</p>")

    close_lists()

    # Если у лекции есть карточки формул — добавляем сводный блок в конец
    if formulas:
        body_parts.append('<h2>Сводка ключевых формул лекции</h2>')
        for f in formulas:
            f_title = html.escape(str(f.get("title", "Формула")))
            f_latex = str(f.get("latex", ""))
            f_ctx = html.escape(str(f.get("context", "")))
            body_parts.append(
                f'<div class="formula-card">'
                f'<div class="formula-title">{f_title}</div>'
                f'<div class="math-block" data-latex="{html.escape(f_latex, quote=True)}">{format_latex_math_offline(f_latex)}</div>'
                f'<div class="formula-ctx">{f_ctx}</div>'
                f'</div>'
            )

    bg_color = "#121215" if dark_mode else "#ffffff"
    text_color = "#e4e4e7" if dark_mode else "#111827"
    heading_color = "#ffffff" if dark_mode else "#09090b"
    accent_color = "#818cf8" if dark_mode else "#4338ca"
    math_bg = "#18181f" if dark_mode else "#f4f4f8"
    math_border = "#312e81" if dark_mode else "#c7d2fe"
    inline_math_bg = "#1e1b4b" if dark_mode else "#eef2ff"
    inline_math_fg = "#c7d2fe" if dark_mode else "#312e81"
    muted_color = "#a1a1aa" if dark_mode else "#4b5563"

    # Подключение локального KaTeX, если он сохранен в storage_path/katex
    katex_head = ""
    katex_script = ""
    if storage_path:
        katex_js = os.path.join(storage_path, "katex", "katex.min.js")
        katex_css = os.path.join(storage_path, "katex", "katex.min.css")
        if os.path.exists(katex_js) and os.path.exists(katex_css):
            css_url = "file:///" + os.path.abspath(katex_css).replace("\\", "/")
            js_url = "file:///" + os.path.abspath(katex_js).replace("\\", "/")
            katex_head = f'<link rel="stylesheet" href="{css_url}">\n<script src="{js_url}"></script>'
            katex_script = """
            <script>
            document.addEventListener("DOMContentLoaded", function() {
              if (typeof katex !== "undefined") {
                document.querySelectorAll(".math-block").forEach(function(el) {
                  var tex = el.getAttribute("data-latex");
                  if (tex) {
                    try { katex.render(tex, el, { displayMode: true, throwOnError: false }); } catch (e) {}
                  }
                });
                document.querySelectorAll(".math-inline").forEach(function(el) {
                  var tex = el.getAttribute("data-latex");
                  if (tex) {
                    try { katex.render(tex, el, { displayMode: false, throwOnError: false }); } catch (e) {}
                  }
                });
              }
            });
            </script>
            """

    header_block = ""
    if not dark_mode and title:
        header_block = (
            f'<div style="border-bottom: 2px solid #e5e7eb; padding-bottom: 12px; margin-bottom: 18px;">'
            f'<h1 style="margin:0 0 6px 0; font-size: 22pt;">{html.escape(title)}</h1>'
            f'<div style="color:{muted_color}; font-size:10pt;">'
            f'<b>Предмет:</b> {html.escape(subject)} &nbsp;·&nbsp; '
            f'<b>Преподаватель:</b> {html.escape(lecturer)} &nbsp;·&nbsp; '
            f'<b>Дата:</b> {html.escape(date)}'
            f'</div></div>'
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
{katex_head}
<style>
  body {{
    background-color: {bg_color};
    color: {text_color};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans", sans-serif;
    font-size: 13.5px;
    line-height: 1.68;
    padding: 20px 26px;
    margin: 0;
  }}
  h1 {{ color: {heading_color}; font-size: 20px; font-weight: 700; margin-top: 18px; margin-bottom: 10px; }}
  h2 {{ color: {accent_color}; font-size: 16.5px; font-weight: 700; margin-top: 22px; margin-bottom: 8px; border-bottom: 1px solid {math_border}; padding-bottom: 4px; }}
  h3 {{ color: {heading_color}; font-size: 14.5px; font-weight: 600; margin-top: 16px; margin-bottom: 6px; }}
  p {{ margin-top: 6px; margin-bottom: 10px; }}
  ul, ol {{ margin-top: 6px; margin-bottom: 12px; padding-left: 24px; }}
  li {{ margin-bottom: 5px; }}
  strong {{ color: {heading_color}; font-weight: 600; }}
  hr {{ border: none; border-top: 1px solid #27272a; margin: 18px 0; }}
  .inline-code {{
    font-family: "JetBrains Mono", Consolas, monospace;
    background-color: {math_bg};
    padding: 2px 5px;
    border-radius: 4px;
    font-size: 12.5px;
  }}
  .math-inline {{
    font-family: "Cambria Math", "STIX Two Math", "Times New Roman", serif;
    background-color: {inline_math_bg};
    color: {inline_math_fg};
    padding: 1px 6px;
    border-radius: 5px;
    font-size: 14.5px;
    font-style: italic;
  }}
  .math-block {{
    font-family: "Cambria Math", "STIX Two Math", "Times New Roman", serif;
    background-color: {math_bg};
    border-left: 3px solid {accent_color};
    color: {heading_color};
    padding: 12px 16px;
    margin: 12px 0;
    border-radius: 8px;
    font-size: 16px;
    text-align: center;
  }}
  .formula-card {{
    background-color: {math_bg};
    border: 1px solid {math_border};
    border-radius: 10px;
    padding: 12px 16px;
    margin: 10px 0;
  }}
  .formula-title {{ font-weight: 600; color: {accent_color}; font-size: 13px; margin-bottom: 4px; }}
  .formula-ctx {{ color: {muted_color}; font-size: 12px; margin-top: 4px; }}
</style>
</head>
<body>
{header_block}
{"".join(body_parts)}
{katex_script}
</body>
</html>"""


def markdown_to_latex_body(raw_markdown: str) -> str:
    """Конвертирует Markdown-конспект с формулами в компилируемый LaTeX (.tex)."""
    clean_md = repair_corrupted_latex(raw_markdown)
    lines = clean_md.split("\n")
    out = []
    in_ul = False
    in_ol = False
    in_block_math = False
    math_buf = []

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("\\end{itemize}")
            in_ul = False
        if in_ol:
            out.append("\\end{enumerate}")
            in_ol = False

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
            out.append("\\begin{equation*}")
            out.append(trimmed[2:-2].strip())
            out.append("\\end{equation*}")
            continue

        if trimmed == "$$":
            close_lists()
            if not in_block_math:
                in_block_math = True
                math_buf = []
            else:
                in_block_math = False
                out.append("\\begin{equation*}")
                out.extend(math_buf)
                out.append("\\end{equation*}")
            continue

        if in_block_math:
            math_buf.append(line)
            continue

        if trimmed.startswith("### "):
            close_lists()
            out.append(f"\\subsubsection*{{{format_inline(trimmed[4:])}}}")
            continue
        if trimmed.startswith("## "):
            close_lists()
            out.append(f"\\subsection*{{{format_inline(trimmed[3:])}}}")
            continue
        if trimmed.startswith("# "):
            close_lists()
            out.append(f"\\section*{{{format_inline(trimmed[2:])}}}")
            continue

        if trimmed.startswith("- ") or trimmed.startswith("* "):
            if in_ol:
                out.append("\\end{enumerate}")
                in_ol = False
            if not in_ul:
                out.append("\\begin{itemize}")
                in_ul = True
            out.append(f"  \\item {format_inline(trimmed[2:])}")
            continue

        m = re.match(r"^(\d+)\.\s+(.*)", trimmed)
        if m:
            if in_ul:
                out.append("\\end{itemize}")
                in_ul = False
            if not in_ol:
                out.append("\\begin{enumerate}")
                in_ol = True
            out.append(f"  \\item {format_inline(m.group(2))}")
            continue

        if not trimmed:
            close_lists()
            out.append("")
            continue

        close_lists()
        out.append(format_inline(line))

    close_lists()
    return "\n".join(out)


def export_lecture_to_markdown(lec: Dict[str, Any], save_path: str) -> None:
    body = repair_corrupted_latex(lec.get("text", ""))
    md = f"# {lec.get('title', '')}\n\n"
    md += f"- **Предмет:** {lec.get('subject', '')}\n"
    md += f"- **Преподаватель:** {lec.get('lecturer', '')}\n"
    md += f"- **Дата:** {lec.get('date', '')}\n\n---\n\n"
    md += f"{body}\n\n"

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
        "\\begin{document}\n"
        "\\maketitle\n\n"
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
