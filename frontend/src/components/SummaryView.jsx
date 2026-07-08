import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import client from '../api/client';

export default function SummaryView({ meetingId }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);

  const loadSummary = () => {
    setLoading(true);
    client.get(`/meetings/${meetingId}/summary`)
      .then((res) => setSummary(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadSummary(); }, [meetingId]);

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      const res = await client.post(`/meetings/${meetingId}/summary/regenerate`);
      setSummary(res.data);
    } catch {}
    setRegenerating(false);
  };

  if (loading) return <div className="text-gray-500 py-4">Загрузка саммари...</div>;
  if (!summary) return <div className="text-gray-500 py-4">Саммари не найдено</div>;

  return (
    <div className="space-y-6">
      {/* Brief */}
      <div className="bg-blue-50 border-l-4 border-blue-500 p-4 rounded-r-lg">
        <h3 className="font-medium text-blue-900 mb-1">Кратко</h3>
        <p className="text-blue-800 text-sm">{summary.brief}</p>
      </div>

      {/* Full summary */}
      <div>
        <h3 className="font-medium text-gray-800 mb-2">Подробное саммари</h3>
        <div className="prose prose-sm max-w-none text-gray-700" translate="no">
          {summary.summary_text ? (
            <ReactMarkdown>{String(summary.summary_text)}</ReactMarkdown>
          ) : (
            <p className="text-gray-400 italic">Саммари ещё не сгенерировано</p>
          )}
        </div>
      </div>

      {/* Key decisions */}
      {summary.key_decisions && summary.key_decisions.length > 0 && (
        <div>
          <h3 className="font-medium text-gray-800 mb-2">Ключевые решения</h3>
          <ol className="list-decimal list-inside space-y-1 text-sm text-gray-700">
            {summary.key_decisions.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ol>
        </div>
      )}

      <button
        onClick={handleRegenerate}
        disabled={regenerating}
        className="px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
      >
        {regenerating ? 'Перегенерация...' : 'Перегенерировать'}
      </button>
    </div>
  );
}
