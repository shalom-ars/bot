import { useState, useEffect } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import axios from 'axios';
import AccountUnderReview from './AccountUnderReview';

/**
 * Route protection wrapper for Fast5M trading dashboard routes.
 * Ensures unauthenticated visitors cannot access trading engines or boards,
 * and pending users are presented with the friendly 'Under Review' screen.
 */
export default function ProtectedRoute() {
  const location = useLocation();
  const token = localStorage.getItem('token');
  const walletAddress = localStorage.getItem('wallet_address');
  const userEmail = localStorage.getItem('user_email');

  const isConfiguredAdmin = (userEmail || '').trim().toLowerCase() === 'shalombinrasheed@gmail.com';
  const initialStatus = isConfiguredAdmin ? 'APPROVED' : (localStorage.getItem('user_status') || 'PENDING');

  const [loading, setLoading] = useState(Boolean(token));
  const [userStatus, setUserStatus] = useState<string>(initialStatus);
  const [activeEmail, setActiveEmail] = useState<string>(userEmail || '');

  useEffect(() => {
    let isMounted = true;
    if (token) {
      axios.get('/api/auth/me', {
        headers: { Authorization: `Bearer ${token}` }
      }).then(res => {
        if (!isMounted) return;
        if (res.data) {
          const email = (res.data.email || userEmail || '').trim().toLowerCase();
          const isAdmin = email === 'shalombinrasheed@gmail.com';
          const status = isAdmin ? 'APPROVED' : (res.data.status || 'PENDING');
          setUserStatus(status);
          setActiveEmail(email);
          localStorage.setItem('user_status', status);
          if (res.data.role) localStorage.setItem('user_role', res.data.role);
          if (res.data.allowed_mode) localStorage.setItem('allowed_mode', res.data.allowed_mode);
          if (email) localStorage.setItem('user_email', email);
        }
      }).catch(err => {
        console.debug('Session check note', err);
        // If 403 or unauthorized, handle accordingly
        if (err?.response?.status === 401) {
          localStorage.removeItem('token');
          window.location.href = '/login';
        } else if (err?.response?.status === 403) {
          setUserStatus('PENDING');
          localStorage.setItem('user_status', 'PENDING');
        }
      }).finally(() => {
        if (isMounted) setLoading(false);
      });
    } else {
      setLoading(false);
    }
    return () => { isMounted = false; };
  }, [token]);

  const isAuthenticated = Boolean(token || walletAddress || userEmail);

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0d1117] flex items-center justify-center font-mono text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span>Verifying session authorization...</span>
        </div>
      </div>
    );
  }

  // Restrict access exclusively to approved accounts; display waiting screen for all pending accounts
  const isSuperAdmin = activeEmail.trim().toLowerCase() === 'shalombinrasheed@gmail.com' ||
    (localStorage.getItem('user_email') || '').trim().toLowerCase() === 'shalombinrasheed@gmail.com';

  if (!isSuperAdmin && userStatus !== 'APPROVED') {
    return (
      <AccountUnderReview 
        email={activeEmail} 
        onApproved={() => setUserStatus('APPROVED')}
        onLogout={() => {
          localStorage.removeItem('token');
          localStorage.removeItem('user_email');
          localStorage.removeItem('user_status');
          localStorage.removeItem('user_role');
          localStorage.removeItem('allowed_mode');
          localStorage.removeItem('wallet_address');
          localStorage.removeItem('account_mode');
          localStorage.removeItem('auth_provider');
          window.location.href = '/login';
        }}
      />
    );
  }

  return <Outlet />;
}
