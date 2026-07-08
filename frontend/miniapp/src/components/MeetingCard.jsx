const STATUS_MAP = {
  uploaded: { label: 'Загружено', color: 'bg-gray-400' },
  processing: { label: 'Обработка...', color: 'bg-yellow-500' },
  transcribing: { label: 'Транскрибация...', color: 'bg-yellow-500' },
  diarizing: { label: 'Диаризация...', color: 'bg-yellow-500' },
  summarizing: { label: 'Саммари...', color: 'bg-yellow-500' },
  done: { label: 'Готово', color: 'bg-green-500' },
  error: { label: 'Ошибка', color: 'bg-red-500' },
};

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDuration(seconds) {
  if (!seconds) return '';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export default function MeetingCard({ meeting, onClick }) {
  const status = STATUS_MAP[meeting.status] || STATUS_MAP.uploaded;

  return (
    <div
      onClick={onClick}
      className="bg-tg-bg-secondary rounded-xl p-4 active:opacity-70 transition-opacity cursor-pointer"
    >
      <div className="flex items-start justify-between">
        <h3 className="font-medium text-tg-text flex-1 mr-2 line-clamp-2">
          {meeting.title}
        </h3>
        <span className={`${status.color} text-white text-xs px-2 py-0.5 rounded-full whitespace-nowrap`}>
          {status.label}
        </span>
      </div>

      <div className="flex items-center gap-3 mt-2 text-xs text-tg-hint">
        {meeting.date && <span>{formatDate(meeting.date)}</span>}
        {meeting.duration_seconds && (
          <span>{formatDuration(meeting.duration_seconds)}</span>
        )}
        {meeting.source === 'bot' && <span>🤖 Бот</span>}
      </div>
    </div>
  );
}
