import { useEffect, useRef } from 'react';

/**
 * Периодический опрос: вызывает fn сразу и далее каждые intervalMs.
 * Интервал стабилен — не пересоздаётся при смене ссылки на fn.
 * enabled=false полностью отключает опрос (включая первый вызов).
 */
export default function usePolling(fn, intervalMs, { enabled = true } = {}) {
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  }, [fn]);

  useEffect(() => {
    if (!enabled) return undefined;
    fnRef.current();
    const interval = setInterval(() => fnRef.current(), intervalMs);
    return () => clearInterval(interval);
  }, [intervalMs, enabled]);
}
