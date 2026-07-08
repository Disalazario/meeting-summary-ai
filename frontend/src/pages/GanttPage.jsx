import { useState, useEffect, useMemo, useRef, useLayoutEffect } from 'react';
import { getPlanFixStatus, getPlanFixUsers, getPlanFixTasksByUser } from '../api/planfix';

/**
 * Диаграмма Ганта по сотрудникам PlanFix.
 *
 * Дизайн вдохновлён Linear Roadmap, GitHub Projects (Roadmap view) и Asana Timeline:
 * — задачи группируются в свимлайны по проектам, группы сворачиваются
 * — масштаб день/неделя/месяц/квартал с фиксированным px-per-day
 * — липкая шапка с месяцами и колонкой задач
 * — клик по бару открывает модалку (не сжимает таблицу)
 * — по умолчанию показываются только активные задачи
 */

// ─────────────────────────────────────────────────────────────────────
// Утилиты
// ─────────────────────────────────────────────────────────────────────
function stripHtml(html) {
  if (!html) return '';
  try {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    return (doc.body.textContent || '').replace(/\s+/g, ' ').trim();
  } catch {
    return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  }
}

function parseDate(str) {
  if (!str) return null;
  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d;
}

function startOfDay(d) {
  const r = new Date(d);
  r.setHours(0, 0, 0, 0);
  return r;
}

function daysBetween(a, b) {
  return Math.round((startOfDay(b) - startOfDay(a)) / 86400000);
}

