import express from 'express';
import { createServer as createViteServer } from 'vite';
import { GoogleGenAI, Type } from '@google/genai';
import dotenv from 'dotenv';
import path from 'path';

dotenv.config();

const app = express();
const PORT = 3000;

// Support audio and PDF uploads up to 50MB
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

function createGeminiClient(apiKey: string) {
  return new GoogleGenAI({
    apiKey,
    httpOptions: {
      headers: {
        'User-Agent': 'aistudio-build',
      },
    },
  });
}

function repairLatexControlChars(val: any): any {
  if (typeof val === 'string') {
    return val
      .replace(/\x0c(rac|orall|lat|rown|box|int)/g, '\\f$1')
      .replace(/\x0c/g, '\\f')
      .replace(/\x08(eta|egin|inom|ar|f|ig|ullet|oxed|ot|ackslash|oldsymbol)/g, '\\b$1')
      .replace(/\x08/g, '\\b')
      .replace(/\x09(heta|au|imes|ext|ilde|an|anh|op|riangle|o\b|herefore|iny)/g, '\\t$1')
      .replace(/\x0d(ight|ightarrow|ho|angle|ceil|floor|ule|m)/g, '\\r$1')
      .replace(/\n(abla|eq\b|u\b|ot\b|atural|exists|ewline|mid|parallel|otin)/g, '\\n$1');
  }
  if (Array.isArray(val)) {
    return val.map(repairLatexControlChars);
  }
  if (val && typeof val === 'object') {
    const out: Record<string, any> = {};
    for (const [k, v] of Object.entries(val)) {
      out[k] = repairLatexControlChars(v);
    }
    return out;
  }
  return val;
}

/**
 * Safely parses JSON returned by an LLM that may contain LaTeX backslashes (e.g. \int, \sum, \alpha, \frac, \beta, \theta)
 */
function parseJsonWithLatexSafe(rawText: string): any {
  const stripped = rawText.replace(/```json\s*|```/g, '').trim();

  // Escape single backslashes before LaTeX commands that collide with JSON escape chars (\f, \b, \t, \r, \n)
  const preSanitized = stripped.replace(
    /(?<!\\)\\(frac|forall|flat|theta|tau|times|text|tilde|tan|tanh|top|triangle|to\b|therefore|beta|begin|binom|bar|bf|big|bullet|boxed|bot|backslash|boldsymbol|rho|right|rightarrow|rangle|rceil|rfloor|nabla|neq\b|nu\b|not\b|natural|nexists|notin)/g,
    '\\\\$1'
  );

  // 1. Try JSON.parse on preSanitized string
  try {
    return repairLatexControlChars(JSON.parse(preSanitized));
  } catch {
    // 2. Also escape any single backslash not followed by valid JSON escape chars
    try {
      const fixedBackslashes = preSanitized.replace(/\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})/g, '\\\\');
      return repairLatexControlChars(JSON.parse(fixedBackslashes));
    } catch {
      // 3. Extract the outermost {...} object and try again
      const firstBrace = preSanitized.indexOf('{');
      const lastBrace = preSanitized.lastIndexOf('}');
      if (firstBrace !== -1 && lastBrace > firstBrace) {
        const slice = preSanitized.slice(firstBrace, lastBrace + 1);
        const fixedSlice = slice.replace(/\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})/g, '\\\\');
        return repairLatexControlChars(JSON.parse(fixedSlice));
      }
      throw new Error('Could not parse JSON even after LaTeX backslash sanitization');
    }
  }
}

// Healthcheck
app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', hasKey: !!process.env.GEMINI_API_KEY });
});

