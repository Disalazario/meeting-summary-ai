import { useState, useEffect } from 'react';
import client from '../api/client';

export default function BotStatus({ meetingId, onStopped }) {
  const [botInfo, setBotInfo] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const [stopping, setStopping] = useState(false);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await client.get('/bot/active');
        const bot = res.data.find(b => b.meeting_id === meetingId);
        setBotInfo(bot || null);
        if (bot?.started_at) {
          const start = new Date(bot.started_at);
          setElapsed(Math.floor((Date.now() - start.getTime()) / 1000));
        }
      } catch {}
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [meetingId]);

  // Tick timer
  useEffect(() => {
    const timer = setInterval(() => setElapsed(prev => prev + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const handleStop = async () => {
    if (!confirm('Остановить запись?')) return;
    setStopping(true);
    try {
      await client.post(`/bot/stop/${meetingId}`);
      onStopped?.();
    } catch {}
    setStopping(false);
  };

  const formatTime = (s) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    return `${m}:${String(sec).padStart(2, '0')}`;
  };

  if (!botInfo) return null;

  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <span className="relative flex h-3 w-3">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
        </span>
        <span className="text-sm font-medium text-red-700">REC</span>
        <span className="text-sm text-red-600 font-mono">{formatTime(elapsed)}</span>
        {botInfo.participants > 0 && (
          <span className="text-xs text-gray-500">
            {botInfo.participants} участн.
          </span>
        )}
      </div>
      <button
        onClick={handleStop}
        disabled={stopping}
        className="px-3 py-1 bg-red-600 text-white rounded text-xs hover:bg-red-700 disabled:opacity-50"
      >
        {stopping ? 'Остановка...' : 'Остановить'}
      </button>
    </div>
  );
}
