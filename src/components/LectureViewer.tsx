import React, { useState } from 'react';
import { 
  FileText, 
  CheckSquare, 
  MessageSquare, 
  Download, 
  Printer, 
  Calendar, 
  Clock, 
  User, 
  Search, 
  Edit3, 
  Save, 
  Copy, 
  Check, 
  Bookmark,
  FileCode,
  ArrowLeft,
  Share2
} from 'lucide-react';
import { Lecture, ActionItem } from '../types';
import { LatexRenderer, SingleFormula } from './LatexRenderer';

interface LectureViewerProps {
  lecture: Lecture | null;
  onUpdateLecture: (updated: Lecture) => void;
  onBackToHistory: () => void;
  onNavigateToRecorder: () => void;
}

export const LectureViewer: React.FC<LectureViewerProps> = ({
  lecture,
  onUpdateLecture,
  onBackToHistory,
  onNavigateToRecorder,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'summary' | 'tasks' | 'transcript'>('summary');
  const [searchQuery, setSearchQuery] = useState('');
  const [isEditingMarkdown, setIsEditingMarkdown] = useState(false);
  const [editedMarkdown, setEditedMarkdown] = useState(lecture?.summaryMarkdown || '');

  if (!lecture) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-neutral-950">
        <div className="w-16 h-16 rounded-full bg-neutral-900 border border-neutral-800 flex items-center justify-center text-neutral-500 mb-4">
          <FileText className="w-8 h-8" />
        </div>
        <h2 className="text-lg font-semibold text-white mb-2">
          Выберите лекцию для просмотра
        </h2>
        <p className="text-xs text-neutral-400 max-w-sm mb-6">
          Выберите занятие из архива лекций или запишите новое с микрофона.
        </p>
        <button
          onClick={onBackToHistory}
          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors"
        >
          Перейти в мои лекции
        </button>
      </div>
    );
  }

  // Toggle action item completed status
  const toggleTask = (taskId: string) => {
    const updatedTasks: ActionItem[] = lecture.actionItems.map(item => 
      item.id === taskId ? { ...item, completed: !item.completed } : item
    );
    onUpdateLecture({
      ...lecture,
      actionItems: updatedTasks
    });
  };

  // Save edited markdown
  const handleSaveMarkdown = () => {
    onUpdateLecture({
      ...lecture,
      summaryMarkdown: editedMarkdown
    });
    setIsEditingMarkdown(false);
  };

  // Export as Markdown .md file download
  const handleExportMarkdown = () => {
    let mdContent = `# ${lecture.title}\n`;
    mdContent += `**Предмет:** ${lecture.subject}  \n`;
    mdContent += `**Преподаватель:** ${lecture.lecturer}  \n`;
    mdContent += `**Дата:** ${lecture.date}  \n\n`;
    mdContent += `---\n\n`;
    mdContent += `${lecture.summaryMarkdown}\n\n`;
    if (lecture.actionItems.length > 0) {
      mdContent += `## Задачи и дедлайны\n`;
      lecture.actionItems.forEach(item => {
        mdContent += `- [${item.completed ? 'x' : ' '}] **${item.task}** (Срок: ${item.deadline})\n`;
      });
    }

    const blob = new Blob([mdContent], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${lecture.title.replace(/\s+/g, '_')}_конспект.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // Export as LaTeX .tex file download
  const handleExportLatex = () => {
    let texContent = `\\documentclass[12pt,a4paper]{article}\n`;
    texContent += `\\usepackage[utf8]{inputenc}\n`;
    texContent += `\\usepackage[russian]{babel}\n`;
    texContent += `\\usepackage{amsmath,amssymb,amsfonts}\n`;
    texContent += `\\usepackage{hyperref}\n\n`;
    texContent += `\\title{${lecture.title}}\n`;
    texContent += `\\author{${lecture.lecturer} \\\\ \\small ${lecture.subject}}\n`;
    texContent += `\\date{${lecture.date}}\n\n`;
    texContent += `\\begin{document}\n`;
    texContent += `\\maketitle\n\n`;
    texContent += `\\section*{Конспект лекции}\n`;
    
    if (lecture.latexFormulas.length > 0) {
      texContent += `\\section*{Формулы}\n`;
      lecture.latexFormulas.forEach(f => {
        texContent += `\\subsection*{${f.title}}\n`;
        texContent += `\\begin{equation}\n${f.latex}\n\\end{equation}\n\n`;
      });
    }

    if (lecture.actionItems.length > 0) {
      texContent += `\\section*{Задачи и дедлайны}\n\\begin{itemize}\n`;
      lecture.actionItems.forEach(item => {
        texContent += `\\item \\textbf{${item.task}} --- \\textit{Дедлайн: ${item.deadline}}\n`;
      });
      texContent += `\\end{itemize}\n\n`;
    }

    texContent += `\\end{document}`;

    const blob = new Blob([texContent], { type: 'text/plain;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${lecture.title.replace(/\s+/g, '_')}.tex`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // Export to PDF via browser print
  const handlePrintPDF = () => {
    window.print();
  };

  // Filter transcript segments
  const filteredTranscript = lecture.transcript.filter(seg => 
    seg.text.toLowerCase().includes(searchQuery.toLowerCase()) ||
    seg.speaker.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-neutral-950">
      
      {/* Top Banner / Lecture Header */}
      <div className="p-4 md:px-6 md:py-3.5 bg-neutral-900 border-b border-neutral-800 shrink-0">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          
          <div className="flex items-start gap-3">
            <button
              onClick={onBackToHistory}
              className="p-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-300 transition-colors mt-0.5"
              title="Назад к списку лекций"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>

            <div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-400 mb-1">
                <span className="font-semibold text-indigo-400">{lecture.subject}</span>
                <span aria-hidden="true">·</span>
                <span className="flex items-center gap-1">
                  <User className="w-3 h-3 text-neutral-500" />
                  {lecture.lecturer}
                </span>
                <span aria-hidden="true">·</span>
                <span className="flex items-center gap-1">
                  <Calendar className="w-3 h-3 text-neutral-500" />
                  {lecture.date}
                </span>
                <span aria-hidden="true">·</span>
                <span className="flex items-center gap-1 font-mono">
                  <Clock className="w-3 h-3 text-neutral-500" />
                  {Math.round(lecture.durationSeconds / 60)} мин
                </span>
              </div>

              <h1 className="text-base md:text-lg font-bold text-white tracking-tight">
                {lecture.title}
              </h1>
            </div>
          </div>

          {/* Action Toolbar */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handlePrintPDF}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 text-neutral-200 text-xs font-medium transition-colors"
              title="Экспортировать или напечатать в PDF"
            >
              <Printer className="w-3.5 h-3.5 text-indigo-400" />
              <span>Печать / PDF</span>
            </button>

            <button
              onClick={handleExportMarkdown}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 text-neutral-200 text-xs font-medium transition-colors"
              title="Скачать Markdown файл (.md)"
            >
              <Download className="w-3.5 h-3.5 text-emerald-400" />
              <span>.MD</span>
            </button>

            <button
              onClick={handleExportLatex}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 text-neutral-200 text-xs font-medium transition-colors"
              title="Скачать документ LaTeX (.tex)"
            >
              <FileCode className="w-3.5 h-3.5 text-amber-400" />
              <span>.TEX</span>
            </button>
          </div>
        </div>

        {/* Clean Sub-Tabs Navigation */}
        <div className="flex items-center gap-2 mt-3 pt-2 border-t border-neutral-800/80">
          <button
            onClick={() => setActiveSubTab('summary')}
            className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-colors ${
              activeSubTab === 'summary'
                ? 'bg-neutral-800 text-white'
                : 'text-neutral-400 hover:text-neutral-200'
            }`}
          >
            <FileText className="w-3.5 h-3.5 text-indigo-400" />
            Конспект
          </button>

          <button
            onClick={() => setActiveSubTab('tasks')}
            className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-colors ${
              activeSubTab === 'tasks'
                ? 'bg-neutral-800 text-white'
                : 'text-neutral-400 hover:text-neutral-200'
            }`}
          >
            <CheckSquare className="w-3.5 h-3.5 text-emerald-400" />
            Задачи лекции
            {lecture.actionItems.length > 0 && (
              <span className="ml-1 px-1.5 py-0.2 rounded-full bg-emerald-950/80 text-emerald-400 text-[10px] font-mono">
                {lecture.actionItems.filter(t => !t.completed).length}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveSubTab('transcript')}
            className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-colors ${
              activeSubTab === 'transcript'
                ? 'bg-neutral-800 text-white'
                : 'text-neutral-400 hover:text-neutral-200'
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5 text-neutral-400" />
            Стенограмма аудио ({lecture.transcript.length})
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 print:p-0 print:bg-white print:text-black">
        <div className="max-w-4xl mx-auto space-y-6">
          
          {/* TAB 1: SUMMARY / LECTURE NOTES */}
          {activeSubTab === 'summary' && (
            <div className="space-y-6">
              
              {/* Toolbar for editing notes */}
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-neutral-400">
                  Конспект занятия с формулами и определениями
                </span>

                <button
                  onClick={() => {
                    if (isEditingMarkdown) {
                      handleSaveMarkdown();
                    } else {
                      setEditedMarkdown(lecture.summaryMarkdown);
                      setIsEditingMarkdown(true);
                    }
                  }}
                  className="flex items-center gap-1 px-2.5 py-1 rounded bg-neutral-900 hover:bg-neutral-800 border border-neutral-800 text-xs text-neutral-300 font-medium transition-colors"
                >
                  {isEditingMarkdown ? (
                    <>
                      <Save className="w-3.5 h-3.5 text-emerald-400" />
                      Сохранить
                    </>
                  ) : (
                    <>
                      <Edit3 className="w-3.5 h-3.5 text-neutral-400" />
                      Редактировать
                    </>
                  )}
                </button>
              </div>

              {/* Rendered Container */}
              <div className="p-6 rounded-xl bg-neutral-900 border border-neutral-800 shadow-sm print:border-none print:bg-transparent">
                {isEditingMarkdown ? (
                  <div className="space-y-3">
                    <textarea
                      value={editedMarkdown}
                      onChange={(e) => setEditedMarkdown(e.target.value)}
                      rows={18}
                      className="w-full p-4 rounded-lg bg-neutral-950 border border-neutral-800 text-neutral-200 font-mono text-xs leading-relaxed focus:outline-none focus:border-indigo-500"
                      placeholder="Редактируйте текст конспекта и формулы LaTeX..."
                    />
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setIsEditingMarkdown(false)}
                        className="px-3 py-1.5 rounded text-xs text-neutral-400 hover:text-white"
                      >
                        Отмена
                      </button>
                      <button
                        onClick={handleSaveMarkdown}
                        className="px-4 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
                      >
                        Применить
                      </button>
                    </div>
                  </div>
                ) : (
                  <LatexRenderer content={lecture.summaryMarkdown} />
                )}
              </div>

              {/* Key Definitions if available */}
              {lecture.keyDefinitions && lecture.keyDefinitions.length > 0 && (
                <div className="p-5 rounded-xl bg-neutral-900/60 border border-neutral-800 space-y-3">
                  <h3 className="text-xs font-semibold text-neutral-300 uppercase tracking-wider">
                    Ключевые термины занятия
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {lecture.keyDefinitions.map((def, dIdx) => (
                      <div key={dIdx} className="p-3 rounded-lg bg-neutral-950/80 border border-neutral-800/80">
                        <div className="text-xs font-semibold text-indigo-300 mb-1">{def.term}</div>
                        <div className="text-[11px] text-neutral-400 leading-relaxed">{def.definition}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: TASKS */}
          {activeSubTab === 'tasks' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-2">
                <div>
                  <h2 className="text-sm font-semibold text-white">
                    Задания и сроки по этой лекции
                  </h2>
                  <p className="text-xs text-neutral-400 mt-0.5">
                    Найденные в аудиопотоке домашние задания и дедлайны
                  </p>
                </div>

                <div className="text-xs text-neutral-400 font-mono">
                  Выполнено: {lecture.actionItems.filter(t => t.completed).length} из {lecture.actionItems.length}
                </div>
              </div>

              {lecture.actionItems.length === 0 ? (
                <div className="p-8 text-center rounded-xl bg-neutral-900 border border-neutral-800 text-neutral-400 text-xs">
                  На этой лекции преподаватель не упоминал домашние задания или дедлайны.
                </div>
              ) : (
                <div className="space-y-2.5">
                  {lecture.actionItems.map((task) => (
                    <div
                      key={task.id}
                      onClick={() => toggleTask(task.id)}
                      className={`p-4 rounded-xl border transition-all cursor-pointer flex items-start gap-3.5 select-none ${
                        task.completed
                          ? 'bg-neutral-900/40 border-neutral-800/60 opacity-60'
                          : 'bg-neutral-900 border-neutral-800 hover:border-neutral-700'
                      }`}
                    >
                      <div className="mt-0.5">
                        <div className={`w-5 h-5 rounded flex items-center justify-center transition-colors ${
                          task.completed 
                            ? 'bg-emerald-600 text-white' 
                            : 'border border-neutral-600 hover:border-indigo-400'
                        }`}>
                          {task.completed && <Check className="w-3.5 h-3.5" />}
                        </div>
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className={`text-xs md:text-sm font-medium ${
                          task.completed ? 'line-through text-neutral-500' : 'text-neutral-100'
                        }`}>
                          {task.task}
                        </div>

                        <div className="flex flex-wrap items-center gap-3 mt-2 text-[11px] text-neutral-400">
                          <span className="flex items-center gap-1 font-mono text-amber-400 font-medium">
                            <Calendar className="w-3 h-3 text-amber-500" />
                            Срок: {task.deadline}
                          </span>

                          <span aria-hidden="true">·</span>

                          <span className={task.priority === 'high' ? 'text-rose-400 font-medium' : 'text-neutral-400'}>
                            {task.priority === 'high' ? 'Высокий приоритет' : 'Обычный'}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TAB 3: TRANSCRIPT */}
          {activeSubTab === 'transcript' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2">
                <div>
                  <h2 className="text-sm font-semibold text-white">
                    Стенограмма лекции
                  </h2>
                  <p className="text-xs text-neutral-400 mt-0.5">
                    Синхронизированная расшифровка речи с таймкодами
                  </p>
                </div>

                <div className="relative w-full sm:w-64">
                  <Search className="w-3.5 h-3.5 text-neutral-500 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Поиск по словам в стенограмме..."
                    className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-neutral-900 border border-neutral-800 text-xs text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="space-y-2.5">
                {filteredTranscript.map((seg) => {
                  const formatSec = (s: number) => {
                    const m = Math.floor(s / 60);
                    const sec = Math.floor(s % 60);
                    return `${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
                  };

                  return (
                    <div
                      key={seg.id}
                      className="p-3.5 rounded-xl bg-neutral-900 border border-neutral-800 flex items-start gap-3 hover:border-neutral-700 transition-colors"
                    >
                      <div className="px-2 py-1 rounded bg-neutral-950 border border-neutral-800 font-mono text-[10px] text-indigo-400 shrink-0">
                        {formatSec(seg.startTime)}
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[11px] font-semibold text-neutral-300">
                            {seg.speaker}
                          </span>
                          {seg.bookmarked && (
                            <span className="text-[10px] text-amber-400 flex items-center gap-1 font-medium">
                              <Bookmark className="w-3 h-3 fill-amber-400" />
                              Важный момент
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-neutral-200 leading-relaxed">
                          {seg.text}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
};
