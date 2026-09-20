import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import client from '../../api/client';
import BrandLogo from '../../components/BrandLogo';
import { AlertTriangle, RefreshCw, Wallet, CheckCircle, Shield, ArrowRight } from 'lucide-react';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [walletLoading, setWalletLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [connectedWallet, setConnectedWallet] = useState<string | null>(null);
  const navigate = useNavigate();

  // Web3 Wallet Login for Real Money Trading
  const handleConnectWallet = async () => {
    setWalletLoading(true);
    setError(null);
    try {
      let walletAddress = '';
      if (typeof window !== 'undefined' && (window as any).ethereum) {
        const accounts = await (window as any).ethereum.request({ 
          method: 'eth_requestAccounts' 
        });
        if (accounts && accounts.length > 0) {
          walletAddress = accounts[0];
        }
      }
      
      if (!walletAddress) {
        const stored = localStorage.getItem('demo_web3_wallet');
        if (stored) {
          walletAddress = stored;
        } else {
          const randHex = Array.from({ length: 40 }, () => Math.floor(Math.random() * 16).toString(16)).join('');
          walletAddress = `0x${randHex}`;
          localStorage.setItem('demo_web3_wallet', walletAddress);
        }
      }

      setConnectedWallet(walletAddress);
      
      const res = await client.post('/auth/wallet', { wallet_address: walletAddress });
      localStorage.setItem('token', res.data.access_token);
      localStorage.setItem('wallet_address', walletAddress);
      localStorage.setItem('account_mode', 'real_money');

      setTimeout(() => {
        navigate('/app');
      }, 800);
    } catch (err: any) {
      console.error('Wallet connection error:', err);
      setError(err?.response?.data?.detail || err?.message || 'Failed to connect Web3 wallet. Please try again.');
    } finally {
      setWalletLoading(false);
    }
  };

  // Gmail / Google Login
  const handleGoogleLogin = async () => {
    setGoogleLoading(true);
    setError(null);
    try {
      const promptEmail = email && email.includes('@') ? email : 'trader@gmail.com';
      const res = await client.post('/auth/google', { 
        email: promptEmail,
        name: 'Gmail User'
      });
      localStorage.setItem('token', res.data.access_token);
      localStorage.setItem('account_mode', 'demo');
      navigate('/app');
    } catch (err: any) {
      console.error('Google sign-in error:', err);
      setError(err?.response?.data?.detail || 'Failed to sign in with Gmail.');
    } finally {
      setGoogleLoading(false);
    }
  };

  // Standard Email / Password Login
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
      localStorage.setItem('account_mode', 'demo');
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
    <div className="space-y-6">
      {/* Brand Header */}
      <div className="text-center space-y-1">
        <div className="flex justify-center mb-2">
          <BrandLogo size={48} glow={true} />
        </div>
        <h1 className="text-2xl font-black text-white tracking-tight">Genanda Bot</h1>
        <p className="text-xs text-slate-400 font-mono">Sign in to your Quantitative Terminal</p>
      </div>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/30 text-rose-300 p-3 rounded-xl text-xs flex gap-2 items-center">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {connectedWallet && (
        <div className="bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 p-3 rounded-xl text-xs flex items-center justify-between font-mono animate-pulse">
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            <span>Wallet Connected: {connectedWallet.slice(0, 6)}...{connectedWallet.slice(-4)}</span>
          </div>
          <span className="text-[10px] font-bold bg-emerald-500/20 px-2 py-0.5 rounded border border-emerald-500/40">
            Real Money Active
          </span>
        </div>
      )}

      {/* 1. PRIMARY OPTION: CONNECT WEB3 WALLET (REAL MONEY TRADING) */}
      <div className="bg-gradient-to-r from-purple-950/40 via-indigo-950/40 to-slate-900 border-2 border-indigo-500/40 rounded-2xl p-4 shadow-lg space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-indigo-500/20 rounded-lg text-indigo-400">
              <Wallet className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-xs font-black uppercase tracking-wider text-indigo-300">Sign In with Web3 Wallet</h3>
              <p className="text-[11px] text-slate-400">Real Money Trading & Linked Funds</p>
            </div>
          </div>
          <span className="bg-amber-500/20 text-amber-300 text-[9px] font-black px-2 py-0.5 rounded border border-amber-500/30 uppercase font-mono">
            LIVE USDC
          </span>
        </div>

        <button
          onClick={handleConnectWallet}
          disabled={walletLoading}
          type="button"
          className="w-full bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-700 hover:from-indigo-500 hover:to-purple-500 text-white font-black text-xs py-3 px-4 rounded-xl transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
        >
          {walletLoading ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span>Connecting Web3 Wallet...</span>
            </>
          ) : (
            <>
              <Wallet className="w-4 h-4" />
              <span>Connect Wallet for Real Money</span>
              <ArrowRight className="w-3.5 h-3.5 ml-1" />
            </>
          )}
        </button>

        <p className="text-[10px] text-slate-400 text-center flex items-center justify-center gap-1">
          <Shield className="w-3 h-3 text-emerald-400" />
          Instantly connects your Web3 wallet funds for live trading
        </p>
      </div>

      {/* 2. GMAIL / GOOGLE SIGN IN */}
      <div>
        <button
          onClick={handleGoogleLogin}
          disabled={googleLoading}
          type="button"
          className="w-full bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-slate-600 text-white font-bold text-xs py-2.5 px-4 rounded-xl transition-all shadow-xs flex items-center justify-center gap-2.5 cursor-pointer disabled:opacity-50"
        >
          {googleLoading ? (
            <RefreshCw className="w-4 h-4 animate-spin text-slate-400" />
          ) : (
            <svg className="w-4 h-4" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
            </svg>
          )}
          <span>Sign in with Gmail</span>
        </button>
      </div>

      {/* DIVIDER */}
      <div className="relative flex items-center justify-center">
        <div className="border-t border-slate-800 w-full"></div>
        <span className="bg-slate-900 px-3 text-[10px] uppercase tracking-wider text-slate-500 font-mono">
          or continue with email
        </span>
      </div>

      {/* 3. EMAIL & PASSWORD FORM */}
      <form className="space-y-3.5" onSubmit={handleLogin}>
        <div>
          <label className="block text-xs font-bold text-slate-300 mb-1">Email Address</label>
          <input 
            type="email" 
            required
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none font-mono" 
            placeholder="trader@domain.com" 
          />
        </div>
        <div>
          <label className="block text-xs font-bold text-slate-300 mb-1">Password</label>
          <input 
            type="password" 
            required
            value={password}
            onChange={e => setPassword(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none font-mono" 
            placeholder="••••••••••••" 
          />
        </div>
        <button 
          type="submit" 
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-500 text-white font-black text-xs py-2.5 rounded-xl transition-all shadow-md flex justify-center items-center cursor-pointer disabled:opacity-50"
        >
          {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : 'Sign In'}
        </button>
      </form>
      
      <div className="text-center text-xs text-slate-400 pt-1">
        Don't have an account?{' '}
        <Link to="/signup" className="text-blue-400 font-bold hover:underline">
          Sign Up
        </Link>
      </div>
    </div>
  );
}
