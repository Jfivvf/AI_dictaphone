import React, { useState } from 'react';
import { 
  Sliders, 
  Mic, 
  Volume2, 
  Keyboard, 
  CheckCircle2, 
  Save, 
  ShieldCheck
} from 'lucide-react';
import { AppSettings } from '../types';

interface SettingsTabProps {
  settings: AppSettings;
  onUpdateSettings: (newSettings: AppSettings) => void;
}

export const SettingsTab: React.FC<SettingsTabProps> = ({
  settings,
  onUpdateSettings,
}) => {
  const [micDevice, setMicDevice] = useState('default');
  const [autoExtractTasks, setAutoExtractTasks] = useState(true);
  const [autoFormatLatex, setAutoFormatLatex] = useState(true);
  const [noiseFilter, setNoiseFilter] = useState(true);
  const [isSaved, setIsSaved] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    onUpdateSettings({
      ...settings,
      asrModel: 'faster-whisper-turbo',
      noiseSuppression: noiseFilter ? 'rnnoise' : 'off'
    });
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
              Настройки приложения
            </h1>
            <p className="text-xs text-neutral-400 mt-1">
              Параметры микрофона, режима распознавания и горячих клавиш
            </p>
          </div>

          <button
            onClick={handleSave}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors shadow-sm self-start sm:self-center"
          >
            <Save className="w-3.5 h-3.5" />
            Сохранить настройки
          </button>
        </div>

        {isSaved && (
          <div className="p-3.5 rounded-xl bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>Настройки успешно применены</span>
          </div>
        )}

        <form onSubmit={handleSave} className="space-y-6">
          
          {/* Section 1: Microphone & Sound */}
          <div className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-4">
            <div className="flex items-center gap-2 pb-2 border-b border-neutral-800">
              <Mic className="w-4 h-4 text-indigo-400" />
              <h2 className="text-sm font-bold text-white">
                Запись звука и микрофон
              </h2>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">
                  Устройство записи (Микрофон):
                </label>
                <select
                  value={micDevice}
                  onChange={(e) => setMicDevice(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                >
                  <option value="default">Основной микрофон системы (По умолчанию)</option>
                  <option value="builtin">Встроенный микрофон ноутбука</option>
                  <option value="headset">Гарнитура / Наушники</option>
                  <option value="usb">Внешний USB-микрофон</option>
                </select>
              </div>

              {/* Noise cancellation toggle */}
              <div className="flex items-center justify-between p-3 rounded-lg bg-neutral-950 border border-neutral-850">
                <div>
                  <div className="text-xs font-semibold text-neutral-200">
                    Подавление шума аудитории
                  </div>
                  <div className="text-[11px] text-neutral-400 mt-0.5">
                    Фильтрует шелест страниц, скрип стульев и гул вентиляторов
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setNoiseFilter(!noiseFilter)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    noiseFilter
                      ? 'bg-indigo-600 text-white'
                      : 'bg-neutral-800 text-neutral-400'
                  }`}
                >
                  {noiseFilter ? 'Включено' : 'Выключено'}
                </button>
              </div>
            </div>
          </div>


          {/* Section 3: Smart Assistance Toggles */}
          <div className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-4">
            <h2 className="text-sm font-bold text-white">
              Автоматизация при расшифровке
            </h2>

            <div className="divide-y divide-neutral-800">
              <div className="py-3 flex items-center justify-between">
                <div>
                  <div className="text-xs font-semibold text-neutral-200">
                    Автоматический поиск дедлайнов и домашних заданий
                  </div>
                  <div className="text-[11px] text-neutral-400 mt-0.5">
                    Находит в речи фразы «сдать к пятнице», «подготовить отчет» и добавляет их во вкладку задач
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setAutoExtractTasks(!autoExtractTasks)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    autoExtractTasks ? 'bg-indigo-600 text-white' : 'bg-neutral-800 text-neutral-400'
                  }`}
                >
                  {autoExtractTasks ? 'Да' : 'Нет'}
                </button>
              </div>

              <div className="py-3 flex items-center justify-between">
                <div>
                  <div className="text-xs font-semibold text-neutral-200">
                    Преобразование формул в красивый вид (LaTeX)
                  </div>
                  <div className="text-[11px] text-neutral-400 mt-0.5">
                    Автоматически форматирует интегралы, дроби и матрицы в читаемый вид
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setAutoFormatLatex(!autoFormatLatex)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    autoFormatLatex ? 'bg-indigo-600 text-white' : 'bg-neutral-800 text-neutral-400'
                  }`}
                >
                  {autoFormatLatex ? 'Да' : 'Нет'}
                </button>
              </div>
            </div>
          </div>

          {/* Section 4: Hotkeys & Privacy */}
          <div className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-3">
            <div className="flex items-center gap-2">
              <Keyboard className="w-4 h-4 text-indigo-400" />
              <h2 className="text-sm font-bold text-white">
                Горячие клавиши
              </h2>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-850 flex items-center justify-between">
                <span className="text-neutral-300">Старт / Пауза записи:</span>
                <kbd className="px-2 py-1 rounded bg-neutral-800 font-mono text-[11px] text-indigo-300">Пробел</kbd>
              </div>
              <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-850 flex items-center justify-between">
                <span className="text-neutral-300">Поставить метку:</span>
                <kbd className="px-2 py-1 rounded bg-neutral-800 font-mono text-[11px] text-indigo-300">M</kbd>
              </div>
              <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-850 flex items-center justify-between">
                <span className="text-neutral-300">Экспорт в PDF:</span>
                <kbd className="px-2 py-1 rounded bg-neutral-800 font-mono text-[11px] text-indigo-300">Ctrl + P</kbd>
              </div>
              <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-850 flex items-center justify-between">
                <span className="text-neutral-300">Сохранить изменения:</span>
                <kbd className="px-2 py-1 rounded bg-neutral-800 font-mono text-[11px] text-indigo-300">Ctrl + S</kbd>
              </div>
            </div>
          </div>

        </form>

      </div>
    </div>
  );
};