// Audio transcription and structuring endpoint with automatic model fallback on 503 spikes
app.post('/api/transcribe', async (req, res) => {
  try {
    const { audioBase64, mimeType, title, subject } = req.body;
    if (!audioBase64) {
      return res.status(400).json({ error: 'Аудиоданные не получены' });
    }

    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      console.warn('GEMINI_API_KEY is not set');
      return res.status(500).json({ error: 'GEMINI_API_KEY не настроен' });
    }

    const ai = createGeminiClient(apiKey);

    const prompt = `Ты — академический ИИ-ассистент для студентов университета.
Тема занятия: "${title || 'Без названия'}"
Предмет: "${subject || 'Учебное занятие'}"

Внимательно прослушай эту аудиозапись и выполни следующие задачи максимально подробно:
1. segments: ПОЛНАЯ, дословная построчная расшифровка всей речи на русском языке без пропусков [{"startTime": секунды_начала, "endTime": секунды_конца, "speaker": "Лектор", "text": "фраза"}].
2. fullText: Полный связный текст всей речи.
3. summaryMarkdown: ОЧЕНЬ ПОДРОБНЫЙ, РАЗВЕРНУТЫЙ, ФУНДАМЕНТАЛЬНЫЙ университетский конспект лекции в формате Markdown.
   КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО делать краткую выжимку из пары абзацев!
   Конспект должен быть максимально полным и глубоким, чтобы по нему можно было готовиться к экзамену:
   - Подробно распиши КАЖДУЮ мысль, определение, теорему, свойство и причинно-следственную связь, озвученную лектором.
   - Если лектор упоминает понятия или формулы вскользь, разверни их и дай четкое академическое пояснение сути, физического или математического смысла и всех входящих величин.
   - Обязательно используй четкую структуру:
     ## 1. Введение и контекст темы
     ## 2. Ключевые понятия и строгие определения
     ## 3. Подробный теоретический разбор (по подразделам ###)
     ## 4. Математический аппарат, формулы и выводы (в синтаксисе LaTeX $...$ и $$...$$ с расшифровкой всех переменных)
     ## 5. Разобранные примеры и практическое применение
     ## 6. Итоговые выводы и контрольные вопросы к экзамену (с ответами)
4. actionItems: Все домашние задания, дедлайны, даты сдачи, коллоквиумы, лабораторные:
   [{"task": "описание задачи", "deadline": "названный срок (например 'к пятнице 18:00')", "priority": "high"|"medium"|"low"}]
5. latexFormulas: Все формулы по теме лекции:
   [{"title": "название формулы", "latex": "код LaTeX без знаков $", "context": "подробное пояснение величин и применения"}]`;

    const candidateModels = [
      'gemini-3.5-transcribe',
      'gemini-3.8-flash',
      'gemini-flash-latest',
      'gemini-3.1-flash-lite',
    ];

    let responseText = '';
    let lastError: any = null;

    for (const modelName of candidateModels) {
      try {
        const response = await ai.models.generateContent({
          model: modelName,
          contents: [
            {
              role: 'user',
              parts: [
                {
                  inlineData: {
                    mimeType: mimeType || 'audio/webm',
                    data: audioBase64,
                  },
                },
                {
                  text: prompt,
                },
              ],
            },
          ],
          config: {
            responseMimeType: 'application/json',
            maxOutputTokens: 16384,
          },
        });
        responseText = response.text || '';
        if (responseText) {
          break;
        }
      } catch (err: any) {
        lastError = err;
        await new Promise((r) => setTimeout(r, 400));
      }
    }

    if (!responseText && lastError) {
      throw lastError;
    }

    try {
      const parsed = parseJsonWithLatexSafe(responseText);
      return res.json(parsed);
    } catch {
      return res.json({
        fullText: responseText,
        summaryMarkdown: `## Конспект лекции\n\n${responseText}`,
        segments: [{ startTime: 0, endTime: 10, speaker: 'Лектор', text: responseText }],
        actionItems: [],
        latexFormulas: [],
      });
    }
  } catch (error: any) {
    console.error('Transcription error:', error);
    res.status(500).json({ error: error.message || 'Ошибка распознавания аудио' });
  }
});

