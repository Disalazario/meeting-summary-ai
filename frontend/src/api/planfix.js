import client from './client';

export async function getPlanFixStatus() {
  const { data } = await client.get('/planfix/status');
  return data;
}

export async function getPlanFixUsers() {
  const { data } = await client.get('/planfix/users');
  return data;
}

export async function getPlanFixProjects() {
  const { data } = await client.get('/planfix/projects');
  return data;
}

export async function getPlanFixTasks(projectId) {
  const { data } = await client.get(`/planfix/tasks?project_id=${projectId}`);
  return data;
}

export async function getPlanFixTasksByUser(userId) {
  // userId — строка вида "user:1" или "contact:102"
  const { data } = await client.get(`/planfix/tasks?user_id=${encodeURIComponent(userId)}`);
  return data;
}

export async function sendTasksToPlanFix(meetingId, payload) {
  const { data } = await client.post(
    `/meetings/${meetingId}/tasks/send-to-planfix`,
    payload
  );
  return data;
}

export async function triggerPlanFixSync() {
  const { data } = await client.post('/planfix/sync');
  return data;
}
