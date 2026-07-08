import { Component } from 'react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);

    // Известная проблема React 19 + расширения автоперевода (Google/Yandex
    // Translate, прочие): они вставляют свои span в DOM, React при ре-рендере
    // не находит ожидаемого узла и кидает NotFoundError: removeChild for Node.
    // Симптом: «Failed to execute 'removeChild' on 'Node'» или
    // «commitDeletionEffectsOnFiber». Лечится auto-reload — после перезагрузки
    // на следующей странице translate="no" на <html> уже отработает.
    const msg = (error && (error.message || String(error))) || '';
    const isTranslateDomCrash = /removeChild|insertBefore|commitDeletionEffects|NotFoundError/.test(msg);
    if (isTranslateDomCrash && !sessionStorage.getItem('__autoReloadedOnce')) {
      sessionStorage.setItem('__autoReloadedOnce', '1');
      console.warn('Auto-reloading due to DOM mismatch (likely translate extension)');
      setTimeout(() => window.location.reload(), 100);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50" role="alert">
          <div className="max-w-md w-full bg-white rounded-lg shadow-md p-8 text-center border-t-4 border-red-500">
            <div className="text-red-500 mb-4">
              <svg
                className="w-16 h-16 mx-auto"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-gray-800 mb-2">Произошла ошибка</h1>
            <p className="text-sm text-gray-500 mb-6">
              {this.state.error?.message || 'Неизвестная ошибка приложения'}
            </p>
            <button
              onClick={() => window.location.reload()}
              className="px-6 py-2 bg-red-500 text-white rounded-md hover:bg-red-600 transition-colors text-sm font-medium"
            >
              Перезагрузить
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
