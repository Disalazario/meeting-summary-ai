import { useEffect } from 'react';
import { telegram } from '../telegram';

export function useTheme() {
  useEffect(() => {
    const tp = telegram.themeParams;
    const root = document.documentElement;

    if (tp.bg_color) root.style.setProperty('--tg-bg', tp.bg_color);
    if (tp.text_color) root.style.setProperty('--tg-text', tp.text_color);
    if (tp.hint_color) root.style.setProperty('--tg-hint', tp.hint_color);
    if (tp.link_color) root.style.setProperty('--tg-link', tp.link_color);
    if (tp.button_color) root.style.setProperty('--tg-button', tp.button_color);
    if (tp.button_text_color) root.style.setProperty('--tg-button-text', tp.button_text_color);
    if (tp.secondary_bg_color) root.style.setProperty('--tg-bg-secondary', tp.secondary_bg_color);
  }, []);

  return {
    colorScheme: telegram.colorScheme,
    isDark: telegram.colorScheme === 'dark',
  };
}
