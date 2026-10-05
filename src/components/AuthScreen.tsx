import React, { useState } from 'react';
import {
  AlertCircle
} from 'lucide-react';
import { signInWithGooglePopup } from '../firebase';
import { AxolotlLogo } from './AxolotlLogo';

interface AuthScreenProps {
  onContinueOffline?: () => void;
}

export const AuthScreen: React.FC<AuthScreenProps> = ({ onContinueOffline }) => {
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleGoogleSignIn = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      await signInWithGooglePopup();
    } catch (err: any) {
      console.error('Sign in error:', err);
      if (err?.code === 'auth/popup-closed-by-user') {
        setErrorMsg('Окно входа было закрыто до завершения авторизации.');
      } else if (err?.code === 'auth/popup-blocked') {
        setErrorMsg('Браузер заблокировал всплывающее окно входа. Разрешите всплывающие окна для этого сайта.');
      } else {
        setErrorMsg(err?.message || 'Не удалось выполнить вход. Попробуйте снова.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-screen bg-neutral-950 text-neutral-100 flex flex-col justify-between p-4 md:p-8 select-none overflow-y-auto">
      {/* Top Bar */}
      <div className="max-w-5xl w-full mx-auto flex items-center justify-between py-2">
        <div className="flex items-center gap-2.5">
          <AxolotlLogo className="w-8 h-8 rounded-lg shadow-sm" />
          <span className="font-bold text-white text-base tracking-tight">AxAI</span>
        </div>
      </div>

      {/* Main Auth Card */}
      <div className="max-w-md w-full mx-auto my-auto py-8">
        <div className="bg-neutral-900 border border-neutral-800 rounded-2xl p-6 md:p-8 shadow-2xl space-y-6">
          <div className="text-center space-y-2">
            <div className="flex justify-center mb-3">
              <AxolotlLogo className="w-16 h-16 rounded-2xl shadow-md" />
            </div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              Вход в AxAI
            </h1>
            <p className="text-xs text-neutral-400 leading-relaxed">
              Войдите в аккаунт для сохранения ваших лекций, формул и учебных задач
            </p>
          </div>

          {errorMsg && (
            <div className="p-3.5 rounded-xl bg-rose-950/60 border border-rose-800/80 text-rose-200 text-xs flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Primary Google Sign-In / Registration Button */}
          <div className="space-y-3">
            <button
              type="button"
              onClick={handleGoogleSignIn}
              disabled={isLoading}
              className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl bg-white hover:bg-neutral-100 text-neutral-950 font-semibold text-xs transition-all shadow-md disabled:opacity-50 cursor-pointer"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              <span>{isLoading ? 'Выполняется вход...' : 'Войти / Зарегистрироваться через Google'}</span>
            </button>

            {onContinueOffline && (
              <button
                type="button"
                onClick={onContinueOffline}
                className="w-full py-2.5 rounded-xl bg-neutral-800/70 hover:bg-neutral-800 border border-neutral-700/70 text-neutral-300 text-xs font-medium transition-colors"
              >
                Продолжить локально без облачной синхронизации
              </button>
            )}
          </div>
        </div>
      </div>

      <div />
    </div>
  );
};
