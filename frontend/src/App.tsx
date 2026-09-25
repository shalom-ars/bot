import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import ResearchTerminal from './pages/ResearchTerminal';
import Login from './pages/auth/Login';
import Signup from './pages/auth/Signup';
import Layout from './components/Layout';
import BTC5M from './pages/BTC5M';
import Fast5MBoard from './pages/Fast5MBoard';
import AuthLayout from './components/AuthLayout';
import ProtectedRoute from './components/ProtectedRoute';
import { 
  Markets, MarketDetail, Signals, Portfolio, 
  Positions, Trades, Performance, Risk, 
  Alerts, Settings, Subscription, OrderBook 
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
          <Route path="/auth/callback" element={<Login />} />
          <Route path="/login/callback" element={<Login />} />
          <Route path="/auth/google/callback" element={<Login />} />
          <Route path="/callback" element={<Login />} />
        </Route>

        {/* Protected Dashboard Routes */}
        <Route element={<ProtectedRoute />}>
          <Route path="/app" element={<Layout />}>
            <Route index element={<Fast5MBoard />} />
            <Route path="fast5m" element={<Fast5MBoard />} />
            <Route path="btc5m" element={<BTC5M />} />
            <Route path="research" element={<ResearchTerminal />} />
            <Route path="markets" element={<Markets />} />
            <Route path="markets/:id" element={<MarketDetail />} />
            <Route path="signals" element={<Signals />} />
            <Route path="portfolio" element={<Portfolio />} />
            <Route path="positions" element={<Positions />} />
            <Route path="trades" element={<Trades />} />
            <Route path="performance" element={<Performance />} />
            <Route path="risk" element={<Risk />} />
            <Route path="orderbook" element={<OrderBook />} />
            <Route path="alerts" element={<Alerts />} />
            <Route path="settings" element={<Settings />} />
            <Route path="subscription" element={<Subscription />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}

