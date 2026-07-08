import { useState, useEffect, useRef } from 'react';
import { getVoiceStatus, enrollVoice, deleteVoice } from '../api/voice';

const TARGET_DURATION_SEC = 30;
const MIN_DURATION_SEC = 5;
const MAX_DURATION_SEC = 60;

// Несколько фонетически богатых отрывков русской классики (~30 секунд чтения каждый).
// Для качественного голосового профиля важна именно разнообразная фонема,
// поэтому берём ровную нейтральную прозу с разными звуками.
const READING_PASSAGES = [
  {
    title: 'И. С. Тургенев. «Бежин луг»',
    text:
      'Был прекрасный июльский день, один из тех дней, которые случаются только ' +
      'тогда, когда погода установилась надолго. С самого раннего утра небо ясно; ' +
      'утренняя заря не пылает пожаром: она разливается кротким румянцем. ' +
      'Солнце — не огнистое, не раскалённое, как во время знойной засухи, не тускло-' +
      'багровое, как перед бурей, но светлое и приветно лучезарное — мирно всплывает ' +
      'под узкой и длинной тучкой, свежо просияет и погрузится в лиловый её туман.',
  },
  {
    title: 'А. П. Чехов. «Степь»',
    text:
      'Из N., уездного города Z-ой губернии, ранним июльским утром выехала и с громом ' +
      'покатила по почтовому тракту бричка. Несмотря на ранний час, в воздухе уже ' +
      'парило; время обещало быть знойным. По обе стороны дороги тянулись ровные холмы, ' +
      'покрытые жёлтой выгоревшей травой. Кое-где попадались одинокие тополя, и в их ' +
      'тени дремали запряжённые быки. День начинался долгий, тихий и жаркий.',
  },
  {
    title: 'И. А. Бунин. «Антоновские яблоки»',
    text:
      'Вспоминается мне ранняя погожая осень. Помню раннее, свежее, тихое утро. ' +
      'Помню большой, весь золотой, подсохший и поредевший сад, помню кленовые аллеи, ' +
      'тонкий аромат опавшей листвы и запах антоновских яблок, запах мёда и осенней ' +
      'свежести. Воздух так чист, точно его совсем нет, по всему саду раздаются голоса ' +
      'и скрип телег. Это работники сыплют яблоки в меры и кадушки.',
  },
];

