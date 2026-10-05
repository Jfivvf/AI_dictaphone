import * as pdfjsLib from 'pdfjs-dist';
import { Lecture, ActionItem, LatexFormula, TranscriptSegment } from '../types';

// Set up pdf.js worker using standard jsdelivr CDN matching the installed version
try {
  pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`;
} catch {
  // Ignored if already set
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode.apply(null, Array.from(chunk));
  }
  return btoa(binary);
}

/**
 * Parses a PDF file and extracts text from all pages
 */
export async function extractTextFromPdf(file: File): Promise<string> {
  try {
    const arrayBuffer = await file.arrayBuffer();
    const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
    const pdf = await loadingTask.promise;
    let fullText = '';

    for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
      const page = await pdf.getPage(pageNum);
      const textContent = await page.getTextContent();
      const pageText = textContent.items
        .map((item) => ('str' in item ? item.str : ''))
        .join(' ');
      
      fullText += `\n\n### Страница ${pageNum}\n` + pageText;
    }

    if (fullText.trim().length > 20) {
      return fullText.trim();
    }
    throw new Error('PDF empty or scanned images');
  } catch (err) {
    console.warn('pdf.js extraction failed, falling back to raw stream decode:', err);
    const arrayBuffer = await file.arrayBuffer();
    const text = new TextDecoder('utf-8', { fatal: false }).decode(arrayBuffer);
    
    const textBlocks: string[] = [];
    const streamRegex = /\(([^)]+)\)\s*T[jJ]/g;
    let match;
    while ((match = streamRegex.exec(text)) !== null) {
      if (match[1] && match[1].length > 2) {
        textBlocks.push(match[1]);
      }
    }

    if (textBlocks.length > 5) {
      return textBlocks.join(' ');
    }

    return '';
  }
}

function buildSourceSegments(rawText: string, lectureId: string): TranscriptSegment[] {
  const clean = (rawText || '').trim();
  if (!clean) {
    return [
      {
        id: `seg_${lectureId}_0`,
        startTime: 0,
        endTime: 10,
        speaker: 'Исходный документ',
        text: 'Импортированный учебный файл.',
        bookmarked: false,
      },
    ];
  }
  const paragraphs = clean
    .split(/\n{2,}/)
    .map((p) => p.replace(/\s+/g, ' ').trim())
    .filter((p) => p.length > 0)
    .slice(0, 60);

  return paragraphs.map((p, idx) => ({
    id: `seg_${lectureId}_${idx}`,
    startTime: idx * 15,
    endTime: (idx + 1) * 15,
    speaker: 'Исходный текст',
    text: p,
    bookmarked: false,
  }));
}

/**
 * Smart AI-powered document import:
 * Automatically detects whether the file is already a clean lecture summary
 * or needs to be structured into a neat academic Markdown + LaTeX note.
 */
export async function smartImportDocumentToLecture(file: File): Promise<Lecture> {
  const isPdf = file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf';
  let rawText = '';
  let fileBase64: string | undefined;

  if (isPdf) {
    rawText = await extractTextFromPdf(file);
    // Always pass base64 for PDFs up to 15MB so Gemini natively reads all pages, formulas, and tables
    if (file.size <= 15 * 1024 * 1024) {
      const buf = await file.arrayBuffer();
      fileBase64 = arrayBufferToBase64(buf);
    }
  } else {
    rawText = await file.text();
  }

  const fallbackLecture = convertTextToLecture(
    rawText || `### Импортированный документ: ${file.name}`,
    file.name
  );

  try {
    const response = await fetch('/api/structure-document', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rawText,
        fileName: file.name,
        fileBase64,
        mimeType: isPdf ? 'application/pdf' : 'text/plain',
      }),
    });

    if (!response.ok) {
      return fallbackLecture;
    }

    const aiData = await response.json();
    const lectureId = `lec_doc_${Date.now()}`;
    const cleanDefaultTitle = file.name.replace(/\.[^/.]+$/, '').replace(/_/g, ' ');

    const aiTasks: ActionItem[] = Array.isArray(aiData.actionItems)
      ? aiData.actionItems.slice(0, 10).map((item: any, idx: number) => ({
          id: `doc_task_${Date.now()}_${idx}`,
          task: String(item.task || 'Повторить материал документа').slice(0, 1000),
          deadline: String(item.deadline || 'К следующему занятию').slice(0, 200),
          dateISO: new Date(Date.now() + 5 * 24 * 3600 * 1000).toISOString().split('T')[0],
          type: 'homework',
          completed: false,
          priority:
            item.priority === 'high' || item.priority === 'medium' || item.priority === 'low'
              ? item.priority
              : 'medium',
        }))
      : fallbackLecture.actionItems;

    const aiFormulas: LatexFormula[] = Array.isArray(aiData.latexFormulas)
      ? aiData.latexFormulas.slice(0, 15).map((f: any, idx: number) => ({
          id: `doc_f_${Date.now()}_${idx}`,
          title: String(f.title || 'Формула из лекции').slice(0, 150),
          latex: String(f.latex || '').replace(/^\$+|\$+$/g, '').trim(),
          context: String(f.context || 'Извлечено из документа').slice(0, 300),
        }))
      : fallbackLecture.latexFormulas;

    const aiTags: string[] =
      Array.isArray(aiData.tags) && aiData.tags.length > 0
        ? aiData.tags.slice(0, 8).map((t: any) => String(t).slice(0, 100))
        : fallbackLecture.tags;

    const modeBadge = aiData.isAlreadyStructured
      ? 'Готовая лекция (форматирование сохранено)'
      : 'Авто-конспект ИИ из документа';

    return {
      id: lectureId,
      title: String(aiData.title || cleanDefaultTitle).slice(0, 300),
      subject: String(aiData.subject || 'Учебная дисциплина').slice(0, 200),
      lecturer: String(aiData.lecturer || 'Материалы курса').slice(0, 200),
      date: new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }),
      durationSeconds: Math.max(60, Math.min(7200, Math.round((rawText.length || 1200) / 15))),
      tags: aiTags,
      noiseLevel: 'quiet',
      modelUsed: modeBadge,
      quantization: isPdf ? 'PDF' : 'Markdown',
      transcript: buildSourceSegments(rawText || aiData.summaryMarkdown || '', lectureId),
      summaryMarkdown: String(aiData.summaryMarkdown || fallbackLecture.summaryMarkdown).slice(0, 100000),
      actionItems: aiTasks.length > 0 ? aiTasks : fallbackLecture.actionItems,
      latexFormulas: aiFormulas,
      keyDefinitions: [],
    };
  } catch (err) {
    console.warn('Smart document structuring fallback:', err);
    return fallbackLecture;
  }
}

