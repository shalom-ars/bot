import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import Dashboard from './pages/Dashboard';
import ResearchTerminal from './pages/ResearchTerminal';
import Login from './pages/auth/Login';
import Signup from './pages/auth/Signup';
import Layout from './components/Layout';
import AuthLayout from './components/AuthLayout';
import { 
  Markets, MarketDetail, Signals, Portfolio, 
  Positions, Trades, Performance, Risk, 
  Alerts, Settings, Subscription 
} from './pages/SaaSPages';

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
          <Route path="markets" element={<Markets />} />
          <Route path="markets/:id" element={<MarketDetail />} />
          <Route path="signals" element={<Signals />} />
          <Route path="portfolio" element={<Portfolio />} />
          <Route path="positions" element={<Positions />} />
          <Route path="trades" element={<Trades />} />
          <Route path="performance" element={<Performance />} />
          <Route path="risk" element={<Risk />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="settings" element={<Settings />} />
          <Route path="subscription" element={<Subscription />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}
