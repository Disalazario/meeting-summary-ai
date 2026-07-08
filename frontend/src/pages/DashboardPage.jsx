import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import client from '../api/client';
import usePolling from '../hooks/usePolling';
import UploadForm from '../components/UploadForm';
import BotConnectForm from '../components/BotConnectForm';
import BotStatus from '../components/BotStatus';

const STATUS_MAP = {
  uploaded: { label: 'Загружено', color: 'bg-gray-100 text-gray-700 border border-gray-200' },
  waiting_bot: { label: 'Ожидание бота', color: 'bg-blue-50 text-blue-700 border border-blue-200' },
  recording: { label: 'Запись', color: 'bg-red-50 text-red-700 border border-red-200' },
  processing: { label: 'Обработка', color: 'bg-amber-50 text-amber-700 border border-amber-200' },
  transcribing: { label: 'Транскрибация', color: 'bg-amber-50 text-amber-700 border border-amber-200' },
  diarizing: { label: 'Диаризация', color: 'bg-amber-50 text-amber-700 border border-amber-200' },
  summarizing: { label: 'Генерация саммари', color: 'bg-amber-50 text-amber-700 border border-amber-200' },
  done: { label: 'Готово', color: 'bg-emerald-50 text-emerald-700 border border-emerald-200' },
  error: { label: 'Ошибка', color: 'bg-red-50 text-red-700 border border-red-200' },
};

