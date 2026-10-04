import express from 'express';
import { createServer as createViteServer } from 'vite';
import { GoogleGenAI } from '@google/genai';
import dotenv from 'dotenv';
import path from 'path';

dotenv.config();

const app = express();
const PORT = 3000;

// Support audio uploads up to 50MB
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Healthcheck
app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', hasKey: !!process.env.GEMINI_API_KEY });
});

// Audio transcription and structuring endpoint
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

    const ai = new GoogleGenAI({ apiKey });

    const prompt = `Ты — AI-движок диктофона для студентов.
Тема занятия: "${title || 'Без названия'}"
Предмет: "${subject || 'Учебное занятие'}"

Внимательно прослушай эту аудиозапись и выполни задачи:
1. transcript: Точная построчная расшифровка речи на русском языке.
   segments: массив объектов [{"startTime": секунды_начала, "endTime": секунды_конца, "speaker": "Лектор", "text": "фраза"}]
2. fullText: Полный связный текст всей речи.
3. summaryMarkdown: Аккуратный, подробный конспект лекции в формате Markdown с заголовками, пунктами и определениями. Если в речи упоминаются математические, физические или химические формулы, обязательно оформи их в синтаксисе LaTeX ($...$ для строчных или $$...$$ для выключных).
4. actionItems: Все домашние задания, дедлайны, даты сдачи, коллоквиумы, лабораторные, упомянутые лектором:
   [{"task": "описание задачи", "deadline": "названный срок (например 'к пятнице 18:00')", "priority": "high"|"medium"|"low"}]
5. latexFormulas: Найденные в речи формулы:
   [{"title": "название формулы", "latex": "код LaTeX без знаков $", "context": "где применяется"}]

Если в аудиозаписи тишина или неразборчивый шум, отрази это в тексте.
ОТВЕТЬ СТРОГО В ФОРМАТЕ JSON (без символов \`\`\`json):
{
  "fullText": "...",
  "summaryMarkdown": "...",
  "segments": [
    {"startTime": 0, "endTime": 5, "speaker": "Лектор", "text": "..."}
  ],
  "actionItems": [
    {"task": "...", "deadline": "...", "priority": "high"}
  ],
  "latexFormulas": [
    {"title": "...", "latex": "...", "context": "..."}
  ]
}`;

    const response = await ai.models.generateContent({
      model: 'gemini-3.8-flash',
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
    });

    const responseText = response.text || '';
    const cleanJson = responseText.replace(/```json\s*|```/g, '').trim();

    try {
      const parsed = JSON.parse(cleanJson);
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
