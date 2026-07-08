import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import client, { setAuthToken } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('token'));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      setAuthToken(token);
      client.get('/auth/me')
        .then((res) => setUser(res.data))
        .catch(() => {
          setToken(null);
          setAuthToken(null);
          localStorage.removeItem('token');
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [token]);

  const login = useCallback(async (username, password) => {
    const res = await client.post('/auth/login', { username, password });
    const newToken = res.data.access_token;
    localStorage.setItem('token', newToken);
    setAuthToken(newToken);
    setToken(newToken);
    const meRes = await client.get('/auth/me');
    setUser(meRes.data);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    setAuthToken(null);
    setToken(null);
    setUser(null);
  }, []);

  const isAdmin = user?.role === 'admin';

  return (
    <AuthContext.Provider value={{ user, token, login, logout, isAdmin, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
