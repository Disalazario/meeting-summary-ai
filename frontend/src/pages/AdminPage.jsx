import { useState, useEffect } from 'react';
import client from '../api/client';
import VoiceEnrollment from '../components/VoiceEnrollment';

export default function AdminPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [createdPassword, setCreatedPassword] = useState('');
  const [error, setError] = useState('');
  const [voiceUser, setVoiceUser] = useState(null);

  const loadUsers = () => {
    client.get('/users')
      .then((res) => setUsers(res.data))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadUsers(); }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    setError('');
    try {
      const res = await client.post('/users', { username, display_name: displayName });
      setCreatedPassword(res.data.password);
      setUsername('');
      setDisplayName('');
      loadUsers();
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка создания');
    }
  };

  const handleDelete = async (userId) => {
    if (!window.confirm('Удалить пользователя?')) return;
    try {
      await client.delete(`/users/${userId}`);
      loadUsers();
    } catch (err) {
      alert(err.response?.data?.detail || 'Ошибка удаления');
    }
  };

  if (loading) return <div className="text-gray-500 py-4">Загрузка...</div>;

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Управление пользователями</h1>
        <button
          onClick={() => { setShowForm(!showForm); setCreatedPassword(''); }}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm"
        >
          Создать пользователя
        </button>
      </div>

      {showForm && (
        <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Логин</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Отображаемое имя</label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>
            </div>
            {error && <div className="text-red-600 text-sm">{error}</div>}
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm"
            >
              Создать
            </button>
          </form>

          {createdPassword && (
            <div className="mt-4 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <div className="text-sm font-medium text-yellow-800 mb-1">Пароль создан (покажите пользователю)</div>
              <div className="font-mono text-lg text-yellow-900 select-all">{createdPassword}</div>
              <div className="text-xs text-yellow-600 mt-1">Этот пароль показывается только один раз!</div>
            </div>
          )}
        </div>
      )}

      <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Логин</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Имя</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Роль</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Дата создания</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {users.map((u) => (
              <tr key={u.id}>
                <td className="px-4 py-3 text-sm">{u.username}</td>
                <td className="px-4 py-3 text-sm">{u.display_name}</td>
                <td className="px-4 py-3 text-sm">
                  <span className={`px-2 py-0.5 rounded-full text-xs ${u.role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600'}`}>
                    {u.role}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-gray-500">
                  {new Date(u.created_at).toLocaleDateString('ru-RU')}
                </td>
                <td className="px-4 py-3 text-right space-x-3">
                  <button
                    onClick={() => setVoiceUser(u)}
                    className="text-blue-600 hover:text-blue-800 text-sm"
                  >
                    Голос
                  </button>
                  {u.role !== 'admin' && (
                    <button
                      onClick={() => handleDelete(u.id)}
                      className="text-red-600 hover:text-red-800 text-sm"
                    >
                      Удалить
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {voiceUser && (
        <div
          className="fixed inset-0 bg-black/40 flex items-start justify-center pt-12 z-50"
          onClick={() => setVoiceUser(null)}
        >
          <div
            className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-start mb-4">
              <h2 className="text-lg font-semibold">Голосовой профиль</h2>
              <button
                onClick={() => setVoiceUser(null)}
                className="text-gray-400 hover:text-gray-700 text-xl leading-none"
              >
                ×
              </button>
            </div>
            <VoiceEnrollment userId={voiceUser.id} userName={voiceUser.display_name} />
          </div>
        </div>
      )}
    </div>
  );
}
