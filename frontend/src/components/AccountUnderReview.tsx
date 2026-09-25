import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Clock, RefreshCw, LogOut, CheckCircle2 } from 'lucide-react';
import BrandLogo from './BrandLogo';

interface AccountUnderReviewProps {
  email: string;
  onApproved?: () => void;
  onLogout?: () => void;
}

export default function AccountUnderReview({ email, onApproved, onLogout }: AccountUnderReviewProps) {
  const [checking, setChecking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const isApprovedRef = useRef(false);

  const checkStatusSilent = async () => {
    if (isApprovedRef.current) return;
    try {
      const token = localStorage.getItem('token');
      if (!token) return;
      const res = await axios.get('/api/auth/me', {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (res.data?.status === 'APPROVED') {
        isApprovedRef.current = true;
        localStorage.setItem('user_status', 'APPROVED');
        if (res.data.role) localStorage.setItem('user_role', res.data.role);
        if (res.data.allowed_mode) localStorage.setItem('allowed_mode', res.data.allowed_mode);
        setMessage('Your account has been approved by the Administrator! Launching terminal...');
        setTimeout(() => {
          if (onApproved) {
            onApproved();
          } else {
            window.location.reload();
          }
        }, 1000);
      }
    } catch (e) {
      console.debug('Silent status poll note', e);
    }
  };

  useEffect(() => {
    // Check immediately upon mount
    checkStatusSilent();

    // Auto-poll approval status every 4 seconds
    const interval = setInterval(() => {
      checkStatusSilent();
    }, 4000);

    return () => clearInterval(interval);
  }, []);

  const handleCheckStatus = async () => {
    setChecking(true);
    setMessage(null);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get('/api/auth/me', {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });

      if (res.data?.status === 'APPROVED') {
        isApprovedRef.current = true;
        localStorage.setItem('user_status', 'APPROVED');
        if (res.data.role) localStorage.setItem('user_role', res.data.role);
        if (res.data.allowed_mode) localStorage.setItem('allowed_mode', res.data.allowed_mode);
        setMessage('Your account has been approved! Redirecting to trading terminal...');
        setTimeout(() => {
          if (onApproved) {
            onApproved();
          } else {
            window.location.reload();
          }
        }, 800);
      } else {
        setMessage('Your account is still pending administrator review. Please check back shortly.');
      }
    } catch (e) {
      setMessage('Unable to verify account status right now. Please try again.');
    } finally {
      setChecking(false);
    }
  };

  const handleSignOut = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user_email');
    localStorage.removeItem('user_status');
    localStorage.removeItem('user_role');
    localStorage.removeItem('allowed_mode');
    localStorage.removeItem('wallet_address');
    localStorage.removeItem('demo_access');
    localStorage.removeItem('account_mode');
    localStorage.removeItem('auth_provider');
    if (onLogout) {
      onLogout();
    } else {
      window.location.href = '/login';
    }
  };

  return (
    <div className="min-h-screen bg-[#0d1117] flex items-center justify-center p-4 font-sans text-slate-100">
      <div className="max-w-md w-full bg-[#161b22] border-2 border-amber-500/30 rounded-3xl p-6 sm:p-8 shadow-2xl space-y-6 text-center relative overflow-hidden animate-fade-in">
        
        {/* Ambient Top Glow */}
        <div className="absolute -top-24 left-1/2 -translate-x-1/2 w-72 h-72 bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />

        {/* Brand Header */}
        <div className="flex flex-col items-center space-y-2">
          <BrandLogo size={52} glow={true} />
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-300 text-xs font-mono font-bold uppercase tracking-wider">
            <Clock className="w-3.5 h-3.5 animate-pulse text-amber-400" />
            <span>Account Under Review</span>
          </div>
        </div>

        {/* Heading & Subtitle */}
        <div className="space-y-1.5">
          <h1 className="text-xl sm:text-2xl font-black text-white tracking-tight">
            Pending Administrator Approval
          </h1>
          <p className="text-xs text-slate-400 leading-relaxed">
            Welcome to <strong className="text-white">Fast5M</strong>. Your account has been registered, but requires verification before accessing live prediction engines and automated execution.
          </p>
        </div>

        {/* Status Card */}
        <div className="bg-[#0d1117] border border-[#30363d] rounded-2xl p-4 text-left space-y-3 font-mono text-xs">
          <div className="flex justify-between items-center pb-2 border-b border-[#21262d]">
            <span className="text-slate-400">Account Email:</span>
            <span className="text-slate-200 font-bold truncate max-w-[200px]" title={email}>
              {email}
            </span>
          </div>
          <div className="flex justify-between items-center pb-2 border-b border-[#21262d]">
            <span className="text-slate-400">Review Status:</span>
            <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-black text-[11px] border border-amber-500/40">
              PENDING
            </span>
          </div>
          <div className="flex justify-between items-center pb-2 border-b border-[#21262d]">
            <span className="text-slate-400">Demo Balance Reserved:</span>
            <span className="text-emerald-400 font-bold">$300.00 Virtual USDC</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-slate-400">Access Mode:</span>
            <span className="text-blue-400 font-bold">Standard User</span>
          </div>
        </div>

        {/* Notification / Feedback */}
        {message && (
          <div className={`p-3 rounded-xl text-xs font-mono text-left flex items-start gap-2 ${
            message.includes('approved') 
              ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-300'
              : 'bg-blue-500/15 border border-blue-500/30 text-blue-300'
          }`}>
            <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{message}</span>
          </div>
        )}

        {/* Action Buttons */}
        <div className="space-y-2.5 pt-2">
          <button
            type="button"
            onClick={handleCheckStatus}
            disabled={checking}
            className="w-full bg-gradient-to-r from-amber-600 via-amber-500 to-yellow-600 hover:from-amber-500 hover:to-yellow-500 text-slate-950 font-black text-xs py-3 px-4 rounded-xl transition-all shadow-md shadow-amber-600/30 flex items-center justify-center gap-2 cursor-pointer active:scale-98 disabled:opacity-50"
          >
            {checking ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Checking Authorization...</span>
              </>
            ) : (
              <>
                <RefreshCw className="w-4 h-4" />
                <span>Check Approval Status</span>
              </>
            )}
          </button>

          <button
            type="button"
            onClick={handleSignOut}
            className="w-full bg-[#21262d] hover:bg-[#30363d] text-slate-300 hover:text-white font-bold text-xs py-2.5 px-4 rounded-xl transition-all border border-[#30363d] flex items-center justify-center gap-2 cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Sign Out</span>
          </button>
        </div>

        <p className="text-[11px] text-slate-500 leading-normal">
          An administrator will review your account shortly. If you are the system owner, sign in with your designated administrator account.
        </p>
      </div>
    </div>
  );
}
