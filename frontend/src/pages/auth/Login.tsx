import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import client from '../../api/client';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);
      
      const res = await client.post('/auth/login', formData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded'
        }
      });
      
      localStorage.setItem('token', res.data.access_token);
      navigate('/app');
    } catch (err: any) {
      if (err.response) {
        setError(err.response.data?.detail || 'Incorrect email or password.');
      } else {
        setError('Network error. Backend might be unreachable.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-slate-900 mb-2">Sign In</h2>
      <p className="text-slate-500 text-sm mb-8">Access your virtual portfolio and analytics.</p>
      
      {error && (
        <div className="bg-red-50 text-red-700 p-3 rounded-lg text-sm mb-4 flex gap-2 items-center border border-red-200">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <form className="space-y-4" onSubmit={handleLogin}>
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
          <div className="flex justify-between items-center mb-1">
            <label className="block text-sm font-medium text-slate-700">Password</label>
          </div>
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
          {loading ? <RefreshCw className="w-5 h-5 animate-spin" /> : 'Sign In'}
        </button>
      </form>
      
      <div className="mt-8 text-center text-sm text-slate-600">
        Don't have an account? <Link to="/signup" className="text-blue-600 font-bold hover:underline">Sign up</Link>
      </div>
    </div>
  );
}
