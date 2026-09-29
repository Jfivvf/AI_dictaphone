import React, { useState, useRef, useEffect } from 'react';
import { 
  Mic, 
  Square, 
  Pause, 
  Play, 
  UploadCloud, 
  FileAudio, 
  Bookmark, 
  CheckCircle2, 
  Sparkles,
  Sliders,
  Volume2
} from 'lucide-react';
import { Lecture, TranscriptSegment, AppSettings } from '../types';
import { SAMPLE_LECTURES } from '../data/sampleLectures';

interface AudioRecorderProps {
  settings: AppSettings;
  onLectureCreated: (lecture: Lecture) => void;
  onNavigateToViewer: () => void;
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
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [bookmarks, setBookmarks] = useState<{ time: number; note: string }[]>([]);
  const [currentDecibels, setCurrentDecibels] = useState(-32);
  
  // File upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileAudioUrl, setFileAudioUrl] = useState<string | null>(null);
  const [noiseProfile, setNoiseProfile] = useState<'quiet' | 'moderate' | 'noisy' | 'echo'>('moderate');
  const [lectureSubject, setLectureSubject] = useState('Высшая математика');
  const [lectureTitle, setLectureTitle] = useState('Дифференциальные уравнения и формулы Тейлора');
  const [lecturerName, setLecturerName] = useState('Проф. Соколов В. П.');

  // Pipeline simulation stages
  const [pipelineStage, setPipelineStage] = useState<number>(0);
  const pipelineSteps = [
    { title: 'Очистка звука', desc: 'Удаление шума аудитории и пауз лектора' },
    { title: 'Распознавание речи', desc: 'Преобразование голоса в текст' },
    { title: 'Поиск задач', desc: 'Автоматический поиск дедлайнов и домашних заданий' },
    { title: 'Формулы и конспект', desc: 'Форматирование математических выражений' }
  ];

