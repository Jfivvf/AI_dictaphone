import React, { useState, useEffect, useRef } from 'react';
import {
  User,
  Building2,
  Save,
  CheckCircle2,
  BookOpen,
  LogOut,
  LogIn,
  Upload
} from 'lucide-react';
import { StudentProfile } from '../types';
import { AxolotlLogo, setCustomAxaiLogo } from './AxolotlLogo';

interface StudentProfileTabProps {
  profile: StudentProfile;
  onUpdateProfile: (updated: StudentProfile) => void;
  isAuthenticated?: boolean;
  userEmail?: string | null;
  userUid?: string | null;
  onSignOut?: () => void;
  onRequireSignIn?: () => void;
}

export const StudentProfileTab: React.FC<StudentProfileTabProps> = ({
  profile,
  onUpdateProfile,
  isAuthenticated,
  onSignOut,
  onRequireSignIn,
}) => {
  const [formData, setFormData] = useState<StudentProfile>(profile);
  const [isSaved, setIsSaved] = useState(false);
  const avatarInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setFormData(profile);
  }, [profile]);

  const handleAvatarUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        setCustomAxaiLogo(reader.result);
      }
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    const sanitized: StudentProfile = {
      ...formData,
      name: formData.name.trim().slice(0, 150) || 'Студент',
      email: formData.email.trim().slice(0, 254) || 'student@university.ru',
      university: formData.university.trim().slice(0, 200) || 'Университет',
      faculty: formData.faculty.trim().slice(0, 200) || 'Факультет',
      group: formData.group.trim().slice(0, 50) || '101-А',
      semester: Math.min(12, Math.max(1, Number(formData.semester) || 1)),
    };
    onUpdateProfile(sanitized);
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 bg-neutral-950">
      <div className="max-w-3xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-neutral-800">
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              Профиль студента
            </h1>
            <p className="text-xs text-neutral-400 mt-1">
              Управление личными и учебными данными
            </p>
          </div>

          <div className="flex items-center gap-2">
            {isSaved && (
              <span className="text-xs text-emerald-400 flex items-center gap-1 font-medium bg-emerald-950/60 px-3 py-1.5 rounded-lg border border-emerald-800/40">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Сохранено
              </span>
            )}

            {isAuthenticated ? (
              <button
                type="button"
                onClick={onSignOut}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-rose-950/60 hover:bg-rose-900/80 border border-rose-800/70 text-rose-200 text-xs font-medium transition-colors"
              >
                <LogOut className="w-3.5 h-3.5 text-rose-400" />
                Выйти из аккаунта
              </button>
            ) : (
              <button
                type="button"
                onClick={onRequireSignIn}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors"
              >
                <LogIn className="w-3.5 h-3.5" />
                Войти в аккаунт
              </button>
            )}
          </div>
        </div>

        {/* Student ID Card Preview */}
        <div className="p-5 rounded-2xl bg-gradient-to-br from-neutral-900 to-neutral-950 border border-neutral-800 shadow-lg relative overflow-hidden">
          <div className="absolute right-0 top-0 translate-x-4 -translate-y-4 w-40 h-40 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
          
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 min-w-0 flex-1">
              <AxolotlLogo className="w-16 h-16 rounded-2xl shadow-md" allowUploadOnClick={true} />

              <div className="space-y-1 min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h2 className="text-base md:text-lg font-bold text-white truncate">
                    {formData.name || 'Имя не указано'}
                  </h2>
                  <span className="px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800/60 text-[10px] font-mono">
                    {formData.group || 'Группа'}
                  </span>
                </div>

                <div className="text-xs text-neutral-400 flex items-center gap-1.5 truncate">
                  <Building2 className="w-3.5 h-3.5 text-neutral-500 shrink-0" />
                  <span className="truncate">{formData.university || 'Университет не указан'}</span>
                </div>

                <div className="text-xs text-neutral-400 flex items-center gap-1.5 truncate">
                  <BookOpen className="w-3.5 h-3.5 text-neutral-500 shrink-0" />
                  <span className="truncate">{formData.faculty || 'Факультет'} · {formData.semester}-й семестр</span>
                </div>
              </div>
            </div>

            <div>
              <input
                ref={avatarInputRef}
                type="file"
                accept="image/*"
                onChange={handleAvatarUpload}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => avatarInputRef.current?.click()}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 text-neutral-200 text-xs font-medium transition-colors"
              >
                <Upload className="w-3.5 h-3.5 text-indigo-400" />
                <span>Загрузить свое фото / логотип</span>
              </button>
            </div>
          </div>
        </div>

        {/* Profile Edit Form */}
        <div className="p-6 rounded-xl bg-neutral-900 border border-neutral-800 space-y-4">
          <div className="flex items-center gap-2 pb-2 border-b border-neutral-800">
            <User className="w-4 h-4 text-indigo-400" />
            <h3 className="text-sm font-bold text-white">
              Личные данные и место учебы
            </h3>
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
                  maxLength={150}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="Иван Иванов"
                  required
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">
                  Электронная почта:
                </label>
                <input
                  type="email"
                  value={formData.email}
                  maxLength={254}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="student@university.ru"
                  required
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">
                  ВУЗ / Университет:
                </label>
                <input
                  type="text"
                  value={formData.university}
                  maxLength={200}
                  onChange={(e) => setFormData({ ...formData, university: e.target.value })}
                  placeholder="Например: МГУ им. М. В. Ломоносова"
                  required
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">
                  Факультет / Институт:
                </label>
                <input
                  type="text"
                  value={formData.faculty}
                  maxLength={200}
                  onChange={(e) => setFormData({ ...formData, faculty: e.target.value })}
                  placeholder="Механико-математический факультет"
                  required
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">
                  Академическая группа:
                </label>
                <input
                  type="text"
                  value={formData.group}
                  maxLength={50}
                  onChange={(e) => setFormData({ ...formData, group: e.target.value })}
                  placeholder="204-Б"
                  required
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
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
                  {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(s => (
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

      </div>
    </div>
  );
};
