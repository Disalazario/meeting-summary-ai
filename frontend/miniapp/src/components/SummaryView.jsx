import { useState, useEffect } from 'react';
import client from '../api/client';

export default function SummaryView({ meetingId }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const { data } = await client.get(`/meetings/${meetingId}/summary`);
        setSummary(data);
      } catch {
        setSummary(null);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [meetingId]);

  if (loading) {
    return <div className="p-4 text-tg-hint text-sm">Загрузка...</div>;
  }

  if (!summary) {
    return (
      <div className="p-4 text-center text-tg-hint">
        Саммари ещё не готово
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Краткое саммари */}
      {summary.brief && (
        <div className="bg-tg-bg-secondary rounded-xl p-4">
          <h3 className="font-semibold text-sm text-tg-hint mb-2">Кратко</h3>
          <p className="text-sm leading-relaxed">{summary.brief}</p>
        </div>
      )}

      {/* Ключевые решения */}
      {summary.key_decisions && (() => {
        let decisions = [];
        try {
          decisions = typeof summary.key_decisions === 'string'
            ? JSON.parse(summary.key_decisions)
            : summary.key_decisions;
        } catch { decisions = []; }
        if (!Array.isArray(decisions) || decisions.length === 0) return null;
        return (
          <div className="bg-tg-bg-secondary rounded-xl p-4">
            <h3 className="font-semibold text-sm text-tg-hint mb-2">Ключевые решения</h3>
            <ul className="space-y-1">
              {decisions.map((decision, i) => (
                <li key={i} className="text-sm flex items-start gap-2">
                  <span className="text-tg-button mt-0.5">•</span>
                  <span>{decision}</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })()}

      {/* Полное саммари */}
      {summary.summary_text && (
        <div className="bg-tg-bg-secondary rounded-xl p-4">
          <h3 className="font-semibold text-sm text-tg-hint mb-2">Подробное саммари</h3>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{summary.summary_text}</p>
        </div>
      )}
    </div>
  );
}
