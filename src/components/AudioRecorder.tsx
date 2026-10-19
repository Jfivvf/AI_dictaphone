import React, { useState, useRef, useEffect } from 'react';
import { 
  Mic, 
  Square, 
  Pause, 
  Play, 
  UploadCloud, 
  FileAudio, 
  Bookmark, 
  Volume2,
  AlertCircle,
  Sparkles
} from 'lucide-react';
import { Lecture, TranscriptSegment, AppSettings, ActionItem, LatexFormula } from '../types';

interface AudioRecorderProps {
  settings: AppSettings;
  onLectureCreated: (lecture: Lecture) => void;
  onNavigateToViewer: () => void;
}

const blobToBase64 = (blob: Blob): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const dataUrl = reader.result as string;
      const base64 = dataUrl.split(',')[1] || '';
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
};

async function transcribeWithChunkSupport(params: {
  base64Audio: string;
  mimeType: string;
  title: string;
  subject: string;
  aiContext: string;
  liveTranscript?: string;
  accuracyMode?: 'fast' | 'high';
  onStatusUpdate?: (msg: string) => void;
}): Promise<any> {
  const { base64Audio, mimeType, title, subject, aiContext, liveTranscript, accuracyMode, onStatusUpdate } = params;
  const CHUNK_SIZE = 3 * 1024 * 1024; // 3MB per chunk — safe for all reverse proxies (prevents HTTP 413)

  if (base64Audio.length > CHUNK_SIZE) {
    const uploadId = `up-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const totalChunks = Math.ceil(base64Audio.length / CHUNK_SIZE);

    for (let i = 0; i < totalChunks; i++) {
      onStatusUpdate?.(`Передача длинной аудиозаписи (${i + 1} из ${totalChunks})...`);
      const chunkData = base64Audio.slice(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE);
      const chunkResp = await fetch('/api/upload-audio-chunk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uploadId, chunkIndex: i, chunkData }),
      });
      if (!chunkResp.ok) {
        throw new Error(`Chunk upload failed with status ${chunkResp.status}`);
      }
    }

    onStatusUpdate?.('Глубокое распознавание речи и формирование академического конспекта...');
    const response = await fetch('/api/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        uploadId,
        mimeType,
        title,
        subject,
        aiContext,
        liveTranscript,
        accuracyMode,
      }),
    });

    if (!response.ok) {
      throw new Error(`Transcribe status ${response.status}`);
    }
    const rawText = (await response.text()).trim();
    return JSON.parse(rawText);
  } else {
    const response = await fetch('/api/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        audioBase64: base64Audio,
        mimeType,
        title,
        subject,
        aiContext,
        liveTranscript,
        accuracyMode,
      }),
    });

    if (!response.ok) {
      throw new Error(`Transcribe status ${response.status}`);
    }
    const rawText = (await response.text()).trim();
    return JSON.parse(rawText);
  }
}

export const AudioRecorder: React.FC<AudioRecorderProps> = ({
  settings,
  onLectureCreated,
  onNavigateToViewer,
}) => {
  // Mode: 'mic' | 'file'
  const [mode, setMode] = useState<'mic' | 'file'>('mic');
  
  // Recording states: 'idle' | 'recording' | 'paused' | 'processing'
  const [recordingState, setRecordingState] = useState<'idle' | 'recording' | 'paused' | 'processing'>('idle');
  const [processingStatus, setProcessingStatus] = useState<string>('Идет распознавание речи и формирование конспекта...');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [bookmarks, setBookmarks] = useState<{ time: number; note: string }[]>([]);
  const [currentDecibels, setCurrentDecibels] = useState(-32);
  
  // Real-time transcribed text (from Web Speech API when available)
  const [liveTranscript, setLiveTranscript] = useState<string>('');
  const [transcriptSegments, setTranscriptSegments] = useState<TranscriptSegment[]>([]);
  const [micError, setMicError] = useState<string | null>(null);
  
  // File upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileAudioUrl, setFileAudioUrl] = useState<string | null>(null);
  const [lectureSubject, setLectureSubject] = useState('');
  const [lectureTitle, setLectureTitle] = useState('');
  const [lecturerName, setLecturerName] = useState('');
  const [aiContext, setAiContext] = useState('');

  // Audio recording refs
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const timerIntervalRef = useRef<number | null>(null);
  const segmentIntervalRef = useRef<number | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const segmentRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recognitionRef = useRef<any>(null);

  // Stop everything on unmount
  useEffect(() => {
    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
      if (segmentIntervalRef.current) clearInterval(segmentIntervalRef.current);
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach(track => track.stop());
      }
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch {}
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close().catch(() => {});
      }
    };
  }, []);

  // Format seconds to mm:ss
  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  // Start live microphone recording
  const startRecording = async () => {
    setMicError(null);
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Ваш браузер или текущее окружение не поддерживает запись аудио через MediaDevices.');
      }

      // 1. Request user microphone with explicit noise suppression and echo cancellation from settings
      const isNoiseSuppressionOn = settings.noiseSuppression !== 'off';
      const audioConstraints: MediaTrackConstraints = {
        noiseSuppression: isNoiseSuppressionOn,
        echoCancellation: isNoiseSuppressionOn,
        autoGainControl: isNoiseSuppressionOn,
      };

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: audioConstraints,
      });
      mediaStreamRef.current = stream;

      setRecordingState('recording');
      setElapsedSeconds(0);
      setBookmarks([]);
      setLiveTranscript('');
      setTranscriptSegments([]);
      audioChunksRef.current = [];

      // 2. Start UI Timer
      timerIntervalRef.current = window.setInterval(() => {
        setElapsedSeconds(prev => prev + 1);
      }, 1000);

      // 3. Audio Context & Waveform Analyser
      const audioCtx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      audioContextRef.current = audioCtx;
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 128;
      analyserRef.current = analyser;

      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyser);
      drawWaveform();

      // 4. Real MediaRecorder to capture audio (24 kbps voice profile so a 45-90 min lecture is only 8-16 MB)
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : MediaRecorder.isTypeSupported('audio/mp4')
        ? 'audio/mp4'
        : '';

      const recorderOptions: MediaRecorderOptions = mimeType
        ? { mimeType, audioBitsPerSecond: 24000 }
        : { audioBitsPerSecond: 24000 };

      const mediaRecorder = new MediaRecorder(stream, recorderOptions);
      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };
      mediaRecorder.start(1000);

      // 4b. Rolling 90-second background AI segment transcriber for long (>1 hour) lectures
      let segStartSec = 0;
      const startRollingSegmentRecorder = () => {
        if (!mediaStreamRef.current || !mediaStreamRef.current.active) return;
        const segChunks: Blob[] = [];
        const currentStart = segStartSec;
        try {
          const segRec = new MediaRecorder(mediaStreamRef.current, recorderOptions);
          segmentRecorderRef.current = segRec;
          segRec.ondataavailable = (ev) => {
            if (ev.data && ev.data.size > 0) segChunks.push(ev.data);
          };
          segRec.onstop = async () => {
            if (segChunks.length === 0) return;
            const segBlob = new Blob(segChunks, { type: mimeType || 'audio/webm' });
            if (segBlob.size < 2000) return;
            try {
              const segB64 = await blobToBase64(segBlob);
              const resp = await fetch('/api/transcribe-segment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  audioBase64: segB64,
                  mimeType: segBlob.type || 'audio/webm',
                  title: lectureTitle,
                  subject: lectureSubject,
                  aiContext,
                }),
              });
              if (resp.ok) {
                const data = await resp.json();
                const cleanText = (data.text || '').trim();
                if (cleanText) {
                  setTranscriptSegments(prev => [
                    ...prev,
                    {
                      id: `seg-ai-${Date.now()}`,
                      startTime: currentStart,
                      endTime: currentStart + 90,
                      speaker: 'Лектор',
                      text: cleanText,
                      bookmarked: false,
                    },
                  ]);
                  setLiveTranscript(prev => (prev ? `${prev} ${cleanText}` : cleanText));
                }
              }
            } catch {}
          };
          segRec.start();
        } catch {}
      };

      startRollingSegmentRecorder();
      segmentIntervalRef.current = window.setInterval(() => {
        segStartSec += 90;
        if (segmentRecorderRef.current && segmentRecorderRef.current.state === 'recording') {
          try {
            segmentRecorderRef.current.stop();
          } catch {}
          startRollingSegmentRecorder();
        }
      }, 90000);

      // 5. Web Speech API (runs in background for live typing feedback if supported by browser)
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        try {
          const recognition = new SpeechRecognition();
          recognitionRef.current = recognition;
          recognition.continuous = true;
          recognition.interimResults = true;
          recognition.lang = 'ru-RU';

          let lastSegmentStart = 0;

          recognition.onresult = (event: any) => {
            for (let i = event.resultIndex; i < event.results.length; ++i) {
              const transcriptText = event.results[i][0].transcript;
              if (event.results[i].isFinal) {
                const textClean = transcriptText.trim();
                if (textClean) {
                  setTranscriptSegments(prev => [
                    ...prev,
                    {
                      id: `seg-${Date.now()}-${prev.length}`,
                      startTime: lastSegmentStart,
                      endTime: elapsedSeconds,
                      speaker: 'Лектор',
                      text: textClean,
                      bookmarked: false
                    }
                  ]);
                  lastSegmentStart = elapsedSeconds;
                  setLiveTranscript(prev => (prev ? prev + ' ' : '') + textClean);
                }
              }
            }
          };

          recognition.onerror = () => {
            // Ignore browser speech recognition events ('aborted', 'no-speech', etc.) since backend AI handles full transcription
          };

          recognition.onend = () => {
            if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
              try { recognition.start(); } catch {}
            }
          };

          recognition.start();
        } catch (err) {
          console.warn('SpeechRecognition start failed (will use backend AI transcription):', err);
        }
      }
    } catch (err: any) {
      console.warn('Mic access error:', err);
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }
      setRecordingState('idle');

      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError' || err.message?.toLowerCase().includes('permission denied') || err.message?.toLowerCase().includes('not allowed')) {
        setMicError('Браузер заблокировал доступ к микрофону. Нажмите на значок замка или микрофона в строке адреса браузера и выберите «Разрешить».');
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setMicError('Микрофон не обнаружен на вашем устройстве. Подключите гарнитуру или микрофон.');
      } else {
        setMicError(err.message || 'Не удалось получить доступ к микрофону. Пожалуйста, разрешите доступ в настройках браузера.');
      }
    }
  };

  const drawWaveform = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dataArray = new Uint8Array(64);

    const render = () => {
      animationFrameRef.current = requestAnimationFrame(render);
      const width = canvas.width;
      const height = canvas.height;

      ctx.clearRect(0, 0, width, height);

      if (analyserRef.current) {
        analyserRef.current.getByteFrequencyData(dataArray);
      }

      // Compute dB
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
      }
      const avg = sum / dataArray.length;
      const db = Math.round((avg / 255) * 60 - 55);
      setCurrentDecibels(db);

      // Draw bars
      const barWidth = (width / 48) - 2;
      let x = 0;

      for (let i = 0; i < 48; i++) {
        const val = dataArray[i] || 4;
        const barHeight = Math.max(3, (val / 255) * (height - 12));

        const gradient = ctx.createLinearGradient(0, height, 0, height - barHeight);
        gradient.addColorStop(0, '#4338ca');
        gradient.addColorStop(1, '#818cf8');

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.roundRect(x, height / 2 - barHeight / 2, barWidth, barHeight, [2, 2, 2, 2]);
        ctx.fill();

        x += barWidth + 2;
      }
    };

    render();
  };

  const pauseRecording = () => {
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.pause();
    }
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch {}
    }
    setRecordingState('paused');
  };

  const resumeRecording = () => {
    setRecordingState('recording');
    timerIntervalRef.current = window.setInterval(() => {
      setElapsedSeconds(prev => prev + 1);
    }, 1000);
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'paused') {
      mediaRecorderRef.current.resume();
    }
    if (recognitionRef.current) {
      try { recognitionRef.current.start(); } catch {}
    }
  };

  const addBookmark = () => {
    setBookmarks(prev => [
      ...prev,
      { time: elapsedSeconds, note: `Важный момент #${prev.length + 1}` }
    ]);
  };

  // Stop recording and perform REAL AI speech recognition
  const finishAndProcess = async () => {
    if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    if (segmentIntervalRef.current) clearInterval(segmentIntervalRef.current);
    if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
    
    // Stop recognition
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch {}
    }

    // Stop rolling segment recorder
    if (segmentRecorderRef.current && segmentRecorderRef.current.state !== 'inactive') {
      try { segmentRecorderRef.current.stop(); } catch {}
    }

    // Stop MediaRecorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch {}
    }

    // Stop tracks
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
    }

    setRecordingState('processing');
    setProcessingStatus('Нейросетевое распознавание речи и выделение дедлайнов...');

    // Small delay to ensure all chunks are flushed
    await new Promise(r => setTimeout(r, 200));

    let recordedAudioUrl: string | undefined = undefined;
    let base64Audio = '';
    const audioBlob = audioChunksRef.current.length > 0 
      ? new Blob(audioChunksRef.current, { type: audioChunksRef.current[0].type || 'audio/webm' }) 
      : null;

    if (audioBlob && audioBlob.size > 0) {
      recordedAudioUrl = URL.createObjectURL(audioBlob);
      try {
        base64Audio = await blobToBase64(audioBlob);
      } catch (e) {
        console.warn('Blob to base64 conversion failed:', e);
      }
    }

    let aiResult: any = null;
    const combinedBrowserTranscript =
      liveTranscript.trim() || transcriptSegments.map(s => s.text).join(' ').trim();

    // Call backend /api/transcribe with chunked support (prevents 413 on 40-90 min recordings)
    if (base64Audio) {
      try {
        aiResult = await transcribeWithChunkSupport({
          base64Audio,
          mimeType: audioBlob?.type || 'audio/webm',
          title: lectureTitle.trim(),
          subject: lectureSubject.trim(),
          aiContext: aiContext.trim(),
          liveTranscript: combinedBrowserTranscript,
          accuracyMode: 'high',
          onStatusUpdate: setProcessingStatus,
        });
      } catch (err) {
        console.warn('Failed to contact transcription backend:', err);
      }
    }

    // Fallback: if audio transcription failed or returned empty, generate full lecture notes from browser transcript + aiContext
    if ((!aiResult || (!aiResult.summaryMarkdown && !aiResult.fullText)) && (combinedBrowserTranscript || aiContext.trim() || lectureTitle.trim())) {
      try {
        setProcessingStatus('Формирование развернутого конспекта по стенограмме и контексту...');
        const expandResp = await fetch('/api/expand-lecture', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: lectureTitle.trim() || 'Лекция',
            subject: lectureSubject.trim() || 'Учебная дисциплина',
            summaryMarkdown: '',
            transcriptText: combinedBrowserTranscript,
            aiContext: aiContext.trim(),
          }),
        });
        if (expandResp.ok) {
          const expandData = await expandResp.json();
          if (expandData.summaryMarkdown) {
            aiResult = {
              fullText: combinedBrowserTranscript || aiContext.trim(),
              summaryMarkdown: expandData.summaryMarkdown,
              segments: transcriptSegments.length > 0 ? transcriptSegments : undefined,
              actionItems: [],
              latexFormulas: [],
            };
          }
        }
      } catch (fallbackErr) {
        console.warn('Fallback expand-lecture failed:', fallbackErr);
      }
    }

    const finalTitle = lectureTitle.trim() || 
      (aiResult?.summaryMarkdown?.match(/^#+\s*(.+)$/m)?.[1]) || 
      'Запись лекции';
    const finalSubject = lectureSubject.trim() || 'Учебное занятие';
    const finalLecturer = lecturerName.trim() || 'Преподаватель';

    // Real text from AI or fallback
    let finalText = '';
    let markdownNotes = '';
    let finalActionItems: ActionItem[] = [];
    let finalLatexFormulas: LatexFormula[] = [];
    let finalSegments: TranscriptSegment[] = [];

    if (aiResult && (aiResult.fullText || aiResult.summaryMarkdown)) {
      finalText = aiResult.fullText || aiResult.summaryMarkdown || '';
      markdownNotes = aiResult.summaryMarkdown || `## ${finalTitle}\n\n${finalText}`;
      
      // Parse tasks
      if (Array.isArray(aiResult.actionItems) && aiResult.actionItems.length > 0) {
        finalActionItems = aiResult.actionItems.map((item: any, idx: number) => ({
          id: `task-ai-${Date.now()}-${idx}`,
          task: item.task || 'Задание',
          deadline: item.deadline || 'В ближайшее время',
          dateISO: new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString().split('T')[0],
          type: 'homework',
          completed: false,
          priority: item.priority === 'high' ? 'high' : 'medium'
        }));
      }

      // Parse formulas
      if (Array.isArray(aiResult.latexFormulas)) {
        finalLatexFormulas = aiResult.latexFormulas.map((f: any, idx: number) => ({
          id: `formula-ai-${Date.now()}-${idx}`,
          title: f.title || 'Формула из лекции',
          latex: f.latex || 'E = mc^2',
          context: f.context || 'Упомянуто в речи'
        }));
      }

      // Parse segments
      if (Array.isArray(aiResult.segments) && aiResult.segments.length > 0) {
        finalSegments = aiResult.segments.map((s: any, idx: number) => ({
          id: `seg-${Date.now()}-${idx}`,
          startTime: s.startTime || 0,
          endTime: s.endTime || elapsedSeconds,
          speaker: s.speaker || 'Лектор',
          text: s.text || '',
          bookmarked: false
        }));
      }
    }

    // Fallback if AI didn't return text (e.g. mic was completely silent)
    if (!finalText) {
      finalText = liveTranscript.trim() || 
        transcriptSegments.map(s => s.text).join(' ').trim() ||
        'Аудиозапись сохранена. В записи не было различимой речи либо микрофон был выключен.';
      
      markdownNotes = `## ${finalTitle}\n\n`;
      markdownNotes += `**Предмет:** ${finalSubject}  \n`;
      markdownNotes += `**Преподаватель:** ${finalLecturer}  \n`;
      markdownNotes += `**Дата:** ${new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })}  \n\n`;
      markdownNotes += `---\n\n`;
      markdownNotes += `### Стенограмма записи\n\n${finalText}\n`;
    }

    if (finalSegments.length === 0) {
      finalSegments = [{
        id: `seg-${Date.now()}`,
        startTime: 0,
        endTime: Math.max(elapsedSeconds, 1),
        speaker: 'Лектор',
        text: finalText,
        bookmarked: false
      }];
    }

    const newLecture: Lecture = {
      id: `lec-${Date.now()}`,
      title: finalTitle,
      subject: finalSubject,
      lecturer: finalLecturer,
      date: new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }),
      durationSeconds: Math.max(elapsedSeconds, 1),
      audioFileName: recordedAudioUrl ? 'mic_recording.webm' : undefined,
      tags: [finalSubject],
      noiseLevel: 'moderate',
      modelUsed: 'Нейросеть распознавания речи',
      quantization: 'Текст',
      transcript: finalSegments,
      summaryMarkdown: markdownNotes,
      actionItems: finalActionItems,
      latexFormulas: finalLatexFormulas,
      keyDefinitions: []
    };

    onLectureCreated(newLecture);
    setRecordingState('idle');
    onNavigateToViewer();
  };

  // Handle file drop / select
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setFileAudioUrl(URL.createObjectURL(file));
      setLectureTitle(file.name.replace(/\.[^/.]+$/, '').replace(/_/g, ' '));
    }
  };

  // Process uploaded audio file with REAL speech recognition
  const processUploadedAudio = async () => {
    if (!selectedFile) return;

    setRecordingState('processing');
    setProcessingStatus(`Нейросетевая расшифровка аудиофайла "${selectedFile.name}"...`);

    let base64Audio = '';
    try {
      base64Audio = await blobToBase64(selectedFile);
    } catch (e) {
      console.warn('File to base64 failed:', e);
    }

    const title = lectureTitle.trim() || selectedFile.name.replace(/\.[^/.]+$/, '');
    const subject = lectureSubject.trim() || 'Аудиозапись';
    const lecturer = lecturerName.trim() || 'Преподаватель';

    let aiResult: any = null;
    if (base64Audio) {
      try {
        aiResult = await transcribeWithChunkSupport({
          base64Audio,
          mimeType: selectedFile.type || 'audio/mp3',
          title,
          subject,
          aiContext: aiContext.trim(),
          onStatusUpdate: setProcessingStatus,
        });
      } catch (err) {
        console.warn('Failed to transcribe file via API:', err);
      }
    }

    let finalText = aiResult?.fullText || `Аудиофайл "${selectedFile.name}" сохранен.`;
    let markdownNotes = aiResult?.summaryMarkdown || `## ${title}\n\n*Файл: ${selectedFile.name}*\n\n---\n\n${finalText}`;
    
    let finalTasks: ActionItem[] = [];
    if (Array.isArray(aiResult?.actionItems) && aiResult.actionItems.length > 0) {
      finalTasks = aiResult.actionItems.map((item: any, idx: number) => ({
        id: `task-file-${Date.now()}-${idx}`,
        task: item.task || 'Задание',
        deadline: item.deadline || 'По графику курса',
        dateISO: new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString().split('T')[0],
        type: 'homework',
        completed: false,
        priority: item.priority === 'high' ? 'high' : 'medium'
      }));
    }

    let finalFormulas: LatexFormula[] = [];
    if (Array.isArray(aiResult?.latexFormulas)) {
      finalFormulas = aiResult.latexFormulas.map((f: any, idx: number) => ({
        id: `formula-file-${Date.now()}-${idx}`,
        title: f.title || 'Формула',
        latex: f.latex || '',
        context: f.context || ''
      }));
    }

    let finalSegments: TranscriptSegment[] = [];
    if (Array.isArray(aiResult?.segments) && aiResult.segments.length > 0) {
      finalSegments = aiResult.segments.map((s: any, idx: number) => ({
        id: `seg-f-${Date.now()}-${idx}`,
        startTime: s.startTime || 0,
        endTime: s.endTime || 60,
        speaker: s.speaker || 'Лектор',
        text: s.text || '',
        bookmarked: false
      }));
    } else {
      finalSegments = [{
        id: `seg-file-${Date.now()}`,
        startTime: 0,
        endTime: 60,
        speaker: 'Лектор',
        text: finalText,
        bookmarked: false
      }];
    }

    const newLecture: Lecture = {
      id: `lec-${Date.now()}`,
      title,
      subject,
      lecturer,
      date: new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }),
      durationSeconds: 1800,
      audioFileName: selectedFile.name,
      tags: [subject],
      noiseLevel: 'moderate',
      modelUsed: 'Нейросеть распознавания речи',
      quantization: 'Текст',
      transcript: finalSegments,
      summaryMarkdown: markdownNotes,
      actionItems: finalTasks,
      latexFormulas: finalFormulas,
      keyDefinitions: []
    };

    onLectureCreated(newLecture);
    setRecordingState('idle');
    onNavigateToViewer();
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 bg-neutral-950">
      <div className="max-w-4xl mx-auto space-y-6">
        
        {/* Header Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-neutral-800">
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              Запись
            </h1>
            <p className="text-xs text-neutral-400 mt-1">
              Запись с микрофона в реальном времени или загрузка аудиофайла
            </p>
          </div>

          {/* Mode Switcher Tabs */}
          <div className="flex items-center gap-1 p-1 bg-neutral-900 border border-neutral-800 rounded-lg">
            <button
              onClick={() => setMode('mic')}
              className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                mode === 'mic' 
                  ? 'bg-neutral-800 text-white shadow-sm' 
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              <Mic className="w-3.5 h-3.5 text-rose-400" />
              Микрофон
            </button>
            <button
              onClick={() => setMode('file')}
              className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                mode === 'file' 
                  ? 'bg-neutral-800 text-white shadow-sm' 
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              <UploadCloud className="w-3.5 h-3.5 text-indigo-400" />
              Аудиофайл
            </button>
          </div>
        </div>

        {/* Lecture Details moved to the top */}
        {recordingState !== 'processing' && (
          <div className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
              Информация о занятии
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1">
                  Предмет / Дисциплина
                </label>
                <input
                  type="text"
                  value={lectureSubject}
                  maxLength={200}
                  onChange={(e) => setLectureSubject(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                  placeholder="Например: Высшая математика"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1">
                  Тема занятия
                </label>
                <input
                  type="text"
                  value={lectureTitle}
                  maxLength={300}
                  onChange={(e) => setLectureTitle(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                  placeholder="Тема лекции"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1">
                  Преподаватель
                </label>
                <input
                  type="text"
                  value={lecturerName}
                  maxLength={200}
                  onChange={(e) => setLecturerName(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                  placeholder="ФИО лектора"
                />
              </div>
            </div>
          </div>
        )}

        {/* Processing State with Live Spinner */}
        {recordingState === 'processing' ? (
          <div className="p-12 rounded-xl bg-neutral-900 border border-neutral-800 text-center space-y-4">
            <div className="w-14 h-14 mx-auto rounded-full bg-indigo-950 border border-indigo-700/80 flex items-center justify-center text-indigo-400 animate-pulse">
              <Sparkles className="w-7 h-7" />
            </div>

            <div>
              <h2 className="text-base font-bold text-white">
                {processingStatus}
              </h2>
              <p className="text-xs text-neutral-400 mt-1">
                Нейросеть слушает вашу аудиозапись, переводит речь в текст, формулирует конспект и выделяет дедлайны
              </p>
            </div>
          </div>
        ) : mode === 'mic' ? (
          /* Live Microphone Mode */
          <div className="space-y-5">

            {/* Mic Permission / Connection Error Banner */}
            {micError && (
              <div className="p-4 rounded-xl bg-amber-950/40 border border-amber-800/80 text-amber-200 text-xs space-y-3">
                <div className="flex items-start gap-2.5">
                  <AlertCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <h4 className="font-semibold text-white text-sm">
                      Доступ к микрофону заблокирован браузером
                    </h4>
                    <p className="text-neutral-300 leading-relaxed">
                      {micError}
                    </p>
                    <ol className="list-decimal pl-4 space-y-1 text-neutral-300 pt-1">
                      <li>Нажмите на иконку замка или микрофона слева в адресной строке браузера.</li>
                      <li>В строке «Микрофон» переключите значение на <strong>«Разрешить»</strong>.</li>
                      <li>Нажмите кнопку <strong>«Попробовать снова»</strong> ниже.</li>
                    </ol>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 pt-1 pl-7">
                  <button
                    onClick={() => {
                      setMicError(null);
                      startRecording();
                    }}
                    className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-colors"
                  >
                    Попробовать снова
                  </button>
                  <button
                    onClick={() => {
                      setMicError(null);
                      setMode('file');
                    }}
                    className="px-3.5 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 transition-colors"
                  >
                    Загрузить аудиофайл
                  </button>
                </div>
              </div>
            )}
            
            {/* Visualizer and Timer Card */}
            <div className="p-6 rounded-xl bg-neutral-900 border border-neutral-800 space-y-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={`w-3 h-3 rounded-full ${
                    recordingState === 'recording' ? 'bg-rose-500 animate-pulse' : 
                    recordingState === 'paused' ? 'bg-amber-400' : 'bg-neutral-600'
                  }`} />
                  <span className="text-xs font-medium text-neutral-300">
                    {recordingState === 'recording' ? 'Идет запись...' : 
                     recordingState === 'paused' ? 'Пауза' : 'Готов к записи'}
                  </span>
                </div>

                <div className="flex items-center gap-4 text-xs font-mono text-neutral-400">
                  <div className="flex items-center gap-1">
                    <Volume2 className="w-3.5 h-3.5 text-neutral-500" />
                    <span>{recordingState === 'recording' ? `${currentDecibels} dB` : '- - dB'}</span>
                  </div>
                  <div className="text-2xl font-bold text-white tabular-nums tracking-wider">
                    {formatTime(elapsedSeconds)}
                  </div>
                </div>
              </div>

              {/* Waveform Canvas */}
              <div className="h-28 w-full bg-neutral-950 rounded-lg border border-neutral-800/80 p-2 flex items-center justify-center overflow-hidden">
                <canvas 
                  ref={canvasRef} 
                  width={720} 
                  height={100} 
                  className="w-full h-full"
                />
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                <div className="flex items-center gap-2">
                  {recordingState === 'idle' ? (
                    <button
                      onClick={startRecording}
                      className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-medium text-sm transition-all shadow-md shadow-rose-900/30"
                    >
                      <Mic className="w-4 h-4" />
                      Начать запись
                    </button>
                  ) : (
                    <>
                      {recordingState === 'recording' ? (
                        <button
                          onClick={pauseRecording}
                          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-sm font-medium transition-colors"
                        >
                          <Pause className="w-4 h-4 text-amber-400" />
                          Пауза
                        </button>
                      ) : (
                        <button
                          onClick={resumeRecording}
                          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-sm font-medium transition-colors"
                        >
                          <Play className="w-4 h-4 text-emerald-400" />
                          Продолжить
                        </button>
                      )}

                      <button
                        onClick={addBookmark}
                        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-neutral-800/80 hover:bg-neutral-700 text-neutral-300 text-sm font-medium transition-colors"
                        title="Поставить закладку к текущей секунде"
                      >
                        <Bookmark className="w-4 h-4 text-indigo-400" />
                        Метка ({bookmarks.length})
                      </button>

                      <button
                        onClick={finishAndProcess}
                        className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-all shadow-md shadow-indigo-900/40"
                      >
                        <Square className="w-4 h-4 fill-white" />
                        Завершить и сохранить
                      </button>
                    </>
                  )}
                </div>

                <div className="text-xs text-neutral-500">
                  <kbd className="px-1.5 py-0.5 rounded bg-neutral-800 font-mono text-[10px] text-neutral-300">Space</kbd> — пауза / старт
                </div>
              </div>

              {/* Bookmarks list if any */}
              {bookmarks.length > 0 && (
                <div className="pt-3 border-t border-neutral-800 flex flex-wrap gap-2 text-xs">
                  <span className="text-neutral-400 self-center">Метки:</span>
                  {bookmarks.map((bm, bIdx) => (
                    <span key={bIdx} className="px-2 py-1 rounded bg-neutral-800 text-neutral-300 font-mono text-[11px] flex items-center gap-1">
                      <Bookmark className="w-3 h-3 text-indigo-400" />
                      {formatTime(bm.time)}: {bm.note}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* AI Context & Terminology Hint (in place of old Lecture Details) */}
            <div className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  Контекст
                </h3>
              </div>

              <textarea
                value={aiContext}
                onChange={(e) => setAiContext(e.target.value)}
                rows={3}
                maxLength={2000}
                placeholder="Повышает точность распознавания терминов и формул"
                className="w-full px-3 py-2.5 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500 leading-relaxed resize-none"
              />
            </div>

          </div>
        ) : (
          /* File Upload Mode */
          <div className="space-y-6">
            <div className="p-8 rounded-xl bg-neutral-900 border-2 border-dashed border-neutral-800 hover:border-indigo-500/60 transition-colors text-center space-y-4">
              <div className="w-12 h-12 mx-auto rounded-full bg-neutral-800 text-indigo-400 flex items-center justify-center">
                <FileAudio className="w-6 h-6" />
              </div>

              <div>
                <h3 className="text-sm font-semibold text-white">
                  Выберите аудиофайл для расшифровки
                </h3>
                <p className="text-xs text-neutral-400 mt-1">
                  Поддерживаются форматы: MP3, WAV, M4A, OGG
                </p>
              </div>

              <input
                type="file"
                id="audio-upload"
                accept="audio/*"
                onChange={handleFileUpload}
                className="hidden"
              />
              <label
                htmlFor="audio-upload"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium cursor-pointer transition-colors"
              >
                <UploadCloud className="w-4 h-4" />
                Выбрать аудиофайл
              </label>

              {selectedFile && (
                <div className="mt-4 p-4 rounded-xl bg-neutral-950 border border-neutral-800 max-w-md mx-auto text-left space-y-3">
                  <div className="flex items-center gap-2 truncate">
                    <FileAudio className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span className="text-xs text-neutral-200 truncate">{selectedFile.name}</span>
                    <span className="text-[10px] text-neutral-500 font-mono">
                      ({(selectedFile.size / (1024 * 1024)).toFixed(1)} МБ)
                    </span>
                  </div>

                  <button
                    onClick={processUploadedAudio}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors shadow-sm"
                  >
                    <Sparkles className="w-4 h-4" />
                    Расшифровать и создать конспект
                  </button>
                </div>
              )}
            </div>

            {/* Audio Preview if selected */}
            {fileAudioUrl && (
              <div className="p-4 rounded-xl bg-neutral-900 border border-neutral-800 flex items-center gap-4">
                <audio controls src={fileAudioUrl} className="w-full h-8" />
              </div>
            )}

            {/* AI Context in File Mode as well */}
            <div className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  Контекст
                </h3>
              </div>

              <textarea
                value={aiContext}
                onChange={(e) => setAiContext(e.target.value)}
                rows={3}
                maxLength={2000}
                placeholder="Повышает точность распознавания терминов и формул"
                className="w-full px-3 py-2.5 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500 leading-relaxed resize-none"
              />
            </div>
          </div>
        )}

      </div>
    </div>
  );
};
