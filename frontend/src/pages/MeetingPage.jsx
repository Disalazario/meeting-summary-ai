import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import client from '../api/client';
import ProcessingStatus from '../components/ProcessingStatus';
import TranscriptView from '../components/TranscriptView';
import SummaryView from '../components/SummaryView';
import TaskList from '../components/TaskList';
import ChatPanel from '../components/ChatPanel';
import NotesPanel from '../components/NotesPanel';
import SendToTelegramButton from '../components/SendToTelegramButton';
import usePolling from '../hooks/usePolling';

const TABS = [
  { key: 'transcript', label: 'Расшифровка' },
  { key: 'summary', label: 'Саммари' },
  { key: 'tasks', label: 'Задачи' },
  { key: 'notes', label: 'Заметки' },
  { key: 'chat', label: 'Чат' },
];

export default function MeetingPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [meeting, setMeeting] = useState(null);
  const [tab, setTab] = useState('transcript');
  const [loading, setLoading] = useState(true);
  const [audioBusy, setAudioBusy] = useState(false);
  const [audioProgress, setAudioProgress] = useState(0); // 0..100
  const [pdfBusy, setPdfBusy] = useState(false);

  const loadMeeting = useCallback(async () => {
    try {
      const res = await client.get(`/meetings/${id}`);
      setMeeting(res.data);
    } catch {
      navigate('/');
    } finally {
      setLoading(false);
    }
  }, [id, navigate]);

  useEffect(() => {
    loadMeeting();
  }, [loadMeeting]);

  // Poll while processing — интервал стабилен, не пересоздаётся на каждый ответ
  const processing = !!meeting && meeting.status !== 'done' && meeting.status !== 'error';
  usePolling(loadMeeting, 5000, { enabled: processing });

  const handleDelete = async () => {
    if (!window.confirm('Удалить это совещание? Это действие необратимо.')) return;
    try {
      await client.delete(`/meetings/${id}`);
      navigate('/');
    } catch {}
  };

  const handleExportPdf = async () => {
    setPdfBusy(true);
    try {
      const res = await client.get(`/meetings/${id}/export/pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${meeting.title?.slice(0, 30)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('PDF export failed:', e);
      alert('Не удалось получить PDF: ' + (e?.response?.data?.detail || e.message || 'неизвестная ошибка'));
    } finally {
      setPdfBusy(false);
    }
  };

  const handleDownloadAudio = async () => {
    setAudioBusy(true);
    setAudioProgress(0);
    try {
      const res = await client.get(`/meetings/${id}/audio`, {
        responseType: 'blob',
        timeout: 0, // отключаем axios-таймаут — крупное аудио через домашний канал может идти 1+ мин
        onDownloadProgress: (evt) => {
          if (evt.total) {
            setAudioProgress(Math.round((evt.loaded / evt.total) * 100));
          } else if (evt.loaded) {
            // total недоступен (Content-Length не пришёл) — показываем мегабайты
            setAudioProgress(Math.min(99, Math.round(evt.loaded / 1024 / 1024)));
          }
        },
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      // backend по умолчанию отдаёт opus (в 10× меньше WAV).
      // Расширение берём из Content-Type, чтобы плеер открывал корректно.
      const ct = res.headers?.['content-type'] || res.data?.type || '';
      const ext = ct.includes('ogg') || ct.includes('opus') ? 'opus' : 'wav';
      a.download = `${meeting.title?.slice(0, 30)}_${id}.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Audio download failed:', e);
      // axios responseType:blob превращает JSON-ошибку в Blob — попробуем прочитать
      let detail = e?.message || 'неизвестная ошибка';
      if (e?.response?.data instanceof Blob) {
        try {
          const txt = await e.response.data.text();
          const parsed = JSON.parse(txt);
          detail = parsed.detail || txt;
        } catch { /* ignore */ }
      } else if (e?.response?.data?.detail) {
        detail = e.response.data.detail;
      }
      alert('Не удалось скачать запись: ' + detail);
    } finally {
      setAudioBusy(false);
      setAudioProgress(0);
    }
  };

  if (loading) return <div className="text-center text-gray-500 py-12">Загрузка...</div>;
  if (!meeting) return null;

  const isDone = meeting.status === 'done';

  return (
    <div>
      <div className="flex justify-between items-start mb-6">
        <div>
          <button onClick={() => navigate('/')} className="text-sm text-blue-600 hover:text-blue-800 mb-2">&larr; Назад</button>
          <h1 className="text-2xl font-bold text-gray-800">{meeting.title}</h1>
          {meeting.date && (
            <div className="text-sm text-gray-500 mt-1">
              {new Date(meeting.date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })}
              {meeting.duration_seconds ? ` · ${Math.floor(meeting.duration_seconds / 60)} мин` : ''}
            </div>
          )}
          {meeting.meeting_url && (
            <a
              href={meeting.meeting_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline inline-flex items-center gap-1 mt-1"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              Открыть в Телемост
            </a>
          )}
        </div>
        <div className="flex gap-2 flex-wrap">
          {meeting.meeting_url && (
            <SendToTelegramButton meetingId={meeting.id} />
          )}
          {(meeting.source === 'bot' || meeting.audio_path) && (
            <button
              onClick={handleDownloadAudio}
              disabled={audioBusy}
              className="px-3 py-1.5 bg-gray-600 text-white rounded-md hover:bg-gray-700 disabled:opacity-60 disabled:cursor-not-allowed text-sm inline-flex items-center gap-2"
              title={audioBusy ? 'Файл скачивается через интернет-канал сервера...' : 'Скачать аудиозапись (может занять до минуты)'}
            >
              {audioBusy && <span className="inline-block w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
              {audioBusy
                ? (audioProgress > 0 && audioProgress <= 100
                    ? `Скачивание... ${audioProgress}%`
                    : 'Скачивание...')
                : 'Скачать запись'}
            </button>
          )}
          {isDone && (
            <button
              onClick={handleExportPdf}
              disabled={pdfBusy}
              className="px-3 py-1.5 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-60 text-sm inline-flex items-center gap-2"
            >
              {pdfBusy && <span className="inline-block w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
              {pdfBusy ? 'Подготовка...' : 'Скачать PDF'}
            </button>
          )}
          {isDone && (
            <button
              onClick={() => window.open(`/api/meetings/${id}/report`, '_blank')}
              className="px-3 py-1.5 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm"
            >
              HTML отчёт
            </button>
          )}
          <button onClick={handleDelete} className="px-3 py-1.5 bg-red-600 text-white rounded-md hover:bg-red-700 text-sm">
            Удалить
          </button>
        </div>
      </div>

      {!isDone ? (
        <div className="space-y-4">
          <ProcessingStatus
            status={meeting.status}
            errorMessage={meeting.error_message}
            progress={meeting.processing_progress}
            etaSeconds={meeting.processing_eta_seconds}
          />
          {meeting.status !== 'error' && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-start justify-between gap-4">
              <div className="text-sm text-blue-900">
                <div className="font-semibold mb-0.5">Сессия идёт — записывайте заметки</div>
                <div className="text-blue-800/90">
                  Пишите своими словами по ходу встречи. После обработки AI обогатит
                  их деталями из расшифровки, не переписывая ваш текст.
                </div>
              </div>
              <button
                onClick={() => setTab('notes')}
                className="px-3 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-medium whitespace-nowrap"
              >
                Открыть заметки
              </button>
            </div>
          )}
          {tab === 'notes' && (
            <div className="bg-white border border-gray-200 rounded-lg p-5">
              <NotesPanel meetingId={id} meetingStatus={meeting.status} />
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="border-b mb-4">
            <div className="flex gap-0">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors
                    ${tab === t.key
                      ? 'border-blue-600 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                    }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {tab === 'transcript' && <TranscriptView meetingId={id} />}
          {tab === 'summary' && <SummaryView meetingId={id} />}
          {tab === 'tasks' && <TaskList meetingId={id} />}
          {tab === 'notes' && <NotesPanel meetingId={id} meetingStatus={meeting.status} />}
          {tab === 'chat' && <ChatPanel meetingId={id} />}
        </>
      )}
    </div>
  );
}
