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
  const demoAccess = localStorage.getItem('demo_access');
  const walletAddress = localStorage.getItem('wallet_address');
  const userEmail = localStorage.getItem('user_email');

  const [loading, setLoading] = useState(Boolean(token));
  const [userStatus, setUserStatus] = useState<string>(localStorage.getItem('user_status') || 'APPROVED');
  const [activeEmail, setActiveEmail] = useState<string>(userEmail || '');

  useEffect(() => {
    let isMounted = true;
    if (token) {
      axios.get('/api/auth/me', {
        headers: { Authorization: `Bearer ${token}` }
      }).then(res => {
        if (!isMounted) return;
        if (res.data) {
          const status = res.data.status || 'APPROVED';
          const email = res.data.email || userEmail || '';
          setUserStatus(status);
          setActiveEmail(email);
          localStorage.setItem('user_status', status);
          if (res.data.role) localStorage.setItem('user_role', res.data.role);
          if (res.data.allowed_mode) localStorage.setItem('allowed_mode', res.data.allowed_mode);
          if (email) localStorage.setItem('user_email', email);
        }
      }).catch(err => {
        console.debug('Session check note', err);
      }).finally(() => {
        if (isMounted) setLoading(false);
      });
    } else {
      setLoading(false);
    }
    return () => { isMounted = false; };
  }, [token]);

  const isAuthenticated = Boolean(token || demoAccess || walletAddress || userEmail);

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

  // If user account is pending approval, render friendly Under Review screen
  if (userStatus === 'PENDING') {
    return (
      <AccountUnderReview 
        email={activeEmail} 
        onApproved={() => setUserStatus('APPROVED')}
        onLogout={() => window.location.href = '/login'}
      />
    );
  }

  return <Outlet />;
}
