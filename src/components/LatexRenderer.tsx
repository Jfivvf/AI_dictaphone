import React, { useMemo } from 'react';
import katex from 'katex';
import { repairCorruptedLatex } from '../utils/exportHelpers';

interface LatexRendererProps {
  content: string;
  className?: string;
}

export const LatexRenderer: React.FC<LatexRendererProps> = ({ content, className = '' }) => {
  // Parse content into markdown blocks with KaTeX math rendering
  const renderedElements = useMemo(() => {
    if (!content) return null;

    const cleanContent = repairCorruptedLatex(content);
    // Split content by block math $$...$$
    const lines = cleanContent.split('\n');
    const elements: React.ReactNode[] = [];
    let inBlockMath = false;
    let blockMathAccumulator = '';
    let inList = false;
    let listItems: React.ReactNode[] = [];

    const flushList = (keyPrefix: string) => {
      if (inList && listItems.length > 0) {
        elements.push(
          <ul key={`${keyPrefix}-list`} className="my-2 space-y-1 pl-5 list-disc text-neutral-300">
            {listItems}
          </ul>
        );
        listItems = [];
        inList = false;
      }
    };

    const renderInlineMathAndFormatting = (text: string): React.ReactNode => {
      // Split by inline math $...$
      const parts = text.split(/(\$[^$]+\$)/g);
      return parts.map((part, idx) => {
        if (part.startsWith('$') && part.endsWith('$') && part.length > 2) {
          const math = part.slice(1, -1);
          try {
            const html = katex.renderToString(math, {
              displayMode: false,
              throwOnError: false,
            });
            return (
              <span
                key={idx}
                dangerouslySetInnerHTML={{ __html: html }}
                className="inline-block px-1 text-indigo-300 font-medium"
              />
            );
          } catch {
            return <code key={idx} className="text-amber-400 font-mono text-xs">{part}</code>;
          }
        }

        // Handle bold **text**
        const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
        return boldParts.map((bPart, bIdx) => {
          if (bPart.startsWith('**') && bPart.endsWith('**')) {
            return <strong key={`${idx}-${bIdx}`} className="text-white font-semibold">{bPart.slice(2, -2)}</strong>;
          }
          // Handle code `inline`
          const codeParts = bPart.split(/(`[^`]+`)/g);
          return codeParts.map((cPart, cIdx) => {
            if (cPart.startsWith('`') && cPart.endsWith('`')) {
              return (
                <code
                  key={`${idx}-${bIdx}-${cIdx}`}
                  className="px-1.5 py-0.5 rounded bg-neutral-800 text-indigo-300 font-mono text-xs"
                >
                  {cPart.slice(1, -1)}
                </code>
              );
            }
            return cPart;
          });
        });
      });
    };

    lines.forEach((line, lineIndex) => {
      const trimmed = line.trim();

      // Check for start/end of block math $$
      if (trimmed.startsWith('$$') && trimmed.endsWith('$$') && trimmed.length > 4) {
        flushList(`flush-${lineIndex}`);
        const math = trimmed.slice(2, -2);
        try {
          const html = katex.renderToString(math, {
            displayMode: true,
            throwOnError: false,
          });
          elements.push(
            <div
              key={`block-math-${lineIndex}`}
              dangerouslySetInnerHTML={{ __html: html }}
              className="my-3 py-2 px-3 rounded-lg bg-neutral-900/80 border border-neutral-800/80 overflow-x-auto text-center"
            />
          );
        } catch {
          elements.push(
            <pre key={`math-err-${lineIndex}`} className="p-2 text-xs text-amber-400 font-mono">
              {math}
            </pre>
          );
        }
        return;
      }

      if (trimmed === '$$') {
        if (!inBlockMath) {
          inBlockMath = true;
          blockMathAccumulator = '';
        } else {
          inBlockMath = false;
          flushList(`flush-${lineIndex}`);
          try {
            const html = katex.renderToString(blockMathAccumulator, {
              displayMode: true,
              throwOnError: false,
            });
            elements.push(
              <div
                key={`multi-math-${lineIndex}`}
                dangerouslySetInnerHTML={{ __html: html }}
                className="my-3 py-2 px-3 rounded-lg bg-neutral-900/80 border border-neutral-800/80 overflow-x-auto text-center"
              />
            );
          } catch {
            elements.push(
              <pre key={`math-err-${lineIndex}`} className="p-2 text-xs text-amber-400 font-mono">
                {blockMathAccumulator}
              </pre>
            );
          }
        }
        return;
      }

      if (inBlockMath) {
        blockMathAccumulator += (blockMathAccumulator ? '\n' : '') + line;
        return;
      }

      // Headers
      if (trimmed.startsWith('### ')) {
        flushList(`flush-${lineIndex}`);
        elements.push(
          <h4 key={`h3-${lineIndex}`} className="text-base font-semibold text-neutral-100 mt-4 mb-2">
            {renderInlineMathAndFormatting(trimmed.slice(4))}
          </h4>
        );
        return;
      }
      if (trimmed.startsWith('## ')) {
        flushList(`flush-${lineIndex}`);
        elements.push(
          <h3 key={`h2-${lineIndex}`} className="text-lg font-bold text-neutral-50 mt-5 mb-2 pb-1 border-b border-neutral-800">
            {renderInlineMathAndFormatting(trimmed.slice(3))}
          </h3>
        );
        return;
      }
      if (trimmed.startsWith('# ')) {
        flushList(`flush-${lineIndex}`);
        elements.push(
          <h2 key={`h1-${lineIndex}`} className="text-xl font-bold text-white mt-6 mb-3">
            {renderInlineMathAndFormatting(trimmed.slice(2))}
          </h2>
        );
        return;
      }

      // Lists
      if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        inList = true;
        listItems.push(
          <li key={`li-${lineIndex}`} className="leading-relaxed">
            {renderInlineMathAndFormatting(trimmed.slice(2))}
          </li>
        );
        return;
      }

      // Numbered lists
      const numberedMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
      if (numberedMatch) {
        inList = true;
        listItems.push(
          <li key={`li-num-${lineIndex}`} className="leading-relaxed">
            <span className="text-neutral-400 font-mono mr-1">{numberedMatch[1]}.</span>{' '}
            {renderInlineMathAndFormatting(numberedMatch[2])}
          </li>
        );
        return;
      }

      // Empty line
      if (trimmed === '') {
        flushList(`flush-${lineIndex}`);
        return;
      }

      // Regular paragraph
      flushList(`flush-${lineIndex}`);
      elements.push(
        <p key={`p-${lineIndex}`} className="my-2 leading-relaxed text-neutral-300 text-sm">
          {renderInlineMathAndFormatting(line)}
        </p>
      );
    });

    flushList('flush-end');
    return elements;
  }, [content]);

  return <div className={`space-y-1 ${className}`}>{renderedElements}</div>;
};

interface SingleFormulaProps {
  latex: string;
  displayMode?: boolean;
}

export const SingleFormula: React.FC<SingleFormulaProps> = ({ latex, displayMode = true }) => {
  const cleanLatex = useMemo(() => repairCorruptedLatex(latex), [latex]);
  const html = useMemo(() => {
    try {
      return katex.renderToString(cleanLatex, {
        displayMode,
        throwOnError: false,
      });
    } catch {
      return null;
    }
  }, [cleanLatex, displayMode]);

  if (!html) {
    return <code className="text-amber-400 font-mono text-xs">{cleanLatex}</code>;
  }

  return (
    <span
      dangerouslySetInnerHTML={{ __html: html }}
      className={displayMode ? "block my-2 overflow-x-auto text-center" : "inline-block px-1"}
    />
  );
};
