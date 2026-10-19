import express from 'express';
import { createServer as createViteServer } from 'vite';
import { GoogleGenAI, Type } from '@google/genai';
import dotenv from 'dotenv';
import path from 'path';
import fs from 'fs';
import os from 'os';

dotenv.config();

const app = express();
const PORT = 3000;

// Support large payloads and chunked audio uploads
app.use(express.json({ limit: '150mb' }));
app.use(express.urlencoded({ extended: true, limit: '150mb' }));

// Temporary store for chunked audio uploads (avoids Cloud Run 32MB per-request HTTP limit on 40-90 min lectures)
const audioChunkStore = new Map<string, { chunks: string[]; createdAt: number }>();

// Cleanup stale chunk sessions older than 30 minutes
setInterval(() => {
  const now = Date.now();
  for (const [key, val] of audioChunkStore.entries()) {
    if (now - val.createdAt > 30 * 60 * 1000) {
      audioChunkStore.delete(key);
    }
  }
}, 5 * 60 * 1000);

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

/**
 * Starts an HTTP 200 JSON stream with periodic whitespace heartbeats every 4 seconds.
 * Prevents Cloud Run / iframe proxy timeouts ("TypeError: Failed to fetch") during long AI generations.
 */
function startKeepAliveJsonResponse(res: express.Response) {
  res.status(200);
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-cache, no-transform');
  res.setHeader('X-Accel-Buffering', 'no');
  res.flushHeaders();

  const timer = setInterval(() => {
    if (!res.writableEnded) {
      try {
        res.write(' ');
      } catch {}
    }
  }, 4000);

  return {
    sendJson: (data: any) => {
      clearInterval(timer);
      if (!res.writableEnded) {
        res.end(JSON.stringify(data));
      }
    },
    stop: () => {
      clearInterval(timer);
    },
  };
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

  // 1. First try native JSON.parse directly (works immediately when model properly escaped \\neg, \\equiv, \\to, etc.)
  try {
    return repairLatexControlChars(JSON.parse(stripped));
  } catch {}

  // 2. Escape ONLY single backslashes (neither preceded nor followed by another backslash) before LaTeX commands that collide with JSON escape chars (\f, \b, \t, \r, \n)
  const preSanitized = stripped.replace(
    /(?<!\\)\\(?!\\)(frac|forall|flat|theta|tau|times|text|tilde|tan|tanh|top|triangle|to\b|therefore|beta|begin|binom|bar|bf|big|bullet|boxed|bot|backslash|boldsymbol|rho|right|rightarrow|rangle|rceil|rfloor|nabla|neq\b|nu\b|not\b|natural|nexists|notin)/g,
    '\\\\$1'
  );

  try {
    return repairLatexControlChars(JSON.parse(preSanitized));
  } catch {}

  // 3. Escape any single unescaped backslash (using negative lookbehind (?<!\\) so valid \\equiv is NEVER turned into \\\equiv)
  const fixedBackslashes = preSanitized.replace(/(?<!\\)\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})/g, '\\\\');
  try {
    return repairLatexControlChars(JSON.parse(fixedBackslashes));
  } catch {
    // 4. Extract outermost {...} object and try again
    const firstBrace = fixedBackslashes.indexOf('{');
    const lastBrace = fixedBackslashes.lastIndexOf('}');
    if (firstBrace !== -1 && lastBrace > firstBrace) {
      const slice = fixedBackslashes.slice(firstBrace, lastBrace + 1);
      return repairLatexControlChars(JSON.parse(slice));
    }
    throw new Error('Could not parse JSON even after LaTeX backslash sanitization');
  }
}

// Healthcheck
app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', hasKey: !!process.env.GEMINI_API_KEY });
});

// Receive 3MB audio chunks so 40-90 minute recordings never trigger HTTP 413 Payload Too Large
app.post('/api/upload-audio-chunk', (req, res) => {
  try {
    const { uploadId, chunkIndex, chunkData } = req.body;
    if (!uploadId || typeof chunkData !== 'string') {
      return res.status(400).json({ error: 'Некорректные данные чанка' });
    }
    let session = audioChunkStore.get(uploadId);
    if (!session) {
      session = { chunks: [], createdAt: Date.now() };
      audioChunkStore.set(uploadId, session);
    }
    session.chunks[Number(chunkIndex) || 0] = chunkData;
    return res.json({ ok: true, receivedChunk: chunkIndex });
  } catch (err: any) {
    console.error('Chunk upload error:', err);
    return res.status(500).json({ error: err.message || 'Ошибка загрузки чанка' });
  }
});

