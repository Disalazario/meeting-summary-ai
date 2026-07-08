import axios from 'axios';
import { telegram } from '../telegram';

const API_BASE = import.meta.env.VITE_API_URL || '';

const client = axios.create({
  baseURL: `${API_BASE}/api/miniapp`,
  headers: { 'Content-Type': 'application/json' },
});

// Авторизация через Telegram initData
client.interceptors.request.use(config => {
  const initData = telegram.initData;
  if (initData) {
    config.headers['X-Telegram-Init-Data'] = initData;
  }
  return config;
});

client.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      telegram.showAlert('Ошибка авторизации. Попробуйте перезапустить приложение.');
    }
    return Promise.reject(error);
  }
);

export default client;
