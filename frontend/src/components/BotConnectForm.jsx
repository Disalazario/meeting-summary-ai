import { useState, useEffect } from 'react';
import client from '../api/client';

export default function BotConnectForm({ onSuccess, onCancel }) {
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [telegramGroupId, setTelegramGroupId] = useState('');
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const isValidUrl = /^https?:\/\/telemost\.yandex\.(ru|com)\/j\/\d{6,20}$/.test(url);

  useEffect(() => {
    client.get('/telegram/groups').then(res => setGroups(res.data)).catch(() => {});
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isValidUrl || !title) return;

    setLoading(true);
    setError('');
    try {
      const res = await client.post('/bot/join', {
        meeting_url: url,
        title,
        telegram_group_id: telegramGroupId ? parseInt(telegramGroupId) : null,
      });
      onSuccess(res.data.meeting_id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка подключения бота');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg border p-5">
      <h3 className="font-semibold text-gray-800 mb-1">Подключить бота к встрече</h3>
      <p className="text-xs text-gray-500 mb-4">
        Бот зайдёт в Телемост гостем — никакая авторизация Яндекса не нужна.
        Создавать встречу нужно <b>вручную</b>: в Telemost откройте «Создать видеовстречу»,
        скопируйте ссылку и вставьте сюда.
      </p>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="block text-sm text-gray-600 mb-1">Ссылка на Телемост *</label>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://telemost.yandex.ru/j/12345678901234567890"
            className="w-full px-3 py-2 border rounded-md text-sm font-mono"
            autoFocus
          />
          {url && !isValidUrl && (
            <p className="text-xs text-red-500 mt-1">
              Невалидная ссылка. Ожидается вид <code>https://telemost.yandex.ru/j/...</code>
            </p>
          )}
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Название встречи *</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Например: Планёрка отдела"
            className="w-full px-3 py-2 border rounded-md text-sm"
          />
        </div>
        {groups.length > 0 && (
          <div>
            <label className="block text-sm text-gray-600 mb-1">
              Отправить ссылку в Telegram-группу (опционально)
            </label>
            <select
              value={telegramGroupId}
              onChange={(e) => setTelegramGroupId(e.target.value)}
              className="w-full px-3 py-2 border rounded-md text-sm"
            >
              <option value="">Не отправлять</option>
              {groups.map(g => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </div>
        )}
        {error && <p className="text-sm text-red-500">{error}</p>}
        <div className="flex gap-2 pt-1">
          <button
            type="submit"
            disabled={loading || !isValidUrl || !title}
            className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Подключение бота...' : 'Подключить бота'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-gray-600 hover:text-gray-800 text-sm"
          >
            Отмена
          </button>
        </div>
      </form>
    </div>
  );
}
