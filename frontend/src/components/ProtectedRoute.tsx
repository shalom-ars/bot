import { Navigate, Outlet, useLocation } from 'react-router-dom';

/**
 * Route protection wrapper for Fast5M trading dashboard routes.
 * Ensures unauthenticated visitors cannot access trading engines or boards.
 */
export default function ProtectedRoute() {
  const location = useLocation();
  const token = localStorage.getItem('token');
  const demoAccess = localStorage.getItem('demo_access');
  const walletAddress = localStorage.getItem('wallet_address');
  const userEmail = localStorage.getItem('user_email');

  const isAuthenticated = Boolean(token || demoAccess || walletAddress || userEmail);

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
