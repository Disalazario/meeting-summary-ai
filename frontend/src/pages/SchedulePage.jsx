import { useState, useCallback } from 'react';
import client from '../api/client';
import ScheduleForm from '../components/ScheduleForm';
import usePolling from '../hooks/usePolling';

const STATUS_MAP = {
  pending: { label: 'Ожидание', color: 'bg-gray-100 text-gray-700' },
  starting: { label: 'Запуск', color: 'bg-yellow-100 text-yellow-700' },
  active: { label: 'Запись', color: 'bg-red-100 text-red-700' },
  completed: { label: 'Завершено', color: 'bg-green-100 text-green-700' },
  cancelled: { label: 'Отменено', color: 'bg-gray-100 text-gray-500' },
  error: { label: 'Ошибка', color: 'bg-red-100 text-red-700' },
};

const WEEKDAYS_FULL = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];

function formatDateTime(dateStr) {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleString('ru-RU', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

function describeRecurrence(sm) {
  if ((sm.recurrence || 'none') === 'none') return null;
  if (sm.recurrence === 'weekly') {
    const day = WEEKDAYS_FULL[sm.recurrence_day ?? -1] || '?';
    return `Каждый${sm.recurrence_day === 2 ? 'у' : ''} ${day.toLowerCase()} в ${sm.recurrence_time} (${sm.timezone})`;
  }
  return sm.recurrence;
}

export default function SchedulePage() {
  const [meetings, setMeetings] = useState([]);
  const [showForm, setShowForm] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await client.get('/schedule');
      setMeetings(res.data);
    } catch {}
  }, []);

  usePolling(load, 10000);

  const handleCancel = async (id) => {
    if (!confirm('Удалить расписание?')) return;
    try {
      await client.delete(`/schedule/${id}`);
      load();
    } catch {}
  };

  const togglePause = async (sm) => {
    try {
      await client.patch(`/schedule/${sm.id}`, { is_active: !sm.is_active });
      load();
    } catch {}
  };

  const recurring = meetings.filter(m => (m.recurrence || 'none') !== 'none');
  const oneOff = meetings.filter(m => (m.recurrence || 'none') === 'none');

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Расписание</h1>
        <button
          onClick={() => setShowForm(true)}
          aria-label="Запланировать новую встречу"
          className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 text-sm"
        >
          Запланировать
        </button>
      </div>

      {showForm && (
        <div className="mb-6">
          <ScheduleForm
            onSuccess={() => { setShowForm(false); load(); }}
            onCancel={() => setShowForm(false)}
          />
        </div>
      )}

      {meetings.length === 0 ? (
        <div className="text-center text-gray-500 py-12">
          Нет запланированных встреч.
        </div>
      ) : (
        <div className="space-y-6">
          {recurring.length > 0 && (
            <Section
              title="Регулярные"
              items={recurring}
              renderItem={(sm) => (
                <RecurringRow key={sm.id} sm={sm} onTogglePause={togglePause} onCancel={handleCancel} />
              )}
            />
          )}
          {oneOff.length > 0 && (
            <Section
              title="Разовые"
              items={oneOff}
              renderItem={(sm) => (
                <OneOffRow key={sm.id} sm={sm} onCancel={handleCancel} />
              )}
            />
          )}
        </div>
      )}
    </div>
  );
}

function Section({ title, items, renderItem }) {
  return (
    <div>
      <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">{title}</h2>
      <div className="grid gap-3">
        {items.map(renderItem)}
      </div>
    </div>
  );
}

function RecurringRow({ sm, onTogglePause, onCancel }) {
  const desc = describeRecurrence(sm);
  return (
    <div className={`bg-white rounded-lg border p-4 ${!sm.is_active ? 'opacity-60' : ''}`}>
      <div className="flex justify-between items-start">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-medium text-gray-800">{sm.title}</h3>
            <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">
              Рекуррентная
            </span>
            {!sm.is_active && (
              <span className="text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded-full">
                Приостановлена
              </span>
            )}
          </div>
          <div className="text-sm text-gray-600 mt-1">{desc}</div>
          {sm.next_run_at && sm.is_active && (
            <div className="text-xs text-gray-500 mt-0.5">
              Следующий запуск: {formatDateTime(sm.next_run_at)}
            </div>
          )}
          {sm.telegram_group_name && (
            <div className="text-xs text-blue-500 mt-0.5">Telegram: {sm.telegram_group_name}</div>
          )}
          {sm.meeting_url && (
            <a href={sm.meeting_url} target="_blank" rel="noopener noreferrer"
               className="text-xs text-blue-600 hover:underline mt-0.5 inline-block">
              Открыть встречу
            </a>
          )}
        </div>
        <div className="flex flex-col items-end gap-1">
          <button
            onClick={() => onTogglePause(sm)}
            className={`text-xs px-2 py-1 rounded-md border ${
              sm.is_active
                ? 'text-amber-700 border-amber-300 hover:bg-amber-50'
                : 'text-green-700 border-green-300 hover:bg-green-50'
            }`}
          >
            {sm.is_active ? 'Приостановить' : 'Возобновить'}
          </button>
          <button
            onClick={() => onCancel(sm.id)}
            className="text-xs text-red-500 hover:text-red-700"
          >
            Удалить
          </button>
        </div>
      </div>
    </div>
  );
}

function OneOffRow({ sm, onCancel }) {
  const st = STATUS_MAP[sm.status] || STATUS_MAP.pending;
  return (
    <div className="bg-white rounded-lg border p-4">
      <div className="flex justify-between items-start">
        <div>
          <h3 className="font-medium text-gray-800">{sm.title}</h3>
          <div className="text-sm text-gray-500 mt-1">
            {formatDateTime(sm.scheduled_at)}
            {sm.telegram_group_name && (
              <span className="ml-2 text-xs text-blue-500">
                Telegram: {sm.telegram_group_name}
              </span>
            )}
          </div>
          {sm.error_message && (
            <p className="text-xs text-red-500 mt-1">{sm.error_message}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-1 rounded-full ${st.color}`}>{st.label}</span>
          {sm.status === 'pending' && (
            <button
              onClick={() => onCancel(sm.id)}
              className="text-xs text-red-500 hover:text-red-700"
            >
              Отменить
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
