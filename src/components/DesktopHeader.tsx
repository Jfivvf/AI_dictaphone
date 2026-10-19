import React from 'react';
import {
  LogOut,
  LogIn
} from 'lucide-react';
import { AppSettings } from '../types';
import { AxolotlLogo, UserAvatar } from './AxolotlLogo';

interface DesktopHeaderProps {
  settings: AppSettings;
  onNavigateToAccount: () => void;
  activeTab: string;
  userEmail?: string | null;
  userPhotoUrl?: string | null;
  isAuthenticated?: boolean;
  onSignOut?: () => void;
  onRequireSignIn?: () => void;
}

export const DesktopHeader: React.FC<DesktopHeaderProps> = ({
  settings,
  onNavigateToAccount,
  isAuthenticated,
  onSignOut,
  onRequireSignIn,
}) => {
  return (
    <header className="h-14 bg-neutral-900 border-b border-neutral-800 flex items-center justify-between px-4 select-none shrink-0">
      {/* Brand Logo + AxAI Name (Fixed App Icon) */}
      <div className="flex items-center gap-2.5">
        <AxolotlLogo className="w-8 h-8 rounded-lg shadow-sm" />
        <span className="font-bold text-white text-base tracking-tight whitespace-nowrap">
          AxAI
        </span>
      </div>

      {/* Primary Actions & Auth Controls (Separate User Avatar) */}
      <div className="flex items-center gap-2">
        <button
          onClick={onNavigateToAccount}
          className="flex items-center gap-2 pl-2 pr-3 py-1 rounded-lg bg-neutral-800/60 hover:bg-neutral-800 border border-neutral-800 text-neutral-200 text-xs transition-colors"
          title="Открыть профиль студента"
        >
          <UserAvatar
            avatarUrl={settings.student.avatarUrl}
            className="w-6 h-6 rounded-full"
            allowUploadOnClick={false}
          />
          <span className="font-medium max-w-[130px] truncate hidden sm:inline">
            {settings.student.name.split(' ')[0]} ({settings.student.group})
          </span>
        </button>

        {isAuthenticated ? (
          <button
            onClick={onSignOut}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-rose-950/50 hover:bg-rose-900/70 border border-rose-800/60 text-rose-200 text-xs font-medium transition-colors"
            title="Выйти из аккаунта"
          >
            <LogOut className="w-3.5 h-3.5 text-rose-400" />
            <span className="hidden sm:inline">Выйти</span>
          </button>
        ) : (
          <button
            onClick={onRequireSignIn}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors"
            title="Войти в аккаунт"
          >
            <LogIn className="w-3.5 h-3.5" />
            <span>Войти</span>
          </button>
        )}
      </div>
    </header>
  );
};
