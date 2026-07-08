import { useEffect } from 'react';
import client from '../api/client';
import { useAuth } from '../hooks/useAuth';
import TelegramSettings from '../components/TelegramSettings';
import TelegramLink from '../components/TelegramLink';
import VoiceEnrollment from '../components/VoiceEnrollment';
import IntegrationsSettings from '../components/IntegrationsSettings';
import WikiSettings from '../components/WikiSettings';

export default function SettingsPage() {
  const { user } = useAuth();

  useEffect(() => {
    // Check Yandex auth status (from bot-info endpoint availability)
    client.get('/telegram/bot-info').catch(() => {});
  }, []);

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-800 mb-6">Настройки</h1>

      <div className="space-y-6">
        {/* Voice profile */}
        {user && (
          <div className="bg-white rounded-lg border p-5">
            <VoiceEnrollment userId={user.id} userName={user.display_name || user.username} />
          </div>
        )}

        {/* Telegram-привязка пользователя */}
        <div className="bg-white rounded-lg border p-5">
          <TelegramLink />
        </div>

        {/* Telegram groups (системные) */}
        <div className="bg-white rounded-lg border p-5">
          <TelegramSettings />
        </div>

        {/* Внешние интеграции (МангоТелеком, AmoCRM, …) */}
        <div className="bg-white rounded-lg border p-5">
          <IntegrationsSettings />
        </div>

        {/* Wiki.js RAG */}
        <div className="bg-white rounded-lg border p-5">
          <WikiSettings />
        </div>

        {/* Yandex Auth — для подключения бота к встрече авторизация Яндекса
            больше не нужна (бот заходит гостем). Раздел оставлен только для
            справки и редкого случая, когда нужны куки для других целей. */}
        <div className="bg-white rounded-lg border p-5">
          <h3 className="font-semibold text-gray-900 mb-1">Яндекс авторизация</h3>
          <p className="text-sm text-gray-700 mb-3">
            Для текущего сценария <b>не требуется</b> — бот подключается к встречам
            Телемоста гостем по ссылке. Скрипт ниже нужен только если когда-нибудь
            понадобится обновить куки Яндекса вручную.
          </p>
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm">
            <p className="font-mono text-xs text-slate-800">
              cd backend && python scripts/setup_yandex_auth.py
            </p>
            <p className="mt-1.5 text-xs text-slate-600">
              Скрипт откроет браузер для ручной авторизации. После входа куки сохраняются автоматически.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
