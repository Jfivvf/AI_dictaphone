import katex from 'katex';
import { jsPDF } from 'jspdf';
import html2canvas from 'html2canvas';
import { Lecture } from '../types';

/**
 * Repairs LaTeX commands that were accidentally corrupted by JSON escape sequences
 * (\f -> \x0C in \frac, \b -> \x08 in \beta/\begin, \t -> \x09 in \theta/\times/\text,
 *  \r -> \x0D in \right/\rho, \n -> newline in \nabla/\neq/\nu)
 * and normalizes \[...\] and \(...\) delimiters.
 */
export function repairCorruptedLatex(input: string): string {
  if (!input) return '';

  let text = String(input);

  // 1. Repair Form Feed (\x0C) -> \f (e.g. \frac, \forall, \flat)
  text = text.replace(/\x0c(rac|orall|lat|rown|box|int)/g, '\\f$1');
  text = text.replace(/\x0c/g, '\\f');

  // 2. Repair Backspace (\x08) -> \b (e.g. \beta, \begin, \binom, \bar, \bf, \big, \bigcup, \bigcap, \bullet, \boxed)
  text = text.replace(/\x08(eta|egin|inom|ar|f|ig|ullet|oxed|ot|ackslash|oldsymbol)/g, '\\b$1');
  text = text.replace(/\x08/g, '\\b');

  // 3. Repair Tab (\x09) when followed by LaTeX command suffixes (\theta, \tau, \times, \text, \tilde, \tan, \tanh, \top, \triangle, \to, \therefore)
  text = text.replace(/\x09(heta|au|imes|ext|ilde|an|anh|op|riangle|o\b|herefore|iny)/g, '\\t$1');

  // 4. Repair Carriage Return (\x0D) when not part of \r\n (\right, \rightarrow, \rho, \rangle, \rceil, \rfloor)
  text = text.replace(/\x0d(ight|ightarrow|ho|angle|ceil|floor|ule|m)/g, '\\r$1');

  // 5. Repair Newline (\n) when it split a LaTeX command inside math (\nabla, \neq, \nu, \not, \natural, \nexists)
  text = text.replace(/\n(abla|eq\b|u\b|ot\b|atural|exists|ewline|mid|parallel|otin)/g, '\\n$1');

  // 6. Normalize \[ ... \] and \( ... \) to $$ ... $$ and $ ... $
  text = text.replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => `\n$$\n${math.trim()}\n$$\n`);
  text = text.replace(/\\\(([\s\S]*?)\\\)/g, (_, math) => `$${math.trim()}$`);

  // 7. Collapse accidental double backslashes before known LaTeX commands inside math
  text = text.replace(
    /\\\\(frac|sqrt|sum|int|prod|lim|infty|alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|vartheta|iota|kappa|lambda|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|varphi|chi|psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Upsilon|Phi|Psi|Omega|cdot|times|div|pm|mp|leq|geq|neq|approx|equiv|sim|propto|partial|nabla|forall|exists|in|notin|subset|subseteq|cup|cap|emptyset|rightarrow|leftarrow|Rightarrow|Leftarrow|leftrightarrow|Leftrightarrow|mapsto|to|left|right|big|Big|bigg|Bigg|text|mathbf|mathrm|mathcal|mathbb|hat|bar|vec|tilde|dot|ddot|overline|underline|binom|matrix|pmatrix|bmatrix|vmatrix|cases)/g,
    '\\$1'
  );

  return text;
}

/**
 * Converts Markdown + LaTeX into clean, compilable LaTeX document body
 */
