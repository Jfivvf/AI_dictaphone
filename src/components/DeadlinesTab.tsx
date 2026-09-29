import React, { useState } from 'react';
import { 
  Calendar, 
  CheckSquare, 
  Clock, 
  Filter, 
  Plus, 
  AlertCircle, 
  BookOpen, 
  Check, 
  ChevronRight,
  Sparkles
} from 'lucide-react';
import { Lecture, ActionItem } from '../types';

interface DeadlinesTabProps {
  lectures: Lecture[];
  onToggleTask: (lectureId: string, taskId: string) => void;
  onOpenLecture: (lectureId: string) => void;
  onAddNewTask: (task: ActionItem, lectureId?: string) => void;
}

export const DeadlinesTab: React.FC<DeadlinesTabProps> = ({
  lectures,
  onToggleTask,
  onOpenLecture,
  onAddNewTask,
}) => {
  const [filterSubject, setFilterSubject] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<'all' | 'pending' | 'completed'>('pending');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newTaskText, setNewTaskText] = useState('');
  const [newTaskDeadline, setNewTaskDeadline] = useState('');
  const [newTaskSubject, setNewTaskSubject] = useState(lectures[0]?.subject || 'Общее');
  const [newTaskPriority, setNewTaskPriority] = useState<'high' | 'medium' | 'low'>('high');

  // Collect all tasks across all lectures with their lecture metadata
  const allTasksWithLecture = lectures.flatMap(lec => 
    lec.actionItems.map(item => ({
      ...item,
      lectureId: lec.id,
      lectureTitle: lec.title,
      lectureSubject: lec.subject
    }))
  );

  // Extract unique subjects
  const subjects = ['all', ...Array.from(new Set(allTasksWithLecture.map(t => t.lectureSubject)))];

  // Filter tasks
  const filteredTasks = allTasksWithLecture.filter(item => {
    const matchesSubject = filterSubject === 'all' || item.lectureSubject === filterSubject;
    const matchesStatus = 
      filterStatus === 'all' ? true :
      filterStatus === 'pending' ? !item.completed : item.completed;
    return matchesSubject && matchesStatus;
  });

  const pendingCount = allTasksWithLecture.filter(t => !t.completed).length;
  const completedCount = allTasksWithLecture.filter(t => t.completed).length;

  const handleCreateTask = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTaskText.trim()) return;

    const targetLecture = lectures.find(l => l.subject === newTaskSubject) || lectures[0];
    const newTask: ActionItem = {
      id: `custom-task-${Date.now()}`,
      task: newTaskText,
      deadline: newTaskDeadline || 'В ближайшее время',
      dateISO: new Date().toISOString().split('T')[0],
      type: 'homework',
      completed: false,
      priority: newTaskPriority
    };

    onAddNewTask(newTask, targetLecture?.id);
    setNewTaskText('');
    setNewTaskDeadline('');
    setIsAddModalOpen(false);
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 bg-neutral-950">
      <div className="max-w-4xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-neutral-800">
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              Задачи и дедлайны
            </h1>
            <p className="text-xs text-neutral-400 mt-1">
              Все домашние задания, даты коллоквиумов и сдачи работ, извлеченные из записей
            </p>
          </div>

          <button
            onClick={() => setIsAddModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors shadow-sm self-start sm:self-center"
          >
            <Plus className="w-4 h-4" />
            Добавить задачу
          </button>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <div className="p-4 rounded-xl bg-neutral-900 border border-neutral-800">
            <div className="text-xs text-neutral-400 mb-1">Предстоит сдать</div>
            <div className="text-2xl font-bold font-mono text-amber-400">
              {pendingCount}
            </div>
            <div className="text-[11px] text-neutral-500 mt-0.5">Активные дедлайны</div>
          </div>

          <div className="p-4 rounded-xl bg-neutral-900 border border-neutral-800">
            <div className="text-xs text-neutral-400 mb-1">Выполнено</div>
            <div className="text-2xl font-bold font-mono text-emerald-400">
              {completedCount}
            </div>
            <div className="text-[11px] text-neutral-500 mt-0.5">Сданные задания</div>
          </div>

          <div className="p-4 rounded-xl bg-neutral-900 border border-neutral-800 col-span-2 sm:col-span-1">
            <div className="text-xs text-neutral-400 mb-1">Всего найдено в лекциях</div>
            <div className="text-2xl font-bold font-mono text-white">
              {allTasksWithLecture.length}
            </div>
            <div className="text-[11px] text-neutral-500 mt-0.5">Задачи из аудиозаписей</div>
          </div>
        </div>

        {/* Filter Controls */}
        <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
          {/* Status Tabs */}
          <div className="flex items-center gap-1 p-1 bg-neutral-900 border border-neutral-800 rounded-lg">
            <button
              onClick={() => setFilterStatus('pending')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                filterStatus === 'pending'
                  ? 'bg-neutral-800 text-white'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              Активные ({pendingCount})
            </button>
            <button
              onClick={() => setFilterStatus('completed')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                filterStatus === 'completed'
                  ? 'bg-neutral-800 text-white'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              Выполненные ({completedCount})
            </button>
            <button
              onClick={() => setFilterStatus('all')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                filterStatus === 'all'
                  ? 'bg-neutral-800 text-white'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              Все задачи
            </button>
          </div>

          {/* Subject Filter Dropdown / Buttons */}
          <div className="flex items-center gap-1 overflow-x-auto">
            <span className="text-xs text-neutral-500 mr-1 hidden sm:inline">Предмет:</span>
            {subjects.map(sub => (
              <button
                key={sub}
                onClick={() => setFilterSubject(sub)}
                className={`px-2.5 py-1 text-xs font-medium rounded-lg whitespace-nowrap transition-colors ${
                  filterSubject === sub
                    ? 'bg-indigo-950 text-indigo-300 border border-indigo-800'
                    : 'bg-neutral-900 text-neutral-400 border border-neutral-800 hover:text-neutral-200'
                }`}
              >
                {sub === 'all' ? 'Все' : sub}
              </button>
            ))}
          </div>
        </div>

        {/* Task List */}
        {filteredTasks.length === 0 ? (
          <div className="p-12 text-center rounded-xl bg-neutral-900 border border-neutral-800">
            <CheckSquare className="w-10 h-10 mx-auto text-neutral-600 mb-3" />
            <h3 className="text-sm font-semibold text-white">Нет задач по выбранным фильтрам</h3>
            <p className="text-xs text-neutral-400 mt-1 max-w-sm mx-auto">
              Запишите лекцию с домашним заданием или добавьте новую задачу вручную.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredTasks.map(item => (
              <div
                key={item.id}
                className={`p-4 rounded-xl border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                  item.completed
                    ? 'bg-neutral-900/40 border-neutral-800/60 opacity-60'
                    : 'bg-neutral-900 border-neutral-800 hover:border-neutral-700'
                }`}
              >
                <div className="flex items-start gap-3 flex-1 min-w-0">
                  <button
                    onClick={() => onToggleTask(item.lectureId, item.id)}
                    className={`mt-0.5 w-5 h-5 rounded flex items-center justify-center transition-colors shrink-0 ${
                      item.completed 
                        ? 'bg-emerald-600 text-white' 
                        : 'border border-neutral-600 hover:border-indigo-400'
                    }`}
                    title={item.completed ? 'Отметить как невыполненное' : 'Отметить как сделанное'}
                  >
                    {item.completed && <Check className="w-3.5 h-3.5" />}
                  </button>

                  <div className="flex-1 min-w-0">
                    <div className={`text-xs md:text-sm font-medium ${
                      item.completed ? 'line-through text-neutral-500' : 'text-neutral-100'
                    }`}>
                      {item.task}
                    </div>

                    <div className="flex flex-wrap items-center gap-2 mt-1.5 text-[11px] text-neutral-400">
                      <span className="font-semibold text-indigo-400">
                        {item.lectureSubject}
                      </span>
                      <span aria-hidden="true">·</span>
                      <span className="flex items-center gap-1 font-mono text-amber-400 font-medium">
                        <Calendar className="w-3 h-3 text-amber-500" />
                        Срок: {item.deadline}
                      </span>
                      <span aria-hidden="true">·</span>
                      <span className={item.priority === 'high' ? 'text-rose-400 font-medium' : 'text-neutral-400'}>
                        {item.priority === 'high' ? 'Высокий приоритет' : 'Обычный'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Link to source lecture */}
                <button
                  onClick={() => onOpenLecture(item.lectureId)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-950 hover:bg-neutral-800 border border-neutral-800 text-[11px] text-neutral-300 hover:text-white transition-colors shrink-0 self-end sm:self-center"
                  title="Открыть конспект этой лекции"
                >
                  <BookOpen className="w-3.5 h-3.5 text-neutral-400" />
                  <span className="truncate max-w-[150px]">{item.lectureTitle}</span>
                  <ChevronRight className="w-3 h-3 text-neutral-500" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Modal for manual task addition */}
        {isAddModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6 w-full max-w-md space-y-4 shadow-xl">
              <h3 className="text-sm font-bold text-white">Добавить задачу или дедлайн</h3>
              
              <form onSubmit={handleCreateTask} className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-neutral-300 mb-1">
                    Что нужно сделать:
                  </label>
                  <input
                    type="text"
                    value={newTaskText}
                    onChange={(e) => setNewTaskText(e.target.value)}
                    placeholder="Например: Сдать типовой расчет № 2"
                    required
                    className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-neutral-300 mb-1">
                    Срок / Дедлайн:
                  </label>
                  <input
                    type="text"
                    value={newTaskDeadline}
                    onChange={(e) => setNewTaskDeadline(e.target.value)}
                    placeholder="Например: Пятница, 18:00"
                    className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-neutral-300 mb-1">
                      Предмет:
                    </label>
                    <select
                      value={newTaskSubject}
                      onChange={(e) => setNewTaskSubject(e.target.value)}
                      className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                    >
                      {subjects.filter(s => s !== 'all').map(s => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-neutral-300 mb-1">
                      Приоритет:
                    </label>
                    <select
                      value={newTaskPriority}
                      onChange={(e) => setNewTaskPriority(e.target.value as unknown as 'high')}
                      className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                    >
                      <option value="high">Высокий</option>
                      <option value="medium">Обычный</option>
                      <option value="low">Низкий</option>
                    </select>
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-3">
                  <button
                    type="button"
                    onClick={() => setIsAddModalOpen(false)}
                    className="px-3 py-1.5 rounded-lg text-xs text-neutral-400 hover:text-white"
                  >
                    Отмена
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
                  >
                    Создать
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};