// Live 2-minute segment transcription during long (>1 hour) recordings
app.post('/api/transcribe-segment', async (req, res) => {
  try {
    const { audioBase64, mimeType, title, subject, aiContext } = req.body;
    if (!audioBase64) {
      return res.status(400).json({ error: 'Empty segment' });
    }
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      return res.status(500).json({ error: 'GEMINI_API_KEY not set' });
    }

    const ai = createGeminiClient(apiKey);
    const cleanMime = (mimeType || 'audio/webm').split(';')[0].trim() || 'audio/webm';

    const prompt = `Ты — точный академический стенографист на университетской лекции.
Предмет: "${subject || 'Учебная дисциплина'}". Тема: "${title || 'Лекция'}".
${aiContext ? `Контекст и термины: "${aiContext}".` : ''}
Дословно и без сокращений расшифруй речь лектора из этого аудиофрагмента на русском языке.
Если в фрагменте тишина или нет речи — верни пустую строку. Верни ТОЛЬКО чистый текст расшифровки без комментариев от себя.`;

    const candidateModels = [
      'gemini-3.5-transcribe',
      'gemini-flash-latest',
      'gemini-3.8-flash',
      'gemini-3.1-flash-lite',
    ];

    let segmentText = '';
    for (const modelName of candidateModels) {
      try {
        const response = await ai.models.generateContent({
          model: modelName,
          contents: [
            {
              role: 'user',
              parts: [
                { inlineData: { mimeType: cleanMime, data: audioBase64 } },
                { text: prompt },
              ],
            },
          ],
          config: {
            maxOutputTokens: 2048,
          },
        });
        segmentText = (response.text || '').trim();
        if (segmentText) break;
      } catch {
        await new Promise((r) => setTimeout(r, 200));
      }
    }

    return res.json({ text: segmentText });
  } catch (err: any) {
    console.warn('Segment transcription error:', err);
    return res.json({ text: '' });
  }
});

