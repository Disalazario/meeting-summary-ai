import { useState, useRef } from 'react';
import client from '../api/client';

const ALLOWED_EXTENSIONS = ['mp3', 'mp4', 'wav', 'ogg', 'opus', 'webm', 'm4a', 'mkv', 'aac', 'flac'];

export default function UploadForm({ onSuccess, onCancel }) {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState('');
  const [date, setDate] = useState('');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef();

  const validateFile = (f) => {
    const ext = f.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setError(`Неподдерживаемый формат. Допустимые: ${ALLOWED_EXTENSIONS.join(', ')}`);
      return false;
    }
    if (f.size > 500 * 1024 * 1024) {
      setError('Файл слишком большой (макс. 500MB)');
      return false;
    }
    setError('');
    return true;
  };

  const handleFile = (f) => {
    if (validateFile(f)) {
      setFile(f);
      if (!title) setTitle(f.name.replace(/\.[^.]+$/, ''));
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file || !title) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', title);
    if (date) formData.append('date', date);

    setUploading(true);
    try {
      const res = await client.post('/meetings', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (e.total) setProgress(Math.round((e.loaded / e.total) * 100));
        },
      });
      onSuccess(res.data.id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка загрузки');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border p-6">
      <h2 className="text-lg font-semibold mb-4">Загрузить запись совещания</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
            ${dragOver ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'}`}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".mp3,.mp4,.wav,.ogg,.opus,.webm,.m4a,.mkv,.aac,.flac"
            onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])}
            className="hidden"
          />
          {file ? (
            <div className="text-gray-700">{file.name} ({(file.size / 1024 / 1024).toFixed(1)} MB)</div>
          ) : (
            <div className="text-gray-500">
              Перетащите файл сюда или нажмите для выбора<br />
              <span className="text-xs">mp3, mp4, wav, ogg, opus, webm, m4a, mkv, aac, flac</span>
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Название совещания</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Дата (необязательно)</label>
          <input
            type="datetime-local"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {error && <div className="text-red-600 text-sm">{error}</div>}

        {uploading && (
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div className="bg-blue-600 h-2 rounded-full transition-all" style={{ width: `${progress}%` }} />
          </div>
        )}

        <div className="flex gap-3">
          <button
            type="submit"
            disabled={!file || !title || uploading}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 text-sm"
          >
            {uploading ? `Загрузка ${progress}%` : 'Загрузить'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50 text-sm"
          >
            Отмена
          </button>
        </div>
      </form>
    </div>
  );
}
