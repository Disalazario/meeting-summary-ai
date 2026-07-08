import { useState, useEffect, useRef } from 'react';
import client from '../api/client';

/**
 * Кнопка "Отправить в Telegram" с выпадающим списком групп.
 * Props:
 *   meetingId — id встречи (обязателен)
 */
export default function SendToTelegramButton({ meetingId }) {
  const [groups, setGroups] = useState([]);
  const [open, setOpen] = useState(false);
  const [sending, setSending] = useState(null); // group_id который отправляется
  const [sent, setSent] = useState(null);        // group_id которому успешно отправлено
  const [error, setError] = useState('');
  const ref = useRef(null);

  useEffect(() => {
    client.get('/telegram/groups').then(res => setGroups(res.data)).catch(() => {});
  }, []);

  // Закрыть при клике вне
  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSend = async (group) => {
    setSending(group.id);
    setError('');
    setSent(null);
    try {
      await client.post(`/telegram/groups/${group.id}/send-link`, { meeting_id: meetingId });
      setSent(group.id);
      setTimeout(() => {
        setSent(null);
        setOpen(false);
      }, 2000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка отправки');
    } finally {
      setSending(null);
    }
  };

  if (groups.length === 0) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => { setOpen(o => !o); setError(''); }}
        className="px-3 py-1.5 bg-blue-500 text-white rounded-md hover:bg-blue-600 text-sm flex items-center gap-1.5"
        title="Отправить ссылку на созвон в Telegram-группу"
      >
        {/* Telegram icon */}
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.248l-2.012 9.475c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12L6.26 14.4l-2.95-.924c-.642-.2-.654-.642.136-.949l11.532-4.448c.535-.194 1.003.131.584.17z"/>
        </svg>
        Отправить в Telegram
      </button>

      {open && (
        <div className="absolute right-0 mt-1 bg-white border rounded-lg shadow-lg z-20 min-w-48">
          <p className="text-xs text-gray-500 px-3 pt-2 pb-1 border-b">Выберите группу:</p>
          {groups.map(group => (
            <button
              key={group.id}
              onClick={() => handleSend(group)}
              disabled={!!sending}
              className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex items-center justify-between gap-2 disabled:opacity-50"
            >
              <span>{group.name}</span>
              {sending === group.id && (
                <span className="text-xs text-gray-400">Отправка...</span>
              )}
              {sent === group.id && (
                <span className="text-xs text-green-600">Отправлено!</span>
              )}
            </button>
          ))}
          {error && (
            <p className="text-xs text-red-500 px-3 py-2 border-t">{error}</p>
          )}
        </div>
      )}
    </div>
  );
}
