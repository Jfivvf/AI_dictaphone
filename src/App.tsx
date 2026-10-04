import React, { useState, useEffect, useRef } from 'react';
import { 
  Mic, 
  BookOpen, 
  CalendarCheck, 
  HardDrive, 
  Settings, 
  User, 
  Upload,
  FileText
} from 'lucide-react';
import { Lecture, AppSettings, StudentProfile, ActionItem } from './types';
import { SAMPLE_LECTURES } from './data/sampleLectures';
import { extractTextFromPdf, convertTextToLecture } from './utils/pdfParser';
import { DesktopHeader } from './components/DesktopHeader';
import { AudioRecorder } from './components/AudioRecorder';
import { LectureViewer } from './components/LectureViewer';
import { LectureHistory } from './components/LectureHistory';
import { DeadlinesTab } from './components/DeadlinesTab';
import { StorageTab } from './components/StorageTab';
import { SettingsTab } from './components/SettingsTab';
import { StudentProfileTab } from './components/StudentProfileTab';
import { PySide6CodeExportModal } from './components/PySide6CodeExportModal';

const DEFAULT_SETTINGS: AppSettings = {
  asrModel: 'faster-whisper-turbo',
  asrQuantization: 'int8',
  llmModel: 'qwen-2.5-7b',
  llmQuantization: 'q4_k_m',
  contextWindowTokens: 32768,
  vadThreshold: 0.5,
  noiseSuppression: 'rnnoise',
  hardwareBackend: 'cuda',
  huggingFaceCacheDir: '~/.cache/huggingface/hub',
  localStorageDbPath: '~/LecturaAI/storage/lectures.db',
  audioSampleRate: 16000,
  offlineStrict: true,
  student: {
    name: 'Алексей Смирнов',
    email: 'smirnov.alex@edu.university.ru',
    university: 'МГУ им. М. В. Ломоносова',
    faculty: 'Механико-математический',
    group: '204-Б',
    semester: 3,
    degree: 'Bachelor',
    theme: 'dark'
  }
};

