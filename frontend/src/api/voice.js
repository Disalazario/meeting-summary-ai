import client from './client';

export async function getVoiceStatus(userId) {
  const { data } = await client.get(`/users/${userId}/voice`);
  return data;
}

export async function enrollVoice(userId, blob, filename = 'enroll.webm') {
  const form = new FormData();
  form.append('file', blob, filename);
  const { data } = await client.post(`/users/${userId}/voice/enroll`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function deleteVoice(userId) {
  await client.delete(`/users/${userId}/voice`);
}
