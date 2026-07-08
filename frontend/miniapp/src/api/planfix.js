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

export async function sendTasksToPlanFix(meetingId, payload) {
  const { data } = await client.post(
    `/meetings/${meetingId}/tasks/send-to-planfix`,
    payload
  );
  return data;
}
