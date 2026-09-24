import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import client from '../../api/client';
import BrandLogo from '../../components/BrandLogo';
import { AlertTriangle, RefreshCw, Wallet, CheckCircle, Shield, ArrowRight, X, ExternalLink, Zap, Play } from 'lucide-react';

export default function Signup() {
  const [selectedAuthMode, setSelectedAuthMode] = useState<'demo' | 'real'>('demo');
  const [demoLoading, setDemoLoading] = useState(false);
  const [showAdminForm, setShowAdminForm] = useState(false);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [walletLoading, setWalletLoading] = useState(false);
  const [walletStatus, setWalletStatus] = useState<string | null>(null);
  const [isWalletModalOpen, setIsWalletModalOpen] = useState(false);

  const [connectedWallet, setConnectedWallet] = useState<string | null>(null);
  const navigate = useNavigate();

  // Instant 1-Click Demo Entry (No Gmail / Signup Required)
  const handleEnterDemoAccount = async () => {
    setDemoLoading(true);
    setError(null);
    try {
      try {
        await client.post('/fast5m/wallet/mode', { mode: 'demo' });
      } catch (e) {
        console.debug('Mode sync notice', e);
      }
      localStorage.setItem('account_mode', 'demo');
      localStorage.setItem('demo_access', 'true');
      navigate('/app');
    } catch (err: any) {
      console.error('Demo enter error:', err);
      navigate('/app');
    } finally {
      setDemoLoading(false);
    }
  };

  // Web3 Wallet Connection with User Signature Approval
  const handleConnectWallet = async () => {
    setError(null);
    setWalletStatus(null);
    
    if (typeof window === 'undefined' || !(window as any).ethereum) {
      setIsWalletModalOpen(true);
      return;
    }

    setWalletLoading(true);
    try {
      setWalletStatus('Please select and approve your wallet in MetaMask...');
      const accounts = await (window as any).ethereum.request({ 
        method: 'eth_requestAccounts' 
      });
      
      if (!accounts || accounts.length === 0) {
        throw new Error('No accounts selected in MetaMask.');
      }
      
      const walletAddress = accounts[0];

      setWalletStatus('Please sign and approve connection in MetaMask...');
      const nonce = Math.floor(Math.random() * 1000000);
      const challengeMessage = `Genanda Bot Real Money Trading Access\n\nPlease approve and sign to verify ownership of your wallet for live trading.\n\nWallet: ${walletAddress}\nNonce: ${nonce}\nTimestamp: ${new Date().toISOString()}`;
      
      const signature = await (window as any).ethereum.request({
        method: 'personal_sign',
        params: [challengeMessage, walletAddress]
      });

      setWalletStatus('Verifying approval and linking real funds...');
      
      const res = await client.post('/auth/wallet', { 
        wallet_address: walletAddress,
        signature: signature,
        message: challengeMessage
      });
      
      setConnectedWallet(walletAddress);
      localStorage.setItem('token', res.data.access_token);
      localStorage.setItem('wallet_address', walletAddress);
      localStorage.setItem('account_mode', 'real_money');

      setWalletStatus('Approved! Entering trading terminal...');
      setTimeout(() => {
        navigate('/app');
      }, 700);
    } catch (err: any) {
      console.error('Wallet connection error:', err);
      if (err?.code === 4001 || err?.message?.includes('User rejected') || err?.message?.includes('denied')) {
        setError('Wallet connection or signature approval was rejected in MetaMask.');
      } else {
        setError(err?.response?.data?.detail || err?.message || 'Failed to connect Web3 wallet. Please try again.');
      }
    } finally {
      setWalletLoading(false);
      setWalletStatus(null);
    }
  };

  // Standard Email Signup (Optional)
  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await client.post('/auth/register', { email, password });
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);
      
      const res = await client.post('/auth/login', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      });
      
      localStorage.setItem('token', res.data.access_token);
      localStorage.setItem('user_email', email);
      localStorage.setItem('account_mode', 'demo');
      navigate('/app');
    } catch (err: any) {
      if (err.response) {
        setError(err.response.data?.detail || 'Registration failed.');
      } else {
        setError('Network error. Backend might be unreachable.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* Brand Header */}
      <div className="text-center space-y-1">
        <div className="flex justify-center mb-2">
          <BrandLogo size={48} glow={true} />
        </div>
        <h1 className="text-2xl font-black text-white tracking-tight">Join Genanda Bot</h1>
        <p className="text-xs text-slate-400 font-mono">Select Your Trading Environment</p>
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

      {/* 1. TRADING MODE SWITCHER (DEMO VS REAL) */}
      <div className="bg-slate-950 p-1.5 rounded-2xl border border-slate-800 flex items-center justify-between gap-1 shadow-inner">
        <button
          type="button"
          onClick={() => setSelectedAuthMode('demo')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-xs font-black transition-all cursor-pointer ${
            selectedAuthMode === 'demo'
              ? 'bg-blue-600 text-white shadow-md shadow-blue-600/40'
              : 'text-slate-400 hover:text-white hover:bg-slate-900'
          }`}
        >
          <span>🎮 Demo Account</span>
          <span className="text-[10px] px-2 py-0.5 rounded-md bg-blue-500/30 text-blue-200 font-bold border border-blue-400/30">
            $300 Virtual
          </span>
        </button>

        <button
          type="button"
          onClick={() => setSelectedAuthMode('real')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-xs font-black transition-all cursor-pointer ${
            selectedAuthMode === 'real'
              ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/40'
              : 'text-slate-400 hover:text-white hover:bg-slate-900'
          }`}
        >
          <span>⚡ Real Account</span>
          <span className="text-[10px] px-2 py-0.5 rounded-md bg-emerald-500/30 text-emerald-200 font-bold border border-emerald-400/30">
            Live Wallet
          </span>
        </button>
      </div>

      {/* 2. DEMO MODE CARD: NO GMAIL / SIGNUP REQUIRED */}
      {selectedAuthMode === 'demo' && (
        <div className="bg-gradient-to-br from-blue-950/40 via-indigo-950/30 to-slate-900 border-2 border-blue-500/40 rounded-2xl p-5 shadow-xl space-y-4 text-left animate-fade-in">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 bg-blue-600 text-white rounded-xl shadow-md shadow-blue-500/30">
                <Zap className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-black text-white">Virtual Demo Account</h2>
                <p className="text-xs text-slate-400">Risk-Free 5-Minute Paper Trading</p>
              </div>
            </div>
            <span className="bg-emerald-500/20 text-emerald-300 text-[10px] font-black px-2.5 py-1 rounded-full border border-emerald-500/30 font-mono uppercase">
              No Gmail Required
            </span>
          </div>

          <p className="text-xs text-slate-300 leading-relaxed bg-blue-950/50 p-3 rounded-xl border border-blue-900/60">
            ✨ Practice automated 5-minute round execution with a fresh <strong>$300.00 virtual paper balance</strong>. Zero signup or Gmail account required — instant 1-click terminal access!
          </p>

          <div className="space-y-1.5 text-xs text-slate-300 font-mono">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
              <span>$300 Initial Virtual Equity (Resettable in Settings)</span>
            </div>
            <div className="flex items-center gap-2">
              <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
              <span>Direct Chainlink & Pyth sub-second feeds</span>
            </div>
            <div className="flex items-center gap-2">
              <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
              <span>Strict hard stop & anti-reversal profit locking</span>
            </div>
          </div>

          <button
            type="button"
            onClick={handleEnterDemoAccount}
            disabled={demoLoading}
            className="w-full bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-700 hover:from-blue-500 hover:to-indigo-500 text-white font-black text-sm py-3.5 px-4 rounded-xl transition-all shadow-lg shadow-blue-600/30 flex items-center justify-center gap-2 cursor-pointer active:scale-98"
          >
            {demoLoading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Entering Demo Terminal...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                <span>Start Demo Trading ($300 Virtual)</span>
                <ArrowRight className="w-4 h-4 ml-1" />
              </>
            )}
          </button>
        </div>
      )}

      {/* 3. REAL MODE CARD: WEB3 WALLET REQUIRED */}
      {selectedAuthMode === 'real' && (
        <div className="bg-gradient-to-br from-purple-950/40 via-indigo-950/30 to-slate-900 border-2 border-emerald-500/40 rounded-2xl p-5 shadow-xl space-y-4 text-left animate-fade-in">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 bg-emerald-600 text-white rounded-xl shadow-md shadow-emerald-500/30">
                <Wallet className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-black text-white">Real Money Account</h2>
                <p className="text-xs text-slate-400">Live Polymarket CLOB Execution</p>
              </div>
            </div>
            <span className="bg-purple-500/20 text-purple-300 text-[10px] font-black px-2.5 py-1 rounded-full border border-purple-500/30 font-mono uppercase">
              Polygon Mainnet
            </span>
          </div>

          <p className="text-xs text-slate-300 leading-relaxed bg-slate-950/50 p-3 rounded-xl border border-slate-800">
            ⚡ Connect your Web3 wallet (MetaMask, Rabby, or Polygon Signer) to trade with real USDC on Polymarket&apos;s Central Limit Order Book with sub-second automation.
          </p>

          {walletStatus && (
            <div className="bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 p-2.5 rounded-xl text-xs flex items-center gap-2 animate-pulse font-mono">
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-400 shrink-0" />
              <span>{walletStatus}</span>
            </div>
          )}

          <button
            onClick={handleConnectWallet}
            disabled={walletLoading}
            type="button"
            className="w-full bg-gradient-to-r from-emerald-600 via-teal-600 to-emerald-700 hover:from-emerald-500 hover:to-teal-500 text-white font-black text-sm py-3.5 px-4 rounded-xl transition-all shadow-lg shadow-emerald-600/30 flex items-center justify-center gap-2 cursor-pointer active:scale-98 disabled:opacity-50"
          >
            {walletLoading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Awaiting MetaMask Approval...</span>
              </>
            ) : (
              <>
                <Wallet className="w-4 h-4" />
                <span>Connect Wallet for Real Money</span>
                <ArrowRight className="w-4 h-4 ml-1" />
              </>
            )}
          </button>

          <p className="text-[10px] text-slate-400 text-center flex items-center justify-center gap-1.5">
            <Shield className="w-3.5 h-3.5 text-emerald-400" />
            <span>Non-custodial: Requires MetaMask signature to verify wallet ownership</span>
          </p>
        </div>
      )}

      {/* 4. COLLAPSIBLE ADMIN / EMAIL SIGNUP */}
      <div className="pt-2 border-t border-slate-800/80">
        <button
          type="button"
          onClick={() => setShowAdminForm(!showAdminForm)}
          className="text-slate-400 hover:text-slate-300 text-xs font-semibold flex items-center justify-center gap-1.5 mx-auto transition-colors cursor-pointer"
        >
          <span>{showAdminForm ? '▲ Hide email registration' : '▼ Or create account with email / password'}</span>
        </button>

        {showAdminForm && (
          <form className="space-y-3 pt-3 animate-fade-in" onSubmit={handleSignup}>
            <div>
              <label className="block text-xs font-bold text-slate-300 mb-1">Email Address</label>
              <input 
                type="email" 
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 outline-none font-mono" 
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
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 outline-none font-mono" 
                placeholder="••••••••••••" 
              />
            </div>
            <button 
              type="submit" 
              disabled={loading}
              className="w-full bg-slate-800 hover:bg-slate-700 text-white font-bold text-xs py-2 rounded-xl transition-all shadow-xs flex justify-center items-center cursor-pointer disabled:opacity-50"
            >
              {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : 'Create Account'}
            </button>
          </form>
        )}
      </div>

      <div className="text-center text-xs text-slate-400 pt-1">
        Already have an account?{' '}
        <Link to="/login" className="text-blue-400 font-bold hover:underline">
          Sign In
        </Link>
      </div>

      {/* MODAL: WEB3 WALLET NOT DETECTED */}
      {isWalletModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="bg-slate-900 border-2 border-indigo-500/40 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 relative text-left">
            <button 
              onClick={() => setIsWalletModalOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-indigo-500/20 text-indigo-400 rounded-xl">
                <Wallet className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-black text-white">Web3 Wallet Required</h3>
                <p className="text-xs text-slate-400">MetaMask or compatible extension not found</p>
              </div>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              To trade with real money and connect live funds on Genanda Bot, please install MetaMask extension or open this website inside the MetaMask mobile app browser.
            </p>

            <div className="flex gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => setIsWalletModalOpen(false)}
                className="w-1/3 py-2.5 rounded-xl text-xs font-bold text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 transition-colors cursor-pointer"
              >
                Close
              </button>
              <a
                href="https://metamask.io/download/"
                target="_blank"
                rel="noopener noreferrer"
                className="w-2/3 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-black text-xs py-2.5 rounded-xl transition-all shadow-md flex justify-center items-center gap-2"
              >
                <span>Install MetaMask</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
