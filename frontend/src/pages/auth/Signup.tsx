import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import client from '../../api/client';
import { ShieldAlert, AlertTriangle, RefreshCw } from 'lucide-react';

export default function Signup() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await client.post('/auth/register', { email, password });
      localStorage.setItem('token', res.data.access_token);
      navigate('/app');
    } catch (err: any) {
      if (err.response) {
        setError(err.response.data?.detail || 'Failed to create account.');
      } else {
        setError('Network error. Backend might be unreachable.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-slate-900 mb-2">Create Account</h2>
      <p className="text-slate-500 text-sm mb-6">Start paper trading with a $500 virtual portfolio.</p>
      
      <div className="bg-rose-50 border border-rose-200 rounded-lg p-3 mb-6 flex items-start gap-3">
        <ShieldAlert className="w-5 h-5 text-rose-600 mt-0.5" />
        <div className="text-xs text-rose-800 leading-relaxed">
          <strong>Notice:</strong> This platform operates strictly in PAPER TRADING mode. Virtual capital cannot be withdrawn or monetized. Real money execution is completely disabled.
        </div>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 p-3 rounded-lg text-sm mb-4 flex gap-2 items-center border border-red-200">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <form className="space-y-4" onSubmit={handleSignup}>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
          <input 
            type="email" 
            required
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="w-full border border-slate-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-blue-600 focus:border-transparent outline-none" 
            placeholder="name@company.com" 
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
          <input 
            type="password" 
            required
            value={password}
            onChange={e => setPassword(e.target.value)}
            className="w-full border border-slate-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-blue-600 focus:border-transparent outline-none" 
            placeholder="••••••••" 
          />
        </div>
        
        <button 
          type="submit" 
          disabled={loading}
          className="w-full bg-blue-600 text-white rounded-lg px-4 py-3 font-bold text-sm hover:bg-blue-700 transition-colors mt-6 flex justify-center items-center shadow-sm disabled:opacity-50"
        >
          {loading ? <RefreshCw className="w-5 h-5 animate-spin" /> : 'Create Account'}
        </button>
      </form>
      
      <div className="mt-8 text-center text-sm text-slate-600">
        Already have an account? <Link to="/login" className="text-blue-600 font-bold hover:underline">Sign in</Link>
      </div>
    </div>
  );
}
