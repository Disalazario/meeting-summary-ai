import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import client from '../api/client';

const DEBOUNCE_MS = 250;

/**
 * Компактный поисковый бар в шапке.
 * Печатаешь → debounce → top-5 в выпадающем dropdown.
 * Enter → переход на /search?q=... со всеми результатами + фильтрами.
 * Esc → закрыть dropdown.
 *
 * Использует "/" как глобальный шорткат фокуса (как у GitHub/Linear).
 */
export default function GlobalSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const inputRef = useRef(null);
  const containerRef = useRef(null);
  const debounceTimer = useRef(null);

  const runSearch = useCallback(async (query) => {
    if (!query.trim()) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const res = await client.get('/search', {
        params: { q: query, scope: 'all', limit: 5 },
      });
      setItems(res.data.items || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleChange = (e) => {
    const v = e.target.value;
    setQ(v);
    setOpen(true);
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => runSearch(v), DEBOUNCE_MS);
  };

  const submitFull = () => {
    if (!q.trim()) return;
    setOpen(false);
    navigate(`/search?q=${encodeURIComponent(q.trim())}`);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      submitFull();
    } else if (e.key === 'Escape') {
      setOpen(false);
      inputRef.current?.blur();
    }
  };

  // Отменить отложенный поиск при размонтировании.
  useEffect(() => () => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
  }, []);

  // Глобальный шорткат: "/" фокусит поиск (если не в input).
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === '/' && document.activeElement?.tagName !== 'INPUT'
          && document.activeElement?.tagName !== 'TEXTAREA') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Клик вне — закрыть dropdown.
  useEffect(() => {
    const onClick = (e) => {
      if (!containerRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  return (
    <div ref={containerRef} className="relative flex-1 max-w-md">
      <div className="relative">
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"
             fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round"
                d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
        </svg>
        <input
          ref={inputRef}
          type="search"
          value={q}
          onChange={handleChange}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Поиск по встречам…  ( / )"
          className="w-full pl-9 pr-3 py-1.5 text-sm bg-gray-50 border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 focus:bg-white transition-colors"
        />
      </div>

      {open && q.trim() && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-md shadow-lg z-40 overflow-hidden">
          {loading ? (
            <div className="px-3 py-2 text-xs text-gray-500">Поиск...</div>
          ) : items.length === 0 ? (
            <div className="px-3 py-2 text-xs text-gray-500">Ничего не найдено</div>
          ) : (
            <>
              {items.map((it) => (
                <button
                  key={it.meeting_id}
                  onClick={() => { setOpen(false); navigate(`/meetings/${it.meeting_id}`); }}
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 border-b last:border-b-0 border-gray-100"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium text-gray-800 truncate">
                      <Highlight text={it.title} query={q} />
                    </div>
                    <MatchedInBadges matched={it.matched_in} />
                  </div>
                  {it.snippet && (
                    <div className="text-xs text-gray-500 mt-0.5 line-clamp-1">
                      <Highlight text={it.snippet} query={q} />
                    </div>
                  )}
                </button>
              ))}
              <button
                onClick={submitFull}
                className="w-full text-left px-3 py-2 text-xs text-blue-600 hover:bg-blue-50 border-t border-gray-100 font-medium"
              >
                Показать все результаты для «{q}» →
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

const MATCH_LABEL = {
  title: 'Название',
  summary: 'Саммари',
  transcript: 'Расшифровка',
};

export function MatchedInBadges({ matched }) {
  if (!matched?.length) return null;
  return (
    <div className="flex gap-1 flex-shrink-0">
      {matched.map((m) => (
        <span key={m} className="text-[10px] uppercase tracking-wider bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
          {MATCH_LABEL[m] || m}
        </span>
      ))}
    </div>
  );
}

export function Highlight({ text, query }) {
  if (!text || !query) return text || '';
  const q = query.trim();
  if (!q) return text;
  // Регэксп с экранированием пользовательского ввода.
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = String(text).split(new RegExp(`(${escaped})`, 'gi'));
  return (
    <>
      {parts.map((p, i) =>
        p.toLowerCase() === q.toLowerCase()
          ? <mark key={i} className="bg-yellow-200 text-gray-900 rounded px-0.5">{p}</mark>
          : <span key={i}>{p}</span>
      )}
    </>
  );
}
