import { useState, useEffect } from 'react';
import client from '../api/client';

export default function TelegramSettings() {
  const [groups, setGroups] = useState([]);
  const [botInfo, setBotInfo] = useState(null);
  const [name, setName] = useState('');
  const [chatId, setChatId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadGroups = async () => {
    try {
      const res = await client.get('/telegram/groups');
      setGroups(res.data);
    } catch {}
  };

  const loadBotInfo = async () => {
    try {
      const res = await client.get('/telegram/bot-info');
      setBotInfo(res.data);
    } catch {
      setBotInfo(null);
    }
  };

  useEffect(() => {
    loadGroups();
    loadBotInfo();
  }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!name || !chatId) return;
    setLoading(true);
    setError('');
    try {
      await client.post('/telegram/groups', { name, chat_id: chatId });
      setName('');
      setChatId('');
      loadGroups();
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Удалить группу?')) return;
    try {
      await client.delete(`/telegram/groups/${id}`);
      loadGroups();
    } catch {}
  };

  const handleTest = async (id) => {
    try {
      await client.post(`/telegram/test/${id}`);
      alert('Тестовое сообщение отправлено');
    } catch (err) {
      alert(err.response?.data?.detail || 'Ошибка отправки');
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900">Telegram-группы</h3>
          {botInfo ? (
            <span className="text-sm font-medium text-green-700">@{botInfo.username}</span>
          ) : (
            <span className="text-sm text-gray-500">Бот не настроен</span>
          )}
        </div>
        <p className="text-sm text-gray-700 mt-1">
          Группы, в которые бот может отправлять ссылки на встречи и саммари.
          Добавьте бота администратором в группу и впишите её chat_id ниже.
        </p>
      </div>

      {groups.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b">
              <th className="pb-2">Название</th>
              <th className="pb-2">Chat ID</th>
              <th className="pb-2"></th>
            </tr>
          </thead>
          <tbody>
            {groups.map(g => (
              <tr key={g.id} className="border-b last:border-0">
                <td className="py-2">{g.name}</td>
                <td className="py-2 text-gray-500 font-mono text-xs">{g.chat_id}</td>
                <td className="py-2 text-right space-x-2">
                  <button
                    onClick={() => handleTest(g.id)}
                    className="text-blue-600 hover:text-blue-800 text-xs"
                  >
                    Тест
                  </button>
                  <button
                    onClick={() => handleDelete(g.id)}
                    className="text-red-500 hover:text-red-700 text-xs"
                  >
                    Удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <form onSubmit={handleAdd} className="flex gap-2 items-end">
        <div className="flex-1">
          <label className="block text-xs text-gray-500 mb-1">Название группы</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Команда разработки"
            className="w-full px-3 py-1.5 border rounded text-sm"
          />
        </div>
        <div className="flex-1">
          <label className="block text-xs text-gray-500 mb-1">Chat ID</label>
          <input
            type="text"
            value={chatId}
            onChange={(e) => setChatId(e.target.value)}
            placeholder="-100..."
            className="w-full px-3 py-1.5 border rounded text-sm font-mono"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !name || !chatId}
          className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? '...' : 'Добавить'}
        </button>
      </form>
      {error && <p className="text-sm text-red-500">{error}</p>}
    </div>
  );
}
