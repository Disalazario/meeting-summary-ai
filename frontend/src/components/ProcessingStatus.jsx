const STEPS = [
  { key: 'uploaded', label: 'Загрузка' },
  { key: 'processing', label: 'Подготовка' },
  { key: 'transcribing', label: 'Транскрибация' },
  { key: 'summarizing', label: 'Анализ' },
  { key: 'done', label: 'Готово' },
];

const STATUS_LABELS = {
  uploaded: 'Подготовка к обработке...',
  processing: 'Подготовка аудио...',
  transcribing: 'Транскрибация и диаризация...',
  summarizing: 'Генерация саммари и задач...',
  done: 'Готово',
};

function formatEta(etaSeconds) {
  if (etaSeconds == null) return 'Оценка времени...';
  if (etaSeconds < 60) return 'Осталось менее минуты';
  if (etaSeconds < 120) return 'Осталось ~1 мин';
  const mins = Math.round(etaSeconds / 60);
  return `Осталось ~${mins} мин`;
}

export default function ProcessingStatus({ status, errorMessage, progress, etaSeconds }) {
  if (status === 'error') {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
        <div className="text-red-600 font-medium mb-2">Ошибка обработки</div>
        {errorMessage && <div className="text-sm text-red-500">{errorMessage}</div>}
      </div>
    );
  }

  const currentIdx = STEPS.findIndex((s) => s.key === status);
  const isIndeterminate = progress == null;
  const displayProgress = progress != null ? Math.min(100, Math.max(0, progress)) : 0;
  const stepLabel = STATUS_LABELS[status] || 'Обработка...';

  return (
    <div className="bg-white rounded-lg shadow-sm border p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600" />
          <span className="text-gray-700 font-medium">{stepLabel}</span>
        </div>
        <span className="text-sm text-gray-500">
          {isIndeterminate ? '' : `${displayProgress}%`}
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full h-4 bg-gray-200 rounded-full overflow-hidden mb-2">
        {isIndeterminate ? (
          <div
            className="h-full rounded-full"
            style={{
              background: 'repeating-linear-gradient(-45deg, #3b82f6, #3b82f6 10px, #60a5fa 10px, #60a5fa 20px)',
              backgroundSize: '200% 100%',
              animation: 'indeterminate-stripe 1.5s linear infinite',
              width: '100%',
            }}
          />
        ) : (
          <div
            className="h-full rounded-full"
            style={{
              width: `${displayProgress}%`,
              background: 'linear-gradient(90deg, #3b82f6, #2563eb)',
              transition: 'width 0.5s ease',
            }}
          />
        )}
      </div>

      {/* ETA */}
      <div className="text-sm text-gray-500 mb-4">
        {formatEta(etaSeconds)}
      </div>

      {/* Step indicators */}
      <div className="flex items-center justify-between">
        {STEPS.map((step, idx) => {
          const isActive = idx === currentIdx;
          const isDone = idx < currentIdx;
          return (
            <div key={step.key} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center">
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium
                    ${isDone ? 'bg-green-500 text-white' : isActive ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-400'}
                    ${isActive ? 'animate-pulse' : ''}`}
                >
                  {isDone ? '\u2713' : idx + 1}
                </div>
                <div className={`text-xs mt-1 whitespace-nowrap ${isActive ? 'text-blue-600 font-medium' : isDone ? 'text-green-600' : 'text-gray-400'}`}>
                  {step.label}
                </div>
              </div>
              {idx < STEPS.length - 1 && (
                <div className={`flex-1 h-0.5 mx-1 ${isDone ? 'bg-green-500' : 'bg-gray-200'}`} />
              )}
            </div>
          );
        })}
      </div>

      {/* CSS for indeterminate animation */}
      <style>{`
        @keyframes indeterminate-stripe {
          0% { background-position: 0 0; }
          100% { background-position: 40px 0; }
        }
      `}</style>
    </div>
  );
}
