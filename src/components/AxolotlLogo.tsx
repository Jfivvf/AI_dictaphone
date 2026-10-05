import React, { useState, useEffect, useRef } from 'react';
import defaultAxolotlImg from '../assets/images/axai_logo_1791229912418.jpg';

const CUSTOM_LOGO_STORAGE_KEY = 'axai_custom_logo_data_url';
const LOGO_UPDATED_EVENT = 'axai-logo-updated';

export function setCustomAxaiLogo(dataUrl: string) {
  try {
    localStorage.setItem(CUSTOM_LOGO_STORAGE_KEY, dataUrl);
    window.dispatchEvent(new CustomEvent(LOGO_UPDATED_EVENT, { detail: dataUrl }));
    const link = document.querySelector("link[rel*='icon']") as HTMLLinkElement | null;
    if (link) {
      link.type = 'image/jpeg';
      link.href = dataUrl;
    }
  } catch (err) {
    console.warn('Could not save custom logo to localStorage:', err);
  }
}

export function getCustomAxaiLogo(): string | null {
  try {
    return localStorage.getItem(CUSTOM_LOGO_STORAGE_KEY);
  } catch {
    return null;
  }
}

interface AxolotlLogoProps {
  className?: string;
  allowUploadOnClick?: boolean;
}

export const AxolotlLogo: React.FC<AxolotlLogoProps> = ({
  className = 'w-8 h-8',
  allowUploadOnClick = true,
}) => {
  const [logoSrc, setLogoSrc] = useState<string>(() => getCustomAxaiLogo() || defaultAxolotlImg);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const stored = getCustomAxaiLogo();
    if (stored) {
      setLogoSrc(stored);
      const link = document.querySelector("link[rel*='icon']") as HTMLLinkElement | null;
      if (link) {
        link.href = stored;
      }
    }

    const handleLogoUpdate = (e: Event) => {
      const customEvent = e as CustomEvent<string>;
      if (customEvent.detail) {
        setLogoSrc(customEvent.detail);
      }
    };

    window.addEventListener(LOGO_UPDATED_EVENT, handleLogoUpdate);
    return () => window.removeEventListener(LOGO_UPDATED_EVENT, handleLogoUpdate);
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        setLogoSrc(reader.result);
        setCustomAxaiLogo(reader.result);
      }
    };
    reader.readAsDataURL(file);
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
        src={logoSrc}
        alt="AxAI"
        referrerPolicy="no-referrer"
        onClick={allowUploadOnClick ? () => fileInputRef.current?.click() : undefined}
        title={allowUploadOnClick ? 'Нажмите, чтобы выбрать свой оригинал картинки с компьютера' : 'AxAI'}
        className={`shrink-0 select-none object-cover ${allowUploadOnClick ? 'cursor-pointer hover:opacity-90 transition-opacity' : ''} ${className}`}
      />
    </>
  );
};
