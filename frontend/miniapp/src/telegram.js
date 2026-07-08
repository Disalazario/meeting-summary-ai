const tg = window.Telegram?.WebApp;

export const telegram = {
  get raw() { return tg; },

  // Данные инициализации (для авторизации на бэкенде)
  get initData() { return tg?.initData || ''; },
  get initDataUnsafe() { return tg?.initDataUnsafe || {}; },

  // Информация о пользователе
  get user() { return tg?.initDataUnsafe?.user || null; },
  get userId() { return tg?.initDataUnsafe?.user?.id || null; },
  get userName() {
    const u = tg?.initDataUnsafe?.user;
    return u ? `${u.first_name} ${u.last_name || ''}`.trim() : 'Пользователь';
  },

  // Тема
  get colorScheme() { return tg?.colorScheme || 'light'; },
  get themeParams() { return tg?.themeParams || {}; },

  // Основные кнопки
  showMainButton(text, onClick) {
    if (!tg) return;
    tg.MainButton.setText(text);
    tg.MainButton.onClick(onClick);
    tg.MainButton.show();
  },
  hideMainButton() {
    tg?.MainButton?.hide();
  },
  showMainButtonProgress() {
    tg?.MainButton?.showProgress(false);
  },
  hideMainButtonProgress() {
    tg?.MainButton?.hideProgress();
  },

  showBackButton(onClick) {
    if (!tg) return;
    tg.BackButton.onClick(onClick);
    tg.BackButton.show();
  },
  hideBackButton() {
    tg?.BackButton?.hide();
  },

  // Haptic feedback
  haptic: {
    impact(style = 'medium') { tg?.HapticFeedback?.impactOccurred(style); },
    notification(type = 'success') { tg?.HapticFeedback?.notificationOccurred(type); },
    selection() { tg?.HapticFeedback?.selectionChanged(); },
  },

  // Утилиты
  close() { tg?.close(); },
  expand() { tg?.expand(); },

  showAlert(message) { tg?.showAlert(message); },
  showConfirm(message) {
    return new Promise(resolve => {
      if (tg) {
        tg.showConfirm(message, resolve);
      } else {
        resolve(window.confirm(message));
      }
    });
  },
};
