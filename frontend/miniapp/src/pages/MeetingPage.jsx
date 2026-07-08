import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import client from '../api/client';
import { telegram } from '../telegram';
import { useBackButton } from '../hooks/useTelegram';
import SummaryView from '../components/SummaryView';
import TranscriptView from '../components/TranscriptView';
import TaskList from '../components/TaskList';
import ChatPanel from '../components/ChatPanel';

const TABS = [
  { id: 'summary', label: 'Саммари' },
  { id: 'transcript', label: 'Расшифровка' },
  { id: 'tasks', label: 'Задачи' },
  { id: 'chat', label: 'Чат' },
];

export default function MeetingPage() {
  const { id } = useParams();
  const [meeting, setMeeting] = useState(null);
  const [activeTab, setActiveTab] = useState('summary');
  const [loading, setLoading] = useState(true);

  useBackButton('/');

  useEffect(() => {
    async function load() {
      try {
        const { data } = await client.get(`/meetings/${id}`);
        setMeeting(data);
      } catch {
        telegram.showAlert('Не удалось загрузить совещание');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  const handleExportPdf = useCallback(async () => {
    // В Telegram WebView обычный download через blob+a.click() работает
    // нестабильно (особенно iOS). Просим backend сгенерировать PDF и
    // отправить его файлом в чат с ботом — пользователь получит как
    // обычный документ Telegram.
    telegram.showMainButtonProgress();
    try {
      await client.post(`/meetings/${id}/export/pdf/send`);
      telegram.showAlert('PDF отправлен в чат с ботом. Откройте чат, чтобы скачать.');
      telegram.haptic.notification('success');
    } catch (err) {
      const detail = err?.response?.data?.detail || 'неизвестная ошибка';
      telegram.showAlert('Не удалось отправить PDF: ' + detail);
      telegram.haptic.notification('error');
    } finally {
      telegram.hideMainButtonProgress();
    }
  }, [id]);

  useEffect(() => {
    if (meeting?.status === 'done' && activeTab !== 'chat') {
      telegram.showMainButton('Отправить PDF в чат', handleExportPdf);
    } else {
      telegram.hideMainButton();
    }
    return () => telegram.hideMainButton();
  }, [meeting, activeTab, handleExportPdf]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-tg-button border-t-transparent" />
      </div>
    );
  }

  if (!meeting) {
    return (
      <div className="p-4 text-center text-tg-hint">
        Совещание не найдено
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <div className="px-4 pt-3 pb-2">
        <h1 className="font-bold text-lg line-clamp-1">{meeting.title}</h1>
        {meeting.status !== 'done' && (
          <p className="text-sm text-yellow-600 mt-1">
            Статус: {meeting.status}
          </p>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-tg-bg-secondary px-2 overflow-x-auto">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => {
              telegram.haptic.selection();
              setActiveTab(tab.id);
            }}
            className={`px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-tg-button text-tg-button'
                : 'border-transparent text-tg-hint'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'summary' && <SummaryView meetingId={id} />}
        {activeTab === 'transcript' && <TranscriptView meetingId={id} />}
        {activeTab === 'tasks' && <TaskList meetingId={id} />}
        {activeTab === 'chat' && <ChatPanel meetingId={id} />}
      </div>
    </div>
  );
}