// Стабильный выбор отрывка по userId — чтобы у одного человека всегда был один и тот же текст
function pickPassage(seed) {
  const n = String(seed || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  return READING_PASSAGES[n % READING_PASSAGES.length];
}

function fmtDate(d) {
  if (!d) return '';
  const dt = new Date(d);
  return dt.toLocaleString('ru-RU');
}

export default function VoiceEnrollment({ userId, userName }) {
  const [status, setStatus] = useState(null); // {enrolled, sample_count, updated_at}
  const [loading, setLoading] = useState(true);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const passage = pickPassage(userId);

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const startedAtRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await getVoiceStatus(userId);
        if (!cancelled) setStatus(s);
      } catch {
        if (!cancelled) setError('Не удалось загрузить статус профиля');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [userId]);

  useEffect(() => () => {
    stopStream();
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  function stopStream() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }

  async function startRecording() {
    setError(null);
    chunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mr = new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      mr.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = handleStop;
      // timeslice=1000ms — Chrome MediaRecorder без него пишет битый WebM
      // (нет Cues / duration), ffmpeg на бэке потом видит ~1 секунду.
      mr.start(1000);
      startedAtRef.current = Date.now();
      setElapsed(0);
      setRecording(true);
      timerRef.current = setInterval(() => {
        const sec = Math.floor((Date.now() - startedAtRef.current) / 1000);
        setElapsed(sec);
        if (sec >= MAX_DURATION_SEC) stopRecording();
      }, 200);
    } catch {
      setError('Не удалось получить доступ к микрофону. Разрешите запись в настройках браузера.');
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setRecording(false);
  }

  async function handleStop() {
    stopStream();
    const duration = Math.floor((Date.now() - startedAtRef.current) / 1000);
    if (duration < MIN_DURATION_SEC) {
      setError(`Слишком короткая запись (${duration} с). Нужно минимум ${MIN_DURATION_SEC} с.`);
      return;
    }
    const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
    setUploading(true);
    try {
      const result = await enrollVoice(userId, blob);
      setStatus(result);
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Не удалось сохранить голосовой профиль';
      setError(msg);
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm('Удалить голосовой профиль? Это сбросит распознавание для следующих встреч.')) {
      return;
    }
    try {
      await deleteVoice(userId);
      setStatus({ enrolled: false });
    } catch {
      setError('Не удалось удалить профиль');
    }
  }

  if (loading) {
    return <div className="text-sm text-gray-500">Загрузка...</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="font-semibold text-gray-900">Голосовой профиль</h3>
        <p className="text-sm text-gray-700 mt-1">
          {userName ? `Для пользователя «${userName}». ` : ''}
          Запишите ~30 секунд своей речи. Система будет автоматически узнавать вас в стенограммах совещаний.
        </p>
      </div>

      {status?.enrolled && (
        <div className="bg-green-50 border border-green-200 rounded p-3 text-sm">
          <div className="font-medium text-green-800">Профиль создан</div>
          <div className="text-green-700 text-xs mt-1">
            Обновлён: {fmtDate(status.updated_at)}
            {status.sample_count > 1 ? ` · образцов: ${status.sample_count}` : ''}
          </div>
        </div>
      )}
      {!status?.enrolled && (
        <div className="bg-yellow-50 border border-yellow-200 rounded p-3 text-sm text-yellow-800">
          Профиль ещё не создан. Без него спикеры будут определяться по контексту разговора (менее точно).
        </div>
      )}

      {/* Краткая инструкция */}
      <div className="text-sm text-gray-700 leading-relaxed">
        Включите запись и спокойно, в обычном темпе, прочитайте отрывок ниже.
        Можно сидя, в комнате без эха. Не переживайте за выразительность —
        нужна именно ваша обычная разговорная интонация.
      </div>

      {/* Литературный отрывок для чтения */}
      <div className="bg-amber-50 border-l-4 border-amber-400 rounded-r p-4 leading-relaxed">
        <div className="text-[11px] uppercase tracking-wider text-amber-700 font-semibold mb-2">
          Прочитайте этот отрывок
        </div>
        <p className="text-[15px] text-gray-800 font-serif" style={{ lineHeight: 1.7 }}>
          {passage.text}
        </p>
        <div className="text-xs text-amber-800 mt-3 italic font-medium">
          {passage.title}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">{error}</div>
      )}

      <div className="flex items-center gap-3">
        {!recording && !uploading && (
          <button
            onClick={startRecording}
            className="px-4 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700"
          >
            {status?.enrolled ? 'Перезаписать профиль' : 'Начать запись'}
          </button>
        )}
        {recording && (
          <button
            onClick={stopRecording}
            className="px-4 py-2 bg-red-600 text-white text-sm rounded-md hover:bg-red-700 inline-flex items-center gap-2"
          >
            <span className="inline-block w-2 h-2 rounded-full bg-white animate-pulse"></span>
            Остановить ({elapsed} c)
          </button>
        )}
        {uploading && (
          <div className="text-sm text-gray-600">Загрузка и обработка...</div>
        )}
        {status?.enrolled && !recording && !uploading && (
          <button
            onClick={handleDelete}
            className="text-sm text-red-600 hover:underline"
          >
            Удалить профиль
          </button>
        )}
      </div>

      {recording && (
        <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
          <div
            className="bg-blue-600 h-2 transition-all"
            style={{ width: `${Math.min(100, (elapsed / TARGET_DURATION_SEC) * 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}
