import { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  Shield, CheckCircle2, AlertTriangle, XCircle, 
  RefreshCw, Search, Wallet, Check, Zap, Clock
} from 'lucide-react';

interface UserRecord {
  id: number;
  email: string;
  google_sub?: string;
  role: 'SUPER_ADMIN' | 'USER';
  status: 'APPROVED' | 'PENDING' | 'SUSPENDED';
  allowed_mode: 'DEMO_ONLY' | 'REAL_AND_DEMO' | 'NONE';
  wallet_address?: string | null;
  auth_provider: string;
  is_active: boolean;
  allocated_balance: number;
  total_trades: number;
  open_trades: number;
  created_at?: string;
}

interface AdminDashboardMetrics {
  total_users: number;
  active_users: number;
  approved_users: number;
  pending_users: number;
  suspended_users: number;
  real_mode_users: number;
  fast5m_trades: number;
}

export default function AdminConsoleTab() {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [metrics, setMetrics] = useState<AdminDashboardMetrics | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  
  // Filters
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [modeFilter, setModeFilter] = useState<string>('ALL');

  const token = localStorage.getItem('token');

  const fetchAdminData = async () => {
    try {
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      const [metricsRes, usersRes] = await Promise.all([
        axios.get('/api/admin/dashboard', { headers }),
        axios.get('/api/admin/users', { headers })
      ]);

      if (metricsRes.data?.metrics) {
        setMetrics(metricsRes.data.metrics);
      }
      if (Array.isArray(usersRes.data)) {
        setUsers(usersRes.data);
      }
    } catch (err: any) {
      console.error('Failed to fetch admin data:', err);
      setNotification({
        type: 'error',
        message: err?.response?.data?.detail || 'Failed to load administrator data.'
      });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchAdminData();
  }, []);

  const handleUpdateStatus = async (userId: number, newStatus: 'APPROVED' | 'SUSPENDED' | 'PENDING') => {
    setActionLoadingId(userId);
    setNotification(null);
    try {
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await axios.post(`/api/admin/users/${userId}/status`, { status: newStatus }, { headers });
      
      setNotification({
        type: 'success',
        message: res.data?.message || `User #${userId} status set to ${newStatus}.`
      });

      // Optimistic update
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, status: newStatus } : u));
      fetchAdminData();
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err?.response?.data?.detail || 'Failed to update user status.'
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleUpdateMode = async (userId: number, newMode: 'DEMO_ONLY' | 'REAL_AND_DEMO') => {
    setActionLoadingId(userId);
    setNotification(null);
    try {
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await axios.post(`/api/admin/users/${userId}/mode`, { allowed_mode: newMode }, { headers });
      
      setNotification({
        type: 'success',
        message: res.data?.message || `User #${userId} mode updated to ${newMode}.`
      });

      // Optimistic update
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, allowed_mode: newMode } : u));
      fetchAdminData();
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err?.response?.data?.detail || 'Failed to update user trading mode.'
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  const filteredUsers = users.filter(u => {
    const matchesSearch = 
      u.email.toLowerCase().includes(searchTerm.toLowerCase()) || 
      (u.wallet_address && u.wallet_address.toLowerCase().includes(searchTerm.toLowerCase())) ||
      String(u.id) === searchTerm;
    
    const matchesStatus = statusFilter === 'ALL' || u.status === statusFilter;
    const matchesMode = modeFilter === 'ALL' || u.allowed_mode === modeFilter;

    return matchesSearch && matchesStatus && matchesMode;
  });

  return (
    <div className="space-y-5 animate-fade-in font-sans text-slate-100 text-left">
      
      {/* 1. Header & Controls */}
      <div className="bg-[#161b22] border border-[#30363d] rounded-2xl p-4 sm:p-5 shadow-md flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-purple-600/20 text-purple-400 rounded-xl border border-purple-500/30">
            <Shield className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-black text-white tracking-tight">
                Super Admin Access Control
              </h2>
              <span className="text-[10px] font-black px-2 py-0.5 rounded-md bg-purple-600 text-white uppercase tracking-wider font-mono">
                RBAC LIVE
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Manage multi-tenant user authorizations, approvals, and Real/Demo trading permissions.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => { setRefreshing(true); fetchAdminData(); }}
          disabled={refreshing}
          className="self-start md:self-auto px-3.5 py-2 bg-[#21262d] hover:bg-[#30363d] text-slate-200 text-xs font-bold rounded-xl border border-[#30363d] transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-purple-400' : ''}`} />
          <span>Refresh Users</span>
        </button>
      </div>

      {/* 2. Platform Metrics Overview */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="bg-[#161b22] border border-[#30363d] rounded-2xl p-3.5 space-y-1">
          <span className="text-[11px] font-bold text-slate-400">Total Users</span>
          <div className="text-xl font-black text-white font-mono">{metrics?.total_users ?? users.length}</div>
          <span className="text-[10px] text-slate-500">Registered platform-wide</span>
        </div>

        <div className="bg-[#161b22] border border-[#30363d] rounded-2xl p-3.5 space-y-1">
          <span className="text-[11px] font-bold text-emerald-400 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" />
            <span>Approved</span>
          </span>
          <div className="text-xl font-black text-emerald-400 font-mono">
            {metrics?.approved_users ?? users.filter(u => u.status === 'APPROVED').length}
          </div>
          <span className="text-[10px] text-emerald-500/70">Full terminal access</span>
        </div>

        <div className="bg-[#161b22] border border-amber-500/30 rounded-2xl p-3.5 space-y-1 relative overflow-hidden">
          <span className="text-[11px] font-bold text-amber-300 flex items-center gap-1">
            <Clock className="w-3 h-3 text-amber-400 animate-pulse" />
            <span>Pending Review</span>
          </span>
          <div className="text-xl font-black text-amber-300 font-mono">
            {metrics?.pending_users ?? users.filter(u => u.status === 'PENDING').length}
          </div>
          <span className="text-[10px] text-amber-400/70">Awaiting your approval</span>
        </div>

        <div className="bg-[#161b22] border border-[#30363d] rounded-2xl p-3.5 space-y-1">
          <span className="text-[11px] font-bold text-rose-400 flex items-center gap-1">
            <XCircle className="w-3 h-3" />
            <span>Suspended</span>
          </span>
          <div className="text-xl font-black text-rose-400 font-mono">
            {metrics?.suspended_users ?? users.filter(u => u.status === 'SUSPENDED').length}
          </div>
          <span className="text-[10px] text-rose-500/70">Blocked from trading</span>
        </div>

        <div className="bg-[#161b22] border border-[#30363d] rounded-2xl p-3.5 space-y-1">
          <span className="text-[11px] font-bold text-blue-400 flex items-center gap-1">
            <Zap className="w-3 h-3" />
            <span>Real Vaults</span>
          </span>
          <div className="text-xl font-black text-blue-400 font-mono">
            {metrics?.real_mode_users ?? users.filter(u => u.allowed_mode === 'REAL_AND_DEMO').length}
          </div>
          <span className="text-[10px] text-blue-500/70">Real trading allowed</span>
        </div>

        <div className="bg-[#161b22] border border-[#30363d] rounded-2xl p-3.5 space-y-1">
          <span className="text-[11px] font-bold text-purple-400">Total 5M Trades</span>
          <div className="text-xl font-black text-purple-300 font-mono">
            {metrics?.fast5m_trades ?? '64+'}
          </div>
          <span className="text-[10px] text-purple-500/70">Execution database</span>
        </div>
      </div>

      {/* 3. Action Notification */}
      {notification && (
        <div className={`p-3 rounded-xl text-xs font-mono flex items-center justify-between gap-2 animate-fade-in ${
          notification.type === 'success' 
            ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-300' 
            : 'bg-rose-500/15 border border-rose-500/30 text-rose-300'
        }`}>
          <div className="flex items-center gap-2">
            {notification.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span>{notification.message}</span>
          </div>
          <button 
            type="button" 
            onClick={() => setNotification(null)}
            className="text-slate-400 hover:text-white text-xs cursor-pointer"
          >
            ✕
          </button>
        </div>
      )}

      {/* 4. Filters Bar */}
      <div className="bg-[#161b22] border border-[#30363d] rounded-2xl p-3 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by user email, ID, or wallet address..."
            className="w-full bg-[#0d1117] border border-[#30363d] rounded-xl pl-9 pr-3.5 py-2 text-xs text-white placeholder-slate-500 focus:border-purple-500 outline-none font-mono"
          />
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Status Filter */}
          <div className="flex items-center gap-1.5 bg-[#0d1117] p-1 rounded-xl border border-[#30363d]">
            <span className="text-[10px] text-slate-400 px-1.5 font-bold uppercase">Status:</span>
            {['ALL', 'PENDING', 'APPROVED', 'SUSPENDED'].map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => setStatusFilter(st)}
                className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition-all cursor-pointer ${
                  statusFilter === st
                    ? 'bg-[#21262d] text-white shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          {/* Mode Filter */}
          <div className="flex items-center gap-1.5 bg-[#0d1117] p-1 rounded-xl border border-[#30363d]">
            <span className="text-[10px] text-slate-400 px-1.5 font-bold uppercase">Mode:</span>
            {['ALL', 'DEMO_ONLY', 'REAL_AND_DEMO'].map((md) => (
              <button
                key={md}
                type="button"
                onClick={() => setModeFilter(md)}
                className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition-all cursor-pointer ${
                  modeFilter === md
                    ? 'bg-[#21262d] text-white shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {md === 'REAL_AND_DEMO' ? 'Real+Demo' : (md === 'DEMO_ONLY' ? 'Demo' : 'All')}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 5. Users Table */}
      <div className="bg-[#161b22] border border-[#30363d] rounded-2xl overflow-hidden shadow-md">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#0d1117] text-slate-400 font-mono text-[11px] uppercase border-b border-[#30363d]">
              <tr>
                <th className="py-3 px-4">User / Email</th>
                <th className="py-3 px-3">Role</th>
                <th className="py-3 px-3">Status</th>
                <th className="py-3 px-3">Allowed Mode</th>
                <th className="py-3 px-3">Web3 Public Wallet</th>
                <th className="py-3 px-3 text-right">Demo Vault</th>
                <th className="py-3 px-3 text-center">Trades</th>
                <th className="py-3 px-4 text-right">Manage Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#21262d]">
              {loading ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-slate-400 font-mono">
                    <div className="flex items-center justify-center gap-2">
                      <RefreshCw className="w-4 h-4 animate-spin text-purple-400" />
                      <span>Loading platform users...</span>
                    </div>
                  </td>
                </tr>
              ) : filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-10 text-center text-slate-400 font-mono">
                    No users matching criteria &quot;{searchTerm}&quot; found.
                  </td>
                </tr>
              ) : (
                filteredUsers.map((u) => {
                  const isPrimaryAdmin = u.email.toLowerCase() === 'arsandhuthree@gmail.com';
                  const isPending = u.status === 'PENDING';
                  const isApproved = u.status === 'APPROVED';
                  const isSuspended = u.status === 'SUSPENDED';
                  const isRealAllowed = u.allowed_mode === 'REAL_AND_DEMO';
                  const isLoading = actionLoadingId === u.id;

                  return (
                    <tr 
                      key={u.id} 
                      className={`hover:bg-[#21262d]/50 transition-colors ${
                        isPending ? 'bg-amber-950/15' : (isPrimaryAdmin ? 'bg-purple-950/10' : '')
                      }`}
                    >
                      {/* User / Email */}
                      <td className="py-3.5 px-4 font-mono">
                        <div className="flex items-center gap-2.5">
                          <div className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-xs ${
                            isPrimaryAdmin 
                              ? 'bg-purple-600 text-white shadow-xs' 
                              : (isPending ? 'bg-amber-500 text-slate-950' : 'bg-blue-600 text-white')
                          }`}>
                            {u.email.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <div className="font-bold text-white flex items-center gap-1.5">
                              <span>{u.email}</span>
                              {isPrimaryAdmin && (
                                <span className="text-[9px] px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300 font-bold border border-purple-500/40">
                                  Owner
                                </span>
                              )}
                            </div>
                            <span className="text-[10px] text-slate-500">ID #{u.id}</span>
                          </div>
                        </div>
                      </td>

                      {/* Role */}
                      <td className="py-3.5 px-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase font-mono border ${
                          u.role === 'SUPER_ADMIN'
                            ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
                            : 'bg-slate-800 text-slate-300 border-slate-700'
                        }`}>
                          {u.role}
                        </span>
                      </td>

                      {/* Status */}
                      <td className="py-3.5 px-3">
                        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase font-mono border ${
                          isApproved
                            ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                            : isPending
                            ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse'
                            : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${
                            isApproved ? 'bg-emerald-400' : (isPending ? 'bg-amber-400' : 'bg-rose-400')
                          }`} />
                          <span>{u.status}</span>
                        </span>
                      </td>

                      {/* Allowed Mode */}
                      <td className="py-3.5 px-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono border ${
                          isRealAllowed
                            ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                            : 'bg-slate-800 text-slate-400 border-slate-700'
                        }`}>
                          {isRealAllowed ? '⚡ Real + Demo' : '🎮 Demo Only'}
                        </span>
                      </td>

                      {/* Web3 Public Wallet */}
                      <td className="py-3.5 px-3 font-mono text-[11px]">
                        {u.wallet_address ? (
                          <div className="flex items-center gap-1.5 text-slate-300 bg-[#0d1117] px-2 py-1 rounded-lg border border-[#30363d] w-fit" title={u.wallet_address}>
                            <Wallet className="w-3 h-3 text-emerald-400 shrink-0" />
                            <span>{u.wallet_address.slice(0, 6)}...{u.wallet_address.slice(-4)}</span>
                          </div>
                        ) : (
                          <span className="text-slate-500 text-[10px] italic">Not Linked</span>
                        )}
                      </td>

                      {/* Demo Vault */}
                      <td className="py-3.5 px-3 text-right font-mono font-bold text-slate-200">
                        ${(u.allocated_balance || 300).toFixed(2)}
                      </td>

                      {/* Trades */}
                      <td className="py-3.5 px-3 text-center font-mono">
                        <span className="text-slate-200 font-bold">{u.total_trades || 0}</span>
                        {u.open_trades > 0 && (
                          <span className="text-emerald-400 text-[10px] ml-1">({u.open_trades} open)</span>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="py-3.5 px-4 text-right">
                        {isPrimaryAdmin ? (
                          <span className="text-[10px] text-purple-400 font-bold italic">
                            Protected Super Admin
                          </span>
                        ) : (
                          <div className="flex items-center justify-end gap-1.5">
                            {/* Status Button */}
                            {isPending && (
                              <button
                                type="button"
                                disabled={isLoading}
                                onClick={() => handleUpdateStatus(u.id, 'APPROVED')}
                                className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-[10px] rounded-lg shadow-sm transition-all flex items-center gap-1 cursor-pointer disabled:opacity-50"
                                title="Approve user for trading"
                              >
                                <Check className="w-3 h-3" />
                                <span>Approve</span>
                              </button>
                            )}

                            {isApproved && (
                              <button
                                type="button"
                                disabled={isLoading}
                                onClick={() => handleUpdateStatus(u.id, 'SUSPENDED')}
                                className="px-2 py-1 bg-rose-950/60 hover:bg-rose-900 border border-rose-700/60 text-rose-300 font-bold text-[10px] rounded-lg transition-all flex items-center gap-1 cursor-pointer disabled:opacity-50"
                                title="Suspend user access"
                              >
                                <XCircle className="w-3 h-3" />
                                <span>Suspend</span>
                              </button>
                            )}

                            {isSuspended && (
                              <button
                                type="button"
                                disabled={isLoading}
                                onClick={() => handleUpdateStatus(u.id, 'APPROVED')}
                                className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-[10px] rounded-lg shadow-sm transition-all flex items-center gap-1 cursor-pointer disabled:opacity-50"
                                title="Re-approve user"
                              >
                                <Check className="w-3 h-3" />
                                <span>Re-Approve</span>
                              </button>
                            )}

                            {/* Mode Button */}
                            {isRealAllowed ? (
                              <button
                                type="button"
                                disabled={isLoading}
                                onClick={() => handleUpdateMode(u.id, 'DEMO_ONLY')}
                                className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-[10px] rounded-lg border border-slate-700 transition-all cursor-pointer disabled:opacity-50"
                                title="Restrict to demo only"
                              >
                                <span>Demo Only</span>
                              </button>
                            ) : (
                              <button
                                type="button"
                                disabled={isLoading}
                                onClick={() => handleUpdateMode(u.id, 'REAL_AND_DEMO')}
                                className="px-2 py-1 bg-blue-600 hover:bg-blue-500 text-white font-bold text-[10px] rounded-lg shadow-sm transition-all flex items-center gap-1 cursor-pointer disabled:opacity-50"
                                title="Grant permission to trade real money on Polymarket"
                              >
                                <Zap className="w-3 h-3" />
                                <span>Grant Real</span>
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
