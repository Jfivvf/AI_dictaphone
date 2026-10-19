import React, { useState } from 'react';
import { 
  Search, 
  Trash2, 
  Calendar, 
  Clock, 
  CheckSquare, 
  FileCode, 
  BookOpen, 
  PlusCircle,
  Upload,
  AlertTriangle
} from 'lucide-react';
import { Lecture } from '../types';

interface LectureHistoryProps {
  lectures: Lecture[];
  activeLectureId: string | null;
  onSelectLecture: (lecture: Lecture) => void;
  onDeleteLecture: (lectureId: string) => void;
  onNavigateToRecorder: () => void;
  onTriggerPdfUpload: () => void;
}

export const LectureHistory: React.FC<LectureHistoryProps> = ({
  lectures,
  activeLectureId,
  onSelectLecture,
  onDeleteLecture,
  onNavigateToRecorder,
  onTriggerPdfUpload,
}) => {
  const [search, setSearch] = useState('');
  const [selectedSubject, setSelectedSubject] = useState<string>('all');
  const [onlyWithTasks, setOnlyWithTasks] = useState(false);
  const [deletingLecture, setDeletingLecture] = useState<Lecture | null>(null);

  // Extract unique subjects
  const subjects = ['all', ...Array.from(new Set(lectures.map(l => l.subject)))];

  // Filter lectures
  const filteredLectures = lectures.filter(l => {
    const matchesSearch = 
      l.title.toLowerCase().includes(search.toLowerCase()) ||
      l.lecturer.toLowerCase().includes(search.toLowerCase()) ||
      l.tags.some(t => t.toLowerCase().includes(search.toLowerCase()));

    const matchesSubject = selectedSubject === 'all' || l.subject === selectedSubject;
    const matchesTasks = !onlyWithTasks || l.actionItems.some(item => !item.completed);

    return matchesSearch && matchesSubject && matchesTasks;
  });

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 bg-neutral-950">
      <div className="max-w-4xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-neutral-800">
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              Мои проекты
            </h1>
            <p className="text-xs text-neutral-400 mt-1">
              Архив всех сохраненных записей и конспектов ({lectures.length})
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onTriggerPdfUpload}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-neutral-900 hover:bg-neutral-800 border border-neutral-700 text-neutral-200 text-xs font-medium transition-colors"
            >
              <Upload className="w-4 h-4 text-indigo-400" />
              Импорт PDF
            </button>

            <button
              onClick={onNavigateToRecorder}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors shadow-sm"
            >
              <PlusCircle className="w-4 h-4" />
              Новая запись
            </button>
          </div>
        </div>

        {/* Search & Filter Controls */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 text-neutral-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по названию, преподавателю или тегам..."
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-neutral-900 border border-neutral-800 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div className="flex items-center gap-2 overflow-x-auto">
            <div className="flex items-center gap-1 p-1 rounded-lg bg-neutral-900 border border-neutral-800">
              {subjects.map((sub) => (
                <button
                  key={sub}
                  onClick={() => setSelectedSubject(sub)}
                  className={`px-2.5 py-1 text-xs font-medium rounded-md whitespace-nowrap transition-colors ${
                    selectedSubject === sub
                      ? 'bg-neutral-800 text-white'
                      : 'text-neutral-400 hover:text-neutral-200'
                  }`}
                >
                  {sub === 'all' ? 'Все предметы' : sub}
                </button>
              ))}
            </div>

            <button
              onClick={() => setOnlyWithTasks(!onlyWithTasks)}
              className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border transition-colors whitespace-nowrap ${
                onlyWithTasks
                  ? 'bg-emerald-950/60 border-emerald-700/60 text-emerald-300'
                  : 'bg-neutral-900 border-neutral-800 text-neutral-400 hover:text-neutral-200'
              }`}
            >
              <CheckSquare className="w-3.5 h-3.5" />
              С дедлайнами
            </button>
          </div>
        </div>

        {/* Lectures List */}
        {filteredLectures.length === 0 ? (
          <div className="p-12 text-center rounded-xl bg-neutral-900 border border-neutral-800 space-y-3">
            <BookOpen className="w-10 h-10 mx-auto text-neutral-600" />
            <h3 className="text-sm font-semibold text-white">Лекции не найдены</h3>
            <p className="text-xs text-neutral-400 max-w-sm mx-auto">
              Запишите лекцию с микрофона или импортируйте PDF-конспект.
            </p>
            <div className="pt-2 flex justify-center gap-2">
              <button
                onClick={onTriggerPdfUpload}
                className="px-3.5 py-2 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-200 font-medium transition-colors"
              >
                Импортировать PDF
              </button>
              <button
                onClick={onNavigateToRecorder}
                className="px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs text-white font-medium transition-colors"
              >
                Записать с микрофона
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {filteredLectures.map((lec) => {
              const isSelected = lec.id === activeLectureId;
              const pendingTasks = lec.actionItems.filter(t => !t.completed).length;

              return (
                <div
                  key={lec.id}
                  onClick={() => onSelectLecture(lec)}
                  className={`p-4 md:p-5 rounded-xl border transition-all cursor-pointer select-none group relative ${
                    isSelected
                      ? 'bg-neutral-900 border-indigo-500/80 shadow-md shadow-indigo-950/20'
                      : 'bg-neutral-900/80 border-neutral-800 hover:border-neutral-700 hover:bg-neutral-900'
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="space-y-1.5 flex-1 min-w-0">
                      
                      {/* Meta header */}
                      <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-400">
                        <span className="font-semibold text-indigo-400">{lec.subject}</span>
                        <span aria-hidden="true">·</span>
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3 text-neutral-500" />
                          {lec.date}
                        </span>
                        <span aria-hidden="true">·</span>
                        <span className="flex items-center gap-1 font-mono">
                          <Clock className="w-3 h-3 text-neutral-500" />
                          {Math.max(1, Math.round(lec.durationSeconds / 60))} мин
                        </span>
                      </div>

                      {/* Title */}
                      <h2 className="text-sm md:text-base font-bold text-white group-hover:text-indigo-200 transition-colors">
                        {lec.title}
                      </h2>

                      {/* Lecturer */}
                      <div className="text-xs text-neutral-400">
                        {lec.lecturer}
                      </div>

                      {/* Tags */}
                      {lec.tags && lec.tags.length > 0 && (
                        <div className="flex flex-wrap items-center gap-1.5 pt-1">
                          {lec.tags.map((tag, tIdx) => (
                            <span
                              key={tIdx}
                              className="px-2 py-0.5 rounded bg-neutral-950 border border-neutral-800 text-[10px] text-neutral-400"
                            >
                              #{tag}
                            </span>
                          ))}
                        </div>
                      )}

                    </div>

                    {/* Stats & Actions */}
                    <div className="flex sm:flex-col items-center sm:items-end justify-between gap-3 shrink-0">
                      <div className="flex items-center gap-3 text-xs">
                        {pendingTasks > 0 ? (
                          <span className="flex items-center gap-1 text-emerald-400 font-mono text-[11px] px-2 py-1 rounded bg-emerald-950/60 border border-emerald-800/40">
                            <CheckSquare className="w-3.5 h-3.5" />
                            {pendingTasks} дедлайн(ов)
                          </span>
                        ) : (
                          <span className="text-[11px] text-neutral-500 font-mono">
                            Все задачи закрыты
                          </span>
                        )}

                        {lec.latexFormulas && lec.latexFormulas.length > 0 && (
                          <span className="flex items-center gap-1 text-amber-400 font-mono text-[11px] px-2 py-1 rounded bg-amber-950/60 border border-amber-800/40">
                            <FileCode className="w-3.5 h-3.5" />
                            {lec.latexFormulas.length} формул
                          </span>
                        )}
                      </div>

                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeletingLecture(lec);
                        }}
                        className="p-2 rounded-lg text-neutral-400 hover:text-rose-400 hover:bg-neutral-800 transition-colors"
                        title="Удалить запись"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* In-App Delete Confirmation Modal (Replaces flaky window.confirm) */}
        {deletingLecture && (
          <div 
            className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => setDeletingLecture(null)}
          >
            <div 
              className="bg-neutral-900 border border-neutral-800 rounded-2xl p-6 max-w-sm w-full space-y-4 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-rose-950/60 border border-rose-800/60 flex items-center justify-center text-rose-400 shrink-0">
                  <Trash2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Удалить лекцию?</h3>
                  <p className="text-xs text-neutral-400 mt-0.5 truncate max-w-[200px]">
                    «{deletingLecture.title}»
                  </p>
                </div>
              </div>

              <p className="text-xs text-neutral-300 leading-relaxed">
                Запись будет удалена безвозвратно. Текст конспекта и все связанные с ней задачи будут стерты из приложения.
              </p>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setDeletingLecture(null)}
                  className="px-3.5 py-2 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-300 font-medium transition-colors"
                >
                  Отмена
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const idToDelete = deletingLecture.id;
                    setDeletingLecture(null);
                    onDeleteLecture(idToDelete);
                  }}
                  className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-xs text-white font-medium transition-colors shadow-sm"
                >
                  Удалить
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};