  // Canvas visualizer refs
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const timerIntervalRef = useRef<number | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);

  // Stop timer on unmount
  useEffect(() => {
    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach(track => track.stop());
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
    try {
      setRecordingState('recording');
      setElapsedSeconds(0);
      setBookmarks([]);

      // Start timer
      timerIntervalRef.current = window.setInterval(() => {
        setElapsedSeconds(prev => prev + 1);
      }, 1000);

      // Attempt to access user microphone
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true }).catch(() => null);
      
      const audioCtx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      audioContextRef.current = audioCtx;
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 128;
      analyserRef.current = analyser;

      if (stream) {
        mediaStreamRef.current = stream;
        const source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyser);
      }

      // Draw real or simulated waveform
      drawWaveform(!!stream);
    } catch {
      // Fallback to simulated audio recording
      drawWaveform(false);
    }
  };

  const drawWaveform = (hasRealMic: boolean) => {
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

      if (analyserRef.current && hasRealMic) {
        analyserRef.current.getByteFrequencyData(dataArray);
      } else {
        // Generate dynamic organic waves simulating student lecture speech
        for (let i = 0; i < 64; i++) {
          dataArray[i] = Math.max(10, Math.floor(60 + Math.sin(Date.now() / 200 + i * 0.2) * 45 + Math.random() * 30));
        }
      }

      // Compute approximate dB
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
      }
      const avg = sum / dataArray.length;
      const db = Math.round((avg / 255) * 60 - 55);
      setCurrentDecibels(db);

      // Draw frequency bars
      const barWidth = (width / 48) - 2;
      let x = 0;

      for (let i = 0; i < 48; i++) {
        const val = dataArray[i] || 15;
        const barHeight = Math.max(4, (val / 255) * (height - 12));

        const gradient = ctx.createLinearGradient(0, height, 0, height - barHeight);
        gradient.addColorStop(0, '#4338ca'); // indigo-700
        gradient.addColorStop(1, '#818cf8'); // indigo-400

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
    setRecordingState('paused');
  };

  const resumeRecording = () => {
    setRecordingState('recording');
    timerIntervalRef.current = window.setInterval(() => {
      setElapsedSeconds(prev => prev + 1);
    }, 1000);
  };

  const addBookmark = () => {
    const bookmarkTitle = prompt('Заметка к таймкоду:', 'Важный тезис / Формула на доске');
    if (bookmarkTitle) {
      setBookmarks(prev => [...prev, { time: elapsedSeconds, note: bookmarkTitle }]);
    }
  };

  // Stop recording and process
  const finishAndProcess = () => {
    if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
    }

    setRecordingState('processing');
    setPipelineStage(0);

    // Simulate the 4 local pipeline steps
    const stepInterval = setInterval(() => {
      setPipelineStage(prev => {
        if (prev < 3) {
          return prev + 1;
        } else {
          clearInterval(stepInterval);
          // Complete pipeline
          setTimeout(() => {
            const newLecture: Lecture = {
              id: `lec-live-${Date.now()}`,
              title: lectureTitle || 'Запись университетской лекции',
              subject: lectureSubject || 'Высшая математика',
              lecturer: lecturerName || 'Преподаватель кафедры',
              date: new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }),
              durationSeconds: Math.max(elapsedSeconds, 45),
              audioFileName: selectedFile ? selectedFile.name : 'live_mic_recording.wav',
              tags: [lectureSubject, 'Офлайн ASR', 'PySide6'],
              noiseLevel: noiseProfile,
              modelUsed: `${settings.asrModel} + ${settings.llmModel}`,
              quantization: `${settings.asrQuantization.toUpperCase()} + ${settings.llmQuantization.toUpperCase()}`,
              transcript: [
                {
                  id: 'live-seg-1',
                  startTime: 0,
                  endTime: Math.round(Math.max(elapsedSeconds * 0.3, 15)),
                  speaker: 'Лектор',
                  text: 'Коллеги, начинаем разбор ключевых уравнений. Обратите внимание на структуру доказательства.',
                  bookmarked: bookmarks.length > 0
                },
                {
                  id: 'live-seg-2',
                  startTime: Math.round(Math.max(elapsedSeconds * 0.35, 18)),
                  endTime: Math.round(Math.max(elapsedSeconds, 45)),
                  speaker: 'Лектор',
                  text: 'К следующему занятию обязательно подготовить решение индивидуальных задач № 12-18 и выучить формулы.',
                  bookmarked: true
                }
              ],
              summaryMarkdown: `## Конспект: ${lectureTitle}

### 1. Основные положения
- Рассмотрен метод решения дифференциальных уравнений и рядов
- Выделены условия сходимости и граничные условия задачи Коши

### 2. Ключевые формулы
$$\\int_{a}^{b} f(x) dx = F(b) - F(a)$$
$$y(x) = C_1 e^{\\lambda_1 x} + C_2 e^{\\lambda_2 x}$$

### 3. Рекомендации к семинару
- Проработать разложение в окрестности нуля по формуле Маклорена.`,
              actionItems: [
                {
                  id: `task-live-1`,
                  task: 'Решить домашнее задание к следующему занятию (задачи 12-18)',
                  deadline: 'Пятница 23:59',
                  dateISO: new Date(Date.now() + 5 * 24 * 3600 * 1000).toISOString().split('T')[0],
                  type: 'homework',
                  completed: false,
                  priority: 'high'
                },
                {
                  id: `task-live-2`,
                  task: 'Выучить базовые формулы и доказательство теоремы',
                  deadline: 'Следующий вторник',
                  dateISO: new Date(Date.now() + 8 * 24 * 3600 * 1000).toISOString().split('T')[0],
                  type: 'exam',
                  completed: false,
                  priority: 'medium'
                }
              ],
              latexFormulas: [
                {
                  id: 'live-f-1',
                  title: 'Формула Ньютона-Лейбница',
                  latex: '\\int_{a}^{b} f(x) dx = F(b) - F(a)',
                  context: 'Вычисление определенного интеграла через первообразную'
                },
                {
                  id: 'live-f-2',
                  title: 'Фундаментальная система решений',
                  latex: 'y(x) = C_1 e^{\\lambda_1 x} + C_2 e^{\\lambda_2 x}',
                  context: 'Базис решений для различных корней'
                }
              ],
              keyDefinitions: [
                {
                  term: 'Задача Коши',
                  definition: 'Нахождение решения дифференциального уравнения, удовлетворяющего начальным условиям y(x₀) = y₀.'
                }
              ]
            };

            onLectureCreated(newLecture);
            setRecordingState('idle');
            onNavigateToViewer();
          }, 800);
          return prev;
        }
      });
    }, 1100);
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

  // Load preset sample
  const loadPresetLecture = (index: number) => {
    const sample = SAMPLE_LECTURES[index];
    if (sample) {
      onLectureCreated(sample);
      onNavigateToViewer();
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 bg-neutral-950">
      <div className="max-w-4xl mx-auto space-y-6">
        
        {/* Header Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-neutral-800">
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              Студия записи и транскрибации
            </h1>
            <p className="text-xs text-neutral-400 mt-1">
              Локальная обработка речи с выделением задач, дедлайнов и LaTeX формул
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
              <Mic className="w-3.5 h-3.5 text-indigo-400" />
              Прямая запись с микрофона
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
              Загрузка аудиофайла
            </button>
          </div>
        </div>

        {/* Processing State Overlay / Panel */}
        {recordingState === 'processing' ? (
          <div className="p-8 rounded-xl bg-neutral-900 border border-neutral-800 text-center space-y-6">
            <div className="w-14 h-14 mx-auto rounded-full bg-indigo-950/60 border border-indigo-700/60 flex items-center justify-center text-indigo-400 animate-pulse">
              <Sparkles className="w-7 h-7" />
            </div>

            <div>
              <h2 className="text-lg font-bold text-white">
                Обработка аудиозаписи...
              </h2>
              <p className="text-xs text-neutral-400 mt-1">
                Распознавание речи, извлечение задач и форматирование конспекта
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-left">
              {pipelineSteps.map((step, idx) => {
                const isDone = idx < pipelineStage;
                const isCurrent = idx === pipelineStage;
                return (
                  <div
                    key={idx}
                    className={`p-3 rounded-lg border transition-all ${
                      isCurrent 
                        ? 'bg-indigo-950/40 border-indigo-500/80 text-white' 
                        : isDone 
                          ? 'bg-neutral-900/60 border-emerald-900/60 text-emerald-300' 
                          : 'bg-neutral-950/40 border-neutral-800 text-neutral-500'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      {isDone ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      ) : (
                        <span className={`w-4 h-4 rounded-full text-[10px] flex items-center justify-center font-mono font-bold ${isCurrent ? 'bg-indigo-600 text-white' : 'bg-neutral-800 text-neutral-400'}`}>
                          {idx + 1}
                        </span>
                      )}
                      <span className="font-semibold text-xs truncate">{step.title}</span>
                    </div>
                    <p className="text-[11px] leading-tight text-neutral-400">
                      {step.desc}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        ) : mode === 'mic' ? (
          /* Live Microphone Mode */
          <div className="space-y-6">
            {/* Visualizer and Timer Card */}
            <div className="p-6 rounded-xl bg-neutral-900 border border-neutral-800 space-y-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={`w-3 h-3 rounded-full ${recordingState === 'recording' ? 'bg-rose-500 animate-pulse' : recordingState === 'paused' ? 'bg-amber-400' : 'bg-neutral-600'}`} />
                  <span className="text-xs font-medium text-neutral-300">
                    {recordingState === 'recording' ? 'Идет запись лекции' : recordingState === 'paused' ? 'Запись на паузе' : 'Микрофон готов к работе'}
                  </span>
                </div>

                <div className="flex items-center gap-4 text-xs font-mono text-neutral-400">
                  <div className="flex items-center gap-1">
                    <Volume2 className="w-3.5 h-3.5 text-neutral-500" />
                    <span>{recordingState === 'recording' ? `${currentDecibels} dB` : '- - dB'}</span>
                  </div>
                  <div className="text-xl font-bold text-white tabular-nums tracking-wider">
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
                        className="flex items-center gap-2 px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-all shadow-md shadow-indigo-900/40"
                      >
                        <Square className="w-4 h-4 fill-white" />
                        Завершить и транскрибировать
                      </button>
                    </>
                  )}
                </div>

                <div className="text-xs text-neutral-500">
                  Горячая клавиша: <kbd className="px-1.5 py-0.5 rounded bg-neutral-800 font-mono text-[10px] text-neutral-300">Space</kbd> — пауза / запись
                </div>
              </div>

              {/* Bookmarks list if any */}
              {bookmarks.length > 0 && (
                <div className="pt-3 border-t border-neutral-800 flex flex-wrap gap-2 text-xs">
                  <span className="text-neutral-400 self-center">Метки лекции:</span>
                  {bookmarks.map((bm, bIdx) => (
                    <span key={bIdx} className="px-2 py-1 rounded bg-neutral-800 text-neutral-300 font-mono text-[11px] flex items-center gap-1">
                      <Bookmark className="w-3 h-3 text-indigo-400" />
                      {formatTime(bm.time)}: {bm.note}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Lecture Metadata inputs */}
            <div className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-4">
              <h3 className="text-sm font-semibold text-neutral-200 flex items-center gap-2">
                <Sliders className="w-4 h-4 text-indigo-400" />
                Параметры текущей лекции
              </h3>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1">
                    Предмет / Дисциплина
                  </label>
                  <input
                    type="text"
                    value={lectureSubject}
                    onChange={(e) => setLectureSubject(e.target.value)}
                    className="w-full px-3 py-1.5 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
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
                    onChange={(e) => setLectureTitle(e.target.value)}
                    className="w-full px-3 py-1.5 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
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
                    onChange={(e) => setLecturerName(e.target.value)}
                    className="w-full px-3 py-1.5 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                    placeholder="ФИО лектора"
                  />
                </div>
              </div>

              {/* Noise Profile selector */}
              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1.5">
                  Акустический профиль аудитории (для VAD и шумоподавления)
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {[
                    { id: 'quiet', title: 'Тихая аудитория', desc: 'Первые ряды, чистый звук' },
                    { id: 'moderate', title: 'Обычный шум', desc: 'Шелест, легкий фоновый шум' },
                    { id: 'noisy', title: 'Шумная задняя парта', desc: '10 dB SNR, разговоры вокруг' },
                    { id: 'echo', title: 'Большой амфитеатр', desc: 'Поточная аудитория с эхом' },
                  ].map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setNoiseProfile(p.id as unknown as 'quiet')}
                      className={`p-2.5 rounded-lg border text-left transition-all ${
                        noiseProfile === p.id
                          ? 'bg-indigo-950/40 border-indigo-500 text-white'
                          : 'bg-neutral-950 border-neutral-800 text-neutral-400 hover:border-neutral-700'
                      }`}
                    >
                      <div className="font-semibold text-xs leading-none mb-1">{p.title}</div>
                      <div className="text-[10px] text-neutral-500 leading-tight">{p.desc}</div>
                    </button>
                  ))}
                </div>
              </div>
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
                  Выберите или перетащите аудиофайл лекции
                </h3>
                <p className="text-xs text-neutral-400 mt-1">
                  Поддерживаются форматы: MP3, WAV, M4A, OGG, FLAC (до 500 МБ)
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
                Выбрать файл на диске
              </label>

              {selectedFile && (
                <div className="mt-4 p-3 rounded-lg bg-neutral-950 border border-neutral-800 max-w-md mx-auto text-left flex items-center justify-between">
                  <div className="flex items-center gap-2 truncate">
                    <FileAudio className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span className="text-xs text-neutral-200 truncate">{selectedFile.name}</span>
                    <span className="text-[10px] text-neutral-500 font-mono">
                      ({(selectedFile.size / (1024 * 1024)).toFixed(1)} МБ)
                    </span>
                  </div>

                  <button
                    onClick={finishAndProcess}
                    className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium shrink-0 ml-2"
                  >
                    Запустить ASR
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
          </div>
        )}

        {/* Quick Demo Lectures Preset Row */}
        <div className="pt-4 border-t border-neutral-800">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-neutral-400">
              Быстрый запуск демо-лекций для тестирования интерфейса и формул:
            </span>
            <span className="text-[11px] text-neutral-500">
              3 готовые университетские записи
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {SAMPLE_LECTURES.map((lec, idx) => (
              <button
                key={lec.id}
                onClick={() => loadPresetLecture(idx)}
                className="p-3 rounded-lg bg-neutral-900/60 hover:bg-neutral-850 border border-neutral-800 hover:border-neutral-700 text-left transition-all group"
              >
                <div className="flex items-center justify-between text-[11px] text-neutral-400 mb-1">
                  <span>{lec.subject}</span>
                  <span className="font-mono text-neutral-500">{Math.round(lec.durationSeconds / 60)} мин</span>
                </div>
                <div className="text-xs font-medium text-neutral-200 group-hover:text-indigo-300 transition-colors line-clamp-1 mb-1">
                  {lec.title}
                </div>
                <div className="text-[10px] text-neutral-500">
                  {lec.lecturer} · {lec.actionItems.length} задач · {lec.latexFormulas.length} формул
                </div>
              </button>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
};
