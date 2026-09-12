import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import Dashboard from './pages/Dashboard';
import ResearchTerminal from './pages/ResearchTerminal';
import Login from './pages/auth/Login';
import Signup from './pages/auth/Signup';
import Layout from './components/Layout';
import AuthLayout from './components/AuthLayout';

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        
        {/* Auth Routes */}
        <Route element={<AuthLayout />}>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
        </Route>

        {/* Dashboard Routes */}
        <Route path="/app" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="research" element={<ResearchTerminal />} />
          {/* Stubs that render Dashboard for now to satisfy links */}
          <Route path="markets" element={<Dashboard />} />
          <Route path="portfolio" element={<Dashboard />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}
