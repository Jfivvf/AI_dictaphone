import React from 'react';
import { 
  User,
  Sparkles,
  FileCode
} from 'lucide-react';
import { AppSettings } from '../types';

interface DesktopHeaderProps {
  settings: AppSettings;
  onOpenPySideCode: () => void;
  onNavigateToAccount: () => void;
  activeTab: string;
}

export const DesktopHeader: React.FC<DesktopHeaderProps> = ({
  settings,
  onOpenPySideCode,
  onNavigateToAccount,
}) => {
  return (
    <header className="h-14 bg-neutral-900 border-b border-neutral-800 flex items-center justify-between px-4 select-none shrink-0">
      {/* Zone 1: Window controls + Clean Brand Wordmark */}
      <div className="flex items-center gap-3">
        {/* Window Controls */}
        <div className="flex items-center gap-1.5 mr-2">
          <div className="w-3 h-3 rounded-full bg-rose-500/80 hover:bg-rose-500 transition-colors cursor-pointer" title="Закрыть" />
          <div className="w-3 h-3 rounded-full bg-amber-500/80 hover:bg-amber-500 transition-colors cursor-pointer" title="Свернуть" />
          <div className="w-3 h-3 rounded-full bg-emerald-500/80 hover:bg-emerald-500 transition-colors cursor-pointer" title="Развернуть" />
        </div>

        <div className="h-4 w-px bg-neutral-800" />

        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-400 font-bold text-sm">
            <Sparkles className="w-4 h-4" />
          </div>
          <span className="font-semibold text-neutral-100 text-sm tracking-tight whitespace-nowrap">
            Lectura AI
          </span>
          <span className="text-xs text-neutral-400 hidden sm:inline">
            Учебный диктофон
          </span>
        </div>
      </div>

      {/* Zone 2: Empty / Clean Center */}
      <div className="hidden md:block text-xs text-neutral-500">
        Учебные конспекты и дедлайны
      </div>

      {/* Zone 3: Primary Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={onOpenPySideCode}
          className="p-2 rounded-lg bg-neutral-800/80 hover:bg-neutral-700 text-neutral-400 hover:text-neutral-200 transition-colors"
          title="Исходный код приложения"
        >
          <FileCode className="w-4 h-4" />
        </button>

        <button
          onClick={onNavigateToAccount}
          className="flex items-center gap-2 pl-2 pr-3 py-1 rounded-lg bg-neutral-800/60 hover:bg-neutral-800 border border-neutral-800 text-neutral-200 text-xs transition-colors"
          title="Открыть профиль"
        >
          <div className="w-6 h-6 rounded-full bg-indigo-600/40 text-indigo-300 font-semibold flex items-center justify-center text-xs">
            <User className="w-3.5 h-3.5" />
          </div>
          <span className="font-medium max-w-[120px] truncate hidden sm:inline">
            {settings.student.name.split(' ')[0]} ({settings.student.group})
          </span>
        </button>
      </div>
    </header>
  );
};
