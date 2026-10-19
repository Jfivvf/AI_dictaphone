import React, { useState, useEffect, useRef } from 'react';
import defaultAxolotlImg from '../assets/images/axai_logo_1791229912418.jpg';

const USER_AVATAR_STORAGE_KEY = 'axai_user_avatar_256_data_url';
const AVATAR_UPDATED_EVENT = 'axai-user-avatar-updated';

/**
 * Обрезает загруженную картинку до квадрата 1:1 по центру и сжимает до 256×256 WebP/JPEG
 * для компактного хранения в профиле пользователя (SQLite / Firestore < 1 МБ).
 */
export function cropAndCompressAvatarSquare256(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Не удалось прочитать файл изображения'));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error('Некорректный формат изображения'));
      img.onload = () => {
        const size = 256;
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          resolve(String(reader.result));
          return;
        }
        const side = Math.min(img.width, img.height);
        const sx = Math.floor((img.width - side) / 2);
        const sy = Math.floor((img.height - side) / 2);
        ctx.drawImage(img, sx, sy, side, side, 0, 0, size, size);

        // Пробуем WebP (компактнее), иначе JPEG
        let compressed = canvas.toDataURL('image/webp', 0.85);
        if (!compressed.startsWith('data:image/webp')) {
          compressed = canvas.toDataURL('image/jpeg', 0.85);
        }
        resolve(compressed);
      };
      img.src = String(reader.result);
    };
    reader.readAsDataURL(file);
  });
}

export function setCustomAxaiLogo(dataUrl: string) {
  try {
    if (dataUrl) {
      localStorage.setItem(USER_AVATAR_STORAGE_KEY, dataUrl);
    } else {
      localStorage.removeItem(USER_AVATAR_STORAGE_KEY);
    }
    window.dispatchEvent(new CustomEvent(AVATAR_UPDATED_EVENT, { detail: dataUrl }));
  } catch (err) {
    console.warn('Could not save user avatar to localStorage:', err);
  }
}

export function getCustomAxaiLogo(): string | null {
  try {
    return localStorage.getItem(USER_AVATAR_STORAGE_KEY);
  } catch {
    return null;
  }
}

interface AxolotlLogoProps {
  className?: string;
  allowUploadOnClick?: boolean;
}

/**
 * Фиксированная системная иконка приложения AxAI (розовый аксолотль в очках с ручкой).
 * Отвечает ТОЛЬКО за логотип бренда в шапке и на экране входа и НЕ меняется при смене аватарки пользователя.
 */
export const AxolotlLogo: React.FC<AxolotlLogoProps> = ({
  className = 'w-8 h-8',
}) => {
  return (
    <img
      src={defaultAxolotlImg}
      alt="AxAI"
      referrerPolicy="no-referrer"
      title="AxAI — Фирменная иконка приложения"
      className={`shrink-0 select-none object-cover ${className}`}
    />
  );
};

interface UserAvatarProps {
  className?: string;
  avatarUrl?: string | null;
  allowUploadOnClick?: boolean;
  onAvatarChange?: (compressedDataUrl: string) => void;
}

/**
 * Отдельный компонент аватарки пользователя.
 * По умолчанию показывает аксолотля, если своей картинки в профиле нет.
 */
export const UserAvatar: React.FC<UserAvatarProps> = ({
  className = 'w-8 h-8 rounded-full',
  avatarUrl,
  allowUploadOnClick = false,
  onAvatarChange,
}) => {
  const [avatarSrc, setAvatarSrc] = useState<string>(
    () => avatarUrl || getCustomAxaiLogo() || defaultAxolotlImg
  );
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (avatarUrl) {
      setAvatarSrc(avatarUrl);
    } else {
      setAvatarSrc(getCustomAxaiLogo() || defaultAxolotlImg);
    }
  }, [avatarUrl]);

  useEffect(() => {
    const handleAvatarUpdate = (e: Event) => {
      const customEvent = e as CustomEvent<string>;
      setAvatarSrc(customEvent.detail || defaultAxolotlImg);
    };

    window.addEventListener(AVATAR_UPDATED_EVENT, handleAvatarUpdate);
    return () => window.removeEventListener(AVATAR_UPDATED_EVENT, handleAvatarUpdate);
  }, []);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const square256 = await cropAndCompressAvatarSquare256(file);
      setAvatarSrc(square256);
      setCustomAxaiLogo(square256);
      if (onAvatarChange) {
        onAvatarChange(square256);
      }
    } catch (err) {
      console.warn('Avatar compression error:', err);
    }
    e.target.value = '';
  };

  return (
    <>
      {allowUploadOnClick && (
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleFileChange}
          className="hidden"
        />
      )}
      <img
        src={avatarSrc}
        alt="Аватар профиля"
        referrerPolicy="no-referrer"
        onClick={allowUploadOnClick ? () => fileInputRef.current?.click() : undefined}
        title={allowUploadOnClick ? 'Нажмите, чтобы сменить аватарку профиля (256×256)' : 'Аватар студента'}
        className={`shrink-0 select-none object-cover ${
          allowUploadOnClick ? 'cursor-pointer hover:opacity-90 transition-opacity' : ''
        } ${className}`}
      />
    </>
  );
};