export function markdownToLatexBody(rawMarkdown: string): string {
  const cleanMd = repairCorruptedLatex(rawMarkdown);
  const lines = cleanMd.split('\n');
  const out: string[] = [];

  let inBlockMath = false;
  let blockMathBuf: string[] = [];
  let inUl = false;
  let inOl = false;

  const closeLists = () => {
    if (inUl) {
      out.push('\\end{itemize}');
      inUl = false;
    }
    if (inOl) {
      out.push('\\end{enumerate}');
      inOl = false;
    }
  };

  const formatInlineLatex = (str: string): string => {
    // Split by inline math $...$ so we only escape/convert non-math text
    const segments = str.split(/(\$[^$]+\$)/g);
    return segments
      .map((seg) => {
        if (seg.startsWith('$') && seg.endsWith('$') && seg.length > 2) {
          return seg;
        }
        let s = seg;
        // Escape LaTeX special characters outside math
        s = s
          .replace(/%/g, '\\%')
          .replace(/&/g, '\\&')
          .replace(/#/g, '\\#')
          .replace(/_/g, '\\_');
        // Bold **text**
        s = s.replace(/\*\*([^*]+)\*\*/g, '\\textbf{$1}');
        // Italic *text*
        s = s.replace(/\*([^*]+)\*/g, '\\textit{$1}');
        // Inline code `text`
        s = s.replace(/`([^`]+)`/g, '\\texttt{$1}');
        return s;
      })
      .join('');
  };

  for (const line of lines) {
    const trimmed = line.trim();

    // Single-line $$ ... $$
    if (trimmed.startsWith('$$') && trimmed.endsWith('$$') && trimmed.length > 4) {
      closeLists();
      const math = trimmed.slice(2, -2).trim();
      out.push('\\begin{equation*}');
      out.push(math);
      out.push('\\end{equation*}');
      continue;
    }

    // Multi-line $$ toggle
    if (trimmed === '$$') {
      closeLists();
      if (!inBlockMath) {
        inBlockMath = true;
        blockMathBuf = [];
      } else {
        inBlockMath = false;
        out.push('\\begin{equation*}');
        out.push(blockMathBuf.join('\n'));
        out.push('\\end{equation*}');
      }
      continue;
    }

    if (inBlockMath) {
      blockMathBuf.push(line);
      continue;
    }

    if (trimmed === '---' || trimmed === '***') {
      closeLists();
      out.push('\\bigskip\\hrule\\bigskip');
      continue;
    }

    if (trimmed.startsWith('### ')) {
      closeLists();
      out.push(`\\subsubsection*{${formatInlineLatex(trimmed.slice(4))}}`);
      continue;
    }

    if (trimmed.startsWith('## ')) {
      closeLists();
      out.push(`\\subsection*{${formatInlineLatex(trimmed.slice(3))}}`);
      continue;
    }

    if (trimmed.startsWith('# ')) {
      closeLists();
      out.push(`\\section*{${formatInlineLatex(trimmed.slice(2))}}`);
      continue;
    }

    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      if (inOl) {
        out.push('\\end{enumerate}');
        inOl = false;
      }
      if (!inUl) {
        out.push('\\begin{itemize}');
        inUl = true;
      }
      out.push(`  \\item ${formatInlineLatex(trimmed.slice(2))}`);
      continue;
    }

    const numMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
    if (numMatch) {
      if (inUl) {
        out.push('\\end{itemize}');
        inUl = false;
      }
      if (!inOl) {
        out.push('\\begin{enumerate}');
        inOl = true;
      }
      out.push(`  \\item ${formatInlineLatex(numMatch[2])}`);
      continue;
    }

    if (trimmed === '') {
      closeLists();
      out.push('');
      continue;
    }

    closeLists();
    out.push(formatInlineLatex(line));
  }

  closeLists();
  return out.join('\n');
}

/**
 * Exports a Lecture as a clean, UTF-8 BOM Markdown (.md) file
 */
export function exportLectureToMarkdown(lecture: Lecture): void {
  const cleanSummary = repairCorruptedLatex(lecture.summaryMarkdown);

  let md = `# ${lecture.title}\n\n`;
  md += `- **Предмет:** ${lecture.subject}\n`;
  md += `- **Преподаватель:** ${lecture.lecturer}\n`;
  md += `- **Дата:** ${lecture.date}\n\n`;
  md += `---\n\n`;
  md += `${cleanSummary}\n\n`;

  if (lecture.latexFormulas.length > 0) {
    md += `---\n\n## Ключевые формулы лекции\n\n`;
    lecture.latexFormulas.forEach((f, idx) => {
      const cleanLatex = repairCorruptedLatex(f.latex).replace(/^\$+|\$+$/g, '').trim();
      md += `### ${idx + 1}. ${f.title}\n\n`;
      md += `$$\n${cleanLatex}\n$$\n\n`;
      if (f.context) {
        md += `*${f.context}*\n\n`;
      }
    });
  }

  if (lecture.actionItems.length > 0) {
    md += `---\n\n## Задачи и дедлайны\n\n`;
    lecture.actionItems.forEach((item) => {
      md += `- [${item.completed ? 'x' : ' '}] **${item.task}** *(Срок: ${item.deadline})*\n`;
    });
  }

  // Prepend UTF-8 BOM (\uFEFF) so Windows/macOS editors detect UTF-8 Cyrillic immediately
  const blob = new Blob(['\uFEFF' + md], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${lecture.title.replace(/[\\/:*?"<>|\s]+/g, '_')}_конспект.md`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Exports a Lecture as a complete, compilable UTF-8 LaTeX (.tex) document including the full lecture body
 */
export function exportLectureToLatex(lecture: Lecture): void {
  const bodyTex = markdownToLatexBody(lecture.summaryMarkdown);

  let tex = `% Конспект лекции: ${lecture.title}\n`;
  tex += `\\documentclass[12pt,a4paper]{article}\n`;
  tex += `\\usepackage[utf8]{inputenc}\n`;
  tex += `\\usepackage[T2A]{fontenc}\n`;
  tex += `\\usepackage[russian]{babel}\n`;
  tex += `\\usepackage{amsmath,amssymb,amsfonts}\n`;
  tex += `\\usepackage[margin=2cm]{geometry}\n`;
  tex += `\\usepackage{hyperref}\n\n`;
  tex += `\\title{${lecture.title.replace(/([%&#_])/g, '\\$1')}}\n`;
  tex += `\\author{${lecture.lecturer.replace(/([%&#_])/g, '\\$1')} \\\\ \\small ${lecture.subject.replace(/([%&#_])/g, '\\$1')}}\n`;
  tex += `\\date{${lecture.date}}\n\n`;
  tex += `\\begin{document}\n`;
  tex += `\\maketitle\n\n`;
  tex += `${bodyTex}\n\n`;

  if (lecture.latexFormulas.length > 0) {
    tex += `\\section*{Сводка ключевых формул}\n`;
    lecture.latexFormulas.forEach((f) => {
      const cleanLatex = repairCorruptedLatex(f.latex).replace(/^\$+|\$+$/g, '').trim();
      tex += `\\subsection*{${f.title.replace(/([%&#_])/g, '\\$1')}}\n`;
      tex += `\\begin{equation*}\n${cleanLatex}\n\\end{equation*}\n`;
      if (f.context) {
        tex += `\\textit{${f.context.replace(/([%&#_])/g, '\\$1')}}\n\n`;
      }
    });
  }

  if (lecture.actionItems.length > 0) {
    tex += `\\section*{Задачи и дедлайны}\n\\begin{itemize}\n`;
    lecture.actionItems.forEach((item) => {
      tex += `  \\item \\textbf{${item.task.replace(/([%&#_])/g, '\\$1')}} --- \\textit{Срок: ${item.deadline.replace(/([%&#_])/g, '\\$1')}}\n`;
    });
    tex += `\\end{itemize}\n\n`;
  }

  tex += `\\end{document}\n`;

  const blob = new Blob(['\uFEFF' + tex], { type: 'application/x-tex;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${lecture.title.replace(/[\\/:*?"<>|\s]+/g, '_')}_конспект.tex`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Converts Markdown + LaTeX into clean HTML with rendered KaTeX formulas for A4 PDF export
 */
function renderMarkdownWithKatexToHtml(rawMarkdown: string): string {
  const cleanMd = repairCorruptedLatex(rawMarkdown);
  const lines = cleanMd.split('\n');
  const htmlParts: string[] = [];
  let inBlockMath = false;
  let blockMathBuf: string[] = [];
  let inList = false;

  const flushList = () => {
    if (inList) {
      htmlParts.push('</ul>');
      inList = false;
    }
  };

  const escapeHtml = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  const renderInline = (text: string): string => {
    const parts = text.split(/(\$[^$]+\$)/g);
    return parts
      .map((part) => {
        if (part.startsWith('$') && part.endsWith('$') && part.length > 2) {
          const math = part.slice(1, -1);
          try {
            return katex.renderToString(math, { displayMode: false, throwOnError: false });
          } catch {
            return `<code>${escapeHtml(math)}</code>`;
          }
        }
        let escaped = escapeHtml(part);
        escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        escaped = escaped.replace(
          /`([^`]+)`/g,
          '<code style="background:#f3f4f6;padding:1px 5px;border-radius:4px;font-family:monospace;font-size:12px;">$1</code>'
        );
        return escaped;
      })
      .join('');
  };

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith('$$') && trimmed.endsWith('$$') && trimmed.length > 4) {
      flushList();
      const math = trimmed.slice(2, -2);
      try {
        const rendered = katex.renderToString(math, { displayMode: true, throwOnError: false });
        htmlParts.push(
          `<div style="margin:12px 0;padding:10px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;text-align:center;overflow-x:auto;">${rendered}</div>`
        );
      } catch {
        htmlParts.push(`<pre>${escapeHtml(math)}</pre>`);
      }
      continue;
    }

    if (trimmed === '$$') {
      flushList();
      if (!inBlockMath) {
        inBlockMath = true;
        blockMathBuf = [];
      } else {
        inBlockMath = false;
        const math = blockMathBuf.join('\n');
        try {
          const rendered = katex.renderToString(math, { displayMode: true, throwOnError: false });
          htmlParts.push(
            `<div style="margin:12px 0;padding:10px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;text-align:center;overflow-x:auto;">${rendered}</div>`
          );
        } catch {
          htmlParts.push(`<pre>${escapeHtml(math)}</pre>`);
        }
      }
      continue;
    }

    if (inBlockMath) {
      blockMathBuf.push(line);
      continue;
    }

    if (trimmed === '---' || trimmed === '***') {
      flushList();
      htmlParts.push('<hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;" />');
      continue;
    }

    if (trimmed.startsWith('### ')) {
      flushList();
      htmlParts.push(
        `<h3 style="font-size:15px;font-weight:700;color:#1e293b;margin:16px 0 6px 0;">${renderInline(trimmed.slice(4))}</h3>`
      );
      continue;
    }

    if (trimmed.startsWith('## ')) {
      flushList();
      htmlParts.push(
        `<h2 style="font-size:17px;font-weight:700;color:#0f172a;margin:20px 0 8px 0;padding-bottom:4px;border-bottom:1px solid #e2e8f0;">${renderInline(trimmed.slice(3))}</h2>`
      );
      continue;
    }

    if (trimmed.startsWith('# ')) {
      flushList();
      htmlParts.push(
        `<h1 style="font-size:20px;font-weight:800;color:#0f172a;margin:22px 0 10px 0;">${renderInline(trimmed.slice(2))}</h1>`
      );
      continue;
    }

    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      if (!inList) {
        htmlParts.push('<ul style="margin:8px 0 8px 20px;padding:0;list-style-type:disc;">');
        inList = true;
      }
      htmlParts.push(
        `<li style="margin:4px 0;line-height:1.6;color:#1f2937;font-size:13.5px;">${renderInline(trimmed.slice(2))}</li>`
      );
      continue;
    }

    const numMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
    if (numMatch) {
      if (!inList) {
        htmlParts.push('<ul style="margin:8px 0 8px 20px;padding:0;list-style-type:none;">');
        inList = true;
      }
      htmlParts.push(
        `<li style="margin:4px 0;line-height:1.6;color:#1f2937;font-size:13.5px;"><strong style="color:#4f46e5;">${numMatch[1]}.</strong> ${renderInline(numMatch[2])}</li>`
      );
      continue;
    }

    if (trimmed === '') {
      flushList();
      continue;
    }

    flushList();
    htmlParts.push(
      `<p style="margin:8px 0;line-height:1.65;color:#1f2937;font-size:13.5px;">${renderInline(line)}</p>`
    );
  }

  flushList();
  return htmlParts.join('\n');
}

/**
 * Generates and downloads a real multi-page A4 .pdf file with Cyrillic text and rendered KaTeX formulas
 */
export async function exportLectureToPdf(lecture: Lecture): Promise<void> {
  const iframe = document.createElement('iframe');
  iframe.style.position = 'fixed';
  iframe.style.left = '-10000px';
  iframe.style.top = '0';
  iframe.style.width = '794px';
  iframe.style.height = '1123px';
  iframe.style.border = 'none';
  document.body.appendChild(iframe);

  try {
    const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
    if (!iframeDoc) {
      throw new Error('Could not initialize PDF render frame');
    }

    const bodyHtml = renderMarkdownWithKatexToHtml(lecture.summaryMarkdown);

    let formulasHtml = '';
    if (lecture.latexFormulas.length > 0) {
      formulasHtml += `<h2 style="font-size:17px;font-weight:700;color:#0f172a;margin:24px 0 10px 0;padding-bottom:4px;border-bottom:1px solid #e2e8f0;">Ключевые формулы лекции</h2>`;
      lecture.latexFormulas.forEach((f) => {
        const cleanMath = repairCorruptedLatex(f.latex).replace(/^\$+|\$+$/g, '').trim();
        let renderedMath = cleanMath;
        try {
          renderedMath = katex.renderToString(cleanMath, { displayMode: true, throwOnError: false });
        } catch {
          // keep fallback
        }
        formulasHtml += `
          <div style="margin:10px 0;padding:10px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;">
            <div style="font-size:13px;font-weight:700;color:#1e293b;margin-bottom:4px;">${f.title}</div>
            <div style="text-align:center;margin:6px 0;">${renderedMath}</div>
            ${f.context ? `<div style="font-size:12px;color:#475569;">${f.context}</div>` : ''}
          </div>
        `;
      });
    }

    let tasksHtml = '';
    if (lecture.actionItems.length > 0) {
      tasksHtml += `<h2 style="font-size:17px;font-weight:700;color:#0f172a;margin:24px 0 10px 0;padding-bottom:4px;border-bottom:1px solid #e2e8f0;">Задачи и дедлайны</h2><ul style="margin:8px 0 8px 18px;padding:0;">`;
      lecture.actionItems.forEach((item) => {
        tasksHtml += `<li style="margin:5px 0;font-size:13px;color:#1f2937;"><strong>${item.task}</strong> <span style="color:#64748b;">(Срок: ${item.deadline})</span></li>`;
      });
      tasksHtml += `</ul>`;
    }

    iframeDoc.open();
    iframeDoc.write(`<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css" crossorigin="anonymous" />
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 40px 48px;
      width: 794px;
      background-color: #ffffff;
      color: #111827;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    .katex { font-size: 1.05em; color: #111827; }
    .katex-display { margin: 0.5em 0; }
  </style>
</head>
<body>
  <div id="pdf-root" style="background:#ffffff;color:#111827;">
    <div style="border-bottom:2px solid #4f46e5;padding-bottom:14px;margin-bottom:20px;">
      <div style="font-size:12px;font-weight:700;color:#4f46e5;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:4px;">
        ${lecture.subject}
      </div>
      <h1 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 8px 0;line-height:1.3;">
        ${lecture.title}
      </h1>
      <div style="font-size:12px;color:#475569;">
        Преподаватель: <strong>${lecture.lecturer}</strong> &nbsp;|&nbsp; Дата: <strong>${lecture.date}</strong>
      </div>
    </div>
    <div>${bodyHtml}</div>
    <div>${formulasHtml}</div>
    <div>${tasksHtml}</div>
  </div>
</body>
</html>`);
    iframeDoc.close();

    // Wait for KaTeX fonts/styles inside iframe to finish loading
    await new Promise((resolve) => setTimeout(resolve, 650));

    const rootEl = iframeDoc.getElementById('pdf-root') || iframeDoc.body;
    const canvas = await html2canvas(rootEl, {
      scale: 2,
      useCORS: true,
      backgroundColor: '#ffffff',
      logging: false,
      windowWidth: 794,
    });

    const pdf = new jsPDF('p', 'mm', 'a4');
    const pageWidthMm = 210;
    const pageHeightMm = 297;
    const marginMm = 10;
    const usableHeightMm = pageHeightMm - marginMm * 2;

    // Slice canvas page by page so multi-page lectures never clip
    const pxPerMm = canvas.width / pageWidthMm;
    const sliceHeightPx = Math.floor(usableHeightMm * pxPerMm);
    let currentY = 0;
    let pageIndex = 0;

    while (currentY < canvas.height) {
      if (pageIndex > 0) {
        pdf.addPage();
      }

      const remainingPx = canvas.height - currentY;
      const thisSlicePx = Math.min(sliceHeightPx, remainingPx);

      const pageCanvas = document.createElement('canvas');
      pageCanvas.width = canvas.width;
      pageCanvas.height = thisSlicePx;
      const ctx = pageCanvas.getContext('2d');
      if (ctx) {
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, pageCanvas.width, pageCanvas.height);
        ctx.drawImage(
          canvas,
          0,
          currentY,
          canvas.width,
          thisSlicePx,
          0,
          0,
          canvas.width,
          thisSlicePx
        );
      }

      const sliceDataUrl = pageCanvas.toDataURL('image/jpeg', 0.95);
      const sliceHeightMm = thisSlicePx / pxPerMm;
      pdf.addImage(sliceDataUrl, 'JPEG', 0, marginMm, pageWidthMm, sliceHeightMm);

      currentY += thisSlicePx;
      pageIndex++;
    }

    pdf.save(`${lecture.title.replace(/[\\/:*?"<>|\s]+/g, '_')}_конспект.pdf`);
  } finally {
    document.body.removeChild(iframe);
  }
}
