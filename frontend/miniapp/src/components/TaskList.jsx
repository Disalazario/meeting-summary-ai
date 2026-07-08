import { useState, useEffect, useCallback } from 'react';
import client from '../api/client';
import { telegram } from '../telegram';
import { getPlanFixStatus, getPlanFixUsers, getPlanFixProjects, sendTasksToPlanFix } from '../api/planfix';

export default function TaskList({ meetingId }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  // PlanFix state
  const [pfConfigured, setPfConfigured] = useState(false);
  const [pfUsers, setPfUsers] = useState([]);
  const [pfProjects, setPfProjects] = useState([]);
  const [pfLoading, setPfLoading] = useState(false);

  // Selection & form state
  const [selected, setSelected] = useState(new Set());
  const [projectId, setProjectId] = useState('');
  const [creatorId, setCreatorId] = useState('');
  const [assigneeIds, setAssigneeIds] = useState({});  // per-task assignee: { taskId: userId }
  const [deadline, setDeadline] = useState('');
  const [sending, setSending] = useState(false);
  const [sendResults, setSendResults] = useState(null);
  const [showPfPanel, setShowPfPanel] = useState(false);
  const [pfError, setPfError] = useState(null);

  // Load tasks
  useEffect(() => {
    async function load() {
      try {
        const { data } = await client.get(`/meetings/${meetingId}/tasks`);
        setTasks(data);
      } catch {
        setTasks([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [meetingId]);

  // Check PlanFix
  useEffect(() => {
    getPlanFixStatus()
      .then((data) => {
        setPfConfigured(data.configured);
        if (data.configured) {
          setPfLoading(true);
          Promise.all([getPlanFixUsers(), getPlanFixProjects()])
            .then(([users, projects]) => {
              setPfUsers(users);
              setPfProjects(projects);
            })
            .catch(() => {
              setPfError('Не удалось загрузить данные PlanFix');
            })
            .finally(() => setPfLoading(false));
        }
      })
      .catch(() => {});
  }, []);

  const toggleSelect = (taskId) => {
    telegram.haptic.selection();
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  };

  const selectAll = () => {
    telegram.haptic.impact('light');
    const unsent = tasks.filter(t => !t.planfix_task_id).map(t => t.id);
    if (selected.size === unsent.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(unsent));
    }
  };

  const handleSend = useCallback(async () => {
    if (selected.size === 0) {
      telegram.showAlert('Выберите задачи для отправки');
      return;
    }

    const confirmed = await new Promise(resolve => {
      telegram.showConfirm(
        `Отправить ${selected.size} задач(и) в PlanFix?`,
        resolve
      );
    });
    if (!confirmed) return;

    setSending(true);
    setSendResults(null);
    telegram.haptic.impact('medium');

    try {
      const payload = {
        task_ids: [...selected],
        project_id: projectId ? parseInt(projectId) : null,
        creator_id: creatorId || null,
        deadline: deadline || null,
        assignee_ids: Object.fromEntries(
          [...selected]
            .filter(taskId => assigneeIds[taskId])
            .map(taskId => [String(taskId), assigneeIds[taskId]])
        ),
      };

      const results = await sendTasksToPlanFix(meetingId, payload);
      setSendResults(results);

      const successCount = results.filter(r => r.success).length;
      const failCount = results.filter(r => !r.success).length;

      const successMap = {};
      for (const r of results) {
        if (r.success && r.planfix_task_id) {
          successMap[r.task_id] = r.planfix_task_id;
        }
      }
      setTasks(prev => prev.map(t =>
        successMap[t.id]
          ? { ...t, planfix_task_id: successMap[t.id], planfix_sent_at: new Date().toISOString() }
          : t
      ));
      setSelected(new Set());

      telegram.haptic.notification(failCount === 0 ? 'success' : 'warning');
      telegram.showAlert(
        failCount === 0
          ? `Отправлено ${successCount} задач в PlanFix`
          : `Отправлено: ${successCount}, ошибок: ${failCount}`
      );
    } catch (e) {
      telegram.haptic.notification('error');
      telegram.showAlert('Ошибка отправки: ' + (e.message || 'неизвестная ошибка'));
    } finally {
      setSending(false);
    }
  }, [selected, projectId, creatorId, assigneeIds, deadline, meetingId]);

  if (loading) {
    return <div className="p-4 text-tg-hint text-sm">Загрузка...</div>;
  }

  if (tasks.length === 0) {
    return (
      <div className="p-4 text-center text-tg-hint">
        Задачи не найдены
      </div>
    );
  }

  const unsentTasks = tasks.filter(t => !t.planfix_task_id);

  return (
    <div className="p-4 space-y-3">
      {/* Task list */}
      {tasks.map(task => (
        <div
          key={task.id}
          className="bg-tg-bg-secondary rounded-xl p-3"
        >
          <div className="flex items-start gap-3">
            {/* PlanFix selection checkbox */}
            {pfConfigured && showPfPanel && !task.planfix_task_id && (
              <div
                onClick={(e) => { e.stopPropagation(); toggleSelect(task.id); }}
                className={`w-5 h-5 rounded-md border-2 flex-shrink-0 mt-0.5 flex items-center justify-center cursor-pointer
                  ${selected.has(task.id) ? 'bg-blue-500 border-blue-500' : 'border-tg-hint'}`}
              >
                {selected.has(task.id) && (
                  <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </div>
            )}

            <div className="flex-1 min-w-0">
              <p className="text-sm">{task.description}</p>
              <div className="flex flex-wrap gap-2 mt-1">
                {task.assignee && (
                  <span className="text-xs text-tg-hint">{task.assignee}</span>
                )}
                {task.deadline && (
                  <span className="text-xs text-tg-hint">{task.deadline}</span>
                )}
                {task.planfix_task_id && (
                  <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                    PF #{task.planfix_task_id}
                  </span>
                )}
              </div>

              {/* Per-task assignee selector */}
              {pfConfigured && showPfPanel && selected.has(task.id) && !task.planfix_task_id && pfUsers.length > 0 && (
                <select
                  value={assigneeIds[task.id] || ''}
                  onChange={(e) => setAssigneeIds(prev => ({ ...prev, [task.id]: e.target.value }))}
                  className="mt-1 w-full text-xs border rounded-lg px-2 py-1 bg-white"
                >
                  <option value="">Исполнитель</option>
                  {pfUsers.map(u => (
                    <option key={u.id} value={u.id}>{u.name}</option>
                  ))}
                </select>
              )}
            </div>
          </div>
        </div>
      ))}

      {/* PlanFix panel toggle & controls */}
      {pfConfigured && unsentTasks.length > 0 && (
        <div className="space-y-3 pt-2">
          <button
            onClick={() => { telegram.haptic.impact('light'); setShowPfPanel(!showPfPanel); }}
            className="w-full text-sm text-center py-2 rounded-xl bg-tg-bg-secondary text-tg-link font-medium"
          >
            {showPfPanel ? 'Скрыть PlanFix' : 'Отправить в PlanFix'}
          </button>

          {showPfPanel && (
            <div className="space-y-3 bg-tg-bg-secondary rounded-xl p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">PlanFix</span>
                <button onClick={selectAll} className="text-xs text-tg-link">
                  {selected.size === unsentTasks.length ? 'Снять всё' : 'Выбрать всё'}
                </button>
              </div>

              {pfError && (
                <div className="text-xs text-red-500 bg-red-50 rounded-lg px-3 py-2">
                  {pfError}
                </div>
              )}

              {pfLoading ? (
                <div className="text-xs text-tg-hint">Загрузка...</div>
              ) : (
                <div className="space-y-2">
                  <select
                    value={projectId}
                    onChange={(e) => setProjectId(e.target.value)}
                    className="w-full text-sm border rounded-lg px-3 py-2 bg-white"
                  >
                    <option value="">Проект</option>
                    {pfProjects.map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>

                  <select
                    value={creatorId}
                    onChange={(e) => setCreatorId(e.target.value)}
                    className="w-full text-sm border rounded-lg px-3 py-2 bg-white"
                  >
                    <option value="">Постановщик</option>
                    {pfUsers.map(u => (
                      <option key={u.id} value={u.id}>{u.name}</option>
                    ))}
                  </select>

                  <div className="flex items-center gap-2">
                    <label className="text-sm text-tg-hint whitespace-nowrap">Дата выполнения:</label>
                    <input
                      type="date"
                      value={deadline}
                      onChange={(e) => setDeadline(e.target.value)}
                      className="flex-1 text-sm border rounded-lg px-3 py-2 bg-white"
                    />
                  </div>

                  <button
                    onClick={handleSend}
                    disabled={selected.size === 0 || sending}
                    className="w-full text-sm bg-tg-button text-tg-button-text py-2.5 rounded-lg font-medium disabled:opacity-50"
                  >
                    {sending ? 'Отправка...' : `Отправить (${selected.size})`}
                  </button>
                </div>
              )}

              {/* Results */}
              {sendResults && (
                <div className="text-xs space-y-1">
                  {sendResults.map((r, i) => (
                    <div key={i} className={r.success ? 'text-green-600' : 'text-red-500'}>
                      {r.success
                        ? `#${r.task_id} → PF #${r.planfix_task_id}`
                        : `#${r.task_id}: ${r.error}`
                      }
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
