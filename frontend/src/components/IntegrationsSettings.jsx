import { useEffect, useState } from 'react';
import client from '../api/client';

/**
 * Список внешних интеграций со статусом.
 * Сейчас здесь — PlanFix (через отдельный endpoint), плюс заглушки Манго/AmoCRM.
 */
export default function IntegrationsSettings() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    client.get('/integrations/status')
      .then((res) => setItems(res.data || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h3 className="font-semibold text-gray-900 mb-1">Интеграции</h3>
      <p className="text-sm text-gray-600 mb-4">
        Состояние подключения внешних сервисов. Ключи задаются в <code className="text-xs bg-gray-100 px-1 rounded">.env</code>.
      </p>

      {loading ? (
        <div className="text-sm text-gray-500">Загрузка...</div>
      ) : (
        <div className="space-y-2">
          {items.map((it) => (
            <div
              key={it.key}
              className="flex items-start justify-between gap-3 p-3 border border-gray-200 rounded-lg"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-900">{it.name}</span>
                  <StatusBadge configured={it.configured} enabled={it.enabled} />
                </div>
                <div className="text-xs text-gray-600 mt-0.5">{it.details}</div>
              </div>
            </div>
          ))}
          {items.length === 0 && (
            <div className="text-sm text-gray-500">Интеграции не настроены.</div>
          )}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ configured, enabled }) {
  if (enabled) {
    return (
      <span className="inline-flex items-center text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded-full border border-green-200/60 font-medium">
        Активно
      </span>
    );
  }
  if (configured) {
    return (
      <span className="inline-flex items-center text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full border border-blue-200/60 font-medium">
        Ключи есть, ждёт реализации
      </span>
    );
  }
  return (
    <span className="inline-flex items-center text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full border border-gray-200/60">
      Не настроено
    </span>
  );
}
