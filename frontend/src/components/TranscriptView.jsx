import { useState, useEffect, useMemo } from 'react';
import client from '../api/client';

const SPEAKER_COLORS = [
  'bg-blue-100 text-blue-800',
  'bg-green-100 text-green-800',
  'bg-purple-100 text-purple-800',
  'bg-orange-100 text-orange-800',
  'bg-pink-100 text-pink-800',
  'bg-teal-100 text-teal-800',
  'bg-yellow-100 text-yellow-800',
  'bg-red-100 text-red-800',
];

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

export default function TranscriptView({ meetingId }) {
  const [segments, setSegments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingSpeaker, setEditingSpeaker] = useState(null);
  const [newName, setNewName] = useState('');
  useEffect(() => {
    client.get(`/meetings/${meetingId}/transcript`)
      .then((res) => setSegments(res.data))
      .finally(() => setLoading(false));
  }, [meetingId]);

  // Цвет закреплён за спикером по порядку появления в транскрипте
  const speakerColorMap = useMemo(() => {
    const map = {};
    for (const seg of segments) {
      if (!(seg.speaker_label in map)) {
        map[seg.speaker_label] = SPEAKER_COLORS[Object.keys(map).length % SPEAKER_COLORS.length];
      }
    }
    return map;
  }, [segments]);

  const getSpeakerColor = (speaker) => speakerColorMap[speaker] || SPEAKER_COLORS[0];

  const handleRename = async (oldName) => {
    if (!newName.trim() || newName === oldName) {
      setEditingSpeaker(null);
      return;
    }
    try {
      await client.patch(`/meetings/${meetingId}/speakers`, { speakers: { [oldName]: newName.trim() } });
      setSegments((prev) => prev.map((s) => s.speaker_label === oldName ? { ...s, speaker_label: newName.trim() } : s));
    } catch {}
    setEditingSpeaker(null);
  };

  if (loading) return <div className="text-gray-500 py-4">Загрузка расшифровки...</div>;

  return (
    <div className="space-y-3 max-h-[70vh] overflow-y-auto">
      {segments.map((seg) => (
        <div key={seg.id} className="flex gap-3">
          <div className="text-xs text-gray-400 pt-1 min-w-[80px]">
            {formatTime(seg.start_time)}
          </div>
          <div className="flex-1">
            <div className="mb-1">
              {editingSpeaker === seg.speaker_label ? (
                <input
                  autoFocus
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onBlur={() => handleRename(seg.speaker_label)}
                  onKeyDown={(e) => e.key === 'Enter' && handleRename(seg.speaker_label)}
                  className="text-xs px-2 py-0.5 border rounded"
                />
              ) : (
                <span
                  onClick={() => { setEditingSpeaker(seg.speaker_label); setNewName(seg.speaker_label); }}
                  className={`text-xs px-2 py-0.5 rounded-full cursor-pointer ${getSpeakerColor(seg.speaker_label)}`}
                  title="Нажмите для переименования"
                >
                  {seg.speaker_label}
                </span>
              )}
            </div>
            <div className="text-sm text-gray-700">{seg.text}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