// Audio transcription and structuring endpoint with chunked upload support & keep-alive streaming
app.post('/api/transcribe', async (req, res) => {
  let tempFilePath: string | null = null;
  const { audioBase64: directBase64, uploadId, mimeType, title, subject, aiContext, liveTranscript } = req.body;

  let audioBase64 = directBase64 || '';
  if (!audioBase64 && uploadId && audioChunkStore.has(uploadId)) {
    const session = audioChunkStore.get(uploadId)!;
    audioBase64 = session.chunks.join('');
    audioChunkStore.delete(uploadId);
  }

  if (!audioBase64 && !liveTranscript && !aiContext) {
    return res.status(400).json({ error: 'Аудиоданные не получены' });
  }

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    console.warn('GEMINI_API_KEY is not set');
    return res.status(500).json({ error: 'GEMINI_API_KEY не настроен' });
  }

  const streamHelper = startKeepAliveJsonResponse(res);

  try {
    const ai = createGeminiClient(apiKey);

    const contextInstruction = aiContext
      ? `\nДополнительный контекст, термины и заметки от студента (ОБЯЗАТЕЛЬНО используй для точного распознавания созвучных научных терминов, фамилий ученых, формул и структуры конспекта): "${aiContext}"\n`
      : '';

    const browserTranscriptHint = liveTranscript
      ? `\nПострочная стенограмма, накопленная по ходу записи лекции (используй её вместе с аудиозаписью, чтобы не упустить ни одной минуты лекции): "${String(liveTranscript).slice(0, 90000)}"\n`
      : '';

    const prompt = `Ты — академический ИИ-ассистент для студентов университета.
Тема занятия: "${title || 'Без названия'}"
Предмет: "${subject || 'Учебное занятие'}"${contextInstruction}${browserTranscriptHint}
Внимательно прослушай эту аудиозапись (и накопленную стенограмму) и выполни следующие задачи (отдай 80% объема ответа именно в поле summaryMarkdown):
1. summaryMarkdown: ОЧЕНЬ ПОДРОБНЫЙ, РАЗВЕРНУТЫЙ, ФУНДАМЕНТАЛЬНЫЙ университетский конспект ВСЕЙ лекции от первой до последней минуты в формате Markdown.
   КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО делать краткую выжимку из пары абзацев!
   Конспект должен быть максимально полным и глубоким, чтобы по нему можно было готовиться к экзамену:
   - Подробно распиши КАЖДУЮ мысль, определение, теорему, свойство и причинно-следственную связь, озвученную лектором и указанную в контексте.
   - Если лектор упоминает понятия или формулы вскользь, разверни их и дай четкое академическое пояснение сути, физического или математического смысла и всех входящих величин.
   - Обязательно используй четкую структуру:
     ## 1. Введение и контекст темы
     ## 2. Ключевые понятия и строгие определения
     ## 3. Подробный теоретический разбор (по подразделам ###)
     ## 4. Математический аппарат, формулы и выводы (в синтаксисе LaTeX $...$ и $$...$$ с расшифровкой всех переменных)
     ## 5. Разобранные примеры и практическое применение
     ## 6. Итоговые выводы и контрольные вопросы к экзамену (с ответами)
2. actionItems: Все домашние задания, дедлайны, даты сдачи, коллоквиумы, лабораторные:
   [{"task": "описание задачи", "deadline": "названный срок (например 'к пятнице 18:00')", "priority": "high"|"medium"|"low"}]
3. latexFormulas: Все формулы по теме лекции:
   [{"title": "название формулы", "latex": "код LaTeX без знаков $", "context": "подробное пояснение величин и применения"}]
4. segments: Смысловые блоки речи с таймкодами [{"startTime": секунды_начала, "endTime": секунды_конца, "speaker": "Лектор", "text": "речь лектора"}].
5. fullText: Связный текст речи.`;

    const cleanMime = (mimeType || 'audio/webm').split(';')[0].trim() || 'audio/webm';
    let audioPart: any = null;

    if (audioBase64) {
      const binaryBuffer = Buffer.from(audioBase64, 'base64');
      if (binaryBuffer.length > 14 * 1024 * 1024) {
        try {
          const ext = cleanMime.includes('mp3') ? 'mp3' : cleanMime.includes('wav') ? 'wav' : 'webm';
          tempFilePath = path.join(os.tmpdir(), `lecture_${Date.now()}.${ext}`);
          fs.writeFileSync(tempFilePath, binaryBuffer);
          const uploadedFile = await ai.files.upload({
            file: tempFilePath,
            config: {
              mimeType: cleanMime,
            },
          });
          audioPart = {
            fileData: {
              fileUri: uploadedFile.uri,
              mimeType: uploadedFile.mimeType || cleanMime,
            },
          };
        } catch (fileUploadErr) {
          console.warn('Gemini File API upload fallback to capped inlineData:', fileUploadErr);
          const cappedBase64 = binaryBuffer.subarray(0, 14 * 1024 * 1024).toString('base64');
          audioPart = {
            inlineData: {
              mimeType: cleanMime,
              data: cappedBase64,
            },
          };
        }
      } else {
        audioPart = {
          inlineData: {
            mimeType: cleanMime,
            data: audioBase64,
          },
        };
      }
    }

    const transcribeResponseSchema = {
      type: Type.OBJECT,
      properties: {
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
        segments: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              startTime: { type: Type.NUMBER },
              endTime: { type: Type.NUMBER },
              speaker: { type: Type.STRING },
              text: { type: Type.STRING },
            },
            required: ['startTime', 'endTime', 'speaker', 'text'],
          },
        },
        fullText: { type: Type.STRING },
      },
      required: ['summaryMarkdown', 'actionItems', 'latexFormulas', 'segments', 'fullText'],
    };

    // Maximum accuracy mode: prioritizes deep reasoning, comprehensive coverage, and precise LaTeX formulas
    const candidateModels = [
      'gemini-flash-latest',
      'gemini-3.5-transcribe',
      'gemini-3.8-flash',
      'gemini-3.1-flash-lite',
    ];

    let responseText = '';
    let lastError: any = null;

    const parts: any[] = [];
    if (audioPart) parts.push(audioPart);
    parts.push({ text: prompt });

    for (const modelName of candidateModels) {
      try {
        const response = await ai.models.generateContent({
          model: modelName,
          contents: [
            {
              role: 'user',
              parts,
            },
          ],
          config: {
            responseMimeType: 'application/json',
            responseSchema: transcribeResponseSchema,
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

    let parsed: any;
    try {
      parsed = parseJsonWithLatexSafe(responseText);
    } catch {
      parsed = {
        fullText: responseText,
        summaryMarkdown: `## Конспект лекции\n\n${responseText}`,
        segments: [{ startTime: 0, endTime: 10, speaker: 'Лектор', text: responseText }],
        actionItems: [],
        latexFormulas: [],
      };
    }

    // Stage 2: In maximum accuracy mode, if the initial summary from the multimodal audio pass is condensed (< 3200 chars),
    // automatically run the dedicated academic note expansion pass so the very first summary is deep, rigorous, and complete.
    const currentSummary = String(parsed?.summaryMarkdown || '').trim();
    const fullTranscriptText =
      String(parsed?.fullText || '').trim() ||
      (Array.isArray(parsed?.segments) ? parsed.segments.map((s: any) => s.text).join('\n') : '') ||
      String(liveTranscript || '').trim();

    if (currentSummary.length < 3200 && (currentSummary || fullTranscriptText)) {
      try {
        const enrichPrompt = `Ты — ведущий университетский профессор по дисциплине "${subject || 'Высшая школа'}".
Тема лекции: "${title || 'Лекция'}".${contextInstruction}
На основе расшифровки аудиозаписи лекции и чернового плана ниже напиши ФУНДАМЕНТАЛЬНЫЙ, МАКСИМАЛЬНО ПОДРОБНЫЙ и РАЗВЕРНУТЫЙ академический конспект в формате Markdown (с формулами LaTeX $...$ и $$...$$).
КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО делать краткую сводку! Разверни каждое определение, теорему, доказательство, свойство и пример так, чтобы по конспекту можно было сдать экзамен на отлично.

Обязательная структура из 6 разделов:
## 1. Введение и контекст темы
## 2. Ключевые понятия и строгие определения
## 3. Подробный теоретический разбор (по подразделам ###)
## 4. Математический аппарат, формулы и выводы (в синтаксисе LaTeX $...$ и $$...$$ с расшифровкой всех переменных)
## 5. Разобранные примеры и практическое применение
## 6. Итоговые выводы и контрольные вопросы к экзамену (с развернутыми ответами)

Верни ТОЛЬКО готовый текст конспекта в формате Markdown (без JSON-обертки).

Черновой конспект из аудио:
${currentSummary.slice(0, 15000)}

Полная расшифровка лекции:
${fullTranscriptText.slice(0, 35000)}`;

        for (const enrichModel of ['gemini-flash-latest', 'gemini-3.8-flash', 'gemini-3.1-flash-lite']) {
          try {
            const enrichResp = await ai.models.generateContent({
              model: enrichModel,
              contents: [{ role: 'user', parts: [{ text: enrichPrompt }] }],
              config: { maxOutputTokens: 12288 },
            });
            const enrichedMd = (enrichResp.text || '').trim();
            if (enrichedMd && enrichedMd.length > currentSummary.length) {
              parsed.summaryMarkdown = repairLatexControlChars(enrichedMd);
              break;
            }
          } catch {
            await new Promise((r) => setTimeout(r, 250));
          }
        }
      } catch (enrichErr) {
        console.warn('Auto summary enrichment skipped:', enrichErr);
      }
    }

    return streamHelper.sendJson(parsed);
  } catch (error: any) {
    console.error('Transcription error:', error);
    return streamHelper.sendJson({ error: error.message || 'Ошибка распознавания аудио' });
  } finally {
    streamHelper.stop();
    if (tempFilePath && fs.existsSync(tempFilePath)) {
      try {
        fs.unlinkSync(tempFilePath);
      } catch {}
    }
  }
});

// Intelligent document analysis & structuring endpoint for PDF / Markdown / Text imports
app.post('/api/structure-document', async (req, res) => {
  const { rawText, fileName, fileBase64, mimeType } = req.body;
  if (!rawText && !fileBase64) {
    return res.status(400).json({ error: 'Текст или содержимое документа не получены' });
  }

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'GEMINI_API_KEY не настроен' });
  }

  const streamHelper = startKeepAliveJsonResponse(res);

  try {
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
      'gemini-flash-latest',
      'gemini-3.8-flash',
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
        await new Promise((r) => setTimeout(r, 300));
      }
    }

    if (!responseText && lastError) {
      throw lastError;
    }

    try {
      const parsed = parseJsonWithLatexSafe(responseText);
      return streamHelper.sendJson(parsed);
    } catch {
      return streamHelper.sendJson({
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
    return streamHelper.sendJson({ error: error.message || 'Ошибка интеллектуальной обработки документа' });
  } finally {
    streamHelper.stop();
  }
});

