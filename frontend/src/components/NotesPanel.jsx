import { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import client from '../api/client';

const AUTOSAVE_DEBOUNCE_MS = 1200;

/**
 * Личные заметки текущего пользователя по встрече + список заметок других участников.
 *
 * Автосейв с debounce. После генерации саммари бэкенд проходит LLM-обогащением
 * и подкладывает enriched_content — он показывается отдельным блоком ниже.
 */
export default function NotesPanel({ meetingId, meetingStatus }) {
  const [myContent, setMyContent] = useState('');
  const [myEnriched, setMyEnriched] = useState(null);
  const [myEnrichedAt, setMyEnrichedAt] = useState(null);
  const [othersNotes, setOthersNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState('idle'); // 'idle' | 'saving' | 'saved' | 'error'
  const [showEnriched, setShowEnriched] = useState(true);

  // Удерживаем последнее отправленное значение, чтобы не дублировать запрос.
  const lastSavedRef = useRef('');
  const saveTimerRef = useRef(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [meRes, allRes] = await Promise.all([
        client.get(`/meetings/${meetingId}/notes/me`),
        client.get(`/meetings/${meetingId}/notes`),
      ]);
      setMyContent(meRes.data.content || '');
      lastSavedRef.current = meRes.data.content || '';
      setMyEnriched(meRes.data.enriched_content || null);
      setMyEnrichedAt(meRes.data.enriched_at || null);
      setOthersNotes(allRes.data || []);
    } catch (e) {
      console.error('Notes load failed', e);
    } finally {
      setLoading(false);
    }
  }, [meetingId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // Перезагрузить заметки, когда встреча перешла в done — там подъехало AI-обогащение.
  useEffect(() => {
    if (meetingStatus === 'done') {
      loadAll();
    }
  }, [meetingStatus, loadAll]);

  const save = useCallback(async (content) => {
    if (content === lastSavedRef.current) return;
    setSaveState('saving');
    try {
      const res = await client.put(`/meetings/${meetingId}/notes/me`, { content });
      lastSavedRef.current = content;
      // Локальный текст уже актуальный, но enriched после правки сбрасывается на бэке.
      setMyEnriched(res.data.enriched_content || null);
      setMyEnrichedAt(res.data.enriched_at || null);
      setSaveState('saved');
      setTimeout(() => setSaveState((s) => (s === 'saved' ? 'idle' : s)), 1500);
    } catch (e) {
      console.error('Notes save failed', e);
      setSaveState('error');
    }
  }, [meetingId]);

  const handleChange = (e) => {
    const v = e.target.value;
    setMyContent(v);
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => save(v), AUTOSAVE_DEBOUNCE_MS);
  };

  // Сохранить при размонтировании / уходе со страницы.
  useEffect(() => () => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    if (myContent !== lastSavedRef.current) {
      // fire-and-forget — пользователь уже уходит
      save(myContent);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveStateLabel = {
    idle: '',
    saving: 'Сохранение...',
    saved: 'Сохранено',
    error: 'Ошибка сохранения',
  }[saveState];

  if (loading) return <div className="text-gray-500 py-4">Загрузка заметок...</div>;

  const isActive = meetingStatus && meetingStatus !== 'done' && meetingStatus !== 'error';

  return (
    <div className="space-y-6">
      {isActive && (
        <div className="bg-amber-50 border-l-4 border-amber-400 px-4 py-2.5 rounded-r-md text-sm text-amber-800">
          Встреча ещё обрабатывается. Заметки можно писать прямо сейчас — после
          окончания обработки AI обогатит их контекстом из расшифровки.
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-medium text-gray-800">Мои заметки</h3>
          <span
            className={`text-xs ${
              saveState === 'error' ? 'text-red-600'
              : saveState === 'saving' ? 'text-gray-400'
              : 'text-green-600'
            }`}
          >
            {saveStateLabel}
          </span>
        </div>
        <textarea
          value={myContent}
          onChange={handleChange}
          placeholder="Пишите тезисы по ходу встречи или после неё. AI потом дополнит их деталями из расшифровки, не переписывая ваш текст."
          className="w-full min-h-[200px] border border-gray-300 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-shadow leading-relaxed"
        />
      </div>

      {myEnriched && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-medium text-gray-800">Обогащённая AI версия</h3>
            <button
              onClick={() => setShowEnriched((v) => !v)}
              className="text-xs text-blue-600 hover:underline"
            >
              {showEnriched ? 'Скрыть' : 'Показать'}
            </button>
          </div>
          {showEnriched && (
            <div className="prose prose-sm max-w-none bg-blue-50/50 border border-blue-100 rounded-lg p-4 text-gray-800" translate="no">
              <ReactMarkdown>{String(myEnriched)}</ReactMarkdown>
              {myEnrichedAt && (
                <div className="text-[11px] text-gray-400 mt-2 not-prose">
                  Сгенерировано {new Date(myEnrichedAt).toLocaleString('ru-RU')}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {othersNotes.length > 0 && (
        <div>
          <h3 className="font-medium text-gray-800 mb-2">Заметки других участников</h3>
          <div className="space-y-3">
            {othersNotes.map((n) => (
              <div key={n.id} className="bg-white border border-gray-200 rounded-lg p-3.5">
                <div className="text-xs text-gray-500 mb-1.5">
                  <span className="font-medium text-gray-700">{n.author.display_name}</span>
                  {n.updated_at && (
                    <> · {new Date(n.updated_at).toLocaleString('ru-RU')}</>
                  )}
                </div>
                <div className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
                  {n.content}
                </div>
                {n.enriched_content && (
                  <details className="mt-2">
                    <summary className="text-xs text-blue-600 hover:underline cursor-pointer">
                      Показать AI-обогащение
                    </summary>
                    <div className="prose prose-sm max-w-none mt-2 bg-blue-50/40 border border-blue-100 rounded-md p-3" translate="no">
                      <ReactMarkdown>{String(n.enriched_content)}</ReactMarkdown>
                    </div>
                  </details>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
