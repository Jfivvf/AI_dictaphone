import React, { useState, useEffect, useRef } from 'react';
import {
  Mic,
  BookOpen,
  CalendarCheck,
  HardDrive,
  Settings,
  User,
  Upload,
  LogOut,
  LogIn
} from 'lucide-react';
import { onAuthStateChanged, User as FirebaseUser } from 'firebase/auth';
import { collection, query, where, onSnapshot } from 'firebase/firestore';
import { Lecture, AppSettings, StudentProfile, ActionItem } from './types';
import { smartImportDocumentToLecture } from './utils/pdfParser';
import {
  auth,
  db,
  sanitizeId,
  ensureUserProfileInFirestore,
  updateUserProfileInFirestore,
  createLectureInFirestore,
  updateLectureInFirestore,
  deleteLectureFromFirestore,
  toggleTaskInFirestore,
  updateTaskPriorityInFirestore,
  addTaskToFirestore,
  loadTasksForLecture,
  mapDocToLecture,
  signOutUser,
  handleFirestoreError,
  OperationType
} from './firebase';
import { DesktopHeader } from './components/DesktopHeader';
import { AudioRecorder } from './components/AudioRecorder';
import { LectureViewer } from './components/LectureViewer';
import { LectureHistory } from './components/LectureHistory';
import { DeadlinesTab } from './components/DeadlinesTab';
import { StorageTab } from './components/StorageTab';
import { SettingsTab } from './components/SettingsTab';
import { StudentProfileTab } from './components/StudentProfileTab';
import { AuthScreen } from './components/AuthScreen';

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
  // Authentication state
  const [currentUser, setCurrentUser] = useState<FirebaseUser | null>(null);
  const [isAuthReady, setIsAuthReady] = useState(false);
  const [isOfflineGuest, setIsOfflineGuest] = useState(false);

  // Navigation active tab: 'record' | 'history' | 'viewer' | 'deadlines' | 'storage' | 'settings' | 'profile'
  const [activeTab, setActiveTab] = useState<'record' | 'history' | 'viewer' | 'deadlines' | 'storage' | 'settings' | 'profile'>('history');

  // Loading state for PDF processing
  const [isProcessingPdf, setIsProcessingPdf] = useState(false);

  // Hidden file input ref for PDF/Markdown import
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Lectures collection
  const [lectures, setLectures] = useState<Lecture[]>(() => {
    const saved = localStorage.getItem('lectura_ai_lectures');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
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

  // Logout confirmation modal state
  const [isLogoutModalOpen, setIsLogoutModalOpen] = useState(false);

  // Track Firebase Auth state
  useEffect(() => {
    const unsubscribeAuth = onAuthStateChanged(auth, async (user) => {
      if (user) {
        setIsOfflineGuest(false);
        try {
          const syncedProfile = await ensureUserProfileInFirestore(user, DEFAULT_SETTINGS.student);
          setSettings(prev => ({
            ...prev,
            student: syncedProfile
          }));
        } catch (err) {
          console.error('Error initializing user profile in Firestore:', err);
        }
      }
      setCurrentUser(user);
      setIsAuthReady(true);
    });
    return () => unsubscribeAuth();
  }, []);

  // Subscribe to user's lectures in Firestore when authenticated
  useEffect(() => {
    if (!isAuthReady || !currentUser) return;

    const safeUid = sanitizeId(currentUser.uid, 'user');
    const lecturesPath = `users/${safeUid}/lectures`;
    const lecturesCol = collection(db, 'users', safeUid, 'lectures');
    const lecturesQuery = query(lecturesCol, where('ownerId', '==', safeUid));

    const unsubscribeLectures = onSnapshot(
      lecturesQuery,
      async (snapshot) => {
        try {
          const loadedLectures: Lecture[] = await Promise.all(
            snapshot.docs.map(async (docSnap) => {
              const data = docSnap.data();
              const lectureId = data.id || docSnap.id;
              const tasks = await loadTasksForLecture(safeUid, lectureId);
              return mapDocToLecture(docSnap.id, data, tasks);
            })
          );
          setLectures(loadedLectures);
          setActiveLectureId(prev => prev || loadedLectures[0]?.id || null);
        } catch (err) {
          console.error('Error loading tasks for lectures:', err);
        }
      },
      (error) => {
        handleFirestoreError(error, OperationType.LIST, lecturesPath);
      }
    );

    return () => unsubscribeLectures();
  }, [isAuthReady, currentUser]);

  // Persist lectures to localStorage in guest mode
  useEffect(() => {
    if (!currentUser) {
      localStorage.setItem('lectura_ai_lectures', JSON.stringify(lectures));
    }
  }, [lectures, currentUser]);

  // Persist settings to localStorage
  useEffect(() => {
    localStorage.setItem('lectura_ai_settings', JSON.stringify(settings));
  }, [settings]);

  // Active lecture object
  const activeLecture = lectures.find(l => l.id === activeLectureId) || lectures[0] || null;

  // Handlers
  const handleLectureCreated = async (newLecture: Lecture) => {
    if (currentUser) {
      try {
        const savedLecture = await createLectureInFirestore(currentUser.uid, newLecture);
        setLectures(prev => {
          const exists = prev.some(l => l.id === savedLecture.id);
          return exists ? prev.map(l => (l.id === savedLecture.id ? savedLecture : l)) : [savedLecture, ...prev];
        });
        setActiveLectureId(savedLecture.id);
      } catch (err) {
        console.error('Failed to save lecture to Firestore:', err);
      }
    } else {
      setLectures(prev => [newLecture, ...prev]);
      setActiveLectureId(newLecture.id);
    }
  };

  const handleUpdateLecture = async (updated: Lecture) => {
    setLectures(prev => prev.map(l => (l.id === updated.id ? updated : l)));
    if (currentUser) {
      try {
        await updateLectureInFirestore(currentUser.uid, updated);
      } catch (err) {
        console.error('Failed to update lecture in Firestore:', err);
      }
    }
  };

  const handleDeleteLecture = async (lectureId: string) => {
    setLectures(prev => prev.filter(l => l.id !== lectureId));
    if (activeLectureId === lectureId) {
      const remaining = lectures.filter(l => l.id !== lectureId);
      setActiveLectureId(remaining.length > 0 ? remaining[0].id : null);
    }
    if (currentUser) {
      try {
        await deleteLectureFromFirestore(currentUser.uid, lectureId);
      } catch (err) {
        console.error('Failed to delete lecture from Firestore:', err);
      }
    }
  };

  const handleToggleTask = async (lectureId: string, taskId: string) => {
    let newCompletedState = false;
    setLectures(prev =>
      prev.map(lec => {
        if (lec.id !== lectureId) return lec;
        return {
          ...lec,
          actionItems: lec.actionItems.map(item => {
            if (item.id === taskId) {
              newCompletedState = !item.completed;
              return { ...item, completed: newCompletedState };
            }
            return item;
          })
        };
      })
    );

    if (currentUser) {
      try {
        await toggleTaskInFirestore(currentUser.uid, lectureId, taskId, newCompletedState);
      } catch (err) {
        console.error('Failed to toggle task in Firestore:', err);
      }
    }
  };

  const handleChangeTaskPriority = async (
    lectureId: string,
    taskId: string,
    priority: 'high' | 'medium' | 'low'
  ) => {
    setLectures(prev =>
      prev.map(lec => {
        if (lec.id !== lectureId) return lec;
        return {
          ...lec,
          actionItems: lec.actionItems.map(item =>
            item.id === taskId ? { ...item, priority } : item
          )
        };
      })
    );

    if (currentUser) {
      try {
        await updateTaskPriorityInFirestore(currentUser.uid, lectureId, taskId, priority);
      } catch (err) {
        console.error('Failed to update task priority in Firestore:', err);
      }
    }
  };

  const handleAddNewTask = async (newTask: ActionItem, lectureId?: string) => {
    const targetLectureId = lectureId || lectures[0]?.id;
    if (!targetLectureId) return;

    if (currentUser) {
      try {
        const savedTask = await addTaskToFirestore(currentUser.uid, targetLectureId, newTask);
        setLectures(prev =>
          prev.map(lec => {
            if (lec.id !== targetLectureId) return lec;
            return {
              ...lec,
              actionItems: [savedTask, ...lec.actionItems]
            };
          })
        );
      } catch (err) {
        console.error('Failed to add task to Firestore:', err);
      }
    } else {
      setLectures(prev =>
        prev.map(lec => {
          if (lec.id !== targetLectureId) return lec;
          return {
            ...lec,
            actionItems: [newTask, ...lec.actionItems]
          };
        })
      );
    }
  };

  const handleClearAudioCache = async () => {
    const updatedList = lectures.map(l => ({ ...l, audioFileName: undefined }));
    setLectures(updatedList);
    if (currentUser) {
      for (const lec of updatedList) {
        try {
          await updateLectureInFirestore(currentUser.uid, lec);
        } catch (err) {
          console.error('Failed to clear audio cache in Firestore for lecture:', lec.id, err);
        }
      }
    }
  };

  const handleImportBackup = async (backupLectures: Lecture[]) => {
    setLectures(backupLectures);
    if (backupLectures.length > 0) {
      setActiveLectureId(backupLectures[0].id);
    }
    if (currentUser) {
      for (const lec of backupLectures) {
        try {
          await createLectureInFirestore(currentUser.uid, lec);
        } catch (err) {
          console.error('Failed to import backup lecture to Firestore:', err);
        }
      }
    }
  };

  const handleUpdateProfile = async (newProfile: StudentProfile) => {
    setSettings(prev => ({ ...prev, student: newProfile }));
    if (currentUser) {
      try {
        await updateUserProfileInFirestore(currentUser.uid, newProfile);
      } catch (err) {
        console.error('Failed to update user profile in Firestore:', err);
      }
    }
  };

  const handleSignOut = async () => {
    try {
      setIsLogoutModalOpen(false);
      await signOutUser();
      setLectures([]);
      setActiveLectureId(null);
      setIsOfflineGuest(false);
    } catch (err) {
      console.error('Sign out error:', err);
    }
  };

  const requestSignOut = () => {
    setIsLogoutModalOpen(true);
  };

  // Import PDF or Markdown / Text file with automatic AI structuring
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsProcessingPdf(true);

    try {
      const newLecture = await smartImportDocumentToLecture(file);
      await handleLectureCreated(newLecture);
      setActiveTab('viewer');
    } catch (err) {
      console.error('Error importing document:', err);
    } finally {
      setIsProcessingPdf(false);
      if (e.target) e.target.value = '';
    }
  };

  // Show loading screen while Firebase Auth initializes
  if (!isAuthReady) {
    return (
      <div className="h-screen w-screen bg-neutral-950 flex items-center justify-center text-neutral-400 text-xs">
        Подключение к базе данных...
      </div>
    );
  }

  // Show Login / Registration screen if not authenticated and not in offline guest mode
  if (!currentUser && !isOfflineGuest) {
    return <AuthScreen onContinueOffline={() => setIsOfflineGuest(true)} />;
  }

  // Count pending deadlines
  const totalPendingDeadlines = lectures.reduce(
    (acc, l) => acc + l.actionItems.filter(t => !t.completed).length,
    0
  );

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-neutral-950 text-neutral-100 font-sans">
      
      {/* Desktop App Window Titlebar */}
      <DesktopHeader
        settings={settings}
        onNavigateToAccount={() => setActiveTab('profile')}
        activeTab={activeTab}
        userEmail={currentUser?.email}
        userPhotoUrl={currentUser?.photoURL}
        isAuthenticated={Boolean(currentUser)}
        onSignOut={requestSignOut}
        onRequireSignIn={() => setIsOfflineGuest(false)}
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

          {/* Import PDF and Auth Controls in Sidebar Footer */}
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
              <span>{isProcessingPdf ? 'Анализ и верстка ИИ...' : 'Импорт PDF / .MD'}</span>
            </button>

            {currentUser ? (
              <button
                onClick={requestSignOut}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-rose-950/40 hover:bg-rose-900/60 border border-rose-800/50 text-rose-300 text-xs font-medium transition-colors"
              >
                <LogOut className="w-3.5 h-3.5 text-rose-400" />
                <span>Выйти из аккаунта</span>
              </button>
            ) : (
              <button
                onClick={() => setIsOfflineGuest(false)}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 text-indigo-300 text-xs font-medium transition-colors"
              >
                <LogIn className="w-3.5 h-3.5 text-indigo-400" />
                <span>Войти в аккаунт</span>
              </button>
            )}
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
              onChangeTaskPriority={handleChangeTaskPriority}
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
              onChangeTaskPriority={handleChangeTaskPriority}
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
              isAuthenticated={Boolean(currentUser)}
              userEmail={currentUser?.email}
              userUid={currentUser?.uid}
              onSignOut={requestSignOut}
              onRequireSignIn={() => setIsOfflineGuest(false)}
            />
          )}

        </main>

      </div>

      {/* Logout Confirmation Modal */}
      {isLogoutModalOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setIsLogoutModalOpen(false)}
        >
          <div
            className="bg-neutral-900 border border-neutral-800 rounded-2xl p-6 max-w-sm w-full space-y-4 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-rose-950/60 border border-rose-800/60 flex items-center justify-center text-rose-400 shrink-0">
                <LogOut className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">Вы точно хотите выйти?</h3>
                <p className="text-xs text-neutral-400 mt-0.5 truncate max-w-[210px]">
                  {currentUser?.email || 'Выход из учетной записи'}
                </p>
              </div>
            </div>

            <p className="text-xs text-neutral-300 leading-relaxed">
              Ваши лекции и дедлайны сохранены в облаке и будут доступны при следующем входе в аккаунт.
            </p>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setIsLogoutModalOpen(false)}
                className="px-3.5 py-2 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-300 font-medium transition-colors"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={handleSignOut}
                className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-xs text-white font-medium transition-colors shadow-sm"
              >
                Выйти
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
