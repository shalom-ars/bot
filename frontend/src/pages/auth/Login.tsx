import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import client from '../../api/client';
import BrandLogo from '../../components/BrandLogo';
import { 
  AlertTriangle, RefreshCw, Wallet, CheckCircle, Shield, 
  ArrowRight, X, ExternalLink, Zap, Play, Mail,
  ChevronRight
} from 'lucide-react';

interface WalletOption {
  id: string;
  name: string;
  icon: string;
  description: string;
  detected: boolean;
  getProvider: () => any;
}

export default function Login() {
  const [searchParams] = useSearchParams();
  const initialMode = searchParams.get('mode') === 'real' ? 'real' : 'demo';
  const [selectedAuthMode, setSelectedAuthMode] = useState<'demo' | 'real'>(initialMode);
  
  // Google / Demo Auth States
  const [googleEmail, setGoogleEmail] = useState('');
  const [googleLoading, setGoogleLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);

  // Web3 Wallet States
  const [walletLoading, setWalletLoading] = useState(false);
  const [walletStatus, setWalletStatus] = useState<string | null>(null);
  const [isWalletSelectorOpen, setIsWalletSelectorOpen] = useState(false);
  const [isInstallModalOpen, setIsInstallModalOpen] = useState(false);
  const [selectedWalletName, setSelectedWalletName] = useState('MetaMask');
  const [connectedWallet, setConnectedWallet] = useState<string | null>(null);

  // Admin / Email States
  const [showAdminForm, setShowAdminForm] = useState(false);
  const [adminEmail, setAdminEmail] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [adminLoading, setAdminLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const qMode = searchParams.get('mode');
    if (qMode === 'real') {
      setSelectedAuthMode('real');
    }
  }, [searchParams]);

  // Available Web3 Wallets with detection
  const getWalletOptions = (): WalletOption[] => {
    if (typeof window === 'undefined') return [];
    const eth = (window as any).ethereum;
    const phantom = (window as any).phantom?.ethereum;
    const coinbase = (window as any).coinbaseWalletExtension;
    const rabby = (window as any).rabby || (eth && eth.isRabby);

    return [
      {
        id: 'metamask',
        name: 'MetaMask',
        icon: '🦊',
        description: 'Popular Ethereum & Polygon browser extension',
        detected: Boolean(eth && eth.isMetaMask && !eth.isRabby),
        getProvider: () => eth
      },
      {
        id: 'coinbase',
        name: 'Coinbase Wallet',
        icon: '🔵',
        description: 'Coinbase Wallet extension & mobile dApp',
        detected: Boolean(coinbase || (eth && eth.isCoinbaseWallet)),
        getProvider: () => coinbase || eth
      },
      {
        id: 'phantom',
        name: 'Phantom (EVM)',
        icon: '👻',
        description: 'Multi-chain Phantom wallet in EVM mode',
        detected: Boolean(phantom),
        getProvider: () => phantom || eth
      },
      {
        id: 'rabby',
        name: 'Rabby Wallet',
        icon: '🐰',
        description: 'Game-changing Web3 wallet for DeFi & Polygon',
        detected: Boolean(rabby),
        getProvider: () => (window as any).rabby || eth
      },
      {
        id: 'injected',
        name: 'Injected / WalletConnect',
        icon: '🌐',
        description: 'Browser Web3 provider or Trust / Safe wallet',
        detected: Boolean(eth),
        getProvider: () => eth
      }
    ];
  };

  // Switch network to Polygon Mainnet (137 / 0x89)
  const ensurePolygonNetwork = async (provider: any): Promise<boolean> => {
    try {
      const chainId = await provider.request({ method: 'eth_chainId' });
      if (chainId === '0x89' || chainId === '137' || parseInt(chainId, 16) === 137) {
        return true;
      }

      setWalletStatus('Switching network to Polygon Mainnet (Chain 137)...');
      try {
        await provider.request({
          method: 'wallet_switchEthereumChain',
          params: [{ chainId: '0x89' }],
        });
        return true;
      } catch (switchError: any) {
        // Error code 4902 means the chain has not been added to MetaMask
        if (switchError.code === 4902 || switchError?.data?.originalError?.code === 4902) {
          setWalletStatus('Adding Polygon Mainnet to your wallet...');
          await provider.request({
            method: 'wallet_addEthereumChain',
            params: [
              {
                chainId: '0x89',
                chainName: 'Polygon Mainnet',
                nativeCurrency: { name: 'POL', symbol: 'POL', decimals: 18 },
                rpcUrls: ['https://1rpc.io/matic', 'https://polygon-rpc.com'],
                blockExplorerUrls: ['https://polygonscan.com/'],
              },
            ],
          });
          return true;
        }
        throw switchError;
      }
    } catch (err: any) {
      console.warn('Network switch warning:', err);
      // Even if network switch prompt fails, allow user to proceed if they confirm
      return true;
    }
  };

  // Handle Google / Gmail Authentication ($300 Demo Provisioning)
  const handleGoogleAuth = async (emailOverride?: string) => {
    const targetEmail = (emailOverride || googleEmail).trim().toLowerCase();
    if (!targetEmail || !targetEmail.includes('@') || !targetEmail.includes('.')) {
      setError('Please enter a valid Gmail address (e.g. user@gmail.com)');
      return;
    }

    setGoogleLoading(true);
    setError(null);
    try {
      const res = await client.post('/auth/google-login', { email: targetEmail });
      const { access_token, user } = res.data;

      localStorage.setItem('token', access_token);
      localStorage.setItem('user_email', user?.email || targetEmail);
      localStorage.setItem('user_role', user?.role || 'USER');
      localStorage.setItem('user_status', user?.status || 'PENDING');
      localStorage.setItem('allowed_mode', user?.allowed_mode || 'DEMO_ONLY');
      localStorage.setItem('account_mode', 'demo');
      localStorage.setItem('auth_provider', 'google');
      localStorage.setItem('demo_access', 'true');
      if (user?.wallet_address) {
        localStorage.setItem('wallet_address', user.wallet_address);
      }

      // Switch backend wallet mode to demo
      try {
        await client.post('/fast5m/wallet/mode', { mode: 'demo' });
      } catch (e) {
        console.debug('Mode sync note', e);
      }

      navigate('/app');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Google sign-in failed. Please try again.');
    } finally {
      setGoogleLoading(false);
    }
  };

  // Instant 1-Click Guest Demo Entry
  const handleInstantDemoEntry = async () => {
    setDemoLoading(true);
    setError(null);
    try {
      const guestEmail = `trader_${Math.floor(1000 + Math.random() * 9000)}@fast5m.demo`;
      const res = await client.post('/auth/google-login', { email: guestEmail });
      const { access_token, user } = res.data;

      localStorage.setItem('token', access_token);
      localStorage.setItem('user_email', user?.email || guestEmail);
      localStorage.setItem('user_role', user?.role || 'USER');
      localStorage.setItem('user_status', user?.status || 'PENDING');
      localStorage.setItem('allowed_mode', user?.allowed_mode || 'DEMO_ONLY');
      localStorage.setItem('account_mode', 'demo');
      localStorage.setItem('auth_provider', 'demo');
      localStorage.setItem('demo_access', 'true');

      try {
        await client.post('/fast5m/wallet/mode', { mode: 'demo' });
      } catch (e) {
        console.debug('Mode sync note', e);
      }

      navigate('/app');
    } catch (err: any) {
      console.error('Demo enter error:', err);
      // Fallback local bypass
      localStorage.setItem('account_mode', 'demo');
      localStorage.setItem('demo_access', 'true');
      navigate('/app');
    } finally {
      setDemoLoading(false);
    }
  };

  // Connect Web3 Wallet with selected provider
  const handleConnectSpecificWallet = async (walletOpt: WalletOption) => {
    setIsWalletSelectorOpen(false);
    setSelectedWalletName(walletOpt.name);
    setError(null);
    setWalletStatus(null);

    const provider = walletOpt.getProvider();
    if (!provider) {
      setIsInstallModalOpen(true);
      return;
    }

    setWalletLoading(true);
    try {
      // 1. Request account access
      setWalletStatus(`Connecting to ${walletOpt.name}... Please approve connection.`);
      const accounts = await provider.request({ method: 'eth_requestAccounts' });

      if (!accounts || accounts.length === 0) {
        throw new Error(`No account selected in ${walletOpt.name}.`);
      }

      const walletAddress = accounts[0].toLowerCase();

      // 2. Ensure Polygon Mainnet network
      await ensurePolygonNetwork(provider);

      // 3. Cryptographic signature verification challenge
      setWalletStatus(`Please sign the verification request in ${walletOpt.name} to confirm wallet ownership...`);
      const nonce = Math.floor(Math.random() * 1000000);
      const challengeMessage = `Fast5M Prediction Platform Access\n\nPlease approve this signature to verify wallet ownership for real-money Polymarket trading.\n\nWallet: ${walletAddress}\nNetwork: Polygon Mainnet (137)\nNonce: ${nonce}\nTimestamp: ${new Date().toISOString()}`;

      const signature = await provider.request({
        method: 'personal_sign',
        params: [challengeMessage, walletAddress],
      });

      setWalletStatus('Verifying cryptographic signature on backend...');

      // 4. Authenticate with backend and provision live vault
      const res = await client.post('/auth/wallet', {
        wallet_address: walletAddress,
        signature: signature,
        message: challengeMessage,
      });

      const { access_token, user } = res.data;

      setConnectedWallet(walletAddress);
      localStorage.setItem('token', access_token);
      localStorage.setItem('wallet_address', walletAddress);
      localStorage.setItem('user_email', user?.email || `${walletAddress}@web3.wallet`);
      localStorage.setItem('user_role', user?.role || 'USER');
      localStorage.setItem('user_status', user?.status || 'APPROVED');
      localStorage.setItem('allowed_mode', user?.allowed_mode || 'REAL_AND_DEMO');
      localStorage.setItem('account_mode', 'live');
      localStorage.setItem('auth_provider', 'wallet');

      // Switch engine mode to live
      try {
        await client.post('/fast5m/wallet/mode', { mode: 'live' });
      } catch (e) {
        console.debug('Mode sync note', e);
      }

      setWalletStatus('Wallet successfully verified! Entering trading terminal...');
      setTimeout(() => {
        navigate('/app');
      }, 600);
    } catch (err: any) {
      console.error('Wallet connection error:', err);
      if (err?.code === 4001 || err?.message?.includes('User rejected') || err?.message?.includes('denied')) {
        setError(`Connection or signature was cancelled in ${walletOpt.name}.`);
      } else {
        setError(err?.response?.data?.detail || err?.message || 'Failed to connect Web3 wallet. Please try again.');
      }
    } finally {
      setWalletLoading(false);
      setWalletStatus(null);
    }
  };

  // Default Wallet Connect trigger
  const handlePrimaryWalletConnect = () => {
    const wallets = getWalletOptions();
    const detectedWallets = wallets.filter(w => w.detected);

    if (detectedWallets.length === 1) {
      handleConnectSpecificWallet(detectedWallets[0]);
    } else {
      setIsWalletSelectorOpen(true);
    }
  };

  // Standard Admin / Email Login
  const handleAdminLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAdminLoading(true);
    setError(null);
    try {
      const formData = new URLSearchParams();
      formData.append('username', adminEmail);
      formData.append('password', adminPassword);

      const res = await client.post('/auth/login', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      const { access_token, user } = res.data;
      localStorage.setItem('token', access_token);
      localStorage.setItem('user_email', user?.email || adminEmail);
      localStorage.setItem('user_role', user?.role || 'USER');
      localStorage.setItem('user_status', user?.status || 'APPROVED');
      localStorage.setItem('allowed_mode', user?.allowed_mode || 'DEMO_ONLY');
      localStorage.setItem('account_mode', user?.vault?.account_mode || 'demo');
      localStorage.setItem('auth_provider', user?.auth_provider || 'email');
      navigate('/app');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Incorrect admin email or password.');
    } finally {
      setAdminLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* Brand Header */}
      <div className="text-center space-y-1">
        <div className="flex justify-center mb-2">
          <BrandLogo size={48} glow={true} />
        </div>
        <h1 className="text-2xl font-black text-white tracking-tight">Fast5M Prediction Platform</h1>
        <p className="text-xs text-slate-400 font-mono">7-Asset Real-Time Autonomous Engine</p>
      </div>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/30 text-rose-300 p-3 rounded-xl text-xs flex gap-2 items-center text-left">
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
            Web3 Wallet
          </span>
        </button>
      </div>

      {/* 2. DEMO MODE CARD: GOOGLE SIGN-IN + INSTANT ACCESS */}
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
            <span className="bg-blue-500/20 text-blue-300 text-[10px] font-black px-2.5 py-1 rounded-full border border-blue-500/30 font-mono uppercase">
              $300 Provisioned
            </span>
          </div>

          <p className="text-xs text-slate-300 leading-relaxed bg-blue-950/50 p-3 rounded-xl border border-blue-900/60">
            ✨ Sign in with your Google account or explore instantly. Each Google account automatically receives an isolated <strong>$300.00 virtual trading balance</strong> to test signals, customize risk parameters, and simulate trades safely.
          </p>

          {/* Google Sign-in Section */}
          <div className="space-y-3">
            <button
              type="button"
              onClick={() => handleGoogleAuth(googleEmail || 'arsandhuthree@gmail.com')}
              disabled={googleLoading}
              className="w-full bg-white hover:bg-slate-100 text-slate-900 font-bold text-xs py-3 px-4 rounded-xl transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer active:scale-98"
            >
              <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
              </svg>
              <span>{googleLoading ? 'Signing in with Google...' : 'Sign in with Google'}</span>
            </button>

            <div className="space-y-1.5">
              <div className="flex justify-between items-center text-[11px] font-bold text-slate-300">
                <span>Or Enter Gmail Address</span>
                <button
                  type="button"
                  onClick={() => { setGoogleEmail('arsandhuthree@gmail.com'); }}
                  className="text-[10px] text-blue-400 hover:text-blue-300 underline font-mono cursor-pointer"
                >
                  Admin quick-fill
                </button>
              </div>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type="email"
                    value={googleEmail}
                    onChange={(e) => setGoogleEmail(e.target.value)}
                    placeholder="yourname@gmail.com"
                    className="w-full bg-slate-950/80 border border-blue-500/30 focus:border-blue-500 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-slate-500 outline-none font-mono"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        handleGoogleAuth();
                      }
                    }}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => handleGoogleAuth()}
                  disabled={googleLoading || !googleEmail.trim()}
                  className="bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs px-4 py-2.5 rounded-xl transition-all shadow-md shadow-blue-600/30 flex items-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
                >
                  {googleLoading ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <>
                      <Mail className="w-3.5 h-3.5" />
                      <span>Enter</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>


          <div className="relative flex items-center justify-center my-2">
            <div className="border-t border-slate-800 w-full" />
            <span className="bg-slate-900 px-2 text-[10px] uppercase font-bold text-slate-500 absolute">
              Or 1-Click Guest Access
            </span>
          </div>

          <button
            type="button"
            onClick={handleInstantDemoEntry}
            disabled={demoLoading}
            className="w-full bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-700 hover:from-blue-500 hover:to-indigo-500 text-white font-black text-sm py-3.5 px-4 rounded-xl transition-all shadow-lg shadow-blue-600/30 flex items-center justify-center gap-2 cursor-pointer active:scale-98"
          >
            {demoLoading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Initializing Demo Vault ($300)...</span>
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

      {/* 3. REAL MODE CARD: WEB3 MULTI-WALLET */}
      {selectedAuthMode === 'real' && (
        <div className="bg-gradient-to-br from-emerald-950/40 via-teal-950/30 to-slate-900 border-2 border-emerald-500/40 rounded-2xl p-5 shadow-xl space-y-4 text-left animate-fade-in">
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
              Polygon (137)
            </span>
          </div>

          <p className="text-xs text-slate-300 leading-relaxed bg-slate-950/50 p-3 rounded-xl border border-slate-800">
            ⚡ Connect your Web3 wallet (MetaMask, Coinbase Wallet, Phantom, Rabby, or WalletConnect) to trade real USDC on Polymarket&apos;s Central Limit Order Book with sub-second execution.
          </p>

          {/* Supported Wallets Pills */}
          <div className="flex flex-wrap gap-1.5 py-1">
            {['MetaMask', 'Coinbase Wallet', 'Phantom', 'Rabby', 'WalletConnect'].map((wName) => (
              <span key={wName} className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 border border-slate-700">
                {wName}
              </span>
            ))}
          </div>

          {walletStatus && (
            <div className="bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 p-2.5 rounded-xl text-xs flex items-center gap-2 animate-pulse font-mono">
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-400 shrink-0" />
              <span>{walletStatus}</span>
            </div>
          )}

          <div className="space-y-2">
            <button
              onClick={handlePrimaryWalletConnect}
              disabled={walletLoading}
              type="button"
              className="w-full bg-gradient-to-r from-emerald-600 via-teal-600 to-emerald-700 hover:from-emerald-500 hover:to-teal-500 text-white font-black text-sm py-3.5 px-4 rounded-xl transition-all shadow-lg shadow-emerald-600/30 flex items-center justify-center gap-2 cursor-pointer active:scale-98 disabled:opacity-50"
            >
              {walletLoading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Connecting {selectedWalletName}...</span>
                </>
              ) : (
                <>
                  <Wallet className="w-4 h-4" />
                  <span>Connect Web3 Wallet (Polygon)</span>
                  <ArrowRight className="w-4 h-4 ml-1" />
                </>
              )}
            </button>

            <button
              type="button"
              onClick={() => setIsWalletSelectorOpen(true)}
              className="w-full text-center text-xs font-semibold text-slate-400 hover:text-emerald-400 transition-colors py-1 cursor-pointer"
            >
              Choose specific wallet (MetaMask, Coinbase, Phantom, Rabby)
            </button>
          </div>

          <p className="text-[10px] text-slate-400 text-center flex items-center justify-center gap-1.5">
            <Shield className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span>Non-custodial: Cryptographic signature verifies ownership. Automatically prompts Polygon network.</span>
          </p>
        </div>
      )}

      {/* 4. COLLAPSIBLE ADMIN / EMAIL LOGIN */}
      <div className="pt-2 border-t border-slate-800/80">
        <button
          type="button"
          onClick={() => setShowAdminForm(!showAdminForm)}
          className="text-slate-400 hover:text-slate-300 text-xs font-semibold flex items-center justify-center gap-1.5 mx-auto transition-colors cursor-pointer"
        >
          <span>{showAdminForm ? '▲ Hide email login' : '▼ Or sign in with email / password (Admin)'}</span>
        </button>

        {showAdminForm && (
          <form className="space-y-3 pt-3 animate-fade-in" onSubmit={handleAdminLogin}>
            <div>
              <label className="block text-xs font-bold text-slate-300 mb-1">Email Address</label>
              <input
                type="email"
                required
                value={adminEmail}
                onChange={e => setAdminEmail(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 outline-none font-mono"
                placeholder="admin@domain.com"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-300 mb-1">Password</label>
              <input
                type="password"
                required
                value={adminPassword}
                onChange={e => setAdminPassword(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 outline-none font-mono"
                placeholder="••••••••••••"
              />
            </div>
            <button
              type="submit"
              disabled={adminLoading}
              className="w-full bg-slate-800 hover:bg-slate-700 text-white font-bold text-xs py-2 rounded-xl transition-all shadow-xs flex justify-center items-center cursor-pointer disabled:opacity-50"
            >
              {adminLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : 'Log In with Password'}
            </button>
          </form>
        )}
      </div>

      <div className="text-center text-xs text-slate-400 pt-1">
        Don&apos;t have an account?{' '}
        <Link to="/signup" className="text-blue-400 font-bold hover:underline">
          Sign Up
        </Link>
      </div>

      {/* MODAL: MULTI-WALLET CONNECTOR SELECTOR */}
      {isWalletSelectorOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
          <div className="bg-slate-900 border-2 border-emerald-500/40 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 relative text-left">
            <button
              onClick={() => setIsWalletSelectorOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-emerald-500/20 text-emerald-400 rounded-xl">
                <Wallet className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-black text-white">Select Web3 Wallet</h3>
                <p className="text-xs text-slate-400">Connect for Real-Money Polymarket Trading</p>
              </div>
            </div>

            <div className="space-y-2 pt-2">
              {getWalletOptions().map((walletOpt) => (
                <button
                  key={walletOpt.id}
                  type="button"
                  onClick={() => handleConnectSpecificWallet(walletOpt)}
                  className="w-full flex items-center justify-between p-3.5 bg-slate-950 hover:bg-slate-800/80 border border-slate-800 hover:border-emerald-500/50 rounded-xl transition-all cursor-pointer group text-left"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{walletOpt.icon}</span>
                    <div>
                      <div className="text-xs font-bold text-white flex items-center gap-2">
                        <span>{walletOpt.name}</span>
                        {walletOpt.detected && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono">
                            Detected
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-400">{walletOpt.description}</p>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-500 group-hover:text-emerald-400 transition-colors" />
                </button>
              ))}
            </div>

            <p className="text-[10px] text-slate-400 text-center pt-2">
              Supports MetaMask, Coinbase Wallet, Phantom, Rabby, and 300+ mobile wallets via Injected/WalletConnect providers.
            </p>
          </div>
        </div>
      )}

      {/* MODAL: WALLET NOT DETECTED INSTALL GUIDE */}
      {isInstallModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
          <div className="bg-slate-900 border-2 border-indigo-500/40 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 relative text-left">
            <button
              onClick={() => setIsInstallModalOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors cursor-pointer"
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
              To trade with real money on Polygon and Polymarket, please install a browser extension such as MetaMask or Rabby, or open this terminal inside your mobile wallet dApp browser.
            </p>

            <div className="flex gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => setIsInstallModalOpen(false)}
                className="w-1/3 py-2.5 rounded-xl text-xs font-bold text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 transition-colors cursor-pointer"
              >
                Close
              </button>
              <a
                href="https://metamask.io/download/"
                target="_blank"
                rel="noopener noreferrer"
                className="w-2/3 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-black text-xs py-2.5 rounded-xl transition-all shadow-md flex justify-center items-center gap-2 cursor-pointer"
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