export default function App() {
  // Navigation active tab: 'record' | 'history' | 'viewer' | 'deadlines' | 'storage' | 'settings' | 'profile'
  const [activeTab, setActiveTab] = useState<'record' | 'history' | 'viewer' | 'deadlines' | 'storage' | 'settings' | 'profile'>('history');
  
  // Loading state for PDF processing
  const [isProcessingPdf, setIsProcessingPdf] = useState(false);

  // Hidden file input ref for PDF/Markdown import
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Lectures collection (starts clean and empty like a new notes app)
  const [lectures, setLectures] = useState<Lecture[]>(() => {
    const saved = localStorage.getItem('lectura_ai_lectures');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        // If it was previous dummy math analysis sample, clear it to start clean
        if (Array.isArray(parsed) && parsed.some(l => l.id === 'lec-math-01')) {
          localStorage.removeItem('lectura_ai_lectures');
          return [];
        }
        return parsed;
      } catch {
        return [];
      }
    }
    return [];
  });

  // Current active lecture being viewed
  const [activeLectureId, setActiveLectureId] = useState<string | null>(null);

  // App settings
  const [settings, setSettings] = useState<AppSettings>(() => {
    const saved = localStorage.getItem('lectura_ai_settings');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        return DEFAULT_SETTINGS;
      }
    }
    return DEFAULT_SETTINGS;
  });

  // PySide6 code export modal state
  const [isPySideModalOpen, setIsPySideModalOpen] = useState(false);

  // Persist lectures
  useEffect(() => {
    localStorage.setItem('lectura_ai_lectures', JSON.stringify(lectures));
  }, [lectures]);

  // Persist settings
  useEffect(() => {
    localStorage.setItem('lectura_ai_settings', JSON.stringify(settings));
  }, [settings]);

  // Active lecture object
  const activeLecture = lectures.find(l => l.id === activeLectureId) || lectures[0] || null;

  // Handlers
  const handleLectureCreated = (newLecture: Lecture) => {
    setLectures(prev => [newLecture, ...prev]);
    setActiveLectureId(newLecture.id);
  };

  const handleUpdateLecture = (updated: Lecture) => {
    setLectures(prev => prev.map(l => l.id === updated.id ? updated : l));
  };

  const handleDeleteLecture = (lectureId: string) => {
    setLectures(prev => prev.filter(l => l.id !== lectureId));
    if (activeLectureId === lectureId) {
      const remaining = lectures.filter(l => l.id !== lectureId);
      if (remaining.length > 0) {
        setActiveLectureId(remaining[0].id);
      }
    }
  };

  const handleToggleTask = (lectureId: string, taskId: string) => {
    setLectures(prev => prev.map(lec => {
      if (lec.id !== lectureId) return lec;
      return {
        ...lec,
        actionItems: lec.actionItems.map(item => 
          item.id === taskId ? { ...item, completed: !item.completed } : item
        )
      };
    }));
  };

  const handleAddNewTask = (newTask: ActionItem, lectureId?: string) => {
    setLectures(prev => prev.map(lec => {
      if (lec.id !== lectureId && lec.id !== prev[0]?.id) return lec;
      return {
        ...lec,
        actionItems: [newTask, ...lec.actionItems]
      };
    }));
  };

  const handleClearAudioCache = () => {
    setLectures(prev => prev.map(l => ({ ...l, audioFileName: undefined })));
  };

  const handleImportBackup = (backupLectures: Lecture[]) => {
    setLectures(backupLectures);
    if (backupLectures.length > 0) {
      setActiveLectureId(backupLectures[0].id);
    }
  };

  const handleUpdateProfile = (newProfile: StudentProfile) => {
    setSettings(prev => ({ ...prev, student: newProfile }));
  };

  // Import PDF or Markdown / Text file
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsProcessingPdf(true);

    try {
      if (file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf') {
        const text = await extractTextFromPdf(file);
        const newLecture = convertTextToLecture(text, file.name);
        handleLectureCreated(newLecture);
        setActiveTab('viewer');
      } else {
        // Plain text / Markdown / TeX
        const reader = new FileReader();
        reader.onload = (event) => {
          const text = event.target?.result as string;
          const newLecture = convertTextToLecture(text, file.name);
          handleLectureCreated(newLecture);
          setActiveTab('viewer');
        };
        reader.readAsText(file);
      }
    } catch (err) {
      console.error('Error importing document:', err);
      alert('Не удалось обработать файл. Попробуйте другой PDF или Markdown документ.');
    } finally {
      setIsProcessingPdf(false);
      // Reset input value so same file can be selected again
      if (e.target) e.target.value = '';
    }
  };

  // Count pending deadlines
  const totalPendingDeadlines = lectures.reduce((acc, l) => 
    acc + l.actionItems.filter(t => !t.completed).length, 0
  );

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-neutral-950 text-neutral-100 font-sans">
      
      {/* Desktop App Window Titlebar */}
      <DesktopHeader
        settings={settings}
        onOpenPySideCode={() => setIsPySideModalOpen(true)}
        onNavigateToAccount={() => setActiveTab('profile')}
        activeTab={activeTab}
      />

      {/* Main Container */}
      <div className="flex flex-1 overflow-hidden">
        
        {/* Left Desktop Sidebar Navigation */}
        <aside className="w-56 lg:w-60 bg-neutral-900 border-r border-neutral-800 flex flex-col justify-between shrink-0 select-none">
          <div className="p-3 space-y-1">
            
            <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
              Основное
            </div>

            {/* 1. Record */}
            <button
              onClick={() => setActiveTab('record')}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-medium transition-colors text-left ${
                activeTab === 'record'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/60'
              }`}
            >
              <Mic className="w-4 h-4 shrink-0 text-rose-400" />
              <span>Запись лекции</span>
            </button>

            {/* 2. My Lectures / History */}
            <button
              onClick={() => setActiveTab('history')}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium transition-colors text-left ${
                activeTab === 'history' || activeTab === 'viewer'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/60'
              }`}
            >
              <div className="flex items-center gap-3">
                <BookOpen className="w-4 h-4 shrink-0" />
                <span>Мои лекции</span>
              </div>
              <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                activeTab === 'history' || activeTab === 'viewer' ? 'bg-indigo-700 text-white' : 'bg-neutral-800 text-neutral-400'
              }`}>
                {lectures.length}
              </span>
            </button>

            {/* 3. Deadlines & Tasks */}
            <button
              onClick={() => setActiveTab('deadlines')}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium transition-colors text-left ${
                activeTab === 'deadlines'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/60'
              }`}
            >
              <div className="flex items-center gap-3">
                <CalendarCheck className="w-4 h-4 shrink-0 text-amber-400" />
                <span>Дедлайны и задачи</span>
              </div>
              {totalPendingDeadlines > 0 && (
                <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono font-bold ${
                  activeTab === 'deadlines' ? 'bg-amber-500 text-neutral-950' : 'bg-amber-950 text-amber-300'
                }`}>
                  {totalPendingDeadlines}
                </span>
              )}
            </button>

            <div className="pt-4 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
              Управление
            </div>

            {/* 4. Storage & Files */}
            <button
              onClick={() => setActiveTab('storage')}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-medium transition-colors text-left ${
                activeTab === 'storage'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/60'
              }`}
            >
              <HardDrive className="w-4 h-4 shrink-0" />
              <span>Память и файлы</span>
            </button>

            {/* 5. Settings */}
            <button
              onClick={() => setActiveTab('settings')}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-medium transition-colors text-left ${
                activeTab === 'settings'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/60'
              }`}
            >
              <Settings className="w-4 h-4 shrink-0" />
              <span>Настройки</span>
            </button>

            {/* 6. Student Profile */}
            <button
              onClick={() => setActiveTab('profile')}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-medium transition-colors text-left ${
                activeTab === 'profile'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/60'
              }`}
            >
              <User className="w-4 h-4 shrink-0" />
              <span>Профиль студента</span>
            </button>

          </div>

          {/* Import PDF and Documents in Sidebar Footer */}
          <div className="p-3 border-t border-neutral-800 space-y-2">
            <input
              type="file"
              ref={fileInputRef}
              accept=".pdf,.md,.txt,.tex"
              onChange={handleFileUpload}
              className="hidden"
            />
            
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isProcessingPdf}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-neutral-950 hover:bg-neutral-800 border border-neutral-800 text-neutral-200 text-xs font-medium transition-colors disabled:opacity-50"
            >
              <Upload className="w-3.5 h-3.5 text-indigo-400" />
              <span>{isProcessingPdf ? 'Чтение PDF...' : 'Импорт PDF / .MD'}</span>
            </button>
          </div>
        </aside>

        {/* Dynamic Viewport Content */}
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden bg-neutral-950">
          
          {/* TAB 1: RECORD */}
          {activeTab === 'record' && (
            <AudioRecorder
              settings={settings}
              onLectureCreated={(newLecture) => {
                handleLectureCreated(newLecture);
                setActiveTab('viewer');
              }}
              onNavigateToViewer={() => setActiveTab('viewer')}
            />
          )}

          {/* TAB 2: MY LECTURES HISTORY */}
          {activeTab === 'history' && (
            <LectureHistory
              lectures={lectures}
              activeLectureId={activeLectureId}
              onSelectLecture={(lec) => {
                setActiveLectureId(lec.id);
                setActiveTab('viewer');
              }}
              onDeleteLecture={handleDeleteLecture}
              onNavigateToRecorder={() => setActiveTab('record')}
              onTriggerPdfUpload={() => fileInputRef.current?.click()}
            />
          )}

          {/* TAB 3: LECTURE VIEWER */}
          {activeTab === 'viewer' && (
            <LectureViewer
              lecture={activeLecture}
              onUpdateLecture={handleUpdateLecture}
              onBackToHistory={() => setActiveTab('history')}
              onNavigateToRecorder={() => setActiveTab('record')}
              onDeleteLecture={handleDeleteLecture}
            />
          )}

          {/* TAB 4: DEADLINES & TASKS TRACKER */}
          {activeTab === 'deadlines' && (
            <DeadlinesTab
              lectures={lectures}
              onToggleTask={handleToggleTask}
              onOpenLecture={(lecId) => {
                setActiveLectureId(lecId);
                setActiveTab('viewer');
              }}
              onAddNewTask={handleAddNewTask}
            />
          )}

          {/* TAB 5: STORAGE & FILES */}
          {activeTab === 'storage' && (
            <StorageTab
              lectures={lectures}
              onClearAudioCache={handleClearAudioCache}
              onImportBackup={handleImportBackup}
            />
          )}

          {/* TAB 6: SETTINGS */}
          {activeTab === 'settings' && (
            <SettingsTab
              settings={settings}
              onUpdateSettings={setSettings}
            />
          )}

          {/* TAB 7: STUDENT PROFILE */}
          {activeTab === 'profile' && (
            <StudentProfileTab
              profile={settings.student}
              onUpdateProfile={handleUpdateProfile}
            />
          )}

        </main>

      </div>

      {/* PySide6 Code Modal */}
      <PySide6CodeExportModal
        isOpen={isPySideModalOpen}
        onClose={() => setIsPySideModalOpen(false)}
      />

    </div>
  );
}
