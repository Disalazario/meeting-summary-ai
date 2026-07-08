import { useState, useEffect } from 'react';
import client from '../api/client';
import { getPlanFixStatus, getPlanFixUsers, getPlanFixProjects, sendTasksToPlanFix } from '../api/planfix';

export default function TaskList({ meetingId }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  // Inline edit state — taskId, на которой включён режим редактирования, и черновик
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState({ description: '', context: '', assignee: '', deadline: '' });
  const [editSaving, setEditSaving] = useState(false);

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
  const [deadline, setDeadline] = useState('');        // global deadline
  const [sending, setSending] = useState(false);
  const [sendResults, setSendResults] = useState(null);
  const [pfError, setPfError] = useState(null);

  // Load tasks
  useEffect(() => {
    client.get(`/meetings/${meetingId}/tasks`)
      .then((res) => setTasks(res.data))
      .finally(() => setLoading(false));
  }, [meetingId]);

  // Check PlanFix status
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
      .catch(() => setPfConfigured(false));
  }, []);

  const deleteTask = async (taskId) => {
    if (!confirm('Удалить задачу?')) return;
    try {
      await client.delete(`/meetings/${meetingId}/tasks/${taskId}`);
      setTasks(prev => prev.filter(t => t.id !== taskId));
      setSelected(prev => { const next = new Set(prev); next.delete(taskId); return next; });
    } catch {}
  };

  const startEdit = (task) => {
    setEditingId(task.id);
    setEditDraft({
      description: task.description || '',
      context: task.context || '',
      assignee: task.assignee || '',
      deadline: task.deadline || '',
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
  };

  const saveEdit = async (taskId) => {
    const desc = editDraft.description.trim();
    if (!desc) {
      alert('Описание задачи не может быть пустым');
      return;
    }
    setEditSaving(true);
    try {
      const res = await client.patch(`/meetings/${meetingId}/tasks/${taskId}`, {
        description: desc,
        context: editDraft.context.trim(),
        assignee: editDraft.assignee.trim(),
        deadline: editDraft.deadline.trim(),
      });
      setTasks(prev => prev.map(t => t.id === taskId ? { ...t, ...res.data } : t));
      setEditingId(null);
    } catch (e) {
      alert('Не удалось сохранить изменения: ' + (e?.response?.data?.detail || e.message));
    } finally {
      setEditSaving(false);
    }
  };

  const toggleDone = async (task) => {
    try {
      const res = await client.patch(`/meetings/${meetingId}/tasks/${task.id}`, { done: !task.done });
      setTasks(prev => prev.map(t => t.id === task.id ? { ...t, ...res.data } : t));
    } catch {}
  };

  const toggleSelect = (taskId) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  };

  const selectAll = () => {
    const unsent = tasks.filter(t => !t.planfix_task_id).map(t => t.id);
    if (selected.size === unsent.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(unsent));
    }
  };

  const handleSend = async () => {
    if (selected.size === 0) return;
    setSending(true);
    setSendResults(null);
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

      // Update local task state with planfix IDs
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
    } catch (e) {
      setSendResults([{ success: false, error: e.message || 'Ошибка отправки' }]);
    } finally {
      setSending(false);
    }
  };

  if (loading) return <div className="text-gray-500 py-4">Загрузка задач...</div>;
  if (tasks.length === 0) return <div className="text-gray-500 py-4">Задач не обнаружено</div>;

  const unsentTasks = tasks.filter(t => !t.planfix_task_id);

  return (
    <div className="space-y-4">
      {/* Task list */}
      <div className="space-y-2">
        {tasks.map((task) => (
          <div
            key={task.id}
            className="flex items-start gap-3 p-3.5 bg-white rounded-lg border border-gray-200 hover:border-gray-300 hover:shadow-sm transition-all duration-150"
          >
            {/* Selection checkbox (PlanFix) */}
            {pfConfigured && !task.planfix_task_id && (
              <input
                type="checkbox"
                checked={selected.has(task.id)}
                onChange={() => toggleSelect(task.id)}
                className="mt-1 h-4 w-4 rounded border-blue-300 text-blue-600"
                title="Выбрать для PlanFix"
              />
            )}

            <div className="flex-1 min-w-0">
              {editingId === task.id ? (
                <div className="space-y-2">
                  <textarea
                    value={editDraft.description}
                    onChange={(e) => setEditDraft(d => ({ ...d, description: e.target.value }))}
                    placeholder="Описание задачи"
                    rows={2}
                    className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    autoFocus
                  />
                  <textarea
                    value={editDraft.context}
                    onChange={(e) => setEditDraft(d => ({ ...d, context: e.target.value }))}
                    placeholder="Контекст / зачем (необязательно)"
                    rows={2}
                    className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-xs italic focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={editDraft.assignee}
                      onChange={(e) => setEditDraft(d => ({ ...d, assignee: e.target.value }))}
                      placeholder="Исполнитель"
                      className="flex-1 border border-gray-300 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <input
                      type="text"
                      value={editDraft.deadline}
                      onChange={(e) => setEditDraft(d => ({ ...d, deadline: e.target.value }))}
                      placeholder="Срок"
                      className="flex-1 border border-gray-300 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                  <div className="flex gap-2 pt-1">
                    <button
                      onClick={() => saveEdit(task.id)}
                      disabled={editSaving}
                      className="px-3 py-1 bg-blue-600 text-white text-xs rounded-md hover:bg-blue-700 disabled:opacity-60"
                    >
                      {editSaving ? 'Сохранение...' : 'Сохранить'}
                    </button>
                    <button
                      onClick={cancelEdit}
                      disabled={editSaving}
                      className="px-3 py-1 border border-gray-300 text-gray-700 text-xs rounded-md hover:bg-gray-50"
                    >
                      Отмена
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className={`text-sm leading-relaxed ${task.done ? 'text-gray-400 line-through' : 'text-gray-800'}`}>
                    {task.description}
                  </div>
                  {task.context && (
                    <div className="text-xs text-gray-500 mt-1 italic">
                      {task.context}
                    </div>
                  )}

                  <div className="flex flex-wrap gap-2 mt-2 items-center">
                    <label className="inline-flex items-center gap-1 text-xs text-gray-500 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={!!task.done}
                        onChange={() => toggleDone(task)}
                        className="h-3.5 w-3.5 rounded border-gray-300 text-blue-600"
                      />
                      Выполнено
                    </label>
                    {task.assignee && (
                      <span className="inline-flex items-center text-xs bg-gray-100 text-gray-600 px-2.5 py-1 rounded-full border border-gray-200/60">
                        <svg className="w-3 h-3 mr-1 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0" />
                        </svg>
                        {task.assignee}
                      </span>
                    )}
                    {task.deadline && (
                      <span className="inline-flex items-center text-xs bg-amber-50 text-amber-700 px-2.5 py-1 rounded-full border border-amber-200/60">
                        <svg className="w-3 h-3 mr-1 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
                        </svg>
                        {task.deadline}
                      </span>
                    )}
                    {task.planfix_task_id && (
                      <span className="inline-flex items-center text-xs bg-green-50 text-green-700 px-2.5 py-1 rounded-full border border-green-200/60 font-medium">
                        <svg className="w-3 h-3 mr-1 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        PlanFix #{task.planfix_task_id}
                      </span>
                    )}
                  </div>
                </>
              )}

              {/* Per-task assignee selector */}
              {pfConfigured && selected.has(task.id) && !task.planfix_task_id && pfUsers.length > 0 && (
                <select
                  value={assigneeIds[task.id] || ''}
                  onChange={(e) => setAssigneeIds(prev => ({ ...prev, [task.id]: e.target.value }))}
                  className="mt-2 text-xs border border-gray-300 rounded-lg px-2 py-1 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-shadow"
                >
                  <option value="">Исполнитель</option>
                  {pfUsers.map(u => (
                    <option key={u.id} value={u.id}>{u.name}</option>
                  ))}
                </select>
              )}
            </div>

            {editingId !== task.id && (
              <div className="flex items-start gap-0.5 flex-shrink-0">
                <button
                  onClick={() => startEdit(task)}
                  className="text-gray-300 hover:text-blue-600 p-1.5 rounded-md hover:bg-blue-50 transition-colors duration-150"
                  title="Редактировать задачу"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 011.13-1.897L16.863 4.487zm0 0L19.5 7.125" />
                  </svg>
                </button>
                <button
                  onClick={() => deleteTask(task.id)}
                  className="text-gray-300 hover:text-red-500 p-1.5 rounded-md hover:bg-red-50 transition-colors duration-150"
                  title="Удалить задачу"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* PlanFix panel */}
      {pfConfigured && unsentTasks.length > 0 && (
        <div className="bg-gradient-to-br from-slate-50 to-gray-50 border border-gray-200 rounded-xl p-5 space-y-4 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-blue-100 flex items-center justify-center">
                <svg className="w-3.5 h-3.5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                </svg>
              </div>
              <h3 className="text-sm font-semibold text-gray-700">Отправить в PlanFix</h3>
            </div>
            <button
              onClick={selectAll}
              className="text-xs text-blue-600 hover:text-blue-800 hover:underline font-medium transition-colors"
            >
              {selected.size === unsentTasks.length ? 'Снять всё' : 'Выбрать всё'}
            </button>
          </div>

          {pfError && (
            <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {pfError}
            </div>
          )}

          {pfLoading ? (
            <div className="text-xs text-gray-500">Загрузка данных PlanFix...</div>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-3">
                <select
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                  className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 bg-white min-w-[140px] focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-shadow"
                >
                  <option value="">Проект</option>
                  {pfProjects.map(p => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>

                <select
                  value={creatorId}
                  onChange={(e) => setCreatorId(e.target.value)}
                  className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 bg-white min-w-[140px] focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-shadow"
                >
                  <option value="">Постановщик</option>
                  {pfUsers.map(u => (
                    <option key={u.id} value={u.id}>{u.name}</option>
                  ))}
                </select>
              </div>

              <div className="flex flex-wrap gap-3 items-center">
                <label className="text-sm text-gray-600 font-medium">Дата выполнения:</label>
                <input
                  type="date"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                  className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-shadow"
                />

                <button
                  onClick={handleSend}
                  disabled={selected.size === 0 || sending}
                  className="text-sm bg-blue-600 text-white px-5 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed ml-auto font-medium shadow-sm hover:shadow transition-all duration-150"
                >
                  {sending ? 'Отправка...' : `Отправить (${selected.size})`}
                </button>
              </div>
            </div>
          )}

          {/* Results */}
          {sendResults && (
            <div className="space-y-1.5 bg-white rounded-lg border border-gray-200 p-3">
              {sendResults.map((r, i) => (
                <div
                  key={i}
                  className={`flex items-center gap-2 text-xs px-2 py-1.5 rounded-md ${
                    r.success
                      ? 'text-green-700 bg-green-50'
                      : 'text-red-700 bg-red-50'
                  }`}
                >
                  {r.success ? (
                    <svg className="w-3.5 h-3.5 text-green-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  ) : (
                    <svg className="w-3.5 h-3.5 text-red-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                    </svg>
                  )}
                  <span>
                    {r.success
                      ? `Задача #${r.task_id} → PlanFix #${r.planfix_task_id}`
                      : `Ошибка задачи #${r.task_id}: ${r.error}`
                    }
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