// Intelligent document analysis & structuring endpoint for PDF / Markdown / Text imports
app.post('/api/structure-document', async (req, res) => {
  try {
    const { rawText, fileName, fileBase64, mimeType } = req.body;
    if (!rawText && !fileBase64) {
      return res.status(400).json({ error: 'Текст или содержимое документа не получены' });
    }

    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      return res.status(500).json({ error: 'GEMINI_API_KEY не настроен' });
    }

    const ai = createGeminiClient(apiKey);
    const cleanDefaultTitle = String(fileName || 'Лекция').replace(/\.[^/.]+$/, '').replace(/_/g, ' ');

    const prompt = `Ты — профессор и составитель фундаментальных университетских конспектов для студентов.
Пользователь загрузил учебный файл: "${fileName || 'Документ'}".

ГЛАВНОЕ ТРЕБОВАНИЕ К ОБЪЕМУ И ГЛУБИНЕ ("summaryMarkdown"):
КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО делать короткую сводку, краткий пересказ или сжимать материал до нескольких абзацев!
Конспект в поле "summaryMarkdown" должен быть МАКСИМАЛЬНО ПОДРОБНЫМ, ОБЪЕМНЫМ, ФУНДАМЕНТАЛЬНЫМ И ИСЧЕРПЫВАЮЩИМ (минимум 1500–3500 слов, с сохранением 100% деталей, определений, доказательств, примеров и формул из документа).

Алгоритм работы:
ШАГ 1. Оцени структуру исходного документа (поле "isAlreadyStructured"):
- Если документ УЖЕ является готовым структурированным конспектом -> установи "isAlreadyStructured": true. Сохрани ВЕСЬ авторский текст целиком без сокращений, исправив склеенные переносы строк из PDF, приведя формулы к LaTeX ($...$ и $$...$$) и дополнив сложные места пояснениями.
- Если документ — «сырой» текст из PDF, презентация со слайдами, методичка, учебник или черновые заметки -> установи "isAlreadyStructured": false. Преобразуй ВЕСЬ материал документа от первой до последней страницы в фундаментальный, развернутый университетский конспект в формате Markdown ("summaryMarkdown"). Если на слайдах или в тексте даны лишь краткие тезисы — РАЗВЕРНИ каждый тезис в полноценное академическое объяснение с теорией, выводом формул и примерами!

Обязательная структура поля "summaryMarkdown" (при "isAlreadyStructured": false):
## 1. Введение, постановка задачи и ключевая идея темы
(Подробное введение: что изучается, зачем это нужно, физический/математический/прикладной смысл).
## 2. Фундаментальные понятия и строгие определения
(Полный разбор каждого термина, обозначения, аксиомы и допущения).
## 3. Детальный теоретический разбор по разделам
(Разбей весь материал документа на логические подразделы ### 3.1, ### 3.2, ### 3.3 и т.д. Подробно изложи каждую теорему, свойство, шаг доказательства, механизм или классификацию из документа без единого пропуска!).
## 4. Математический аппарат, вывод формул и расчетные соотношения
(Все формулы в синтаксисе LaTeX $...$ и $$...$$, с пошаговым пояснением вывода и подробной расшифровкой каждой буквы/переменной и единиц измерения).
## 5. Подробный разбор практических примеров и задач
(Детальный пошаговый разбор всех примеров из документа + пояснение алгоритма решения типовых задач по этой теме).
## 6. Тонкости, граничные случаи и вопросы для подготовки к экзамену
(Развернутые ответы на 4–6 ключевых экзаменационных вопросов по материалу этой лекции).

ШАГ 2. Извлеки метаданные, задачи и формулы:
- "title": Точная тема лекции или документа.
- "subject": Название учебного предмета / дисциплины.
- "lecturer": Имя преподавателя или автора, если указано (иначе "Материалы курса").
- "tags": Массив из 2–4 коротких тегов по теме лекции.
- "actionItems": Все упомянутые в документе домашние задания, задачи для самостоятельного решения, вопросы к коллоквиуму или дедлайны.
- "latexFormulas": Все важные формулы из документа (до 15 штук), где поле "latex" содержит чистый код LaTeX без символов $.`;

    const parts: any[] = [];
    if (fileBase64 && mimeType === 'application/pdf') {
      parts.push({
        inlineData: {
          mimeType: 'application/pdf',
          data: fileBase64,
        },
      });
    }
    if (rawText) {
      parts.push({
        text: `Содержимое файла (${fileName || 'документ'}):\n\n${String(rawText).slice(0, 90000)}`,
      });
    }
    parts.push({ text: prompt });

    const documentResponseSchema = {
      type: Type.OBJECT,
      properties: {
        isAlreadyStructured: { type: Type.BOOLEAN },
        processingNote: { type: Type.STRING },
        title: { type: Type.STRING },
        subject: { type: Type.STRING },
        lecturer: { type: Type.STRING },
        tags: {
          type: Type.ARRAY,
          items: { type: Type.STRING },
        },
        summaryMarkdown: { type: Type.STRING },
        actionItems: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              task: { type: Type.STRING },
              deadline: { type: Type.STRING },
              priority: { type: Type.STRING },
            },
            required: ['task', 'deadline', 'priority'],
          },
        },
        latexFormulas: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              title: { type: Type.STRING },
              latex: { type: Type.STRING },
              context: { type: Type.STRING },
            },
            required: ['title', 'latex', 'context'],
          },
        },
      },
      required: [
        'isAlreadyStructured',
        'title',
        'subject',
        'lecturer',
        'tags',
        'summaryMarkdown',
        'actionItems',
        'latexFormulas',
      ],
    };

    const candidateModels = [
      'gemini-3.8-flash',
      'gemini-flash-latest',
      'gemini-3.1-flash-lite',
    ];

    let responseText = '';
    let lastError: any = null;

    for (const modelName of candidateModels) {
      try {
        const response = await ai.models.generateContent({
          model: modelName,
          contents: [{ role: 'user', parts }],
          config: {
            responseMimeType: 'application/json',
            responseSchema: documentResponseSchema,
            maxOutputTokens: 16384,
          },
        });
        responseText = response.text || '';
        if (responseText) {
          break;
        }
      } catch (err: any) {
        lastError = err;
        await new Promise((r) => setTimeout(r, 400));
      }
    }

    if (!responseText && lastError) {
      throw lastError;
    }

    try {
      const parsed = parseJsonWithLatexSafe(responseText);
      return res.json(parsed);
    } catch {
      return res.json({
        isAlreadyStructured: false,
        title: cleanDefaultTitle,
        subject: 'Учебная дисциплина',
        lecturer: 'Материалы курса',
        tags: ['Конспект', 'Документ'],
        summaryMarkdown: responseText || String(rawText || ''),
        actionItems: [],
        latexFormulas: [],
      });
    }
  } catch (error: any) {
    console.error('Document structuring error:', error);
    res.status(500).json({ error: error.message || 'Ошибка интеллектуальной обработки документа' });
  }
});

