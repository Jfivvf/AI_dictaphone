/// <reference types="vite/client" />
import React, { useState } from 'react';
import {
  X,
  Copy,
  Check,
  FileCode,
  Terminal,
  Download
} from 'lucide-react';

import mainPyRaw from '../../python_desktop/main.py?raw';
import dbReposPyRaw from '../../python_desktop/db/repositories.py?raw';
import mlEnginePyRaw from '../../python_desktop/ml/engine.py?raw';
import exportersPyRaw from '../../python_desktop/export/exporters.py?raw';
import latexPreviewPyRaw from '../../python_desktop/ui/latex_preview.py?raw';
import audioWorkerPyRaw from '../../python_desktop/audio_worker.py?raw';
import pdfImporterPyRaw from '../../python_desktop/pdf_importer.py?raw';
import requirementsTxtRaw from '../../python_desktop/requirements.txt?raw';

interface PySide6CodeExportModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type PythonFileKey =
  | 'main.py'
  | 'db/repositories.py'
  | 'ml/engine.py'
  | 'export/exporters.py'
  | 'ui/latex_preview.py'
  | 'audio_worker.py'
  | 'pdf_importer.py'
  | 'requirements.txt';

export const PySide6CodeExportModal: React.FC<PySide6CodeExportModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [activeFile, setActiveFile] = useState<PythonFileKey>('main.py');
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const files: Record<PythonFileKey, string> = {
    'main.py': mainPyRaw,
    'db/repositories.py': dbReposPyRaw,
    'ml/engine.py': mlEnginePyRaw,
    'export/exporters.py': exportersPyRaw,
    'ui/latex_preview.py': latexPreviewPyRaw,
    'audio_worker.py': audioWorkerPyRaw,
    'pdf_importer.py': pdfImporterPyRaw,
    'requirements.txt': requirementsTxtRaw,
  };

  const handleCopyCode = () => {
    navigator.clipboard.writeText(files[activeFile]);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadFile = () => {
    const blob = new Blob([files[activeFile]], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = activeFile.replace('/', '_');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-neutral-900 border border-neutral-800 rounded-2xl w-full max-w-6xl h-[88vh] flex flex-col overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="px-6 py-4 bg-neutral-900 border-b border-neutral-800 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
              <FileCode className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">
                AxAI — Нативное модульное десктопное приложение на Python + PySide6
              </h2>
              <p className="text-[11px] text-neutral-400">
                Пакеты: main.py · db/repositories.py (SQLite + FTS5) · ml/engine.py (Transcriber & Summarizer + Map-Reduce) · export/exporters.py · ui/latex_preview.py
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

        {/* File Tabs & Actions */}
        <div className="px-6 py-2 bg-neutral-950 border-b border-neutral-800 flex flex-wrap items-center justify-between gap-2 shrink-0">
          <div className="flex items-center gap-1.5 overflow-x-auto py-1">
            {(
              [
                'main.py',
                'db/repositories.py',
                'ml/engine.py',
                'export/exporters.py',
                'ui/latex_preview.py',
                'audio_worker.py',
                'pdf_importer.py',
                'requirements.txt',
              ] as const
            ).map((fname) => (
              <button
                key={fname}
                onClick={() => setActiveFile(fname)}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors whitespace-nowrap ${
                  activeFile === fname
                    ? 'bg-neutral-800 text-indigo-400 border border-neutral-700 font-semibold'
                    : 'text-neutral-400 hover:text-neutral-200'
                }`}
              >
                {fname}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleDownloadFile}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-xs font-medium transition-colors"
              title="Скачать текущий модуль на диск"
            >
              <Download className="w-3.5 h-3.5 text-indigo-400" />
              Скачать {activeFile}
            </button>

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
                  Копировать
                </>
              )}
            </button>
          </div>
        </div>

        {/* Code View Area */}
        <div className="flex-1 overflow-y-auto p-6 bg-neutral-950">
          <pre className="font-mono text-xs text-neutral-300 leading-relaxed overflow-x-auto select-text">
            <code>{files[activeFile]}</code>
          </pre>
        </div>

        {/* Footer */}
        <div className="p-4 px-6 bg-neutral-900 border-t border-neutral-800 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs shrink-0">
          <div className="flex items-center gap-2 text-neutral-400 font-mono text-[11px]">
            <Terminal className="w-3.5 h-3.5 text-indigo-400" />
            <span>
              Запуск нативного приложения: cd python_desktop && pip install -r requirements.txt && python main.py
            </span>
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
