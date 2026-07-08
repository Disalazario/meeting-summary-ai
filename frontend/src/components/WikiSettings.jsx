import { useEffect, useState } from 'react';
import client from '../api/client';
import { useAuth } from '../hooks/useAuth';

/**
 * Статус Wiki.js RAG-индекса + ручной запуск синхронизации (admin only).
 */
export default function WikiSettings() {
  const { user } = useAuth();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const res = await client.get('/wiki/status');
      setStatus(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const runSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    setError(null);
    try {
      const res = await client.post('/wiki/sync');
      setSyncResult(res.data);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setSyncing(false);
    }
  };

  if (loading) return <div className="text-sm text-gray-500">Загрузка...</div>;

  const isAdmin = user?.role === 'admin';

  return (
    <div>
      <h3 className="font-semibold text-gray-900 mb-1">Wiki.js (RAG-контекст)</h3>
      <p className="text-sm text-gray-600 mb-4">
        Локальный индекс внутренней документации. Используется как контекст для саммари,
        задач и AI-чата по встрече.
      </p>

      {!status?.configured ? (
        <div className="text-sm bg-gray-50 border border-gray-200 rounded-md p-3">
          Wiki.js не настроен. Добавьте <code className="text-xs bg-gray-100 px-1 rounded">WIKI_BASE_URL</code>
          {' '}и <code className="text-xs bg-gray-100 px-1 rounded">WIKI_API_TOKEN</code> в <code>.env</code>.
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <Metric label="Страниц" value={status.total_pages} />
            <Metric label="Чанков" value={status.total_chunks} />
            <Metric
              label="Последний синк"
              value={status.last_indexed_at
                ? new Date(status.last_indexed_at).toLocaleString('ru-RU', {
                    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
                  })
                : '—'}
            />
          </div>

          {status.last_sync_summary && (
            <div className="text-xs text-gray-500">{status.last_sync_summary}</div>
          )}

          {isAdmin ? (
            <div className="flex items-center gap-2">
              <button
                onClick={runSync}
                disabled={syncing}
                className="px-3 py-1.5 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-60 text-sm"
              >
                {syncing ? 'Синхронизация...' : 'Пересинхронизировать'}
              </button>
              <span className="text-xs text-gray-500">
                Авто-синк каждый час, ручной — только если что-то срочно поменялось.
              </span>
            </div>
          ) : (
            <div className="text-xs text-gray-500">
              Ручной запуск синхронизации доступен только администратору.
            </div>
          )}

          {syncResult && (
            <div className="text-xs bg-green-50 border border-green-200 rounded-md p-3">
              <div>Обновлено: <b>{syncResult.pages_changed}</b></div>
              <div>Без изменений: {syncResult.pages_unchanged}</div>
              <div>Удалено: {syncResult.pages_deleted}</div>
              <div>Чанков проиндексировано: {syncResult.chunks_indexed}</div>
              <div>За {syncResult.elapsed_seconds.toFixed(1)}с</div>
              {syncResult.errors?.length > 0 && (
                <div className="text-red-600 mt-1">
                  Ошибок: {syncResult.errors.length}
                </div>
              )}
            </div>
          )}

          {error && (
            <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-md p-2">
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="bg-white border border-gray-200 rounded-md px-3 py-2">
      <div className="text-[11px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className="text-sm font-medium text-gray-800">{value}</div>
    </div>
  );
}
