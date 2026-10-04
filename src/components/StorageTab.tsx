import React, { useState } from 'react';
import { 
  HardDrive, 
  Trash2, 
  Download, 
  Upload, 
  FileText, 
  Folder, 
  CheckCircle2, 
  FileAudio,
  AlertCircle
} from 'lucide-react';
import { Lecture } from '../types';

interface StorageTabProps {
  lectures: Lecture[];
  onClearAudioCache: () => void;
  onImportBackup: (backupLectures: Lecture[]) => void;
}

export const StorageTab: React.FC<StorageTabProps> = ({
  lectures,
  onClearAudioCache,
  onImportBackup,
}) => {
  const [cleanedSuccess, setCleanedSuccess] = useState(false);
  const [isConfirmingClear, setIsConfirmingClear] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; isError?: boolean } | null>(null);

  // Compute storage statistics
  const audioCount = lectures.filter(l => l.audioFileName).length;
  const totalAudioSeconds = lectures.reduce((acc, l) => acc + l.durationSeconds, 0);
  const audioSizeMb = ((totalAudioSeconds / 60) * 0.45).toFixed(1);
  const textSizeMb = ((lectures.length * 25) / 1024).toFixed(2);
  const totalSizeMb = (+audioSizeMb + +textSizeMb).toFixed(1);

  // Export all lectures
  const handleExportAll = () => {
    const backupData = {
      version: '1.0',
      exportedAt: new Date().toISOString(),
      lecturesCount: lectures.length,
      lectures: lectures
    };

    const blob = new Blob([JSON.stringify(backupData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `lectura_backup_${new Date().toISOString().split('T')[0]}.json`;
    link.click();
    URL.revokeObjectURL(url);
    setStatusMessage({ text: 'Файл резервной копии успешно экспортирован!' });
    setTimeout(() => setStatusMessage(null), 3000);
  };

  // Import JSON backup
  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        try {
          const parsed = JSON.parse(event.target?.result as string);
          if (parsed && Array.isArray(parsed.lectures)) {
            onImportBackup(parsed.lectures);
            setStatusMessage({ text: `Успешно импортировано ${parsed.lectures.length} лекций!` });
            setTimeout(() => setStatusMessage(null), 3000);
          } else {
            setStatusMessage({ text: 'Файл резервной копии поврежден или имеет неверный формат.', isError: true });
            setTimeout(() => setStatusMessage(null), 4000);
          }
        } catch {
          setStatusMessage({ text: 'Ошибка при чтении файла JSON.', isError: true });
          setTimeout(() => setStatusMessage(null), 4000);
        }
      };
      reader.readAsText(file);
    }
  };

  const executeClearAudio = () => {
    onClearAudioCache();
    setIsConfirmingClear(false);
    setCleanedSuccess(true);
    setTimeout(() => setCleanedSuccess(false), 3000);
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 bg-neutral-950">
      <div className="max-w-4xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-neutral-800">
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              Хранилище и файлы
            </h1>
            <p className="text-xs text-neutral-400 mt-1">
              Управление занятым дисковым пространством, резервные копии и экспорт
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleExportAll}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-900 hover:bg-neutral-800 border border-neutral-800 text-neutral-200 text-xs font-medium transition-colors"
            >
              <Download className="w-3.5 h-3.5 text-indigo-400" />
              Экспорт всех конспектов (.json)
            </button>
          </div>
        </div>

        {statusMessage && (
          <div className={`p-3.5 rounded-xl border text-xs flex items-center gap-2 ${
            statusMessage.isError 
              ? 'bg-rose-950/80 border-rose-800 text-rose-300' 
              : 'bg-indigo-950/80 border-indigo-800 text-indigo-200'
          }`}>
            {statusMessage.isError ? <AlertCircle className="w-4 h-4 shrink-0" /> : <CheckCircle2 className="w-4 h-4 shrink-0" />}
            <span>{statusMessage.text}</span>
          </div>
        )}

        {cleanedSuccess && (
          <div className="p-3.5 rounded-xl bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>Аудиофайлы очищены. Освобождено дисковое пространство. Все конспекты сохранены.</span>
          </div>
        )}

        {/* Disk Space Overview Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="p-4 rounded-xl bg-neutral-900 border border-neutral-800">
            <div className="flex items-center gap-2 text-neutral-400 text-xs mb-1">
              <HardDrive className="w-3.5 h-3.5 text-indigo-400" />
              <span>Общий объем данных</span>
            </div>
            <div className="text-2xl font-bold font-mono text-white">
              {totalSizeMb} МБ
            </div>
            <div className="text-[11px] text-neutral-500 mt-0.5">Всего файлов на диске</div>
          </div>

          <div className="p-4 rounded-xl bg-neutral-900 border border-neutral-800">
            <div className="flex items-center gap-2 text-neutral-400 text-xs mb-1">
              <FileAudio className="w-3.5 h-3.5 text-amber-400" />
              <span>Аудиозаписи лекций</span>
            </div>
            <div className="text-2xl font-bold font-mono text-amber-400">
              {audioSizeMb} МБ
            </div>
            <div className="text-[11px] text-neutral-500 mt-0.5">{audioCount} аудиофайлов</div>
          </div>

          <div className="p-4 rounded-xl bg-neutral-900 border border-neutral-800">
            <div className="flex items-center gap-2 text-neutral-400 text-xs mb-1">
              <FileText className="w-3.5 h-3.5 text-emerald-400" />
              <span>Текстовые конспекты</span>
            </div>
            <div className="text-2xl font-bold font-mono text-emerald-400">
              {textSizeMb} МБ
            </div>
            <div className="text-[11px] text-neutral-500 mt-0.5">{lectures.length} конспектов в базе</div>
          </div>
        </div>

        {/* Local Folder Location */}
        <div className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Folder className="w-4 h-4 text-indigo-400" />
              <h2 className="text-sm font-bold text-white">
                Папка сохранения на компьютере
              </h2>
            </div>
          </div>

          <p className="text-xs text-neutral-400">
            Все файлы, расшифровки и конспекты сохраняются в вашей домашней директории:
          </p>

          <div className="p-3 rounded-lg bg-neutral-950 border border-neutral-800 font-mono text-xs text-neutral-300 flex items-center justify-between">
            <span className="truncate">~/Документы/LecturaAI/Конспекты/</span>
            <span className="text-[11px] text-neutral-500 font-sans">Локальная папка</span>
          </div>
        </div>

        {/* Storage Optimization Actions */}
        <div className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-4">
          <h2 className="text-sm font-bold text-white">
            Оптимизация и резервное копирование
          </h2>

          <div className="divide-y divide-neutral-800">
            
            {/* Action 1: Clear audio files */}
            <div className="py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold text-neutral-200">
                  Удалить аудиозаписи (оставив конспекты)
                </div>
                <div className="text-[11px] text-neutral-400 mt-0.5">
                  Если на диске мало места, можно безопасно стереть тяжелые аудиофайлы. Текст конспекта и формулы не пострадают.
                </div>
              </div>

              <button
                onClick={() => setIsConfirmingClear(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-950 hover:bg-neutral-800 border border-neutral-800 text-rose-400 hover:text-rose-300 text-xs font-medium transition-colors shrink-0 self-start sm:self-center"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Очистить аудио ({audioSizeMb} МБ)
              </button>
            </div>

            {/* Action 2: Import backup */}
            <div className="py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold text-neutral-200">
                  Восстановить конспекты из файла резервной копии
                </div>
                <div className="text-[11px] text-neutral-400 mt-0.5">
                  Загрузить ранее экспортированный файл .json со всеми лекциями и дедлайнами
                </div>
              </div>

              <div>
                <input
                  type="file"
                  id="backup-import"
                  accept=".json"
                  onChange={handleImportFile}
                  className="hidden"
                />
                <label
                  htmlFor="backup-import"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-xs font-medium cursor-pointer transition-colors"
                >
                  <Upload className="w-3.5 h-3.5 text-indigo-400" />
                  Выбрать файл .json
                </label>
              </div>
            </div>

          </div>
        </div>

        {/* Confirmation Modal for Clearing Audio */}
        {isConfirmingClear && (
          <div 
            className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => setIsConfirmingClear(false)}
          >
            <div 
              className="bg-neutral-900 border border-neutral-800 rounded-2xl p-6 max-w-sm w-full space-y-4 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-amber-950/60 border border-amber-800/60 flex items-center justify-center text-amber-400 shrink-0">
                  <Trash2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Очистить аудиофайлы?</h3>
                  <p className="text-xs text-neutral-400 mt-0.5">
                    Будет освобождено ~{audioSizeMb} МБ
                  </p>
                </div>
              </div>

              <p className="text-xs text-neutral-300 leading-relaxed">
                Текстовые конспекты, формулы и дедлайны останутся нетронутыми. Будут удалены только исходные аудиозаписи.
              </p>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsConfirmingClear(false)}
                  className="px-3.5 py-2 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-300 font-medium transition-colors"
                >
                  Отмена
                </button>
                <button
                  type="button"
                  onClick={executeClearAudio}
                  className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-xs text-white font-medium transition-colors shadow-sm"
                >
                  Очистить
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};
