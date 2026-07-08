import { useState } from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import GlobalSearch from './GlobalSearch';

export default function Layout() {
  const { user, logout, isAdmin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isActive = (path) => location.pathname === path;

  const linkClass = (path) => {
    const active = isActive(path);
    return [
      'relative px-3 py-2 text-sm rounded-md transition-colors duration-150',
      active
        ? 'text-blue-700 font-semibold bg-blue-50'
        : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100',
    ].join(' ');
  };

  const mobileLinkClass = (path) => {
    const active = isActive(path);
    return [
      'block px-3 py-2 text-sm rounded-md transition-colors duration-150',
      active
        ? 'text-blue-700 font-semibold bg-blue-50'
        : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100',
    ].join(' ');
  };

  const navLinks = (
    <>
      <Link to="/" className={linkClass('/')}>Совещания</Link>
      <Link to="/schedule" className={linkClass('/schedule')}>Расписание</Link>
      <Link to="/gantt" className={linkClass('/gantt')}>Ганта</Link>
      <Link to="/settings" className={linkClass('/settings')}>Настройки</Link>
      {isAdmin && <Link to="/admin" className={linkClass('/admin')}>Пользователи</Link>}
    </>
  );

  const mobileNavLinks = (
    <>
      <Link to="/" className={mobileLinkClass('/')} onClick={() => setMobileOpen(false)}>Совещания</Link>
      <Link to="/schedule" className={mobileLinkClass('/schedule')} onClick={() => setMobileOpen(false)}>Расписание</Link>
      <Link to="/gantt" className={mobileLinkClass('/gantt')} onClick={() => setMobileOpen(false)}>Ганта</Link>
      <Link to="/settings" className={mobileLinkClass('/settings')} onClick={() => setMobileOpen(false)}>Настройки</Link>
      {isAdmin && <Link to="/admin" className={mobileLinkClass('/admin')} onClick={() => setMobileOpen(false)}>Пользователи</Link>}
    </>
  );

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            {/* Logo + desktop nav */}
            <div className="flex items-center gap-1">
              <Link to="/" className="flex items-center gap-2 mr-6 shrink-0">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center">
                  <svg className="w-4.5 h-4.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
                  </svg>
                </div>
                <span className="text-lg font-bold text-gray-800 tracking-tight">Meeting Summary</span>
              </Link>
              {/* Desktop links */}
              <div className="hidden md:flex items-center gap-1">
                {navLinks}
              </div>
            </div>

            {/* Center: global search */}
            <div className="hidden md:flex flex-1 justify-center px-6">
              <GlobalSearch />
            </div>

            {/* Right side: user info + logout */}
            <div className="hidden md:flex items-center gap-3">
              <span className="text-sm text-gray-500 bg-gray-50 px-3 py-1 rounded-full">{user?.display_name}</span>
              <button
                onClick={handleLogout}
                className="text-sm text-red-500 hover:text-red-700 hover:bg-red-50 px-3 py-1.5 rounded-md transition-colors duration-150"
              >
                Выйти
              </button>
            </div>

            {/* Mobile hamburger */}
            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="md:hidden p-2 rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors"
              aria-label="Открыть меню"
            >
              {mobileOpen ? (
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              ) : (
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* Mobile menu */}
        {mobileOpen && (
          <div className="md:hidden border-t border-gray-200 bg-white px-4 py-3 space-y-1 shadow-lg">
            {mobileNavLinks}
            <div className="border-t border-gray-100 mt-2 pt-2 flex items-center justify-between">
              <span className="text-sm text-gray-500">{user?.display_name}</span>
              <button
                onClick={() => { handleLogout(); setMobileOpen(false); }}
                className="text-sm text-red-500 hover:text-red-700 px-3 py-1.5 rounded-md transition-colors"
              >
                Выйти
              </button>
            </div>
          </div>
        )}
      </nav>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>
    </div>
  );
}
