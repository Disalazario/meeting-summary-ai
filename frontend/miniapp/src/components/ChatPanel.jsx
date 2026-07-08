import { useState, useEffect, useRef } from 'react';
import client from '../api/client';
import { telegram } from '../telegram';

export default function ChatPanel({ meetingId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    async function loadHistory() {
      try {
        const { data } = await client.get(`/meetings/${meetingId}/chat/history`);
        setMessages(data);
      } catch {
        // Нет истории — нормально
      }
    }
    loadHistory();
  }, [meetingId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || sending) return;

    setInput('');
    setSending(true);
    telegram.haptic.impact('light');

    // Оптимистичное добавление
    const userMsg = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);

    try {
      const { data } = await client.post(`/meetings/${meetingId}/chat`, {
        message: text,
      });
      setMessages(prev => [...prev, { role: 'assistant', content: data.response }]);
    } catch {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Не удалось получить ответ. Попробуйте ещё раз.' },
      ]);
      telegram.haptic.notification('error');
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Сообщения */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 chat-scroll">
        {messages.length === 0 && (
          <div className="text-center text-tg-hint text-sm py-8">
            Задайте вопрос по совещанию
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-tg-button text-tg-button-text rounded-br-md'
                  : 'bg-tg-bg-secondary rounded-bl-md'
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
            </div>
          </div>
        ))}

        {sending && (
          <div className="flex justify-start">
            <div className="bg-tg-bg-secondary rounded-2xl rounded-bl-md px-4 py-3">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-tg-hint rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-tg-hint rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                <div className="w-2 h-2 bg-tg-hint rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Ввод */}
      <div className="p-3 border-t border-tg-bg-secondary">
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Спросите о совещании..."
            rows={1}
            className="flex-1 resize-none bg-tg-bg-secondary rounded-xl px-3 py-2 text-sm
                       outline-none focus:ring-1 focus:ring-tg-button placeholder-tg-hint
                       max-h-24 overflow-y-auto"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || sending}
            className="w-9 h-9 rounded-full bg-tg-button flex items-center justify-center
                       disabled:opacity-40 transition-opacity flex-shrink-0"
          >
            <svg className="w-4 h-4 text-tg-button-text" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-7 7m7-7l7 7" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