// Deeply expand an existing lecture summary into a comprehensive textbook-grade lecture note
app.post('/api/expand-lecture', async (req, res) => {
  try {
    const { title, subject, summaryMarkdown, transcriptText } = req.body;
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      return res.status(500).json({ error: 'GEMINI_API_KEY не настроен' });
    }

    const ai = createGeminiClient(apiKey);

    const prompt = `Ты — ведущий университетский профессор по дисциплине "${subject || 'Высшая школа'}".
Перед тобой текущий конспект лекции на тему "${title || 'Лекция'}" и исходная стенограмма/текст.
Студент просит сделать этот конспект НАМНОГО ПОДРОБНЕЕ, ГЛУБЖЕ и ПОЛНЕЕ.

Задача:
Напиши фундаментальный, максимально подробный, развернутый академический конспект этой лекции в формате Markdown (с формулами LaTeX $...$ и $$...$$).
1. Сохрани все факты из текущего конспекта и исходного текста, но расширь каждый раздел в 3–4 раза:
   - Добавь строгие академические определения каждого понятия.
   - Подробно распиши физический, математический или теоретический смысл каждого утверждения.
   - Пошагово распиши выводы формул и расшифруй каждую переменную.
   - Добавь подробные практические примеры с пошаговым решением/разбором.
   - В конце добавь раздел с развернутыми ответами на главные вопросы, которые задают по этой теме на коллоквиуме и экзамене.
2. Не используй общие фразы — пиши содержательный, плотный учебный материал университетского уровня.
3. Верни ТОЛЬКО готовый расширенный текст конспекта в формате Markdown (без JSON-обертки).

Текущий конспект:
${String(summaryMarkdown || '').slice(0, 40000)}

Исходный текст / стенограмма:
${String(transcriptText || '').slice(0, 40000)}`;

    const candidateModels = [
      'gemini-3.8-flash',
      'gemini-flash-latest',
      'gemini-3.1-flash-lite',
    ];

    let expandedMarkdown = '';
    let lastError: any = null;

    for (const modelName of candidateModels) {
      try {
        const response = await ai.models.generateContent({
          model: modelName,
          contents: [{ role: 'user', parts: [{ text: prompt }] }],
          config: {
            maxOutputTokens: 16384,
          },
        });
        expandedMarkdown = (response.text || '').trim();
        if (expandedMarkdown) {
          break;
        }
      } catch (err: any) {
        lastError = err;
        await new Promise((r) => setTimeout(r, 400));
      }
    }

    if (!expandedMarkdown && lastError) {
      throw lastError;
    }

    return res.json({ summaryMarkdown: expandedMarkdown });
  } catch (error: any) {
    console.error('Expand lecture error:', error);
    res.status(500).json({ error: error.message || 'Не удалось расширить конспект' });
  }
});

async function startServer() {
  if (process.env.NODE_ENV === 'production') {
    app.use(express.static(path.resolve('dist')));
    app.get('*', (_req, res) => {
      res.sendFile(path.resolve('dist', 'index.html'));
    });
  } else {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server listening on http://0.0.0.0:${PORT}`);
  });
}

startServer();