/**
 * Local fallback: converts extracted raw PDF or Markdown text into a Lecture note
 */
export function convertTextToLecture(rawText: string, fileName: string): Lecture {
  const cleanTitle = fileName.replace(/\.[^/.]+$/, '').replace(/_/g, ' ');
  const lectureId = `lec_pdf_${Date.now()}`;
  
  const lines = rawText.split('\n');
  const actionItems: ActionItem[] = [];
  const formulas: LatexFormula[] = [];

  const taskKeywords = [
    'задание', 'домашн', 'сдать', 'дедлайн', 'подготовить', 'коллоквиум', 
    'лабораторн', 'контрольн', 'экзамен', 'homework', 'task', 'deadline', 'due'
  ];

  lines.forEach((line, idx) => {
    const lower = line.toLowerCase();
    const isTask = taskKeywords.some(kw => lower.includes(kw));

    if (isTask && line.trim().length > 10 && line.trim().length < 200) {
      actionItems.push({
        id: `pdf_task_${idx}_${Date.now()}`,
        task: line.trim().replace(/^[-*•\d.)\s]+/, ''),
        deadline: 'По графику курса',
        dateISO: new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString().split('T')[0],
        type: lower.includes('лабораторн') ? 'project' : lower.includes('коллоквиум') || lower.includes('экзамен') ? 'exam' : 'homework',
        completed: false,
        priority: lower.includes('срочн') || lower.includes('важн') ? 'high' : 'medium'
      });
    }

    if ((line.includes('$') || line.includes('\\int') || line.includes('\\sum') || line.includes('\\frac')) && line.trim().length > 5) {
      formulas.push({
        id: `pdf_f_${idx}`,
        title: `Формула из ${fileName}`,
        latex: line.replace(/^\$+|\$+$/g, '').trim(),
        context: 'Извлечено из текста документа'
      });
    }
  });

  if (actionItems.length === 0) {
    actionItems.push({
      id: `pdf_task_default_${Date.now()}`,
      task: `Ознакомиться с материалами документа "${cleanTitle}"`,
      deadline: 'К следующему занятию',
      dateISO: new Date(Date.now() + 5 * 24 * 3600 * 1000).toISOString().split('T')[0],
      type: 'reading',
      completed: false,
      priority: 'medium'
    });
  }

  let formattedMarkdown = `## ${cleanTitle}\n\n`;
  formattedMarkdown += `*Импортировано из файла ${fileName}*\n\n`;
  formattedMarkdown += `---\n\n`;
  formattedMarkdown += rawText;

  return {
    id: lectureId,
    title: cleanTitle,
    subject: 'Импортированные материалы',
    lecturer: 'Материалы курса',
    date: new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }),
    durationSeconds: 1800,
    tags: ['Документ', 'Конспект'],
    noiseLevel: 'quiet',
    modelUsed: 'Импорт документа',
    quantization: 'Текст',
    transcript: buildSourceSegments(rawText, lectureId),
    summaryMarkdown: formattedMarkdown,
    actionItems: actionItems.slice(0, 8),
    latexFormulas: formulas.slice(0, 10),
    keyDefinitions: []
  };
}
