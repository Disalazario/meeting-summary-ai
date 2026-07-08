import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import client from '../api/client';
import { telegram } from '../telegram';
import MeetingCard from '../components/MeetingCard';

export default function HomePage() {
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  const fetchMeetings = useCallback(async () => {
    try {
      setLoading(true);
      const { data } = await client.get('/meetings');
      setMeetings(data);
      setError(null);
    } catch {
      setError('Не удалось загрузить совещания');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    telegram.hideBackButton();
    telegram.hideMainButton();
    fetchMeetings();
  }, [fetchMeetings]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-tg-button border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center">
        <p className="text-red-500 mb-4">{error}</p>
        <button
          onClick={fetchMeetings}
          className="px-4 py-2 bg-tg-button text-tg-button-text rounded-lg"
        >
          Повторить
        </button>
      </div>
    );
  }

  return (
    <div className="p-4 pb-20">
      <h1 className="text-xl font-bold mb-1">Совещания</h1>
      <p className="text-sm text-tg-hint mb-4">
        {telegram.userName}
      </p>

      {meetings.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-4xl mb-3">📋</p>
          <p className="text-tg-hint">Нет совещаний</p>
          <p className="text-sm text-tg-hint mt-1">
            Отправьте аудио боту или используйте /create
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {meetings.map(meeting => (
            <MeetingCard
              key={meeting.id}
              meeting={meeting}
              onClick={() => {
                telegram.haptic.selection();
                navigate(`/meeting/${meeting.id}`);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
