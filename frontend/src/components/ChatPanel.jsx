import { useState, useEffect, useRef } from 'react';
import client from '../api/client';

export default function ChatPanel({ meetingId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const bottomRef = useRef();

  useEffect(() => {
    client.get(`/meetings/${meetingId}/chat/history`)
      .then((res) => setMessages(res.data))
      .finally(() => setLoading(false));
  }, [meetingId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    const msg = input.trim();
    setInput('');
    setSending(true);

    // Optimistically add user message
    setMessages((prev) => [...prev, { id: Date.now(), role: 'user', content: msg }]);

    try {
      const res = await client.post(`/meetings/${meetingId}/chat`, { message: msg });
      setMessages((prev) => [...prev, { id: Date.now() + 1, role: 'assistant', content: res.data.response }]);
    } catch {
      setMessages((prev) => [...prev, { id: Date.now() + 1, role: 'assistant', content: 'Ошибка получения ответа' }]);
    }
    setSending(false);
  };

  if (loading) return <div className="text-gray-500 py-4">Загрузка чата...</div>;

  return (
    <div className="flex flex-col h-[60vh]">
      <div className="flex-1 overflow-y-auto space-y-3 mb-4 p-2">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 text-sm py-8">
            Задайте вопрос о совещании
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[70%] px-3 py-2 rounded-lg text-sm
              ${msg.role === 'user'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-800'}`}>
              {msg.content}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-gray-100 text-gray-500 px-3 py-2 rounded-lg text-sm">
              Думаю...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="Введите вопрос о совещании..."
          className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          disabled={sending}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || sending}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 text-sm"
        >
          Отправить
        </button>
      </div>
    </div>
  );
}
