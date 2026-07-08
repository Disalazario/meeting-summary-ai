import { useState, useEffect, useCallback } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import client from '../api/client';
import { Highlight, MatchedInBadges } from '../components/GlobalSearch';

function formatDuration(seconds) {
  if (!seconds) return '';
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m} мин`;
  const h = Math.floor(m / 60);
  return `${h} ч ${m % 60} мин`;
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const initialQ = params.get('q') || '';
  const initialScope = params.get('scope') || 'all';

  const [q, setQ] = useState(initialQ);
  const [scope, setScope] = useState(initialScope);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const runSearch = useCallback(async (query, sc) => {
    if (!query.trim()) {
      setItems([]); setTotal(0); setHasSearched(false);
      return;
    }
    setLoading(true);
    setHasSearched(true);
    try {
      const res = await client.get('/search', {
        params: { q: query, scope: sc, limit: 50 },
      });
      setItems(res.data.items || []);
      setTotal(res.data.total || 0);
    } catch {
      setItems([]); setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  // Запустить при загрузке страницы и при изменении query/scope в URL.
  useEffect(() => {
    runSearch(initialQ, initialScope);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQ, initialScope]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const next = new URLSearchParams();
    if (q.trim()) next.set('q', q.trim());
    if (scope !== 'all') next.set('scope', scope);
    setParams(next, { replace: true });
  };

  const switchScope = (newScope) => {
    setScope(newScope);
    const next = new URLSearchParams(params);
    if (newScope === 'all') next.delete('scope');
    else next.set('scope', newScope);
    setParams(next, { replace: true });
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-800 mb-4">Поиск</h1>

      <form onSubmit={handleSubmit} className="mb-5 flex gap-2">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Что искать в встречах?"
          className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          autoFocus
        />
        <button
          type="submit"
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-medium"
        >
          Найти
        </button>
      </form>

      <div className="flex items-center gap-2 mb-4" role="tablist" aria-label="Фильтр доступа">
        {[
          { v: 'all',  label: 'Все встречи' },
          { v: 'mine', label: 'Только мои' },
        ].map((opt) => (
          <button
            key={opt.v}
            type="button"
            onClick={() => switchScope(opt.v)}
            className={`px-3 py-1.5 text-sm rounded-md border ${
              scope === opt.v
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
            }`}
            role="tab"
            aria-selected={scope === opt.v}
          >
            {opt.label}
          </button>
        ))}
        {hasSearched && !loading && (
          <span className="text-sm text-gray-500 ml-2">
            Найдено: <b>{total}</b>
          </span>
        )}
      </div>

      {loading ? (
        <div className="text-gray-500 py-8">Поиск...</div>
      ) : !hasSearched ? (
        <div className="text-gray-500 py-8 text-sm">
          Введите запрос и нажмите Найти. Поиск идёт по названию, саммари и расшифровке встреч.
        </div>
      ) : items.length === 0 ? (
        <div className="text-gray-500 py-8 text-sm">
          Ничего не найдено{scope === 'mine' ? ' среди ваших встреч' : ''}.
          {scope === 'mine' && (
            <>
              {' '}
              <button onClick={() => switchScope('all')} className="text-blue-600 hover:underline">
                Поискать во всех
              </button>?
            </>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((it) => (
            <Link
              key={it.meeting_id}
              to={`/meetings/${it.meeting_id}`}
              className="block p-3.5 bg-white border border-gray-200 rounded-lg hover:border-gray-300 hover:shadow-sm transition-all"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-gray-800">
                    <Highlight text={it.title} query={initialQ} />
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5 flex flex-wrap gap-2">
                    {it.date && (
                      <span>{new Date(it.date).toLocaleDateString('ru-RU', {
                        day: 'numeric', month: 'short', year: 'numeric'
                      })}</span>
                    )}
                    {it.duration_seconds && <span>· {formatDuration(it.duration_seconds)}</span>}
                    <span>· статус: {it.status}</span>
                  </div>
                  {it.snippet && (
                    <div className="text-sm text-gray-600 mt-2 leading-relaxed">
                      <Highlight text={it.snippet} query={initialQ} />
                    </div>
                  )}
                </div>
                <MatchedInBadges matched={it.matched_in} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
