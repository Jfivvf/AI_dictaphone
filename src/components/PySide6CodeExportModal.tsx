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

import webviewPyRaw from '../../python_desktop/axai_webview_desktop.py?raw';
import mainPyRaw from '../../python_desktop/main.py?raw';
import pdfImporterPyRaw from '../../python_desktop/pdf_importer.py?raw';
import audioWorkerPyRaw from '../../python_desktop/audio_worker.py?raw';
import requirementsTxtRaw from '../../python_desktop/requirements.txt?raw';

interface PySide6CodeExportModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type PythonFileKey =
  | 'axai_webview_desktop.py'
  | 'main.py'
  | 'pdf_importer.py'
  | 'audio_worker.py'
  | 'requirements.txt';

export const PySide6CodeExportModal: React.FC<PySide6CodeExportModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [activeFile, setActiveFile] = useState<PythonFileKey>('axai_webview_desktop.py');
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const files: Record<PythonFileKey, string> = {
    'axai_webview_desktop.py': webviewPyRaw,
    'main.py': mainPyRaw,
    'pdf_importer.py': pdfImporterPyRaw,
    'audio_worker.py': audioWorkerPyRaw,
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
    link.download = activeFile;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-neutral-900 border border-neutral-800 rounded-2xl w-full max-w-5xl h-[85vh] flex flex-col overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="px-6 py-4 bg-neutral-900 border-b border-neutral-800 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
              <FileCode className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">
                AxAI — Десктопное приложение на Python + PySide6
              </h2>
              <p className="text-[11px] text-neutral-400">
                1) axai_webview_desktop.py — окно PySide6 1-в-1 с этим веб-интерфейсом · 2) main.py — автономная версия на виджетах QtWidgets
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
          <div className="flex items-center gap-1.5 overflow-x-auto">
            {(
              [
                'axai_webview_desktop.py',
                'main.py',
                'pdf_importer.py',
                'audio_worker.py',
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
              title="Скачать текущий файл на диск"
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
              {activeFile === 'axai_webview_desktop.py'
                ? 'Запуск 1-в-1 окна PySide6: pip install -r python_desktop/requirements.txt && python python_desktop/axai_webview_desktop.py'
                : 'Запуск нативных виджетов PySide6: cd python_desktop && pip install -r requirements.txt && python main.py'}
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
