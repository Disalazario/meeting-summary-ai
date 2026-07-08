import { useState, useEffect } from 'react';
import { getTelegramStatus, createTelegramLink, unlinkTelegram } from '../api/telegramLink';

export default function TelegramLink() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [linkInfo, setLinkInfo] = useState(null); // {deeplink, expires_in_seconds}
  const [error, setError] = useState(null);
  const [linking, setLinking] = useState(false);

  // Опрос статуса (каждые 5 сек, пока пользователь ждёт привязки)
  useEffect(() => {
    let cancelled = false;
    let interval = null;

    async function refresh() {
      try {
        const s = await getTelegramStatus();
        if (cancelled) return;
        setStatus(s);
        if (s.linked && linkInfo) {
          // Привязка состоялась — убрать deeplink-блок
          setLinkInfo(null);
          setLinking(false);
        }
      } catch {
        if (!cancelled) setError('Не удалось загрузить статус');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    refresh();
    if (linkInfo) {
      interval = setInterval(refresh, 5000);
    }
    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [linkInfo]);

  async function startLink() {
    setError(null);
    setLinking(true);
    try {
      const info = await createTelegramLink();
      setLinkInfo(info);
      // открыть в новой вкладке
      window.open(info.deeplink, '_blank', 'noopener,noreferrer');
    } catch (e) {
      setError(e?.response?.data?.detail || 'Не удалось создать ссылку привязки');
      setLinking(false);
    }
  }

  async function handleUnlink() {
    if (!window.confirm('Отвязать Telegram? Уведомления о совещаниях перестанут приходить.')) {
      return;
    }
    try {
      await unlinkTelegram();
      setStatus({ linked: false });
    } catch {
      setError('Не удалось отвязать');
    }
  }

  if (loading) {
    return <div className="text-sm text-gray-500">Загрузка...</div>;
  }

  return (
    <div className="space-y-3">
      <div>
        <h3 className="font-semibold text-gray-900">Уведомления в Telegram</h3>
        <p className="text-sm text-gray-700 mt-1">
          Привяжите Telegram — после каждого совещания, где распознан ваш голос,
          вам в личку придёт краткое саммари и ссылка на полный отчёт.
        </p>
      </div>

      {status?.linked ? (
        <div className="bg-green-50 border border-green-200 rounded p-3 text-sm flex items-center justify-between gap-3">
          <div>
            <div className="font-medium text-green-800">Telegram привязан</div>
            <div className="text-green-700 text-xs mt-0.5">
              chat_id: <span className="font-mono">{status.telegram_id}</span>
            </div>
          </div>
          <button
            onClick={handleUnlink}
            className="text-sm text-red-600 hover:underline whitespace-nowrap"
          >
            Отвязать
          </button>
        </div>
      ) : (
        <div className="bg-yellow-50 border border-yellow-200 rounded p-3 text-sm text-yellow-800">
          Telegram не привязан — уведомления приходить не будут.
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">{error}</div>
      )}

      {linkInfo && (
        <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-900 space-y-2">
          <div className="font-medium">Откроется бот в Telegram.</div>
          <div className="text-xs">
            Нажмите кнопку <b>«Запустить» / «Start»</b> в чате — привязка пройдёт автоматически.
            Если вкладка не открылась, перейдите по ссылке вручную:
          </div>
          <a
            href={linkInfo.deeplink}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-xs font-mono break-all text-blue-700 hover:underline"
          >
            {linkInfo.deeplink}
          </a>
          <div className="text-[11px] text-blue-700">
            Ссылка действует ~10 минут, одноразовая. Эта страница сама обновится, когда привязка состоится.
          </div>
        </div>
      )}

      {!status?.linked && !linkInfo && (
        <button
          onClick={startLink}
          disabled={linking}
          className="px-4 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          Привязать Telegram
        </button>
      )}
    </div>
  );
}
