import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useTheme } from './hooks/useTheme';
import HomePage from './pages/HomePage';
import MeetingPage from './pages/MeetingPage';

export default function App() {
  useTheme();

  return (
    <BrowserRouter basename="/miniapp">
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/meeting/:id" element={<MeetingPage />} />
      </Routes>
    </BrowserRouter>
  );
}
