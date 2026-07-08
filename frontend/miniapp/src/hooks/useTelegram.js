import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { telegram } from '../telegram';

export function useTelegram() {
  return { telegram };
}

export function useBackButton(path) {
  const navigate = useNavigate();

  useEffect(() => {
    if (path) {
      telegram.showBackButton(() => navigate(path));
    }
    return () => telegram.hideBackButton();
  }, [path, navigate]);
}

export function useMainButton(text, onClick) {
  useEffect(() => {
    if (text && onClick) {
      telegram.showMainButton(text, onClick);
    }
    return () => telegram.hideMainButton();
  }, [text, onClick]);
}
