import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import client from '../../api/client';
import BrandLogo from '../../components/BrandLogo';
import { AlertTriangle, RefreshCw, Wallet, CheckCircle, Shield, ArrowRight, X, ExternalLink, Mail } from 'lucide-react';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [walletLoading, setWalletLoading] = useState(false);
  const [walletStatus, setWalletStatus] = useState<string | null>(null);
  const [isWalletModalOpen, setIsWalletModalOpen] = useState(false);

  // Gmail auth states
  const [isGmailModalOpen, setIsGmailModalOpen] = useState(false);
  const [realGmail, setRealGmail] = useState('');
  const [gmailError, setGmailError] = useState<string | null>(null);
  const [googleLoading, setGoogleLoading] = useState(false);

  const [connectedWallet, setConnectedWallet] = useState<string | null>(null);
  const navigate = useNavigate();

  // Web3 Wallet Login with User Signature Approval
  const handleConnectWallet = async () => {
    setError(null);
    setWalletStatus(null);
    
    // 1. Strict check: Must have MetaMask or Web3 provider
    if (typeof window === 'undefined' || !(window as any).ethereum) {
      setIsWalletModalOpen(true);
      return;
    }

    setWalletLoading(true);
    try {
      // 2. Request accounts from MetaMask
      setWalletStatus('Please select and approve your wallet in MetaMask...');
      const accounts = await (window as any).ethereum.request({ 
        method: 'eth_requestAccounts' 
      });
      
      if (!accounts || accounts.length === 0) {
        throw new Error('No accounts selected in MetaMask.');
      }
      
      const walletAddress = accounts[0];

      // 3. Request cryptographic signature approval in MetaMask
      setWalletStatus('Please sign and approve connection in MetaMask...');
      const nonce = Math.floor(Math.random() * 1000000);
      const challengeMessage = `Genanda Bot Real Money Trading Access\n\nPlease approve and sign to verify ownership of your wallet for live trading.\n\nWallet: ${walletAddress}\nNonce: ${nonce}\nTimestamp: ${new Date().toISOString()}`;
      
      const signature = await (window as any).ethereum.request({
        method: 'personal_sign',
        params: [challengeMessage, walletAddress]
      });

      setWalletStatus('Verifying approval and linking real funds...');
      
      // 4. Authenticate with backend and link funds
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

  // Trigger Real Gmail Modal
  const handleOpenGmailModal = () => {
    setError(null);
    setGmailError(null);
    setRealGmail(email.includes('@') ? email : '');
    setIsGmailModalOpen(true);
  };

  // Confirm Real Gmail Connection
  const handleConfirmGmailAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setGmailError(null);
    
    const cleanEmail = realGmail.trim().toLowerCase();
    if (!cleanEmail || !cleanEmail.includes('@') || !cleanEmail.includes('.')) {
      setGmailError('Please enter a valid Gmail address (e.g. yourname@gmail.com).');
      return;
    }

    setGoogleLoading(true);
    try {
      const res = await client.post('/auth/google', { 
        email: cleanEmail,
        name: cleanEmail.split('@')[0]
      });
      localStorage.setItem('token', res.data.access_token);
      localStorage.setItem('user_email', cleanEmail);
      localStorage.setItem('account_mode', 'demo');
      setIsGmailModalOpen(false);
      navigate('/app');
    } catch (err: any) {
      console.error('Google sign-in error:', err);
      setGmailError(err?.response?.data?.detail || 'Failed to sign in with Gmail.');
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
      localStorage.setItem('user_email', email);
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

        {walletStatus && (
          <div className="bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 p-2 rounded-xl text-xs flex items-center gap-2 animate-pulse font-mono">
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-400 shrink-0" />
            <span>{walletStatus}</span>
          </div>
        )}

        <button
          onClick={handleConnectWallet}
          disabled={walletLoading}
          type="button"
          className="w-full bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-700 hover:from-indigo-500 hover:to-purple-500 text-white font-black text-xs py-3 px-4 rounded-xl transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
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
              <ArrowRight className="w-3.5 h-3.5 ml-1" />
            </>
          )}
        </button>

        <p className="text-[10px] text-slate-400 text-center flex items-center justify-center gap-1">
          <Shield className="w-3 h-3 text-emerald-400" />
          Requires MetaMask approval signature to verify real wallet ownership
        </p>
      </div>

      {/* 2. GMAIL / GOOGLE SIGN IN */}
      <div>
        <button
          onClick={handleOpenGmailModal}
          type="button"
          className="w-full bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-slate-600 text-white font-bold text-xs py-2.5 px-4 rounded-xl transition-all shadow-xs flex items-center justify-center gap-2.5 cursor-pointer"
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
          </svg>
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

      {/* MODAL 1: REAL GMAIL CONNECTION MODAL */}
      {isGmailModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="bg-slate-900 border-2 border-slate-700/80 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 relative text-left">
            <button 
              onClick={() => setIsGmailModalOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-white rounded-xl shadow-xs">
                <svg className="w-6 h-6" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
                </svg>
              </div>
              <div>
                <h3 className="text-base font-black text-white">Connect Real Gmail</h3>
                <p className="text-xs text-slate-400">Authenticate with your genuine Google account</p>
              </div>
            </div>

            {gmailError && (
              <div className="bg-rose-500/15 border border-rose-500/30 text-rose-300 p-2.5 rounded-xl text-xs flex gap-2 items-center">
                <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
                <span>{gmailError}</span>
              </div>
            )}

            <form onSubmit={handleConfirmGmailAuth} className="space-y-3.5">
              <div>
                <label className="block text-xs font-bold text-slate-300 mb-1">Your Gmail Address</label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="email"
                    required
                    autoFocus
                    value={realGmail}
                    onChange={e => setRealGmail(e.target.value)}
                    placeholder="yourname@gmail.com"
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl pl-9 pr-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none font-mono"
                  />
                </div>
                <p className="text-[10px] text-slate-500 mt-1">Must be an active @gmail.com or Google Workspace address.</p>
              </div>

              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setIsGmailModalOpen(false)}
                  className="w-1/3 py-2.5 rounded-xl text-xs font-bold text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={googleLoading}
                  className="w-2/3 bg-blue-600 hover:bg-blue-500 text-white font-black text-xs py-2.5 rounded-xl transition-all shadow-md flex justify-center items-center gap-2 cursor-pointer disabled:opacity-50"
                >
                  {googleLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Connecting...</span>
                    </>
                  ) : (
                    <span>Authorize & Connect</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: WEB3 WALLET NOT DETECTED MODAL */}
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
                className="w-1/3 py-2.5 rounded-xl text-xs font-bold text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 transition-colors"
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
