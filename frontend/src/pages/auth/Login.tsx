import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import client from '../../api/client';
import BrandLogo from '../../components/BrandLogo';
import { 
  AlertTriangle, RefreshCw, CheckCircle, 
  ArrowRight, X, ExternalLink, Zap, Mail,
  Lock
} from 'lucide-react';

export default function Login() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // Modals state
  const [isDemoModalOpen, setIsDemoModalOpen] = useState(false);
  const [isInstallModalOpen, setIsInstallModalOpen] = useState(false);

  // Google / Demo Auth States
  const [googleEmail, setGoogleEmail] = useState('');
  const [googleLoading, setGoogleLoading] = useState(false);

  // Web3 Wallet States
  const [walletLoading, setWalletLoading] = useState(false);
  const [walletStatus, setWalletStatus] = useState<string | null>(null);
  const [connectedWallet, setConnectedWallet] = useState<string | null>(null);

  // Admin / Password Login States
  const [showAdminForm, setShowAdminForm] = useState(false);
  const [adminEmail, setAdminEmail] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [adminLoading, setAdminLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const getOAuthRedirectUri = () => {
    if (typeof window === 'undefined') return 'http://localhost/api/auth/google/callback';
    // Must match what the backend sends to Google's token exchange endpoint.
    // Flow: Google → /api/auth/google/callback (backend) → /login?token=xxx (frontend)
    const envRedirectUri = (import.meta as any).env?.VITE_GOOGLE_REDIRECT_URI;
    if (envRedirectUri) return envRedirectUri;
    return `${window.location.origin}/api/auth/google/callback`;
  };

  useEffect(() => {
    const qMode = searchParams.get('mode');
    if (qMode === 'demo') {
      setIsDemoModalOpen(true);
    } else if (qMode === 'real') {
      handleConnectRabby();
    }

    // 1. Check for Google OAuth errors in query parameters
    const qError = searchParams.get('error') || searchParams.get('error_description');
    if (qError) {
      setError(`Google authentication failed: ${qError}`);
      window.history.replaceState(null, '', window.location.pathname);
      return;
    }

    // 2. Check for session token returned via backend redirect
    const qToken = searchParams.get('token');
    if (qToken) {
      localStorage.setItem('token', qToken);
      localStorage.setItem('account_mode', 'demo');
      localStorage.setItem('auth_provider', 'google');
      window.history.replaceState(null, '', window.location.pathname);
      client.get('/auth/me').then(res => {
        applyAuthSession(qToken, res.data);
      }).catch(() => {
        navigate('/app');
      });
      return;
    }

    // 3. Check for Google OAuth authorization code in query parameters
    const qCode = searchParams.get('code');
    if (qCode) {
      if (window.opener && window.opener !== window) {
        try {
          window.opener.postMessage({ type: 'GOOGLE_OAUTH_CODE', code: qCode }, window.location.origin);
          window.close();
          return;
        } catch (e) {
          console.debug('Opener postMessage notice', e);
        }
      }
      window.history.replaceState(null, '', window.location.pathname);
      handleGoogleCodeExchange(qCode, getOAuthRedirectUri());
      return;
    }

    // 4. Check for Google OAuth callback in URL hash (implicit flow fallback)
    if (typeof window !== 'undefined' && window.location.hash) {
      const hash = window.location.hash;
      if (hash.includes('access_token=') || hash.includes('id_token=')) {
        const hashParams = new URLSearchParams(hash.replace(/^#/, ''));
        const accessTok = hashParams.get('access_token');
        const idTok = hashParams.get('id_token');
        window.history.replaceState(null, '', window.location.pathname);
        if (accessTok || idTok) {
          processGoogleAuthPayload({ access_token: accessTok || undefined, id_token: idTok || undefined });
        }
      }
    }
  }, [searchParams]);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type === 'GOOGLE_OAUTH_CODE' && event.data.code) {
        handleGoogleCodeExchange(event.data.code, getOAuthRedirectUri());
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  // Rabby Wallet Provider Detection (Sole and Default Web3 Wallet)
  const getRabbyProvider = (): any => {
    if (typeof window === 'undefined') return null;
    const eth = (window as any).ethereum;
    if ((window as any).rabby) return (window as any).rabby;
    if (eth && eth.isRabby) return eth;
    if (eth && eth.providers && Array.isArray(eth.providers)) {
      const found = eth.providers.find((p: any) => p.isRabby);
      if (found) return found;
    }
    return null;
  };

  const isRabbyDetected = (): boolean => Boolean(getRabbyProvider());

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
      return true;
    }
  };

  // Common helper to store session and route user into dashboard
  const applyAuthSession = (access_token: string, user: any) => {
    const userEmail = (user?.email || '').trim().toLowerCase();
    const isAdmin = userEmail === 'shalombinrasheed@gmail.com';
    const userStatus = isAdmin ? 'APPROVED' : (user?.status || 'PENDING');
    const userRole = isAdmin ? 'SUPER_ADMIN' : (user?.role || 'USER');

    localStorage.setItem('token', access_token);
    localStorage.setItem('user_email', userEmail);
    localStorage.setItem('user_role', userRole);
    localStorage.setItem('user_status', userStatus);
    localStorage.setItem('allowed_mode', user?.allowed_mode || (isAdmin ? 'REAL_AND_DEMO' : 'DEMO_ONLY'));
    localStorage.setItem('account_mode', 'demo');
    localStorage.setItem('auth_provider', 'google');
    if (user?.wallet_address) {
      localStorage.setItem('wallet_address', user.wallet_address);
    }

    try {
      client.post('/fast5m/wallet/mode', { mode: 'demo' }).catch(() => {});
    } catch (e) {
      console.debug('Mode sync note', e);
    }

    setIsDemoModalOpen(false);
    navigate('/app');
  };

  // Google OAuth authorization code exchange
  const handleGoogleCodeExchange = async (code: string, redirectUri?: string) => {
    setGoogleLoading(true);
    setError(null);
    try {
      const effectiveRedirectUri = redirectUri || getOAuthRedirectUri();
      const res = await client.post('/auth/google/callback', {
        code,
        redirect_uri: effectiveRedirectUri
      });
      const { access_token, user } = res.data;
      applyAuthSession(access_token, user);
    } catch (err: any) {
      console.error('Google authorization code exchange error:', err);
      setError(err?.response?.data?.detail || 'Google authentication failed. Please try again.');
    } finally {
      setGoogleLoading(false);
    }
  };

  // Common processor for Google authentication payloads (access_token, id_token, direct email)
  const processGoogleAuthPayload = async (payload: { access_token?: string; id_token?: string; credential?: string; email?: string }) => {
    setGoogleLoading(true);
    setError(null);
    try {
      const res = await client.post('/auth/google-login', payload);
      const { access_token, user } = res.data;
      applyAuthSession(access_token, user);
    } catch (err: any) {
      console.error('Google sign-in error:', err);
      setError(err?.response?.data?.detail || 'Google sign-in failed. Please try again.');
    } finally {
      setGoogleLoading(false);
    }
  };

  // Open Google OAuth popup window with URL
  const openGoogleOAuthUrlPopup = (url: string, redirectUri: string) => {
    const width = 520;
    const height = 640;
    const left = window.screenX + (window.outerWidth - width) / 2;
    const top = window.screenY + (window.outerHeight - height) / 2;

    const popup = window.open(
      url,
      'google_oauth_select_account',
      `width=${width},height=${height},left=${left},top=${top},status=no,toolbar=no,menubar=no`
    );

    if (!popup || popup.closed) {
      window.location.href = url;
      return;
    }

    const pollTimer = setInterval(async () => {
      try {
        if (!popup || popup.closed) {
          clearInterval(pollTimer);
          setGoogleLoading(false);
          return;
        }

        if (popup.location && popup.location.origin === window.location.origin) {
          const search = popup.location.search;
          const hash = popup.location.hash;

          if (search) {
            const pParams = new URLSearchParams(search);
            const code = pParams.get('code');
            const err = pParams.get('error') || pParams.get('error_description');
            const token = pParams.get('token');

            if (code || err || token) {
              clearInterval(pollTimer);
              popup.close();

              if (err) {
                setError(`Google authentication failed: ${err}`);
                setGoogleLoading(false);
                return;
              }
              if (token) {
                applyAuthSession(token, { email: '' });
                return;
              }
              if (code) {
                await handleGoogleCodeExchange(code, redirectUri);
                return;
              }
            }
          }

          if (hash && (hash.includes('access_token=') || hash.includes('id_token='))) {
            clearInterval(pollTimer);
            popup.close();
            const hashParams = new URLSearchParams(hash.replace(/^#/, ''));
            const accessTok = hashParams.get('access_token');
            const idTok = hashParams.get('id_token');
            processGoogleAuthPayload({ access_token: accessTok || undefined, id_token: idTok || undefined });
          }
        }
      } catch {
        // Cross-origin access expected while user is selecting account on accounts.google.com
      }
    }, 500);
  };


  // Trigger Google OAuth flow with explicit prompt: 'select_account'
  const triggerGoogleOAuthFlow = async () => {
    setGoogleLoading(true);
    setError(null);

    const redirectUri = getOAuthRedirectUri();
    const googleClientId =
      (import.meta as any).env?.VITE_GOOGLE_CLIENT_ID ||
      '249826315250-n48g1r4vhfv9h7kndfmlq0d60sk64u6f.apps.googleusercontent.com';

    console.log('[OAuth] Starting Google OAuth flow');
    console.log('[OAuth] redirect_uri:', redirectUri);

    // 1. Fetch formatted OAuth authorization URL from backend (preferred — ensures redirect_uri matches exactly)
    try {
      const res = await client.get(`/auth/google/url?redirect_uri=${encodeURIComponent(redirectUri)}`);
      if (res.data?.auth_url) {
        console.log('[OAuth] Got auth_url from backend:', res.data.auth_url);
        // If redirect goes to backend callback, use direct navigation (not popup).
        // Backend /api/auth/google/callback will redirect to /login?token=xxx after exchange.
        const isBackendCallback = redirectUri.includes('/api/auth/');
        if (isBackendCallback) {
          window.location.href = res.data.auth_url;
        } else {
          openGoogleOAuthUrlPopup(res.data.auth_url, redirectUri);
        }
        return;
      }
    } catch (e) {
      console.warn('[OAuth] Could not fetch auth URL from backend, using client-side URL:', e);
    }

    // 2. Fallback: build URL client-side and use direct redirect (backend callback) or popup (frontend callback)
    const stateNonce = Math.random().toString(36).substring(2, 12);
    sessionStorage.setItem('oauth_state', stateNonce);
    const params = new URLSearchParams({
      client_id: googleClientId,
      redirect_uri: redirectUri,
      response_type: 'code',
      scope: 'openid email profile',
      prompt: 'select_account',
      access_type: 'offline',
      state: stateNonce,
    });
    const fallbackUrl = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
    console.log('[OAuth] Fallback auth URL:', fallbackUrl);
    const isBackendCallback = redirectUri.includes('/api/auth/');
    if (isBackendCallback) {
      window.location.href = fallbackUrl;
    } else {
      openGoogleOAuthUrlPopup(fallbackUrl, redirectUri);
    }
  };

  // Direct manual Gmail authentication
  const handleGoogleAuth = async (emailOverride?: string) => {
    const targetEmail = (emailOverride || googleEmail).trim().toLowerCase();
    if (!targetEmail || !targetEmail.includes('@') || !targetEmail.includes('.')) {
      setError('Please enter a valid Gmail address (e.g. user@gmail.com)');
      return;
    }
    await processGoogleAuthPayload({ email: targetEmail });
  };


  // Connect Rabby Wallet (Sole & Default Web3 Provider)
  const handleConnectRabby = async () => {
    setError(null);
    setWalletStatus(null);

    const provider = getRabbyProvider();
    if (!provider || !isRabbyDetected()) {
      setIsInstallModalOpen(true);
      return;
    }

    setWalletLoading(true);
    try {
      setWalletStatus('Connecting to Rabby Wallet... Please approve access.');
      const accounts = await provider.request({ method: 'eth_requestAccounts' });

      if (!accounts || accounts.length === 0) {
        throw new Error('No account selected in Rabby Wallet.');
      }

      const walletAddress = accounts[0].toLowerCase();
      // Enforce network validation for Polygon Mainnet (Chain ID 137 / 0x89) directly through Rabby's provider API
      await ensurePolygonNetwork(provider);

      setWalletStatus('Please sign verification request in Rabby Wallet to confirm wallet ownership...');
      const nonce = Math.floor(Math.random() * 1000000);
      const challengeMessage = `Fast5M Prediction Platform Access (Rabby Wallet)\n\nPlease approve this signature to verify wallet ownership for real-money Polymarket trading.\n\nWallet: ${walletAddress}\nNetwork: Polygon Mainnet (137)\nNonce: ${nonce}\nTimestamp: ${new Date().toISOString()}`;

      const signature = await provider.request({
        method: 'personal_sign',
        params: [challengeMessage, walletAddress],
      });

      setWalletStatus('Verifying Rabby wallet signature on backend...');

      const res = await client.post('/auth/wallet', {
        wallet_address: walletAddress,
        wallet_type: 'rabby',
        signature: signature,
        message: challengeMessage,
      });

      const { access_token, user } = res.data;

      setConnectedWallet(walletAddress);
      localStorage.setItem('token', access_token);
      localStorage.setItem('wallet_address', walletAddress);
      localStorage.setItem('wallet_type', 'rabby');
      localStorage.setItem('user_email', user?.email || `${walletAddress}@web3.wallet`);
      localStorage.setItem('user_role', user?.role || 'USER');
      localStorage.setItem('user_status', user?.status || 'APPROVED');
      localStorage.setItem('allowed_mode', user?.allowed_mode || 'REAL_AND_DEMO');
      localStorage.setItem('account_mode', 'live');
      localStorage.setItem('auth_provider', 'wallet');

      try {
        await client.post('/fast5m/wallet/mode', { mode: 'live' });
      } catch (e) {
        console.debug('Mode sync note', e);
      }

      try {
        await client.post('/fast5m/wallet/sync-rabby', {
          wallet_address: walletAddress,
          action: 'connect'
        }, {
          headers: { Authorization: `Bearer ${access_token}` }
        });
      } catch (e) {
        console.debug('Rabby sync note', e);
      }

      setWalletStatus('Rabby Wallet connected! Entering trading terminal...');
      setTimeout(() => {
        navigate('/app');
      }, 500);
    } catch (err: any) {
      console.error('Rabby connect error:', err);
      if (err?.code === 4001 || err?.message?.includes('User rejected') || err?.message?.includes('denied')) {
        setError('Connection or signature was cancelled in Rabby Wallet.');
      } else {
        setError(err?.response?.data?.detail || err?.message || 'Failed to connect Rabby Wallet. Please ensure Rabby is unlocked.');
      }
    } finally {
      setWalletLoading(false);
      setWalletStatus(null);
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
    <div className="space-y-6">
      {/* Brand Header */}
      <div className="text-center space-y-1.5">
        <div className="flex justify-center mb-2">
          <BrandLogo size={52} glow={true} />
        </div>
        <h1 className="text-2xl font-black text-white tracking-tight">Fast5M Prediction Platform</h1>
        <p className="text-xs text-slate-400 font-mono">Autonomous 5-Minute Algorithmic Trading</p>
      </div>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/30 text-rose-300 p-3.5 rounded-2xl text-xs flex gap-2.5 items-center text-left">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {walletStatus && (
        <div className="bg-blue-500/10 border border-blue-500/30 text-blue-300 p-3 rounded-xl text-xs flex items-center gap-2 font-mono animate-pulse text-left">
          <RefreshCw className="w-3.5 h-3.5 animate-spin text-blue-400 shrink-0" />
          <span>{walletStatus}</span>
        </div>
      )}

      {connectedWallet && (
        <div className="bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 p-3 rounded-xl text-xs flex items-center justify-between font-mono">
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            <span>Connected: {connectedWallet.slice(0, 6)}...{connectedWallet.slice(-4)}</span>
          </div>
          <span className="text-[10px] font-bold bg-emerald-500/20 px-2 py-0.5 rounded border border-emerald-500/40">
            Real Vault
          </span>
        </div>
      )}

      {/* 
        CLEAN SIMPLIFIED LOGIN INTERFACE:
        Only two primary buttons: "Real Account" and "Demo Account", both in consistent blue.
      */}
      <div className="space-y-3.5 pt-1">
        {/* Primary Button 1: Real Account via Rabby Wallet */}
        <button
          type="button"
          onClick={handleConnectRabby}
          disabled={walletLoading}
          className="w-full bg-gradient-to-r from-purple-900/60 via-indigo-900/60 to-blue-900/60 hover:from-purple-800/80 hover:to-blue-800/80 text-white p-4 rounded-2xl transition-all shadow-lg shadow-purple-900/30 flex items-center justify-between cursor-pointer active:scale-98 border border-purple-500/40 group disabled:opacity-50"
        >
          <div className="flex items-center gap-3.5 text-left">
            <div className="p-2.5 bg-purple-800/60 group-hover:bg-purple-700 text-white rounded-xl border border-purple-400/40 shadow-inner text-xl flex items-center justify-center">
              🐰
            </div>
            <div>
              <div className="text-base font-black tracking-tight text-white flex items-center gap-2">
                <span>Connect Rabby Wallet</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30 font-bold">
                  Polygon 137
                </span>
              </div>
              <p className="text-xs text-purple-200 font-medium">Sole Web3 Provider • Real Polymarket Execution</p>
            </div>
          </div>
          <ArrowRight className="w-5 h-5 text-purple-200 group-hover:translate-x-1 transition-transform" />
        </button>

        {/* Primary Button 2: Demo Account */}
        <button
          type="button"
          onClick={() => setIsDemoModalOpen(true)}
          disabled={googleLoading}
          className="w-full bg-blue-600 hover:bg-blue-500 text-white p-4 rounded-2xl transition-all shadow-lg shadow-blue-600/30 flex items-center justify-between cursor-pointer active:scale-98 border border-blue-400/30 group disabled:opacity-50"
        >
          <div className="flex items-center gap-3.5 text-left">
            <div className="p-2.5 bg-blue-700/60 group-hover:bg-blue-700 text-white rounded-xl border border-blue-400/30 shadow-inner">
              <Zap className="w-5 h-5" />
            </div>
            <div>
              <div className="text-base font-black tracking-tight text-white flex items-center gap-2">
                <span>Demo Account</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-blue-400/20 text-blue-200 border border-blue-300/30 font-bold">
                  $300 Virtual
                </span>
              </div>
              <p className="text-xs text-blue-100 font-medium">Risk-Free 5-Minute Paper Trading</p>
            </div>
          </div>
          <ArrowRight className="w-5 h-5 text-blue-200 group-hover:translate-x-1 transition-transform" />
        </button>
      </div>

      {/* Discrete Administrator Login & Links */}
      <div className="pt-2 border-t border-slate-800/80">
        <button
          type="button"
          onClick={() => setShowAdminForm(!showAdminForm)}
          className="text-slate-400 hover:text-slate-300 text-xs font-semibold flex items-center justify-center gap-1.5 mx-auto transition-colors cursor-pointer py-1"
        >
          <Lock className="w-3.5 h-3.5 text-slate-500" />
          <span>{showAdminForm ? '▲ Hide administrator sign-in' : '▼ Administrator email sign-in'}</span>
        </button>

        {showAdminForm && (
          <form className="space-y-3 pt-3 animate-fade-in text-left" onSubmit={handleAdminLogin}>
            <div>
              <label className="block text-xs font-bold text-slate-300 mb-1">Admin Email</label>
              <input
                type="email"
                required
                value={adminEmail}
                onChange={e => setAdminEmail(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 outline-none font-mono"
                placeholder="shalombinrasheed@gmail.com"
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
              {adminLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : 'Log In as Administrator'}
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

      {/* MODAL: DEMO ACCOUNT ACCESS ($300 VIRTUAL) */}
      {isDemoModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
          <div className="bg-slate-900 border-2 border-blue-500/40 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 relative text-left">
            <button
              onClick={() => setIsDemoModalOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2.5 bg-blue-600 text-white rounded-xl shadow-md shadow-blue-500/30">
                  <Zap className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-black text-white">Demo Account Access</h3>
                  <p className="text-xs text-slate-400">Risk-Free 5-Minute Paper Trading</p>
                </div>
              </div>
              <span className="bg-blue-500/20 text-blue-300 text-[10px] font-black px-2.5 py-1 rounded-full border border-blue-500/30 font-mono uppercase">
                $300 Provisioned
              </span>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed bg-blue-950/50 p-3 rounded-xl border border-blue-900/60">
              Each Google account receives an isolated <strong>$300.00 virtual trading balance</strong> to test signals, customize risk parameters, and simulate trades safely.
            </p>

            {/* Google Sign In Button (Forces prompt=select_account) */}
            <div className="space-y-3 pt-1">
              <button
                type="button"
                onClick={triggerGoogleOAuthFlow}
                disabled={googleLoading}
                className="w-full bg-white hover:bg-slate-100 text-slate-900 font-bold text-xs py-3 px-4 rounded-xl transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer active:scale-98 disabled:opacity-50"
              >
                <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
                </svg>
                <span>{googleLoading ? 'Opening Google Account Selection...' : 'Sign in with Google'}</span>
              </button>

              <div className="space-y-1.5">
                <div className="flex justify-between items-center text-[11px] font-bold text-slate-300">
                  <span>Or Enter Gmail Address</span>
                  <button
                    type="button"
                    onClick={() => { setGoogleEmail('shalombinrasheed@gmail.com'); }}
                    className="text-[10px] text-blue-400 hover:text-blue-300 underline font-mono cursor-pointer"
                  >
                    Admin quick-fill
                  </button>
                </div>
                <div className="flex gap-2">
                  <input
                    type="email"
                    value={googleEmail}
                    onChange={(e) => setGoogleEmail(e.target.value)}
                    placeholder="yourname@gmail.com"
                    className="flex-1 bg-slate-950/80 border border-blue-500/30 focus:border-blue-500 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-slate-500 outline-none font-mono"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        handleGoogleAuth();
                      }
                    }}
                  />
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

            <div className="pt-2 text-center">
              <span className="text-[10px] text-slate-500 font-mono">
                🔒 Protected by Administrator Verification & Google OAuth
              </span>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: RABBY WALLET REQUIRED NOTICE */}
      {isInstallModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
          <div className="bg-slate-900 border-2 border-purple-500/40 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 relative text-left">
            <button
              onClick={() => setIsInstallModalOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-purple-500/20 text-purple-400 rounded-xl text-2xl flex items-center justify-center">
                🐰
              </div>
              <div>
                <h3 className="text-base font-black text-white">Rabby Wallet Required</h3>
                <p className="text-xs text-purple-300 font-mono">Sole & Default Web3 Provider</p>
              </div>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              Rabby Wallet extension required. Please install Rabby to continue.
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
                href="https://rabby.io"
                target="_blank"
                rel="noopener noreferrer"
                className="w-2/3 bg-gradient-to-r from-purple-600 via-indigo-600 to-sky-600 hover:from-purple-500 hover:to-sky-500 text-white font-black text-xs py-2.5 rounded-xl transition-all shadow-md flex justify-center items-center gap-2 cursor-pointer"
              >
                <span>Download Rabby Wallet</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