function formatDuration(seconds) {
  if (!seconds) return '';
  const mins = Math.floor(seconds / 60);
  if (mins >= 60) {
    const hrs = Math.floor(mins / 60);
    return `${hrs}ч ${mins % 60}мин`;
  }
  return `${mins}мин`;
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

export default function DashboardPage() {
  const [meetings, setMeetings] = useState([]);
  const [activeForm, setActiveForm] = useState(null); // 'upload' | 'connect'
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all'); // 'all' | 'mine' | 'participated'
  const navigate = useNavigate();

  const loadMeetings = useCallback(async () => {
    try {
      const res = await client.get('/meetings');
      setMeetings(res.data);
    } catch {}
  }, []);

  usePolling(loadMeetings, 10000);

  const visibleMeetings = (() => {
    const q = search.trim().toLowerCase();
    return meetings.filter((m) => {
      if (filter === 'mine' && !m.is_owner) return false;
      if (filter === 'participated' && !m.participated) return false;
      if (q && !(m.title || '').toLowerCase().includes(q)) return false;
      return true;
    });
  })();

  const handleSuccess = (id) => {
    setActiveForm(null);
    navigate(`/meetings/${id}`);
  };

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-3 gap-4">
        <h1 className="text-2xl font-bold text-gray-800">Совещания</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setActiveForm(activeForm === 'connect' ? null : 'connect')}
            className={`px-4 py-2 rounded-lg text-sm font-semibold shadow-sm transition-all duration-150 ${activeForm === 'connect' ? 'bg-indigo-700 text-white shadow-indigo-200' : 'bg-indigo-600 text-white hover:bg-indigo-700 hover:shadow-md'}`}
          >
            Подключить бота к встрече
          </button>
          <button
            onClick={() => setActiveForm(activeForm === 'upload' ? null : 'upload')}
            className={`px-4 py-2 rounded-lg text-sm font-medium border transition-all duration-150 ${activeForm === 'upload' ? 'bg-blue-50 text-blue-700 border-blue-300' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`}
          >
            Загрузить запись
          </button>
        </div>
      </div>

      {/* Поиск + фильтр */}
      <div className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-center mb-4">
        <div className="relative flex-1">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по названию"
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div className="inline-flex rounded-lg border border-gray-300 bg-white overflow-hidden">
          {[
            ['all', 'Все'],
            ['participated', 'Где участвую'],
            ['mine', 'Мои'],
          ].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={[
                'text-xs px-3 py-2 border-r last:border-r-0 transition-colors',
                filter === key ? 'bg-blue-50 text-blue-700 font-semibold' : 'bg-white text-gray-600 hover:bg-gray-50',
              ].join(' ')}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="text-xs text-gray-500 px-1 self-center whitespace-nowrap">
          {visibleMeetings.length} / {meetings.length}
        </span>
      </div>

      {/* Информационная плашка о том, как работает запись */}
      <div className="mb-6 bg-indigo-50/60 border border-indigo-100 rounded-lg p-4 text-sm text-gray-700">
        <div className="flex items-start gap-3">
          <svg className="w-5 h-5 text-indigo-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <div className="font-medium text-gray-800 mb-1">Как записать совещание</div>
            <ol className="list-decimal list-inside space-y-1 text-gray-600">
              <li>Создайте встречу в <b>Telemost</b> любым удобным способом (сайт, мобильное приложение).</li>
              <li>Скопируйте ссылку вида <code className="text-xs bg-white px-1.5 py-0.5 rounded border">https://telemost.yandex.ru/j/…</code></li>
              <li>Нажмите <b>«Подключить бота к встрече»</b> и вставьте её — бот зайдёт гостем, запишет и обработает.</li>
            </ol>
            <div className="text-xs text-gray-500 mt-2">
              Можно также загрузить уже готовый аудио- или видеофайл — мы его расшифруем и сделаем саммари.
            </div>
          </div>
        </div>
      </div>

      {activeForm === 'upload' && (
        <div className="mb-6">
          <UploadForm
            onSuccess={handleSuccess}
            onCancel={() => setActiveForm(null)}
          />
        </div>
      )}
      {activeForm === 'connect' && (
        <div className="mb-6">
          <BotConnectForm
            onSuccess={handleSuccess}
            onCancel={() => setActiveForm(null)}
          />
        </div>
      )}

      {meetings.length === 0 ? (
        <div className="text-center text-gray-500 py-16 bg-white rounded-xl border border-dashed border-gray-300">
          <svg className="w-12 h-12 mx-auto text-gray-300 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
          </svg>
          Нет совещаний. Подключите бота к встрече или загрузите готовую запись.
        </div>
      ) : visibleMeetings.length === 0 ? (
        <div className="text-center text-gray-500 py-12 bg-white rounded-xl border border-dashed border-gray-300 text-sm">
          Ничего не найдено по фильтру/поиску.
        </div>
      ) : (
        <div className="grid gap-3">
          {visibleMeetings.map((m) => {
            const st = STATUS_MAP[m.status] || STATUS_MAP.uploaded;
            const isRecording = m.status === 'recording';
            return (
              <div
                key={m.id}
                className="bg-white rounded-xl border border-gray-200 hover:border-gray-300 hover:shadow-md transition-all duration-200 group"
              >
                {isRecording && (
                  <div className="px-5 pt-4">
                    <BotStatus meetingId={m.id} onStopped={loadMeetings} />
                  </div>
                )}
                <div
                  onClick={() => navigate(`/meetings/${m.id}`)}
                  className="p-5 cursor-pointer"
                >
                  <div className="flex justify-between items-start gap-3">
                    <div className="min-w-0">
                      <h3 className="font-semibold text-gray-800 group-hover:text-blue-700 transition-colors duration-150">
                        {m.title}
                        {m.source === 'bot' && (
                          <span className="ml-2 text-xs text-indigo-500 font-normal bg-indigo-50 px-1.5 py-0.5 rounded">бот</span>
                        )}
                        {m.participated && (
                          <span className="ml-2 text-xs text-emerald-700 font-medium bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded inline-flex items-center gap-1">
                            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                            </svg>
                            вы участвовали
                          </span>
                        )}
                        {m.is_owner && !m.participated && (
                          <span className="ml-2 text-xs text-gray-500 font-normal bg-gray-100 px-1.5 py-0.5 rounded">создал я</span>
                        )}
                      </h3>
                      <div className="text-sm text-gray-500 mt-1.5 flex items-center gap-1">
                        <svg className="w-3.5 h-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
                        </svg>
                        {formatDate(m.date)}
                        {m.duration_seconds ? ` · ${formatDuration(m.duration_seconds)}` : ''}
                        {m.owner_name && !m.is_owner && (
                          <span className="text-gray-400 ml-1">· {m.owner_name}</span>
                        )}
                      </div>
                      {m.meeting_url && (m.status === 'recording' || m.status === 'waiting_bot') && (
                        <a
                          href={m.meeting_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-xs text-blue-600 hover:underline mt-2 inline-flex items-center gap-1"
                        >
                          Открыть в Телемост
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                          </svg>
                        </a>
                      )}
                    </div>
                    <span className={`text-xs font-medium px-2.5 py-1 rounded-full whitespace-nowrap ${st.color}`}>
                      {st.label}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
