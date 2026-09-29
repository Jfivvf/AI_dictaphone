import React, { useState } from 'react';
import { 
  User, 
  GraduationCap, 
  Clock, 
  CheckSquare, 
  FileCode, 
  HardDrive, 
  ShieldCheck, 
  Save, 
  Download, 
  Trash2, 
  CheckCircle2,
  Lock
} from 'lucide-react';
import { StudentProfile, Lecture } from '../types';

interface StudentAccountTabProps {
  profile: StudentProfile;
  lectures: Lecture[];
  onUpdateProfile: (updated: StudentProfile) => void;
}

export const StudentAccountTab: React.FC<StudentAccountTabProps> = ({
  profile,
  lectures,
  onUpdateProfile,
}) => {
  const [formData, setFormData] = useState<StudentProfile>(profile);
  const [isSaved, setIsSaved] = useState(false);
  const [isDbEncrypted, setIsDbEncrypted] = useState(true);

  // Compute academic metrics
  const totalDurationSeconds = lectures.reduce((acc, l) => acc + l.durationSeconds, 0);
  const totalHours = (totalDurationSeconds / 3600).toFixed(1);
  const totalTasks = lectures.reduce((acc, l) => acc + l.actionItems.length, 0);
  const completedTasks = lectures.reduce((acc, l) => acc + l.actionItems.filter(t => t.completed).length, 0);
  const totalFormulas = lectures.reduce((acc, l) => acc + l.latexFormulas.length, 0);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    onUpdateProfile(formData);
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  // Export full JSON backup
  const handleExportBackup = () => {
    const backupData = {
      profile: formData,
      exportedAt: new Date().toISOString(),
      lecturesCount: lectures.length,
      lectures: lectures
    };

    const blob = new Blob([JSON.stringify(backupData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `lectura_backup_${formData.name.replace(/\s+/g, '_')}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 bg-neutral-950">
      <div className="max-w-4xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-neutral-800">
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              Профиль студента и хранилище данных
            </h1>
            <p className="text-xs text-neutral-400 mt-1">
              Локальный профиль, академическая статистика и резервные копии
            </p>
          </div>

          <button
            onClick={handleExportBackup}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-900 hover:bg-neutral-800 border border-neutral-800 text-neutral-200 text-xs font-medium transition-colors"
          >
            <Download className="w-3.5 h-3.5 text-indigo-400" />
            Экспорт резервной копии (.json)
          </button>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="p-4 rounded-xl bg-neutral-900 border border-neutral-800">
            <div className="flex items-center gap-2 text-neutral-400 text-xs mb-1">
              <Clock className="w-3.5 h-3.5 text-indigo-400" />
              <span>Записано лекций</span>
            </div>
            <div className="text-xl font-bold font-mono text-white">
              {totalHours} ч
            </div>
            <div className="text-[10px] text-neutral-500 mt-0.5">{lectures.length} пар и семинаров</div>
          </div>

          <div className="p-4 rounded-xl bg-neutral-900 border border-neutral-800">
            <div className="flex items-center gap-2 text-neutral-400 text-xs mb-1">
              <CheckSquare className="w-3.5 h-3.5 text-emerald-400" />
              <span>Задачи и дедлайны</span>
            </div>
            <div className="text-xl font-bold font-mono text-emerald-400">
              {completedTasks} / {totalTasks}
            </div>
            <div className="text-[10px] text-neutral-500 mt-0.5">
              {totalTasks > 0 ? `${Math.round((completedTasks / totalTasks) * 100)}% закрыто` : 'Нет задач'}
            </div>
          </div>

          <div className="p-4 rounded-xl bg-neutral-900 border border-neutral-800">
            <div className="flex items-center gap-2 text-neutral-400 text-xs mb-1">
              <FileCode className="w-3.5 h-3.5 text-amber-400" />
              <span>Формулы в конспектах</span>
            </div>
            <div className="text-xl font-bold font-mono text-amber-400">
              {totalFormulas}
            </div>
            <div className="text-[10px] text-neutral-500 mt-0.5">LaTeX уравнений</div>
          </div>

          <div className="p-4 rounded-xl bg-neutral-900 border border-neutral-800">
            <div className="flex items-center gap-2 text-neutral-400 text-xs mb-1">
              <HardDrive className="w-3.5 h-3.5 text-indigo-400" />
              <span>Локальное место</span>
            </div>
            <div className="text-xl font-bold font-mono text-white">
              24.2 МБ
            </div>
            <div className="text-[10px] text-neutral-500 mt-0.5">SQLite + Аудиокэш</div>
          </div>
        </div>

        {/* Student Information Form */}
        <div className="p-6 rounded-xl bg-neutral-900 border border-neutral-800 space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <GraduationCap className="w-4 h-4 text-indigo-400" />
              <h2 className="text-sm font-bold text-white">
                Академические данные
              </h2>
            </div>

            {isSaved && (
              <span className="text-xs text-emerald-400 flex items-center gap-1 font-medium">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Сохранено
              </span>
            )}
          </div>

          <form onSubmit={handleSave} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">
                  ФИО студента:
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">
                  Email (для локального экспорта):
                </label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">
                  Университет / ВУЗ:
                </label>
                <input
                  type="text"
                  value={formData.university}
                  onChange={(e) => setFormData({ ...formData, university: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                  placeholder="МГУ / МФТИ / СПбГУ / ВШЭ"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">
                  Факультет / Институт:
                </label>
                <input
                  type="text"
                  value={formData.faculty}
                  onChange={(e) => setFormData({ ...formData, faculty: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                  placeholder="Механико-математический / ФИВТ"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">
                  Номер учебной группы:
                </label>
                <input
                  type="text"
                  value={formData.group}
                  onChange={(e) => setFormData({ ...formData, group: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                  placeholder="204-Б"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">
                  Текущий семестр:
                </label>
                <select
                  value={formData.semester}
                  onChange={(e) => setFormData({ ...formData, semester: Number(e.target.value) })}
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                >
                  {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(s => (
                    <option key={s} value={s}>{s}-й семестр</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="submit"
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors"
              >
                <Save className="w-3.5 h-3.5" />
                Сохранить профиль
              </button>
            </div>
          </form>
        </div>

        {/* Security & Local Data Management */}
        <div className="p-6 rounded-xl bg-neutral-900 border border-neutral-800 space-y-4">
          <div className="flex items-center gap-2">
            <Lock className="w-4 h-4 text-emerald-400" />
            <h2 className="text-sm font-bold text-white">
              Конфиденциальность и шифрование базы SQLite
            </h2>
          </div>

          <div className="flex items-center justify-between p-3.5 rounded-lg bg-neutral-950 border border-neutral-800">
            <div>
              <div className="text-xs font-semibold text-neutral-200">
                Шифрование базы конспектов SQLCipher (AES-256)
              </div>
              <div className="text-[11px] text-neutral-400 mt-0.5">
                Защищает файлы базы данных от чтения посторонними при утере ноутбука
              </div>
            </div>

            <button
              onClick={() => setIsDbEncrypted(!isDbEncrypted)}
              className={`px-3 py-1 rounded text-xs font-mono font-medium transition-colors ${
                isDbEncrypted
                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                  : 'bg-neutral-800 text-neutral-400'
              }`}
            >
              {isDbEncrypted ? 'Включено (AES-256)' : 'Выключено'}
            </button>
          </div>

          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2 text-xs">
            <span className="text-neutral-400">
              Очистка временных аудиокэшей (сохраняет текст, но удаляет тяжелые WAV-исходники):
            </span>

            <button
              onClick={() => alert('Временный аудиокэш очищен. Освобождено 18.4 МБ дискового пространства.')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-950 hover:bg-neutral-850 border border-neutral-800 text-neutral-300 hover:text-white transition-colors shrink-0"
            >
              <Trash2 className="w-3.5 h-3.5 text-neutral-500" />
              Очистить аудиокэш
            </button>
          </div>
        </div>

      </div>
    </div>
  );
};