// Deeply expand or reconstruct an existing lecture summary into a comprehensive textbook-grade lecture note
app.post('/api/expand-lecture', async (req, res) => {
  const { title, subject, summaryMarkdown, transcriptText, aiContext } = req.body;
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'GEMINI_API_KEY не настроен' });
  }

  const streamHelper = startKeepAliveJsonResponse(res);

  try {
    const ai = createGeminiClient(apiKey);

    const contextBlock = aiContext
      ? `\nКонтекст, ключевые термины и план занятия от студента:\n${String(aiContext).slice(0, 10000)}\n`
      : '';

    const prompt = `Ты — ведущий университетский профессор по дисциплине "${subject || 'Высшая школа'}".
Тема лекции: "${title || 'Лекция'}".${contextBlock}
Перед тобой текущий конспект лекции и исходная стенограмма/заметки.
Студент просит сформировать или расширить этот конспект так, чтобы он стал МАКСИМАЛЬНО ПОДРОБНЫМ, ГЛУБОКИМ и ФУНДАМЕНТАЛЬНЫМ университетским конспектом.

Задача:
Напиши фундаментальный, максимально подробный, развернутый академический конспект по теме лекции и предоставленному контексту/стенограмме в формате Markdown (с формулами LaTeX $...$ и $$...$$).
1. Обязательно используй четкую структуру из 6 разделов:
   ## 1. Введение и контекст темы
   ## 2. Ключевые понятия и строгие определения
   ## 3. Подробный теоретический разбор (по подразделам ###)
   ## 4. Математический аппарат, формулы и выводы (в синтаксисе LaTeX $...$ и $$...$$ с расшифровкой всех переменных)
   ## 5. Разобранные примеры и практическое применение
   ## 6. Итоговые выводы и контрольные вопросы к экзамену (с развернутыми ответами)
2. Если в текущем конспекте или стенограмме мало текста (например, произошел сбой записи, но указана тема и контекст), полностью раскрой всю тему "${title}" по предмету "${subject}" с опорой на переданный контекст, термины и тезисы студента!
3. Верни ТОЛЬКО готовый расширенный текст конспекта в формате Markdown (без JSON-обертки).

Текущий конспект:
${String(summaryMarkdown || '').slice(0, 30000)}

Исходный текст / стенограмма:
${String(transcriptText || '').slice(0, 30000)}`;

    const candidateModels = [
      'gemini-flash-latest',
      'gemini-3.8-flash',
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
            maxOutputTokens: 12288,
          },
        });
        expandedMarkdown = (response.text || '').trim();
        if (expandedMarkdown) {
          break;
        }
      } catch (err: any) {
        lastError = err;
        await new Promise((r) => setTimeout(r, 300));
      }
    }

    if (!expandedMarkdown && lastError) {
      throw lastError;
    }

    return streamHelper.sendJson({ summaryMarkdown: repairLatexControlChars(expandedMarkdown) });
  } catch (error: any) {
    console.error('Expand lecture error:', error);
    return streamHelper.sendJson({ error: error.message || 'Не удалось расширить конспект' });
  } finally {
    streamHelper.stop();
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
