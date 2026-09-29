import React, { useState } from 'react';
import { 
  X, 
  Copy, 
  Check, 
  FileCode, 
  Terminal, 
  FolderDown, 
  Layers
} from 'lucide-react';

interface PySide6CodeExportModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const PySide6CodeExportModal: React.FC<PySide6CodeExportModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [activeFile, setActiveFile] = useState<'app.py' | 'transcription_worker.py' | 'requirements.txt'>('app.py');
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const files = {
    'app.py': `"""
Lectura AI — Автономный AI-диктофон для студентов
PySide6 (Qt6) Desktop GUI Application
Реализация современного интерфейса на Python
"""
import sys
import os
import json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QTabWidget, QTextEdit,
    QProgressBar, QFileDialog, QListWidget, QListWidgetItem, QFrame
)
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QIcon, QFont, QColor
from transcription_worker import AudioRecorderWorker, TranscriptionPipelineWorker

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lectura AI — Автономный AI-диктофон для студентов [PySide6]")
        self.resize(1100, 720)
        self.setStyleSheet("""
            QMainWindow { background-color: #0a0a0a; }
            QWidget { color: #f5f5f5; font-family: 'Segoe UI', Arial, sans-serif; }
            QTabWidget::pane { border: 1px solid #262626; background: #0f0f0f; border-radius: 8px; }
            QTabBar::tab { background: #171717; color: #a3a3a3; padding: 8px 16px; border-radius: 6px; margin: 2px; }
            QTabBar::tab:selected { background: #4f46e5; color: #ffffff; font-weight: bold; }
            QPushButton { background-color: #262626; border: 1px solid #404040; border-radius: 6px; padding: 6px 14px; }
            QPushButton:hover { background-color: #333333; }
            QTextEdit { background-color: #0f0f0f; border: 1px solid #262626; border-radius: 6px; padding: 10px; }
        """)
        
        self.init_ui()
        
    def init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        
        # 1. Top Header Bar
        header = QHBoxLayout()
        title_label = QLabel("🎙️ Lectura AI · Студия конспектов")
        title_label.setFont(QFont("Arial", 13, QFont.Bold))
        header.addWidget(title_label)
        
        status_badge = QLabel("🔒 100% Офлайн · Whisper INT8 + Qwen 2.5 7B")
        status_badge.setStyleSheet("color: #34d399; font-size: 11px; padding: 4px 8px; background: #064e3b; border-radius: 4px;")
        header.addStretch()
        header.addWidget(status_badge)
        main_layout.addLayout(header)
        
        # 2. Main Tabs
        self.tabs = QTabWidget()
        
        # Tab 1: Studio / Recorder
        self.studio_tab = QWidget()
        self.setup_studio_tab()
        self.tabs.addTab(self.studio_tab, "🎙️ Запись и Загрузка")
        
        # Tab 2: Notes & LaTeX
        self.notes_tab = QWidget()
        self.setup_notes_tab()
        self.tabs.addTab(self.notes_tab, "📝 Конспект и Формулы")
        
        # Tab 3: History Archive
        self.history_tab = QWidget()
        self.setup_history_tab()
        self.tabs.addTab(self.history_tab, "📚 История лекций")
        
        # Tab 4: AI Research & Settings
        self.settings_tab = QWidget()
        self.setup_settings_tab()
        self.tabs.addTab(self.settings_tab, "⚙️ Настройки и Модели")
        
        main_layout.addWidget(self.tabs)
        self.setCentralWidget(central_widget)
        
    def setup_studio_tab(self):
        layout = QVBoxLayout(self.studio_tab)
        # Visualizer frame
        self.visualizer_frame = QFrame()
        self.visualizer_frame.setFixedHeight(120)
        self.visualizer_frame.setStyleSheet("background: #000000; border: 1px solid #262626; border-radius: 8px;")
        layout.addWidget(self.visualizer_frame)
        
        # Controls
        btn_layout = QHBoxLayout()
        self.record_btn = QPushButton("🔴 Начать запись лекции")
        self.record_btn.setStyleSheet("background: #dc2626; color: white; font-weight: bold; padding: 10px 20px;")
        self.record_btn.clicked.connect(self.toggle_recording)
        
        self.upload_btn = QPushButton("📁 Загрузить WAV/MP3 файл")
        self.upload_btn.clicked.connect(self.upload_audio)
        
        btn_layout.addWidget(self.record_btn)
        btn_layout.addWidget(self.upload_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # Progress bar for local pipeline
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #4f46e5; }")
        layout.addWidget(self.progress_bar)
        layout.addStretch()

    def setup_notes_tab(self):
        layout = QVBoxLayout(self.notes_tab)
        self.notes_viewer = QTextEdit()
        self.notes_viewer.setReadOnly(True)
        self.notes_viewer.setHtml("<h3>Конспект лекции появится здесь после распознавания</h3>")
        layout.addWidget(self.notes_viewer)

    def setup_history_tab(self):
        layout = QVBoxLayout(self.history_tab)
        self.history_list = QListWidget()
        self.history_list.addItem("Высшая математика: Дифференциальные уравнения (28 сент, 87 мин)")
        self.history_list.addItem("Общая физика: Уравнения Максвелла (25 сент, 80 мин)")
        self.history_list.addItem("Алгоритмы: Красно-черные деревья (22 сент, 75 мин)")
        layout.addWidget(self.history_list)

    def setup_settings_tab(self):
        layout = QVBoxLayout(self.settings_tab)
        info = QLabel("Локальный бэкенд: faster-whisper-large-v3-turbo (int8)\\nМодель суммаризации: Qwen/Qwen2.5-7B-Instruct-GGUF (Q4_K_M)\\nУскорение: CUDA / Metal MPS")
        layout.addWidget(info)
        layout.addStretch()

    def toggle_recording(self):
        print("Toggling local recording worker...")

    def upload_audio(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите аудиозапись лекции", "", "Audio (*.wav *.mp3 *.m4a)")
        if file_path:
            print(f"Starting offline transcription pipeline for: {file_path}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
`,
    'transcription_worker.py': `"""
Автономный конвейер транскрибации и структурирования
1. Silero VAD (фильтрация пауз)
2. Faster-Whisper (ASR)
3. llama-cpp-python (Локальная LLM Qwen 2.5)
"""
import os
from PySide6.QtCore import QThread, Signal
from faster_whisper import WhisperModel
from llama_cpp import Llama

class TranscriptionPipelineWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(dict)
    
    def __init__(self, audio_path: str, asr_model_size="large-v3-turbo", device="cuda", compute_type="int8"):
        super().__init__()
        self.audio_path = audio_path
        self.asr_model_size = asr_model_size
        self.device = device
        self.compute_type = compute_type

    def run(self):
        # Шаг 1: Инициализация VAD и Whisper (CTranslate2)
        self.progress.emit(20, "Загрузка модели Faster-Whisper (INT8)...")
        model = WhisperModel(
            self.asr_model_size,
            device=self.device,
            compute_type=self.compute_type,
            vad_filter=True, # Встроенный Silero VAD!
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        
        # Шаг 2: Распознавание речи
        self.progress.emit(50, "Офлайн транскрибация аудиозаписи...")
        segments, info = model.transcribe(
            self.audio_path,
            language="ru",
            beam_size=5,
            word_timestamps=True
        )
        
        transcript_text = ""
        transcript_segments = []
        for segment in segments:
            transcript_segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text
            })
            transcript_text += f"[{segment.start:.1f}s - {segment.end:.1f}s]: {segment.text}\\n"
            
        # Шаг 3: Структурирование и извлечение задач локальной LLM
        self.progress.emit(75, "Извлечение задач, дедлайнов и LaTeX формул (Qwen 2.5)...")
        llm = Llama(
            model_path="models/qwen2.5-7b-instruct-q4_k_m.gguf",
            n_ctx=16384,
            n_gpu_layers=33 # Полный сброс на GPU
        )
        
        prompt = f"""<|im_start|>system
Ты автономный ассистент студента. Извлеки из стенограммы лекции:
1. Краткий конспект в Markdown с формулами в формате LaTeX ($...$ и $$...$$)
2. Все домашние задания, дедлайны и даты сдачи
3. Ключевые термины и определения
Ответь в формате JSON.<|im_end|>
<|im_start|>user
Стенограмма лекции:
{transcript_text[:12000]}<|im_end|>
<|im_start|>assistant
"""
        response = llm(prompt, max_tokens=2048, stop=["<|im_end|>"])
        llm_output = response["choices"][0]["text"]
        
        self.progress.emit(100, "Готово!")
        self.finished.emit({
            "transcript": transcript_segments,
            "raw_text": transcript_text,
            "structured_output": llm_output
        })
`,
    'requirements.txt': `# Зависимости для автономного десктопного диктофона Lectura AI
# Python 3.10 / 3.11

# Графический интерфейс Qt6
PySide6>=6.6.0

# Локальное распознавание речи (CTranslate2 + Silero VAD)
faster-whisper>=1.0.3

# Локальная LLM (GGUF инференс на CPU/GPU)
llama-cpp-python>=0.2.80

# Захват аудио с микрофона и обработка
sounddevice>=0.4.6
soundfile>=0.12.1
numpy>=1.24.0

# Утилиты Hugging Face для кэширования моделей
huggingface-hub>=0.23.0
`
  };

  const handleCopyCode = () => {
    navigator.clipboard.writeText(files[activeFile]);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-neutral-900 border border-neutral-800 rounded-2xl w-full max-w-4xl max-h-[88vh] flex flex-col shadow-2xl overflow-hidden">
        
        {/* Modal Header */}
        <div className="p-4 px-6 border-b border-neutral-800 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
              <FileCode className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">
                Архитектура и код PySide6 / Python бэкенда
              </h2>
              <p className="text-[11px] text-neutral-400">
                Готовые скрипты для запуска автономного десктопного приложения на вашем ПК
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* File Tabs & Copy Action */}
        <div className="px-6 py-2 bg-neutral-950 border-b border-neutral-850 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2 overflow-x-auto">
            {(['app.py', 'transcription_worker.py', 'requirements.txt'] as const).map((fname) => (
              <button
                key={fname}
                onClick={() => setActiveFile(fname)}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors ${
                  activeFile === fname
                    ? 'bg-neutral-850 text-indigo-400 border border-neutral-750 font-semibold'
                    : 'text-neutral-400 hover:text-neutral-200'
                }`}
              >
                {fname}
              </button>
            ))}
          </div>

          <button
            onClick={handleCopyCode}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5" />
                Скопировано!
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                Скопировать файл
              </>
            )}
          </button>
        </div>

        {/* Code View Area */}
        <div className="flex-1 overflow-y-auto p-6 bg-neutral-950">
          <pre className="font-mono text-xs text-neutral-300 leading-relaxed overflow-x-auto select-text">
            <code>{files[activeFile]}</code>
          </pre>
        </div>

        {/* Footer with quick command */}
        <div className="p-4 px-6 bg-neutral-900 border-t border-neutral-800 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs shrink-0">
          <div className="flex items-center gap-2 text-neutral-400 font-mono text-[11px]">
            <Terminal className="w-3.5 h-3.5 text-indigo-400" />
            <span>Запуск: pip install -r requirements.txt && python app.py</span>
          </div>

          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-xs font-medium"
          >
            Закрыть
          </button>
        </div>

      </div>
    </div>
  );
};
