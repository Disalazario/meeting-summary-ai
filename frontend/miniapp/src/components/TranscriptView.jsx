import { useState, useEffect } from 'react';
import client from '../api/client';

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

const SPEAKER_COLORS = [
  'text-blue-600', 'text-green-600', 'text-purple-600',
  'text-orange-600', 'text-pink-600', 'text-teal-600',
];

export default function TranscriptView({ meetingId }) {
  const [segments, setSegments] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const { data } = await client.get(`/meetings/${meetingId}/transcript`);
        setSegments(data);
      } catch {
        setSegments([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [meetingId]);

  if (loading) {
    return <div className="p-4 text-tg-hint text-sm">Загрузка...</div>;
  }

  if (segments.length === 0) {
    return (
      <div className="p-4 text-center text-tg-hint">
        Расшифровка ещё не готова
      </div>
    );
  }

  // Маппинг спикеров к цветам
  const speakers = [...new Set(segments.map(s => s.speaker_label))];
  const speakerColor = {};
  speakers.forEach((s, i) => {
    speakerColor[s] = SPEAKER_COLORS[i % SPEAKER_COLORS.length];
  });

  return (
    <div className="p-4 space-y-3">
      {segments.map((seg, i) => (
        <div key={i} className="flex gap-2">
          <span className="text-xs text-tg-hint mt-1 w-10 flex-shrink-0 text-right">
            {formatTime(seg.start_time)}
          </span>
          <div className="flex-1 min-w-0">
            <span className={`text-xs font-semibold ${speakerColor[seg.speaker_label]}`}>
              {seg.speaker_label}
            </span>
            <p className="text-sm leading-relaxed mt-0.5">{seg.text}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
