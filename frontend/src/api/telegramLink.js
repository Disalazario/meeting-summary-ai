import client from './client';

export async function getTelegramStatus() {
  const { data } = await client.get('/users/me/telegram');
  return data;
}

export async function createTelegramLink() {
  const { data } = await client.post('/users/me/telegram/link');
  return data;
}

export async function unlinkTelegram() {
  await client.delete('/users/me/telegram');
}