function addDays(d, n) {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

function fmtShort(d) {
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
}

function fmtFull(d) {
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function fmtMonth(d) {
  return d.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
}

// ─────────────────────────────────────────────────────────────────────
// Масштабы (как в Linear)
// ─────────────────────────────────────────────────────────────────────
const ZOOM_PRESETS = {
  day:     { label: 'День',    pxPerDay: 36 },
  week:    { label: 'Неделя',  pxPerDay: 12 },
  month:   { label: 'Месяц',   pxPerDay: 4 },
  quarter: { label: 'Квартал', pxPerDay: 1.5 },
};

function autoZoom(totalDays) {
  if (totalDays <= 60) return 'day';
  if (totalDays <= 180) return 'week';
  if (totalDays <= 540) return 'month';
  return 'quarter';
}

// ─────────────────────────────────────────────────────────────────────
// Палитра проектов — soft-цвета, как в Linear/Asana
// ─────────────────────────────────────────────────────────────────────
const PROJECT_PALETTE = [
  { bar: '#6366f1', soft: '#eef2ff', text: '#4338ca' }, // indigo
  { bar: '#10b981', soft: '#ecfdf5', text: '#047857' }, // emerald
  { bar: '#f59e0b', soft: '#fffbeb', text: '#b45309' }, // amber
  { bar: '#ec4899', soft: '#fdf2f8', text: '#be185d' }, // pink
  { bar: '#06b6d4', soft: '#ecfeff', text: '#0e7490' }, // cyan
  { bar: '#8b5cf6', soft: '#f5f3ff', text: '#6d28d9' }, // violet
  { bar: '#14b8a6', soft: '#f0fdfa', text: '#0f766e' }, // teal
  { bar: '#f43f5e', soft: '#fff1f2', text: '#be123c' }, // rose
];

function colorForProject(projectName) {
  if (!projectName) return { bar: '#94a3b8', soft: '#f1f5f9', text: '#475569' }; // slate
  let h = 0;
  for (let i = 0; i < projectName.length; i++) h = (h * 31 + projectName.charCodeAt(i)) >>> 0;
  return PROJECT_PALETTE[h % PROJECT_PALETTE.length];
}

const OVERDUE_COLOR = { bar: '#dc2626', soft: '#fef2f2', text: '#b91c1c' };

// ─────────────────────────────────────────────────────────────────────
// Группировка задач
// ─────────────────────────────────────────────────────────────────────
function isOverdue(task, today) {
  if (!task.is_active) return false;
  if (!task.end_date) return false;
  return parseDate(task.end_date) < today;
}

function groupByProject(tasks) {
  const groups = new Map();
  for (const t of tasks) {
    const key = t.project_name || (t.project_id ? `Проект #${t.project_id}` : 'Без проекта');
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(t);
  }
  return groups;
}

// ─────────────────────────────────────────────────────────────────────
// Главный компонент
// ─────────────────────────────────────────────────────────────────────
export default function GanttPage() {
  const [configured, setConfigured] = useState(false);
  const [users, setUsers] = useState([]);
  const [userId, setUserId] = useState('');
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedTask, setSelectedTask] = useState(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [search, setSearch] = useState('');
  const [zoom, setZoom] = useState('auto');
  const [collapsed, setCollapsed] = useState(new Set());
  const [pfAccount, setPfAccount] = useState(null);
  const [pfSync, setPfSync] = useState(null);

  const timelineRef = useRef(null);

  // Загрузка конфига и пользователей
  useEffect(() => {
    getPlanFixStatus()
      .then((data) => {
        setConfigured(data.configured);
        if (data.account) setPfAccount(data.account);
        if (data.sync) setPfSync(data.sync);
        if (data.configured) return getPlanFixUsers().then(setUsers);
      })
      .catch(() => {})
      .finally(() => setInitialLoading(false));
  }, []);

  // Загрузка задач при смене сотрудника
  useEffect(() => {
    if (!userId) { setTasks([]); return; }
    setLoading(true);
    setError(null);
    setSelectedTask(null);
    setCollapsed(new Set());
    getPlanFixTasksByUser(userId)
      .then(setTasks)
      .catch((e) => setError('Ошибка загрузки задач: ' + (e.message || 'неизвестная')))
      .finally(() => setLoading(false));
  }, [userId]);

  const today = useMemo(() => startOfDay(new Date()), []);

  // Отфильтрованные задачи
  const filteredTasks = useMemo(() => {
    const q = search.trim().toLowerCase();
    return tasks.filter((t) => {
      if (!t.start_date) return false;
      if (!showCompleted && !t.is_active) return false;
      if (q && !t.name.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [tasks, showCompleted, search]);

  // Границы таймлайна
  const { timelineStart, timelineEnd, totalDays } = useMemo(() => {
    if (filteredTasks.length === 0) {
      const start = addDays(today, -7);
      const end = addDays(today, 30);
      return { timelineStart: start, timelineEnd: end, totalDays: daysBetween(start, end) };
    }
    let min = Infinity, max = -Infinity;
    for (const t of filteredTasks) {
      const s = parseDate(t.start_date);
      const e = parseDate(t.end_date);
      if (s) { min = Math.min(min, s.getTime()); max = Math.max(max, s.getTime()); }
      if (e) { min = Math.min(min, e.getTime()); max = Math.max(max, e.getTime()); }
    }
    // Включить «сегодня» в видимый диапазон
    min = Math.min(min, today.getTime());
    max = Math.max(max, today.getTime());
    const start = addDays(new Date(min), -3);
    const end = addDays(new Date(max), 7);
    return { timelineStart: start, timelineEnd: end, totalDays: Math.max(daysBetween(start, end), 7) };
  }, [filteredTasks, today]);

  // Текущий zoom (auto → presets)
  const activeZoom = zoom === 'auto' ? autoZoom(totalDays) : zoom;
  const pxPerDay = ZOOM_PRESETS[activeZoom].pxPerDay;
  const timelineWidth = Math.max(totalDays * pxPerDay, 800);

  // Месяцы для шапки
  const months = useMemo(() => {
    const arr = [];
    let cur = new Date(timelineStart.getFullYear(), timelineStart.getMonth(), 1);
    while (cur <= timelineEnd) {
      const monthStart = cur < timelineStart ? timelineStart : new Date(cur);
      const nextMonth = new Date(cur.getFullYear(), cur.getMonth() + 1, 1);
      const monthEnd = nextMonth > timelineEnd ? timelineEnd : nextMonth;
      arr.push({
        label: fmtMonth(monthStart),
        offsetPx: daysBetween(timelineStart, monthStart) * pxPerDay,
        widthPx: daysBetween(monthStart, monthEnd) * pxPerDay,
      });
      cur = nextMonth;
    }
    return arr;
  }, [timelineStart, timelineEnd, pxPerDay]);

  // Недельные риски (для day/week видов)
  const showWeekTicks = activeZoom === 'day' || activeZoom === 'week';
  const weekTicks = useMemo(() => {
    if (!showWeekTicks) return [];
    const arr = [];
    let cur = new Date(timelineStart);
    // Сдвигаем к понедельнику
    const dow = (cur.getDay() + 6) % 7; // 0=Mon
    cur = addDays(cur, -dow);
    while (cur <= timelineEnd) {
      const offsetPx = daysBetween(timelineStart, cur) * pxPerDay;
      arr.push({ offsetPx, label: fmtShort(cur) });
      cur = addDays(cur, 7);
    }
    return arr;
  }, [timelineStart, timelineEnd, pxPerDay, showWeekTicks]);

  // Группы (только из filteredTasks)
  const groups = useMemo(() => {
    const m = groupByProject(filteredTasks);
    const arr = [];
    for (const [name, items] of m.entries()) {
      items.sort((a, b) => parseDate(a.start_date) - parseDate(b.start_date));
      const overdueCount = items.filter((t) => isOverdue(t, today)).length;
      const earliest = items.length ? parseDate(items[0].start_date) : null;
      arr.push({ name, items, overdueCount, earliest });
    }
    // Сначала группы с просроченными, затем по самой ранней задаче
    arr.sort((a, b) => {
      if (a.overdueCount !== b.overdueCount) return b.overdueCount - a.overdueCount;
      return (a.earliest || 0) - (b.earliest || 0);
    });
    return arr;
  }, [filteredTasks, today]);

  // Позиция «сегодня»
  const todayPx = daysBetween(timelineStart, today) * pxPerDay;

  // Авто-прокрутка к «сегодня» при изменении сотрудника или зума
  useLayoutEffect(() => {
    if (!timelineRef.current || filteredTasks.length === 0) return;
    const container = timelineRef.current;
    container.scrollLeft = Math.max(0, todayPx - container.clientWidth / 3);
  }, [userId, activeZoom, filteredTasks.length, todayPx]);

  // Подсчёты
  const overdueTotal = useMemo(
    () => filteredTasks.filter((t) => isOverdue(t, today)).length,
    [filteredTasks, today],
  );
  const tasksWithoutDates = tasks.filter((t) => !t.start_date).length;
  const hiddenCompleted = useMemo(
    () => (showCompleted ? 0 : tasks.filter((t) => !t.is_active).length),
    [tasks, showCompleted],
  );

  function toggleGroup(name) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  }

  // ───────────────────────────────────────────────────────────────────
  if (initialLoading) return <div className="text-gray-500 py-8 text-center">Загрузка...</div>;
  if (!configured) return <div className="text-gray-500 py-8 text-center">PlanFix не настроен</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-800">Диаграмма Ганта</h1>
        {overdueTotal > 0 && (
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-red-700 bg-red-50 border border-red-200 px-3 py-1.5 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
            {overdueTotal} просрочено
          </span>
        )}
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-2 items-center bg-white border rounded-lg p-2.5 shadow-sm">
        <select
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          className="text-sm border border-gray-300 rounded-md px-3 py-1.5 bg-white min-w-[220px] focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Выберите сотрудника</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>{u.name}</option>
          ))}
        </select>

        <div className="h-6 w-px bg-gray-200 mx-1" />

        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по названию"
          className="text-sm border border-gray-300 rounded-md px-3 py-1.5 bg-white min-w-[200px] focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        <div className="h-6 w-px bg-gray-200 mx-1" />

        <div className="inline-flex rounded-md border border-gray-200 overflow-hidden">
          {[['auto', 'Авто'], ['day', 'День'], ['week', 'Неделя'], ['month', 'Месяц'], ['quarter', 'Квартал']].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setZoom(key)}
              className={[
                'text-xs px-2.5 py-1.5 border-r last:border-r-0 transition-colors',
                zoom === key ? 'bg-blue-50 text-blue-700 font-medium' : 'bg-white text-gray-600 hover:bg-gray-50',
              ].join(' ')}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="h-6 w-px bg-gray-200 mx-1" />

        <label className="inline-flex items-center gap-2 text-xs text-gray-600 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={showCompleted}
            onChange={(e) => setShowCompleted(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          Показать завершённые
        </label>

        <div className="flex-1" />

        {userId && tasks.length > 0 && (
          <span className="text-xs text-gray-500">
            {filteredTasks.length}
            {!showCompleted && hiddenCompleted > 0 && ` из ${tasks.length - tasksWithoutDates}`}
            {' активн.'}
            {tasksWithoutDates > 0 && ` · ${tasksWithoutDates} без дат`}
          </span>
        )}
      </div>

      {/* Hints */}
      {users.length === 0 && pfSync && (
        <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2">
          {pfSync.status === 'ok'
            ? 'Пользователи PlanFix ещё не подгружены — попробуйте обновить страницу через минуту.'
            : pfSync.status === 'error'
              ? 'Ошибка синхронизации PlanFix: ' + (pfSync.error || '')
              : 'PlanFix-синхронизация ещё не запущена. Подождите 30 секунд после старта backend.'}
        </div>
      )}

      {error && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
          {error}
        </div>
      )}

      {loading && (
        <div className="text-gray-500 py-12 text-center">
          <div className="inline-block w-6 h-6 border-2 border-gray-200 border-t-blue-600 rounded-full animate-spin mb-2" />
          <div className="text-sm">Загрузка задач из PlanFix...</div>
        </div>
      )}

      {!loading && !userId && (
        <div className="text-gray-400 py-16 text-center text-sm">
          Выберите сотрудника, чтобы увидеть его задачи на временной шкале
        </div>
      )}

      {!loading && userId && filteredTasks.length === 0 && !error && (
        <div className="text-gray-500 py-12 text-center text-sm">
          {tasks.length === 0
            ? 'У этого сотрудника нет задач'
            : !showCompleted
              ? 'У этого сотрудника нет активных задач с датами'
              : 'Нет задач, подходящих под фильтр'}
        </div>
      )}

      {/* Gantt */}
      {!loading && filteredTasks.length > 0 && (
        <div className="bg-white border rounded-lg overflow-hidden shadow-sm">
          <div className="flex">
            {/* Left: sticky tasks column */}
            <div className="flex-shrink-0 w-72 border-r bg-gray-50/40">
              {/* Header */}
              <div className="h-14 border-b px-4 flex items-center bg-gray-50">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Задача</span>
              </div>

              {/* Groups */}
              {groups.map((group) => {
                const color = colorForProject(group.name);
                const isCollapsed = collapsed.has(group.name);
                return (
                  <div key={group.name}>
                    {/* Group header */}
                    <div
                      onClick={() => toggleGroup(group.name)}
                      className="h-9 border-b px-3 flex items-center cursor-pointer hover:bg-gray-50 group"
                      style={{ backgroundColor: color.soft }}
                      title={group.name}
                    >
                      <svg
                        className={`w-3.5 h-3.5 mr-2 flex-shrink-0 transition-transform ${isCollapsed ? '' : 'rotate-90'}`}
                        style={{ color: color.text }}
                        fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                      </svg>
                      <span className="text-xs font-semibold truncate flex-1" style={{ color: color.text }}>
                        {group.name}
                      </span>
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-white/70" style={{ color: color.text }}>
                        {group.items.length}
                      </span>
                      {group.overdueCount > 0 && (
                        <span className="ml-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-red-100 text-red-700">
                          {group.overdueCount}
                        </span>
                      )}
                    </div>
                    {/* Task rows */}
                    {!isCollapsed && group.items.map((task) => {
                      const overdue = isOverdue(task, today);
                      return (
                        <div
                          key={task.id}
                          onClick={() => setSelectedTask(task)}
                          className={[
                            'h-9 border-b px-3 flex items-center cursor-pointer transition-colors',
                            selectedTask?.id === task.id ? 'bg-blue-50' : 'hover:bg-gray-50',
                          ].join(' ')}
                          title={task.name}
                        >
                          <span className="w-1 h-1 rounded-full mr-2 flex-shrink-0" style={{ backgroundColor: overdue ? OVERDUE_COLOR.bar : color.bar }} />
                          <span className="text-xs text-gray-700 truncate flex-1">{task.name}</span>
                          {overdue && (
                            <span className="ml-1 text-[9px] font-medium text-red-700 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded">!</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>

            {/* Right: scrollable timeline */}
            <div className="flex-1 overflow-x-auto" ref={timelineRef}>
              <div style={{ width: timelineWidth }} className="relative">
                {/* Header: months + (optional) weeks */}
                <div className="h-14 border-b bg-gray-50 sticky top-0 z-10">
                  {/* Months */}
                  <div className="h-7 relative border-b border-gray-200">
                    {months.map((m, i) => (
                      <div
                        key={i}
                        className="absolute top-0 h-full border-r border-gray-200 flex items-center px-2"
                        style={{ left: m.offsetPx, width: m.widthPx }}
                      >
                        <span className="text-[11px] font-semibold text-gray-600 capitalize whitespace-nowrap">
                          {m.label}
                        </span>
                      </div>
                    ))}
                  </div>
                  {/* Week ticks (only on dense zoom) */}
                  <div className="h-7 relative">
                    {showWeekTicks && weekTicks.map((w, i) => (
                      <div
                        key={i}
                        className="absolute top-0 h-full border-r border-gray-100 flex items-center px-1.5"
                        style={{ left: w.offsetPx }}
                      >
                        <span className="text-[10px] text-gray-400 whitespace-nowrap">{w.label}</span>
                      </div>
                    ))}
                    {!showWeekTicks && (
                      <div className="text-[10px] text-gray-400 px-2 leading-7">
                        {ZOOM_PRESETS[activeZoom].label.toLowerCase()}-вид
                      </div>
                    )}
                  </div>
                </div>

                {/* Today line — поверх рядов */}
                {todayPx >= 0 && todayPx <= timelineWidth && (
                  <div
                    className="absolute top-0 bottom-0 z-20 pointer-events-none"
                    style={{ left: todayPx }}
                  >
                    <div className="absolute top-0 left-0 w-px h-full bg-red-500/70" />
                    <div className="absolute top-1 -translate-x-1/2 bg-red-500 text-white text-[10px] font-semibold px-2 py-0.5 rounded-full shadow whitespace-nowrap">
                      Сегодня · {fmtShort(today)}
                    </div>
                  </div>
                )}

                {/* Rows */}
                {groups.map((group) => {
                  const color = colorForProject(group.name);
                  const isCollapsed = collapsed.has(group.name);
                  return (
                    <div key={group.name}>
                      {/* Group strip */}
                      <div
                        className="h-9 border-b relative"
                        style={{ backgroundColor: color.soft }}
                      >
                        {months.map((m, mi) => (
                          <div key={mi} className="absolute top-0 bottom-0 w-px bg-white/40" style={{ left: m.offsetPx }} />
                        ))}
                      </div>
                      {/* Task rows */}
                      {!isCollapsed && group.items.map((task, idx) => {
                        const start = parseDate(task.start_date);
                        const end = parseDate(task.end_date) || addDays(start, 1);
                        const offsetPx = daysBetween(timelineStart, start) * pxPerDay;
                        const widthPx = Math.max(daysBetween(start, end), 1) * pxPerDay;
                        const overdue = isOverdue(task, today);
                        const bar = overdue ? OVERDUE_COLOR.bar : color.bar;
                        const isSelected = selectedTask?.id === task.id;
                        const tooltip = `${task.name}\n${fmtFull(start)} → ${task.end_date ? fmtFull(end) : 'нет дедлайна'}${overdue ? '\n⚠ Просрочена' : ''}`;
                        return (
                          <div
                            key={task.id}
                            className={[
                              'h-9 border-b border-gray-100 relative',
                              idx % 2 === 1 ? 'bg-gray-50/30' : '',
                              isSelected ? '!bg-blue-50' : '',
                            ].join(' ')}
                          >
                            {/* Vertical month gridlines */}
                            {months.map((m, mi) => (
                              <div key={mi} className="absolute top-0 bottom-0 w-px bg-gray-100" style={{ left: m.offsetPx }} />
                            ))}
                            {/* Bar */}
                            <div
                              onClick={() => setSelectedTask(task)}
                              className="absolute top-1.5 h-6 rounded-md cursor-pointer flex items-center px-2 overflow-hidden transition-all duration-150 hover:brightness-110 hover:shadow-md hover:z-10"
                              style={{
                                left: offsetPx,
                                width: Math.max(widthPx, 6),
                                backgroundColor: bar,
                                boxShadow: isSelected ? `0 0 0 2px ${bar}55, 0 2px 8px ${bar}40` : undefined,
                              }}
                              title={tooltip}
                            >
                              {widthPx > 24 && (
                                <span className="text-[10px] text-white truncate font-medium drop-shadow-sm">
                                  {task.name}
                                </span>
                              )}
                              {/* Маркер начала — для очень коротких баров */}
                              {widthPx <= 8 && (
                                <span className="absolute inset-0 rounded-md ring-2 ring-white/40" />
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Footer legend */}
          <div className="border-t bg-gray-50/60 px-4 py-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-[11px] text-gray-600">
            <div className="flex items-center gap-1.5">
              <span className="inline-block w-3 h-2 rounded-sm bg-red-500" />
              <span>Просрочена</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="inline-block w-px h-3 bg-red-500" />
              <span>Сегодня</span>
            </div>
            <div className="text-gray-400">
              Цвета баров — по проектам
            </div>
            <div className="flex-1" />
            <div className="text-gray-400">
              Клик по задаче — детали
            </div>
          </div>
        </div>
      )}

      {/* Modal */}
      {selectedTask && (
        <TaskDetailModal task={selectedTask} onClose={() => setSelectedTask(null)} account={pfAccount} today={today} />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Модалка с деталями
// ─────────────────────────────────────────────────────────────────────
function TaskDetailModal({ task, onClose, account, today }) {
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const planfixUrl = account ? `https://${account}.planfix.ru/task/${task.id}` : null;
  const start = parseDate(task.start_date);
  const end = parseDate(task.end_date);
  const overdue = isOverdue(task, today);
  const color = colorForProject(task.project_name);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4 animate-fade-in"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl max-w-xl w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top stripe */}
        <div className="h-1.5" style={{ backgroundColor: overdue ? OVERDUE_COLOR.bar : color.bar }} />

        <div className="p-6 space-y-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              {task.project_name && (
                <div
                  className="inline-block text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded mb-2"
                  style={{ backgroundColor: color.soft, color: color.text }}
                >
                  {task.project_name}
                </div>
              )}
              <h2 className="text-base font-semibold text-gray-900 leading-snug">{task.name}</h2>
            </div>
            <button
              onClick={onClose}
              aria-label="Закрыть"
              className="text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-md p-1.5 transition-colors flex-shrink-0"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {overdue && (
            <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-800">
              <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
              </svg>
              <span>Дедлайн прошёл — задача просрочена</span>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 text-sm">
            <Field label="Статус">
              <span
                className="inline-block px-2 py-0.5 rounded-full text-[11px] font-medium text-white"
                style={{ backgroundColor: task.status_color }}
              >
                {task.status_name}
              </span>
            </Field>
            <Field label="Дата создания">{start ? fmtFull(start) : '—'}</Field>
            <Field label="Дедлайн">{end ? fmtFull(end) : 'Не указан'}</Field>
            {task.assigner && <Field label="Постановщик">{task.assigner.name}</Field>}
          </div>

          {task.assignees?.length > 0 && (
            <div>
              <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-1.5">Исполнители</div>
              <div className="flex flex-wrap gap-1.5">
                {task.assignees.map((a) => (
                  <span
                    key={a.id}
                    className="inline-flex items-center text-xs px-2.5 py-1 rounded-full border font-medium"
                    style={{ backgroundColor: color.soft, color: color.text, borderColor: color.bar + '40' }}
                  >
                    {a.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {task.description && (
            <div>
              <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-1.5">Описание</div>
              <p className="text-xs text-gray-700 bg-gray-50 border rounded-lg p-3 max-h-40 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                {stripHtml(task.description) || '—'}
              </p>
            </div>
          )}

          {planfixUrl && (
            <a
              href={planfixUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-800"
            >
              Открыть в PlanFix
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          )}
        </div>
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
        .animate-fade-in { animation: fadeIn 0.15s ease-out forwards; }
      `}</style>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <div className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      <div className="text-xs text-gray-800 font-medium">{children}</div>
    </div>
  );
}
