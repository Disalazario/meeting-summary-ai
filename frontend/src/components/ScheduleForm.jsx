import { useState, useEffect } from 'react';
import client from '../api/client';

const WEEKDAYS = [
  { value: 0, label: 'Пн' },
  { value: 1, label: 'Вт' },
  { value: 2, label: 'Ср' },
  { value: 3, label: 'Чт' },
  { value: 4, label: 'Пт' },
  { value: 5, label: 'Сб' },
  { value: 6, label: 'Вс' },
];

const TIMEZONES = [
  'Europe/Moscow',
  'Europe/Kaliningrad',
  'Asia/Yekaterinburg',
  'Asia/Novosibirsk',
  'Asia/Krasnoyarsk',
  'Asia/Irkutsk',
  'Asia/Vladivostok',
];

export default function ScheduleForm({ onSuccess, onCancel }) {
  const [title, setTitle] = useState('');
  const [meetingUrl, setMeetingUrl] = useState('');
  const [recurrence, setRecurrence] = useState('none'); // 'none' | 'weekly'
  const [scheduledAt, setScheduledAt] = useState('');   // datetime-local
  const [recurrenceDay, setRecurrenceDay] = useState(4); // Friday
  const [recurrenceTime, setRecurrenceTime] = useState('09:30');
  const [timezone, setTimezone] = useState('Europe/Moscow');
  const [telegramGroupId, setTelegramGroupId] = useState('');
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const isValidUrl = /^https?:\/\/telemost\.yandex\.(ru|com)\/j\/\d{6,20}$/.test(meetingUrl);
  const isValidTime = /^([01]\d|2[0-3]):([0-5]\d)$/.test(recurrenceTime);

  useEffect(() => {
    client.get('/telegram/groups').then(res => setGroups(res.data)).catch(() => {});
  }, []);

  const canSubmit = () => {
    if (!title || !isValidUrl) return false;
    if (recurrence === 'none') return !!scheduledAt;
    return isValidTime && recurrenceDay >= 0 && recurrenceDay <= 6;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!canSubmit()) return;

    const payload = {
      title,
      meeting_url: meetingUrl.trim(),
      recurrence,
      timezone,
      telegram_group_id: telegramGroupId ? parseInt(telegramGroupId) : null,
    };

    if (recurrence === 'none') {
      const dt = new Date(scheduledAt);
      if (dt <= new Date()) {
        setError('Время должно быть в будущем');
        return;
      }
      payload.scheduled_at = dt.toISOString();
    } else {
      payload.recurrence_day = recurrenceDay;
      payload.recurrence_time = recurrenceTime;
    }

    setLoading(true);
    setError('');
    try {
      await client.post('/schedule', payload);
      onSuccess();
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка планирования');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg border p-5">
      <h3 className="font-semibold text-gray-800 mb-1">Запланировать встречу</h3>
      <p className="text-xs text-gray-500 mb-4">
        В назначенное время бот подключится к Телемосту по сохранённой ссылке как гость.
        Встречу нужно создать заранее в Telemost — скопируйте её ссылку сюда.
      </p>

      {/* Тип: одноразовая / еженедельная */}
      <div className="mb-4 flex gap-2" role="radiogroup" aria-label="Тип расписания">
        {[
          { v: 'none',   label: 'Одноразовая' },
          { v: 'weekly', label: 'Еженедельно' },
        ].map((opt) => (
          <button
            key={opt.v}
            type="button"
            onClick={() => setRecurrence(opt.v)}
            className={`px-3 py-1.5 text-sm rounded-md border ${
              recurrence === opt.v
                ? 'bg-purple-600 text-white border-purple-600'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
            }`}
            role="radio"
            aria-checked={recurrence === opt.v}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="space-y-3" aria-label="Планирование встречи">
        <div>
          <label htmlFor="schedule-title" className="block text-sm text-gray-600 mb-1">Название *</label>
          <input
            id="schedule-title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={recurrence === 'weekly' ? 'Например: Еженедельная планёрка' : 'Например: Планёрка отдела'}
            autoComplete="off"
            className="w-full px-3 py-2 border rounded-md text-sm"
          />
        </div>
        <div>
          <label htmlFor="schedule-url" className="block text-sm text-gray-600 mb-1">Ссылка на Телемост *</label>
          <input
            id="schedule-url"
            type="text"
            value={meetingUrl}
            onChange={(e) => setMeetingUrl(e.target.value)}
            placeholder="https://telemost.yandex.ru/j/12345678901234567890"
            autoComplete="off"
            className="w-full px-3 py-2 border rounded-md text-sm font-mono"
          />
          {meetingUrl && !isValidUrl && (
            <p className="text-xs text-red-500 mt-1">Невалидная ссылка на Телемост</p>
          )}
        </div>

        {recurrence === 'none' ? (
          <div>
            <label htmlFor="schedule-datetime" className="block text-sm text-gray-600 mb-1">Дата и время *</label>
            <input
              id="schedule-datetime"
              type="datetime-local"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
              className="w-full px-3 py-2 border rounded-md text-sm"
            />
          </div>
        ) : (
          <>
            <div>
              <span className="block text-sm text-gray-600 mb-1">День недели *</span>
              <div className="flex gap-1" role="radiogroup" aria-label="День недели">
                {WEEKDAYS.map((d) => (
                  <button
                    key={d.value}
                    type="button"
                    onClick={() => setRecurrenceDay(d.value)}
                    className={`px-3 py-1.5 text-sm rounded-md border ${
                      recurrenceDay === d.value
                        ? 'bg-purple-600 text-white border-purple-600'
                        : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                    }`}
                    role="radio"
                    aria-checked={recurrenceDay === d.value}
                  >
                    {d.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex gap-3">
              <div className="flex-1">
                <label htmlFor="schedule-time" className="block text-sm text-gray-600 mb-1">Время *</label>
                <input
                  id="schedule-time"
                  type="time"
                  value={recurrenceTime}
                  onChange={(e) => setRecurrenceTime(e.target.value)}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div className="flex-1">
                <label htmlFor="schedule-tz" className="block text-sm text-gray-600 mb-1">Таймзона</label>
                <select
                  id="schedule-tz"
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                >
                  {TIMEZONES.map((tz) => (
                    <option key={tz} value={tz}>{tz}</option>
                  ))}
                </select>
              </div>
            </div>
          </>
        )}

        <div>
          <label htmlFor="schedule-telegram-group" className="block text-sm text-gray-600 mb-1">Telegram-группа (опционально)</label>
          <select
            id="schedule-telegram-group"
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
        {error && <p className="text-sm text-red-500" role="alert">{error}</p>}
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={loading || !canSubmit()}
            className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Планирование...' : 'Запланировать'}
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
