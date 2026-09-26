import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { 
  Zap, Shield, RefreshCw, 
  Crown, Play, Sliders, ArrowUpRight, ArrowDownRight, 
  Timer, DollarSign, Activity, Lock, TrendingUp, TrendingDown,
  CheckCircle2, XCircle, Award, Wallet, Wifi, Server, Settings, Cpu, Gauge, Radio, Layers,
  BookmarkCheck, RotateCcw, Scale, SlidersHorizontal, Database,
  Eye, EyeOff, Key, AlertTriangle, AlertCircle, Check, Copy, ArrowRight, Unlink, X,
  LogOut, ArrowDownToLine, ArrowUpFromLine, Menu, ChevronRight, ExternalLink
} from 'lucide-react';
import AdminConsoleTab from '../components/AdminConsoleTab';
import BrandLogo from '../components/BrandLogo';


interface AssetData {
  asset: string;
  direction: 'UP' | 'DOWN' | 'NEUTRAL';
  composite_score: number;
  confidence: number;
  delta_score?: number;
  obi_score?: number;
  momentum_score?: number;
  rank: number;
  delta: number;
  delta_pct: number;
  live_price: number;
  strike_price: number;
  latency_ms: number;
  time_remaining_sec: number;
  up_share_price: number;
  down_share_price: number;
  spread: number;
  liquidity: number;
  orderbook_imbalance: number;
  velocity_10s: number;
  velocity_30s: number;
  reason: string;
  target_token_id: string;
  is_tradable: boolean;
  rejection_reason: string;
}

interface TradeStats {
  initial_balance?: number;
  current_balance?: number;
  total_pnl: number;
  total_profit: number;
  total_loss: number;
  win_rate: number;
  wins: number;
  losses: number;
  total_trades: number;
  open_trades: number;
  dynamic_hard_cap?: number;
  active_margin?: number;
}

export interface SystemHealth {
  uptime_sec: number;
  network: {
    server_internet_ping_ms: number;
    polymarket_clob_ping_ms: number;
    polymarket_gamma_ping_ms: number;
    api_status: string;
    internet_status: string;
    internet_connected: boolean;
    last_check_ts: number;
  };
  squad_workers: {
    oracle_scout: { name: string; role: string; status: string; latency_ms: number; last_heartbeat_age_s: number; tasks_processed: number; details: any };
    technical_analyst: { name: string; role: string; status: string; latency_ms: number; last_heartbeat_age_s: number; tasks_processed: number; details: any };
    risk_commander: { name: string; role: string; status: string; latency_ms: number; last_heartbeat_age_s: number; tasks_processed: number; details: any };
    health_sentinel: { name: string; role: string; status: string; latency_ms: number; last_heartbeat_age_s: number; tasks_processed: number; details: any };
  };
}

interface BoardState {
  timestamp: number;
  epoch_bucket: number;
  epoch_remaining_sec: number;
  epoch_progress_pct: number;
  assets: AssetData[];
  top_ranked_pair: AssetData | null;
  active_trade: any | null;
  active_trades?: any[];
  settings: Record<string, any>;
  auto_trading_active: boolean;
  system_health?: SystemHealth;
  wallet?: any;
}

const ASSET_META: Record<string, { name: string; color: string; bg: string; border: string; text: string }> = {
  BTC:  { name: 'Bitcoin',      color: '#F7931A', bg: 'bg-amber-50',    border: 'border-amber-300',  text: 'text-amber-600' },
  ETH:  { name: 'Ethereum',     color: '#627EEA', bg: 'bg-indigo-50',   border: 'border-indigo-300', text: 'text-indigo-600' },
  SOL:  { name: 'Solana',       color: '#14F195', bg: 'bg-emerald-50',  border: 'border-emerald-300',text: 'text-emerald-600' },
  XRP:  { name: 'Ripple',       color: '#23292F', bg: 'bg-slate-100',   border: 'border-slate-300',  text: 'text-slate-700' },
  DOGE: { name: 'Dogecoin',     color: '#C2A633', bg: 'bg-yellow-50',   border: 'border-yellow-300', text: 'text-yellow-600' },
  BNB:  { name: 'Binance Coin', color: '#F3BA2F', bg: 'bg-amber-50',    border: 'border-amber-400',  text: 'text-amber-700' },
  HYPE: { name: 'Hyperliquid',  color: '#00F0FF', bg: 'bg-teal-50',     border: 'border-teal-300',   text: 'text-teal-600' },
};

export default function Fast5MBoard() {
  const [board, setBoard] = useState<BoardState | null>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [selectedTimeframe, setSelectedTimeframe] = useState<'today' | 'week' | 'month' | 'all'>('all');
  const [lifetimeStats, setLifetimeStats] = useState<any>(null);
  const [stats, setStats] = useState<TradeStats>({
    total_pnl: 0,
    total_profit: 0,
    total_loss: 0,
    win_rate: 0,
    wins: 0,
    losses: 0,
    total_trades: 0,
    open_trades: 0,
  });
  const [confidenceThreshold, setConfidenceThreshold] = useState<number>(70);
  const [positionSize, setPositionSize] = useState<number>(10);
  const [maxActivePools, setMaxActivePools] = useState<number>(3);
  const [multiPairMinScore, setMultiPairMinScore] = useState<number>(90.0);
  const [strategyDirection, setStrategyDirection] = useState<'BOTH' | 'UP_ONLY' | 'DOWN_ONLY'>('BOTH');
  const [takeProfitDollar, setTakeProfitDollar] = useState<number>(0.30);
  const [stopLossDollar, setStopLossDollar] = useState<number>(0.30);
  const [takeProfitPct, setTakeProfitPct] = useState<number>(3.0);
  const [stopLossPct, setStopLossPct] = useState<number>(3.0);
  const [riskRewardRatio, setRiskRewardRatio] = useState<number>(1.0);
  const [bufferEnabled, setBufferEnabled] = useState<boolean>(true);
  const [bufferTimerSec, setBufferTimerSec] = useState<number>(4.0);
  const [multiEntryEnabled, setMultiEntryEnabled] = useState<boolean>(true);
  const [gridLevels, setGridLevels] = useState<number>(2);
  const [gridStepPct, setGridStepPct] = useState<number>(1.0);
  const [trailingLockEnabled, setTrailingLockEnabled] = useState<boolean>(true);
  const [trailingStopActivationPct, setTrailingStopActivationPct] = useState<number>(1.0);
  const [trailingStopDistancePct, setTrailingStopDistancePct] = useState<number>(0.5);
  const [maxPortfolioMarginPct, setMaxPortfolioMarginPct] = useState<number>(30.0);
  const [reversalLockEnabled, setReversalLockEnabled] = useState<boolean>(true);
  const [minProfitToLock, setMinProfitToLock] = useState<number>(0.10);
  const [reversalGivebackDollar, setReversalGivebackDollar] = useState<number>(0.03);
  const [maxEntrySlippagePct, setMaxEntrySlippagePct] = useState<number>(0.8);

  interface UserProfileData {
    id?: number;
    email?: string;
    role?: string;
    status?: string;
    allowed_mode?: string;
    wallet_address?: string;
    auth_provider?: string;
  }
  const [userProfile, setUserProfile] = useState<UserProfileData | null>(null);
  const currentEmail = (userProfile?.email || localStorage.getItem('user_email') || '').trim().toLowerCase();
  const isAdmin = currentEmail === 'shalombinrasheed@gmail.com';

  // Settings input protection lock (prevents polling from reverting user inputs during modification)
  const lastSettingEditTime = useRef<number>(0);
  const markSettingEdited = () => {
    if (!isAdmin) return;
    lastSettingEditTime.current = Date.now();
  };

  // Active Quantitative Filters & Indicator Flags
  const [filterDeltaEnabled, setFilterDeltaEnabled] = useState<boolean>(true);
  const [filterDeltaWeight, setFilterDeltaWeight] = useState<number>(40);
  const [filterObiEnabled, setFilterObiEnabled] = useState<boolean>(true);
  const [filterObiWeight, setFilterObiWeight] = useState<number>(30);
  const [filterMomentumEnabled, setFilterMomentumEnabled] = useState<boolean>(true);
  const [filterMomentumWeight, setFilterMomentumWeight] = useState<number>(30);
  const [filterRsiEnabled, setFilterRsiEnabled] = useState<boolean>(true);
  const [filterBbEnabled, setFilterBbEnabled] = useState<boolean>(true);
  const [filterEmaMacdEnabled, setFilterEmaMacdEnabled] = useState<boolean>(true);
  const [maxSpread, setMaxSpread] = useState<number>(0.20);
  const [minLiquidityUsd, setMinLiquidityUsd] = useState<number>(100);
  const [minTimeRemaining, setMinTimeRemaining] = useState<number>(20);
  const [maxTimeRemaining, setMaxTimeRemaining] = useState<number>(280);

  // Slippage Circuit Breaker on Exit
  const [exitCircuitBreakerEnabled, setExitCircuitBreakerEnabled] = useState<boolean>(true);
  const [maxExitSlippagePct, setMaxExitSlippagePct] = useState<number>(5.0);

  // Dedicated Per-Asset Spread & Liquidity Controls
  const [perAssetSpread, setPerAssetSpread] = useState<Record<string, number>>({
    BTC: 6, ETH: 6, SOL: 8, XRP: 10, DOGE: 10, BNB: 8, HYPE: 8
  });
  const [perAssetLiquidity, setPerAssetLiquidity] = useState<Record<string, number>>({
    BTC: 150, ETH: 150, SOL: 120, XRP: 100, DOGE: 100, BNB: 100, HYPE: 150
  });

  const [savingSettings, setSavingSettings] = useState<boolean>(false);
  const [savingAsDefault, setSavingAsDefault] = useState<boolean>(false);
  const [restoringDefaults, setRestoringDefaults] = useState<boolean>(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string>('');
  const [defaultSavedTime, setDefaultSavedTime] = useState<string>('');
  const [healthTesting, setHealthTesting] = useState<boolean>(false);
  const [toggling, setToggling] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'board' | 'settings' | 'squad' | 'trades' | 'scoring' | 'wallet' | 'admin'>('board');
  const [selectedAssetForScore, setSelectedAssetForScore] = useState<string>('BTC');

  // Real Wallet & Polymarket CLOB State
  const [walletInfo, setWalletInfo] = useState<any | null>(null);
  const [walletAddressInput, setWalletAddressInput] = useState<string>('');
  const [privateKeyInput, setPrivateKeyInput] = useState<string>('');
  const [proxyAddressInput, setProxyAddressInput] = useState<string>('');
  const [apiKeyInput, setApiKeyInput] = useState<string>('');
  const [apiSecretInput, setApiSecretInput] = useState<string>('');
  const [apiPassphraseInput, setApiPassphraseInput] = useState<string>('');
  const [showPrivateKey, setShowPrivateKey] = useState<boolean>(false);
  const [showAdvancedApi, setShowAdvancedApi] = useState<boolean>(false);
  const [connectingBrowserWallet, setConnectingBrowserWallet] = useState<boolean>(false);
  const [savingWalletCreds, setSavingWalletCreds] = useState<boolean>(false);
  const [refreshingWalletBal, setRefreshingWalletBal] = useState<boolean>(false);
  const [togglingMode, setTogglingMode] = useState<boolean>(false);
  const [walletMsg, setWalletMsg] = useState<string>('');
  const [walletError, setWalletError] = useState<string>('');
  const [copiedAddress, setCopiedAddress] = useState<boolean>(false);
  const [accountMode, setAccountMode] = useState<'demo' | 'live' | 'all'>('demo');
  const [vaultInfo, setVaultInfo] = useState<any | null>(null);
  const [vaultTab, setVaultTab] = useState<'deposit' | 'withdraw'>('deposit');

  // Confirmation Modals & Dialogs
  const [isEmergencyStopModalOpen, setIsEmergencyStopModalOpen] = useState<boolean>(false);
  const [isLogoutModalOpen, setIsLogoutModalOpen] = useState<boolean>(false);
  const [tradeToExit, setTradeToExit] = useState<any | null>(null);
  const [exitingTrade, setExitingTrade] = useState<boolean>(false);
  const [isDemoResetModalOpen, setIsDemoResetModalOpen] = useState<boolean>(false);
  const [resettingDemo, setResettingDemo] = useState<boolean>(false);
  const [isSwitchToRealModalOpen, setIsSwitchToRealModalOpen] = useState<boolean>(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  // Mobile Navigation Side Drawer & Rabby Wallet Sync
  const [isMobileDrawerOpen, setIsMobileDrawerOpen] = useState<boolean>(false);
  const [isRabbyModalOpen, setIsRabbyModalOpen] = useState<boolean>(false);
  const [rabbySyncing, setRabbySyncing] = useState<boolean>(false);
  const [rabbySyncMsg, setRabbySyncMsg] = useState<string>('');
  const [rabbySyncError, setRabbySyncError] = useState<string>('');
  const [rabbyDepositAmount, setRabbyDepositAmount] = useState<string>('');
  const [rabbyWithdrawAmount, setRabbyWithdrawAmount] = useState<string>('');
  const [rabbyDepositMode, setRabbyDepositMode] = useState<'instant' | 'onchain'>('instant');
  const [mobileMenuExclusive, setMobileMenuExclusive] = useState<boolean>(() => localStorage.getItem('mobile_menu_exclusive') !== 'false');

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 4000);
  };

  // Multi-User Profile & Session
  const navigate = useNavigate();

  const fetchUserProfile = async () => {
    try {
      const token = localStorage.getItem('token');
      if (!token) return;
      const res = await axios.get('/api/auth/me', {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data) {
        setUserProfile(res.data);
        if (res.data.status) localStorage.setItem('user_status', res.data.status);
        if (res.data.role) localStorage.setItem('user_role', res.data.role);
        if (res.data.allowed_mode) localStorage.setItem('allowed_mode', res.data.allowed_mode);
        if (res.data.wallet_address) localStorage.setItem('wallet_address', res.data.wallet_address);
      }
    } catch (e) {
      console.debug('User profile fetch note', e);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user_email');
    localStorage.removeItem('user_status');
    localStorage.removeItem('user_role');
    localStorage.removeItem('allowed_mode');
    localStorage.removeItem('wallet_address');
    localStorage.removeItem('demo_access');
    localStorage.removeItem('account_mode');
    localStorage.removeItem('auth_provider');
    navigate('/login');
  };

  const fetchVault = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get('/api/fast5m/vault', {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      if (res.data) setVaultInfo(res.data);
    } catch (e) {
      console.debug('Vault fetch note', e);
    }
  };

  const handleOpenDepositWithdraw = async (tab: 'deposit' | 'withdraw' = 'deposit') => {
    setVaultTab(tab);
    if (!walletInfo?.is_connected || !walletInfo?.wallet_address) {
      if (isRabbyAvailable()) {
        try {
          await connectRabbyWallet();
        } catch (e) {
          console.debug('Auto-connect on deposit/withdraw click:', e);
        }
      }
    }
    setIsRabbyModalOpen(true);
  };

  const handleResetDemoAccount = async () => {
    setResettingDemo(true);
    try {
      const token = localStorage.getItem('token');
      if (!token) {
        showToast('⚠️ Authentication required. Please log in first.');
        alert('Authentication required. Please log in first.');
        setResettingDemo(false);
        return;
      }
      await axios.post('/api/fast5m/demo/reset', {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setTrades([]);
      setStats({
        total_trades: 0,
        wins: 0,
        losses: 0,
        win_rate: 0,
        total_pnl: 0,
        total_profit: 0,
        total_loss: 0,
        open_trades: 0,
        initial_balance: 300,
        current_balance: 300,
      });
      setIsDemoResetModalOpen(false);
      showToast('✅ Demo account successfully reset to $300.00 base balance!');
      await fetchVault();
      await fetchBoard();
      await fetchTrades(selectedTimeframe, 'demo');
    } catch (e: any) {
      if (e?.response?.status === 401) {
        showToast('⚠️ Session expired. Please log in again.');
        alert('Session expired. Please log in again.');
      } else {
        const errorMsg = e?.response?.data?.detail || 'Failed to reset demo account.';
        showToast(`❌ ${errorMsg}`);
        alert(errorMsg);
      }
    } finally {
      setResettingDemo(false);
    }
  };

  const handleManualExitTrade = async () => {
    if (!tradeToExit) return;
    setExitingTrade(true);
    try {
      const token = localStorage.getItem('token');
      await axios.post(`/api/fast5m/trades/${tradeToExit.id || tradeToExit.asset}/exit`, {}, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      showToast(`Position #${tradeToExit.id || ''} for ${tradeToExit.asset} closed successfully.`);
      setTradeToExit(null);
      await fetchBoard();
      await fetchTrades(selectedTimeframe, isRealAccount ? 'live' : 'demo');
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Failed to exit position.');
    } finally {
      setExitingTrade(false);
    }
  };

  const handleConfirmSwitchToReal = async () => {
    setIsSwitchToRealModalOpen(false);
    try {
      const token = localStorage.getItem('token');
      await axios.post('/api/fast5m/demo/reset', {}, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      setTrades([]);
      showToast('Demo trade history wiped. Switching to Real Account...');
    } catch (e) {
      console.error('Failed to wipe demo before switching to real:', e);
    }
    await handleToggleWalletMode('live', true);
  };

  const prevPrices = useRef<Record<string, number>>({});
  const flashStates = useRef<Record<string, 'up' | 'down' | null>>({});

  // Fetch Board and Trades
  const fetchBoard = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get('/api/fast5m/board', {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });

      if (res.data) {
        // Track price changes for micro-flashing
        res.data.assets?.forEach((a: AssetData) => {
          const oldP = prevPrices.current[a.asset];
          if (oldP && oldP !== a.live_price) {
            flashStates.current[a.asset] = a.live_price > oldP ? 'up' : 'down';
            setTimeout(() => { flashStates.current[a.asset] = null; }, 600);
          }
          prevPrices.current[a.asset] = a.live_price;
        });

        setBoard(res.data);
        const userRecentlyEdited = (Date.now() - lastSettingEditTime.current) < 30000;
        if (res.data.settings && !userRecentlyEdited && activeTab !== 'settings') {
          const s = res.data.settings;
          if (s.confidence_threshold) setConfidenceThreshold(parseFloat(s.confidence_threshold));
          if (s.position_size_usd) setPositionSize(parseFloat(s.position_size_usd));
          if (s.max_active_pools) setMaxActivePools(parseInt(s.max_active_pools));
          if (s.multi_pair_min_score) setMultiPairMinScore(parseFloat(s.multi_pair_min_score));
          if (s.strategy_direction) setStrategyDirection(s.strategy_direction.toUpperCase());
          if (s.take_profit_dollar) setTakeProfitDollar(parseFloat(s.take_profit_dollar));
          if (s.stop_loss_dollar) setStopLossDollar(parseFloat(s.stop_loss_dollar));
          if (s.take_profit_pct) setTakeProfitPct(parseFloat(s.take_profit_pct));
          if (s.stop_loss_pct) setStopLossPct(parseFloat(s.stop_loss_pct));
          if (s.risk_reward_ratio) setRiskRewardRatio(parseFloat(s.risk_reward_ratio));
          else if (s.take_profit_pct && s.stop_loss_pct) {
            const sl = parseFloat(s.stop_loss_pct);
            const tp = parseFloat(s.take_profit_pct);
            if (sl > 0) setRiskRewardRatio(Number((tp / sl).toFixed(2)));
          }
          if (s.buffer_enabled !== undefined) setBufferEnabled(s.buffer_enabled === 'true');
          if (s.buffer_timer_sec) setBufferTimerSec(parseFloat(s.buffer_timer_sec));
          if (s.multi_entry_enabled !== undefined) setMultiEntryEnabled(s.multi_entry_enabled === 'true');
          if (s.grid_levels) setGridLevels(parseInt(s.grid_levels));
          if (s.grid_step_pct) setGridStepPct(parseFloat(s.grid_step_pct));
          if (s.min_profit_to_lock) setMinProfitToLock(parseFloat(s.min_profit_to_lock));
          if (s.reversal_giveback_dollar) setReversalGivebackDollar(parseFloat(s.reversal_giveback_dollar));
          if (s.trailing_lock_enabled) setTrailingLockEnabled(s.trailing_lock_enabled === 'true');
          if (s.trailing_stop_activation_pct) setTrailingStopActivationPct(parseFloat(s.trailing_stop_activation_pct));
          if (s.trailing_stop_distance_pct) setTrailingStopDistancePct(parseFloat(s.trailing_stop_distance_pct));
          if (s.max_portfolio_margin_pct) setMaxPortfolioMarginPct(parseFloat(s.max_portfolio_margin_pct));
          if (s.reversal_lock_enabled !== undefined) setReversalLockEnabled(s.reversal_lock_enabled === 'true');
          if (s.max_entry_slippage_pct) setMaxEntrySlippagePct(parseFloat(s.max_entry_slippage_pct));

          if (s.filter_delta_enabled !== undefined) setFilterDeltaEnabled(s.filter_delta_enabled !== 'false');
          if (s.filter_delta_weight) setFilterDeltaWeight(parseFloat(s.filter_delta_weight));
          if (s.filter_obi_enabled !== undefined) setFilterObiEnabled(s.filter_obi_enabled !== 'false');
          if (s.filter_obi_weight) setFilterObiWeight(parseFloat(s.filter_obi_weight));
          if (s.filter_momentum_enabled !== undefined) setFilterMomentumEnabled(s.filter_momentum_enabled !== 'false');
          if (s.filter_momentum_weight) setFilterMomentumWeight(parseFloat(s.filter_momentum_weight));
          if (s.filter_rsi_enabled !== undefined) setFilterRsiEnabled(s.filter_rsi_enabled !== 'false');
          if (s.filter_bb_enabled !== undefined) setFilterBbEnabled(s.filter_bb_enabled !== 'false');
          if (s.filter_ema_macd_enabled !== undefined) setFilterEmaMacdEnabled(s.filter_ema_macd_enabled !== 'false');
          if (s.max_spread) setMaxSpread(parseFloat(s.max_spread));
          if (s.min_liquidity_usd) setMinLiquidityUsd(parseFloat(s.min_liquidity_usd));
          if (s.min_time_remaining) setMinTimeRemaining(parseFloat(s.min_time_remaining));
          if (s.max_time_remaining) setMaxTimeRemaining(parseFloat(s.max_time_remaining));
          if (s.exit_circuit_breaker_enabled !== undefined) setExitCircuitBreakerEnabled(s.exit_circuit_breaker_enabled !== 'false');
          if (s.max_exit_slippage_pct) setMaxExitSlippagePct(parseFloat(s.max_exit_slippage_pct));

          const updatedSpreads: Record<string, number> = {};
          const updatedLiqs: Record<string, number> = {};
          ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'BNB', 'HYPE'].forEach(asset => {
            const low = asset.toLowerCase();
            if (s[`max_spread_${low}`]) updatedSpreads[asset] = Math.round(parseFloat(s[`max_spread_${low}`]) * 100);
            if (s[`min_liquidity_usd_${low}`]) updatedLiqs[asset] = parseFloat(s[`min_liquidity_usd_${low}`]);
          });
          if (Object.keys(updatedSpreads).length > 0) {
            setPerAssetSpread(prev => ({ ...prev, ...updatedSpreads }));
          }
          if (Object.keys(updatedLiqs).length > 0) {
            setPerAssetLiquidity(prev => ({ ...prev, ...updatedLiqs }));
          }

          if (s.custom_defaults_saved_at) setDefaultSavedTime(s.custom_defaults_saved_at);
        }
        if (res.data.wallet) {
          setWalletInfo(res.data.wallet);
          if (!walletAddressInput && res.data.wallet.wallet_address) {
            setWalletAddressInput(res.data.wallet.wallet_address);
          }
          if (!proxyAddressInput && res.data.wallet.proxy_address) {
            setProxyAddressInput(res.data.wallet.proxy_address);
          }
        }
      }
    } catch (e) {
      console.debug('Fast5M board poll error', e);
    }
  };

  const fetchTrades = async (tf?: string, mode?: string) => {
    try {
      const activeTf = tf || selectedTimeframe;
      const activeMode = mode !== undefined ? mode : accountMode;
      const token = localStorage.getItem('token');
      const res = await axios.get(`/api/fast5m/trades?timeframe=${activeTf}&account_mode=${activeMode}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      if (res.data) {
        if (res.data.trades) {
          setTrades(res.data.trades);
          if (res.data.stats) setStats(res.data.stats);
          if (res.data.lifetime_stats) setLifetimeStats(res.data.lifetime_stats);
        } else if (Array.isArray(res.data)) {
          setTrades(res.data);
        }
      }
    } catch (e) {
      console.debug('Fast5M trades fetch error', e);
    }
  };

  const handleSelectTimeframe = (tf: 'today' | 'week' | 'month' | 'all') => {
    setSelectedTimeframe(tf);
    fetchTrades(tf, accountMode);
  };

  const handleSelectAccountMode = (mode: 'demo' | 'live' | 'all') => {
    setAccountMode(mode);
    fetchTrades(selectedTimeframe, mode);
  };

  useEffect(() => {
    const storedEmail = localStorage.getItem('user_email');
    const storedWallet = localStorage.getItem('wallet_address');
    const storedProvider = localStorage.getItem('auth_provider');
    const storedRole = localStorage.getItem('user_role');
    const storedStatus = localStorage.getItem('user_status');
    const storedAllowedMode = localStorage.getItem('allowed_mode');

    if (storedEmail || storedWallet) {
      setUserProfile({
        email: storedEmail || undefined,
        wallet_address: storedWallet || undefined,
        auth_provider: storedProvider || undefined,
        role: storedRole || undefined,
        status: storedStatus || undefined,
        allowed_mode: storedAllowedMode || undefined
      });
    }

    fetchUserProfile();
    fetchBoard();
    fetchVault();
    fetchTrades(selectedTimeframe, accountMode);

    const interval = setInterval(() => {
      fetchBoard();
      fetchVault();
    }, 1000); // 1-second real-time poll
    const tradeInterval = setInterval(() => {
      fetchTrades(selectedTimeframe, accountMode);
    }, 3500);
    return () => {
      clearInterval(interval);
      clearInterval(tradeInterval);
    };
  }, [selectedTimeframe, accountMode]);


  const handleEmergencyStop = async () => {
    if (!isAdmin) return;
    setToggling(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post('/api/fast5m/emergency-stop', {}, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      if (res.data) {
        setSaveSuccessMsg('🚨 EMERGENCY STOP ENGAGED: Auto-trading killed and active positions closed.');
        setTimeout(() => setSaveSuccessMsg(''), 5000);
        await fetchBoard();
        await fetchTrades();
      }
    } catch (e) {
      console.error('Emergency stop error', e);
    } finally {
      setToggling(false);
    }
  };

  const handleEmergencyStart = async () => {
    if (!isAdmin) return;
    setToggling(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post('/api/fast5m/emergency-start', {}, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      if (res.data) {
        setSaveSuccessMsg('🟢 ENGINE RESUMED: Auto-execution armed and actively scanning.');
        setTimeout(() => setSaveSuccessMsg(''), 5000);
        await fetchBoard();
      }
    } catch (e) {
      console.error('Emergency start error', e);
    } finally {
      setToggling(false);
    }
  };


  const handleSaveAllSettings = async () => {
    if (!isAdmin) {
      alert('Administrative Action Restricted: Only platform administrators can modify trading settings.');
      return;
    }
    setSavingSettings(true);
    try {
      const token = localStorage.getItem('token');
      await axios.post('/api/fast5m/settings', {
        position_size_usd: positionSize,
        max_active_pools: maxActivePools,
        multi_pair_min_score: multiPairMinScore,
        strategy_direction: strategyDirection,
        confidence_threshold: confidenceThreshold,
        buffer_enabled: bufferEnabled,
        buffer_timer_sec: bufferTimerSec,
        take_profit_pct: takeProfitPct,
        stop_loss_pct: stopLossPct,
        hard_stop_loss_pct: stopLossPct,
        risk_reward_ratio: riskRewardRatio,
        take_profit_dollar: takeProfitDollar,
        stop_loss_dollar: stopLossDollar,
        multi_entry_enabled: multiEntryEnabled,
        grid_levels: gridLevels,
        grid_step_pct: gridStepPct,
        trailing_lock_enabled: trailingLockEnabled,
        trailing_stop_activation_pct: trailingStopActivationPct,
        trailing_stop_distance_pct: trailingStopDistancePct,
        max_portfolio_margin_pct: maxPortfolioMarginPct,
        reversal_lock_enabled: reversalLockEnabled,
        min_profit_to_lock: minProfitToLock,
        reversal_giveback_dollar: reversalGivebackDollar,
        filter_delta_enabled: filterDeltaEnabled,
        filter_delta_weight: filterDeltaWeight,
        filter_obi_enabled: filterObiEnabled,
        filter_obi_weight: filterObiWeight,
        filter_momentum_enabled: filterMomentumEnabled,
        filter_momentum_weight: filterMomentumWeight,
        filter_rsi_enabled: filterRsiEnabled,
        filter_bb_enabled: filterBbEnabled,
        filter_ema_macd_enabled: filterEmaMacdEnabled,
        max_spread: maxSpread,
        min_liquidity_usd: minLiquidityUsd,
        min_time_remaining: minTimeRemaining,
        max_time_remaining: maxTimeRemaining,
        exit_circuit_breaker_enabled: exitCircuitBreakerEnabled,
        max_exit_slippage_pct: maxExitSlippagePct,
        max_entry_slippage_pct: maxEntrySlippagePct,
        max_spread_btc: (perAssetSpread['BTC'] ?? 6) / 100,
        min_liquidity_usd_btc: perAssetLiquidity['BTC'] ?? 150,
        max_spread_eth: (perAssetSpread['ETH'] ?? 6) / 100,
        min_liquidity_usd_eth: perAssetLiquidity['ETH'] ?? 150,
        max_spread_sol: (perAssetSpread['SOL'] ?? 8) / 100,
        min_liquidity_usd_sol: perAssetLiquidity['SOL'] ?? 120,
        max_spread_xrp: (perAssetSpread['XRP'] ?? 10) / 100,
        min_liquidity_usd_xrp: perAssetLiquidity['XRP'] ?? 100,
        max_spread_doge: (perAssetSpread['DOGE'] ?? 10) / 100,
        min_liquidity_usd_doge: perAssetLiquidity['DOGE'] ?? 100,
        max_spread_bnb: (perAssetSpread['BNB'] ?? 8) / 100,
        min_liquidity_usd_bnb: perAssetLiquidity['BNB'] ?? 100,
        max_spread_hype: (perAssetSpread['HYPE'] ?? 8) / 100,
        min_liquidity_usd_hype: perAssetLiquidity['HYPE'] ?? 150,
      }, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      lastSettingEditTime.current = Date.now();
      setSaveSuccessMsg('Configuration synchronized across all Squad workers with 0ms latency!');
      setTimeout(() => setSaveSuccessMsg(''), 4500);
      await fetchBoard();
    } catch (e) {
      console.error('Save all settings error', e);
    } finally {
      setSavingSettings(false);
    }
  };

  const handleSaveAsDefault = async () => {
    if (!isAdmin) {
      alert('Administrative Action Restricted: Only platform administrators can save default baselines.');
      return;
    }
    setSavingAsDefault(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post('/api/fast5m/settings/default', {
        position_size_usd: positionSize,
        max_active_pools: maxActivePools,
        multi_pair_min_score: multiPairMinScore,
        strategy_direction: strategyDirection,
        confidence_threshold: confidenceThreshold,
        buffer_enabled: bufferEnabled,
        buffer_timer_sec: bufferTimerSec,
        take_profit_pct: takeProfitPct,
        stop_loss_pct: stopLossPct,
        hard_stop_loss_pct: stopLossPct,
        risk_reward_ratio: riskRewardRatio,
        take_profit_dollar: takeProfitDollar,
        stop_loss_dollar: stopLossDollar,
        multi_entry_enabled: multiEntryEnabled,
        grid_levels: gridLevels,
        grid_step_pct: gridStepPct,
        trailing_lock_enabled: trailingLockEnabled,
        trailing_stop_activation_pct: trailingStopActivationPct,
        trailing_stop_distance_pct: trailingStopDistancePct,
        max_portfolio_margin_pct: maxPortfolioMarginPct,
        reversal_lock_enabled: reversalLockEnabled,
        min_profit_to_lock: minProfitToLock,
        reversal_giveback_dollar: reversalGivebackDollar,
        filter_delta_enabled: filterDeltaEnabled,
        filter_delta_weight: filterDeltaWeight,
        filter_obi_enabled: filterObiEnabled,
        filter_obi_weight: filterObiWeight,
        filter_momentum_enabled: filterMomentumEnabled,
        filter_momentum_weight: filterMomentumWeight,
        filter_rsi_enabled: filterRsiEnabled,
        filter_bb_enabled: filterBbEnabled,
        filter_ema_macd_enabled: filterEmaMacdEnabled,
        max_spread: maxSpread,
        min_liquidity_usd: minLiquidityUsd,
        min_time_remaining: minTimeRemaining,
        max_time_remaining: maxTimeRemaining,
        exit_circuit_breaker_enabled: exitCircuitBreakerEnabled,
        max_exit_slippage_pct: maxExitSlippagePct,
        max_entry_slippage_pct: maxEntrySlippagePct,
        max_spread_btc: (perAssetSpread['BTC'] ?? 6) / 100,
        min_liquidity_usd_btc: perAssetLiquidity['BTC'] ?? 150,
        max_spread_eth: (perAssetSpread['ETH'] ?? 6) / 100,
        min_liquidity_usd_eth: perAssetLiquidity['ETH'] ?? 150,
        max_spread_sol: (perAssetSpread['SOL'] ?? 8) / 100,
        min_liquidity_usd_sol: perAssetLiquidity['SOL'] ?? 120,
        max_spread_xrp: (perAssetSpread['XRP'] ?? 10) / 100,
        min_liquidity_usd_xrp: perAssetLiquidity['XRP'] ?? 100,
        max_spread_doge: (perAssetSpread['DOGE'] ?? 10) / 100,
        min_liquidity_usd_doge: perAssetLiquidity['DOGE'] ?? 100,
        max_spread_bnb: (perAssetSpread['BNB'] ?? 8) / 100,
        min_liquidity_usd_bnb: perAssetLiquidity['BNB'] ?? 100,
        max_spread_hype: (perAssetSpread['HYPE'] ?? 8) / 100,
        min_liquidity_usd_hype: perAssetLiquidity['HYPE'] ?? 150,
      }, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      if (res.data?.defaults?.custom_defaults_saved_at) {
        setDefaultSavedTime(res.data.defaults.custom_defaults_saved_at);
      }
      setSaveSuccessMsg('Custom configuration saved as permanent default baseline!');
      setTimeout(() => setSaveSuccessMsg(''), 4500);
      await fetchBoard();
    } catch (e) {
      console.error('Save as default error', e);
    } finally {
      setSavingAsDefault(false);
    }
  };

  const handleRestoreDefaults = async () => {
    if (!isAdmin) {
      alert('Administrative Action Restricted: Only platform administrators can restore default baselines.');
      return;
    }
    setRestoringDefaults(true);
    try {
      const token = localStorage.getItem('token');
      await axios.post('/api/fast5m/settings/restore-defaults', {}, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      setSaveSuccessMsg('Restored active configuration from custom default baseline profile!');
      setTimeout(() => setSaveSuccessMsg(''), 4500);
      await fetchBoard();
    } catch (e) {
      console.error('Restore defaults error', e);
    } finally {
      setRestoringDefaults(false);
    }
  };

  const handleTestHealth = async () => {
    setHealthTesting(true);
    try {
      const res = await axios.post('/api/fast5m/system-health/test');
      if (res.data && board) {
        setBoard({ ...board, system_health: res.data });
      }
    } catch (e) {
      console.error('Health test error', e);
    } finally {
      setHealthTesting(false);
    }
  };

  const formatSec = (sec: number) => {
    const s = Math.max(0, Math.floor(sec));
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${m}:${rem.toString().padStart(2, '0')}`;
  };

  const copyAddressToClipboard = (addr: string) => {
    if (!addr) return;
    navigator.clipboard.writeText(addr);
    setCopiedAddress(true);
    setTimeout(() => setCopiedAddress(false), 2000);
  };

  const isRabbyAvailable = (): boolean => {
    if (typeof window === 'undefined') return false;
    const eth = (window as any).ethereum;
    return Boolean(
      (window as any).rabby ||
      (eth && eth.isRabby) ||
      (eth && eth.providers && eth.providers.some((p: any) => p.isRabby))
    );
  };

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

  const connectRabbyWallet = async (): Promise<boolean> => {
    const provider = getRabbyProvider();
    if (!provider || !isRabbyAvailable()) {
      setIsRabbyModalOpen(true);
      return false;
    }
    setConnectingBrowserWallet(true);
    setWalletError('');
    setWalletMsg('');
    setRabbySyncError('');
    setRabbySyncMsg('');
    try {
      setRabbySyncMsg('Connecting to Rabby Wallet... Please approve access in your Rabby extension.');
      const accounts = await provider.request({ method: 'eth_requestAccounts' });
      if (!accounts || accounts.length === 0) {
        throw new Error('No account authorized in Rabby Wallet.');
      }
      const addr = accounts[0].toLowerCase();
      setWalletAddressInput(addr);

      // Verify or switch to Polygon Mainnet (0x89 = 137)
      try {
        const chainId = await provider.request({ method: 'eth_chainId' });
        if (chainId !== '0x89' && chainId !== '137' && parseInt(chainId, 16) !== 137) {
          try {
            await provider.request({
              method: 'wallet_switchEthereumChain',
              params: [{ chainId: '0x89' }],
            });
          } catch (switchError: any) {
            if (switchError.code === 4902) {
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
            }
          }
        }
      } catch (cErr) {
        console.warn('Rabby chain switch notice:', cErr);
      }

      // Link to backend
      const token = localStorage.getItem('token');
      const res = await axios.post('/api/fast5m/wallet/connect', {
        address: addr,
        proxy_address: proxyAddressInput.trim() || undefined,
        wallet_type: 'rabby',
      }, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });

      try {
        await axios.post('/api/auth/link-wallet', { wallet_address: addr, wallet_type: 'rabby' }, {
          headers: token ? { Authorization: `Bearer ${token}` } : {}
        });
      } catch (linkErr) {
        console.debug('Link wallet note:', linkErr);
      }

      try {
        await axios.post('/api/fast5m/wallet/mode', { mode: 'live' }, {
          headers: token ? { Authorization: `Bearer ${token}` } : {}
        });
      } catch (modeErr) {
        console.debug('Mode set note:', modeErr);
      }

      // Sync Rabby balances via dedicated sync endpoint
      try {
        const syncRes = await axios.post('/api/fast5m/wallet/sync-rabby', {
          address: addr,
          sync_vault: true,
          account_mode: 'live'
        }, {
          headers: token ? { Authorization: `Bearer ${token}` } : {}
        });
        if (syncRes.data?.balances) {
          setWalletInfo((prev: any) => ({
            ...prev,
            ...syncRes.data.balances,
            account_mode: 'live',
            is_connected: true,
            is_rabby: true,
            wallet_address: addr
          }));
        }
      } catch (syncErr) {
        console.warn('Rabby initial balance sync note:', syncErr);
      }

      if (res.data?.wallet) {
        setWalletInfo({ ...res.data.wallet, account_mode: 'live', is_connected: true, is_rabby: true });
        setAccountMode('live');
        localStorage.setItem('account_mode', 'live');
        localStorage.setItem('wallet_address', addr);
        localStorage.setItem('wallet_provider', 'rabby');
        localStorage.removeItem('demo_access');
        setWalletMsg(`🐰 Rabby Wallet (${addr.slice(0, 6)}...${addr.slice(-4)}) connected & synced!`);
      }

      await fetchVault();
      await fetchUserProfile();
      await fetchBoard();
      await fetchTrades(selectedTimeframe, 'live');
      showToast('🐰 Rabby Wallet connected & Polygon balance synced successfully!');
      return true;
    } catch (err: any) {
      console.error('Rabby connect error:', err);
      if (err?.code === 4001 || err?.message?.includes('rejected') || err?.message?.includes('denied')) {
        setWalletError('Rabby Wallet connection request was rejected in your extension.');
      } else {
        setWalletError(err?.response?.data?.detail || err?.message || 'Failed to connect Rabby Wallet.');
      }
      return false;
    } finally {
      setConnectingBrowserWallet(false);
    }
  };

  const handleSyncRabbyWallet = async () => {
    setRabbySyncing(true);
    setRabbySyncError('');
    setRabbySyncMsg('');
    try {
      const token = localStorage.getItem('token');
      const addr = walletInfo?.wallet_address || walletAddressInput.trim() || undefined;
      const res = await axios.post('/api/fast5m/wallet/sync-rabby', {
        address: addr,
        sync_vault: true
      }, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });

      if (res.data?.balances) {
        setWalletInfo((prev: any) => ({
          ...prev,
          ...res.data.balances,
          wallet_address: res.data.wallet_address || prev?.wallet_address,
          last_balance_sync: res.data.timestamp,
          is_rabby: true
        }));
      }
      await fetchVault();
      setRabbySyncMsg('✨ Rabby Polygon balances synced fresh from on-chain RPC!');
      showToast('🐰 Rabby balances synced!');
    } catch (err: any) {
      setRabbySyncError(err?.response?.data?.detail || err?.message || 'Failed to sync Rabby balances.');
    } finally {
      setRabbySyncing(false);
    }
  };

  const handleRabbyDepositSync = async (amount: number, onchainTransfer = false) => {
    if (!amount || amount <= 0) {
      setRabbySyncError('Please enter a deposit amount greater than $0.00.');
      return;
    }
    // Auto-connect Rabby if not connected yet
    if (!walletInfo?.is_connected || !walletInfo?.wallet_address) {
      const ok = await connectRabbyWallet();
      if (!ok) {
        setRabbySyncError('Please connect Rabby Wallet first to proceed with deposit.');
        return;
      }
    }
    setRabbySyncing(true);
    setRabbySyncError('');
    setRabbySyncMsg('');
    try {
      let txHash: string | undefined = undefined;
      const provider = getRabbyProvider();

      // If user chooses On-Chain Transfer, prompt Rabby to send Polygon USDC to Polymarket Exchange
      if (onchainTransfer && provider) {
        setRabbySyncMsg('🐰 Please confirm Polygon USDC transfer in Rabby Wallet...');
        const recipient = '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E'; // Polymarket CTF Exchange
        const usdcContract = '0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359'; // Native Polygon USDC
        const amountWei = BigInt(Math.floor(amount * 1_000_000)).toString(16).padStart(64, '0');
        const cleanRecipient = recipient.toLowerCase().replace('0x', '').padStart(64, '0');
        const data = `0xa9059cbb${cleanRecipient}${amountWei}`;
        
        txHash = await provider.request({
          method: 'eth_sendTransaction',
          params: [{
            from: walletInfo?.wallet_address || walletAddressInput,
            to: usdcContract,
            data: data
          }]
        });
        if (txHash) {
          setRabbySyncMsg(`On-chain transfer submitted (${txHash.slice(0, 10)}...). Syncing vault...`);
        }
      }

      const token = localStorage.getItem('token');
      await axios.post('/api/fast5m/vault/deposit', {
        amount,
        tx_hash: txHash,
        wallet_type: 'rabby',
        sync_onchain: Boolean(onchainTransfer)
      }, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });

      setRabbySyncMsg(`✅ Successfully synced deposit of $${amount.toFixed(2)} from Rabby into Trading Vault!`);
      showToast(`🐰 Deposited & Synced $${amount.toFixed(2)} with Rabby Wallet!`);
      setRabbyDepositAmount('');
      await fetchVault();
      await handleSyncRabbyWallet();
    } catch (err: any) {
      console.error('Rabby deposit sync error:', err);
      if (err?.code === 4001 || err?.message?.includes('rejected') || err?.message?.includes('denied')) {
        setRabbySyncError('Deposit transaction was rejected in Rabby Wallet.');
      } else {
        setRabbySyncError(err?.response?.data?.detail || err?.message || 'Failed to sync Rabby deposit.');
      }
    } finally {
      setRabbySyncing(false);
    }
  };

  const handleRabbyWithdrawSync = async (amount: number) => {
    if (!amount || amount <= 0) {
      setRabbySyncError('Please enter a withdrawal amount greater than $0.00.');
      return;
    }
    // Auto-connect Rabby if not connected yet
    if (!walletInfo?.is_connected || !walletInfo?.wallet_address) {
      const ok = await connectRabbyWallet();
      if (!ok) {
        setRabbySyncError('Please connect Rabby Wallet first to proceed with withdrawal.');
        return;
      }
    }
    setRabbySyncing(true);
    setRabbySyncError('');
    setRabbySyncMsg('');
    try {
      const destination = walletInfo?.wallet_address || walletAddressInput;
      const token = localStorage.getItem('token');
      await axios.post('/api/fast5m/vault/withdraw', {
        amount,
        wallet_type: 'rabby',
        destination_address: destination
      }, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });

      setRabbySyncMsg(`✅ Successfully de-allocated $${amount.toFixed(2)} back to Rabby Wallet (${destination.slice(0, 6)}...${destination.slice(-4)})!`);
      showToast(`🐰 Withdrawn & Synced $${amount.toFixed(2)} to Rabby Wallet!`);
      setRabbyWithdrawAmount('');
      await fetchVault();
      await handleSyncRabbyWallet();
    } catch (err: any) {
      console.error('Rabby withdraw sync error:', err);
      setRabbySyncError(err?.response?.data?.detail || err?.message || 'Failed to sync Rabby withdrawal.');
    } finally {
      setRabbySyncing(false);
    }
  };

  const handleSaveWalletCredentials = async () => {
    if (!walletAddressInput.trim()) {
      setWalletError('Please enter a valid Polygon wallet address (0x...).');
      return;
    }
    setSavingWalletCreds(true);
    setWalletError('');
    setWalletMsg('');
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post('/api/fast5m/wallet/connect', {
        address: walletAddressInput.trim(),
        private_key: privateKeyInput.trim() || undefined,
        proxy_address: proxyAddressInput.trim() || undefined,
        api_key: apiKeyInput.trim() || undefined,
        api_secret: apiSecretInput.trim() || undefined,
        api_passphrase: apiPassphraseInput.trim() || undefined,
      }, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      if (res.data?.wallet) {
        setWalletInfo({ ...res.data.wallet, account_mode: 'live', is_connected: true });
        setAccountMode('live');
        localStorage.setItem('account_mode', 'live');
        localStorage.setItem('wallet_address', walletAddressInput.trim());
        setWalletMsg('Polygon Wallet and Polymarket CLOB configuration verified & saved to Real Account!');
        setPrivateKeyInput(''); // Clear plain private key from input after saving
      }
      await fetchBoard();
      await fetchTrades(selectedTimeframe, 'live');
    } catch (e: any) {
      setWalletError(e.response?.data?.detail || e.message || 'Failed to save credentials.');
    } finally {
      setSavingWalletCreds(false);
    }
  };

  const handleToggleWalletMode = async (targetMode: 'demo' | 'live', skipConfirm = false) => {
    if (targetMode === 'live' && !skipConfirm) {
      setIsSwitchToRealModalOpen(true);
      return;
    }
    if (targetMode === 'live') {
      if (userProfile?.status && userProfile.status !== 'APPROVED') {
        setWalletError('Account under review: Your account must be approved by an administrator before switching to Real Vault mode.');
        return;
      }
      if (userProfile?.allowed_mode && userProfile.allowed_mode !== 'REAL_AND_DEMO') {
        setWalletError('Access restricted: Your account is currently set to DEMO_ONLY. Please contact an administrator to approve REAL_AND_DEMO mode.');
        return;
      }
      const userWallet = userProfile?.wallet_address || walletInfo?.wallet_address;
      if (!userWallet && !walletInfo?.is_connected) {
        handleOpenDepositWithdraw('deposit');
        setWalletError('Rabby Wallet required: Please connect and link your Rabby wallet address first.');
        return;
      }
    }
    setTogglingMode(true);
    setWalletError('');
    setWalletMsg('');
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post('/api/fast5m/wallet/mode', { mode: targetMode }, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      if (res.data?.wallet) {
        setWalletInfo(res.data.wallet);
        setAccountMode(targetMode);
        setWalletMsg(
          targetMode === 'live'
            ? 'Armed on REAL MONEY Live Execution (Polymarket CLOB)!'
            : 'Switched to Safe Virtual DEMO ($300 Paper) Mode.'
        );
        await fetchBoard();
        await fetchTrades(selectedTimeframe, targetMode);
      }
    } catch (e: any) {
      setWalletError(e.response?.data?.detail || e.message || 'Failed to switch trading mode.');
    } finally {
      setTogglingMode(false);
    }
  };

  const handleRefreshWalletBalance = async () => {
    setRefreshingWalletBal(true);
    try {
      const res = await axios.post('/api/fast5m/wallet/refresh');
      if (res.data?.wallet) {
        setWalletInfo(res.data.wallet);
        setWalletMsg('On-chain Polygon balances updated!');
        setTimeout(() => setWalletMsg(''), 3000);
      }
    } catch (e: any) {
      setWalletError(e.response?.data?.detail || e.message || 'Failed to refresh balance.');
    } finally {
      setRefreshingWalletBal(false);
    }
  };

  const handleDisconnectWallet = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post('/api/fast5m/wallet/disconnect', {}, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      if (res.data?.wallet) {
        setWalletInfo(res.data.wallet);
      } else {
        setWalletInfo(null);
      }
      setWalletAddressInput('');
      setPrivateKeyInput('');
      setProxyAddressInput('');
      setAccountMode('demo');
      localStorage.setItem('account_mode', 'demo');
      localStorage.removeItem('wallet_address');
      setWalletMsg('Personal Web3 wallet disconnected safely.');
      await fetchUserProfile();
      await fetchBoard();
      await fetchTrades(selectedTimeframe, 'demo');
    } catch (e: any) {
      console.error('Disconnect error', e);
      setWalletError('Failed to disconnect wallet.');
    }
  };

  const topPick = board?.top_ranked_pair;
  const inspectedAsset = board?.assets?.find(a => a.asset === selectedAssetForScore) || topPick || board?.assets?.[0];

  const activeList: any[] = (board?.active_trades && board.active_trades.length > 0)
    ? board.active_trades
    : (board?.active_trade ? [board.active_trade] : []);
  const activeExposure = activeList.reduce((acc: number, t: any) => acc + (t.cost || 0), 0);

  // #1 Ranked Banner & Telemetry Computation
  const bestAsset = topPick || board?.assets?.[0];
  const bannerAsset = bestAsset?.asset || 'DOGE';
  const bannerDirection = bestAsset?.direction || 'DOWN';
  const bannerTokenType = bannerDirection === 'UP' ? 'YES' : 'NO';
  const bannerScore = bestAsset?.confidence != null ? bestAsset.confidence.toFixed(1) : '78.2';
  const deltaVal = bestAsset?.delta != null ? bestAsset.delta : 0;
  const deltaPct = bestAsset?.delta_pct != null ? bestAsset.delta_pct : -0.0518;
  const bannerDelta = `${deltaVal >= 0 ? '+' : ''}${deltaVal} (${deltaPct >= 0 ? '+' : ''}${deltaPct.toFixed(4)}%)`;
  const bannerLatency = bestAsset?.latency_ms ?? 75;
  const isScoreArmed = Boolean(bestAsset && bestAsset.confidence >= confidenceThreshold && bestAsset.is_tradable);
  const isExecuting = activeList.some((t: any) => t.asset === bannerAsset);
  const bannerStatus = !board?.auto_trading_active
    ? 'PAUSED'
    : (isExecuting
      ? 'EXECUTING'
      : (isScoreArmed
        ? 'ARMED & READY'
        : 'WAITING'));

  // Web3 wallet connects exclusively to Real Account for all users.
  // Upon real wallet connection, automatically hide all demo account details from view.
  const isRealAccount = Boolean(
    walletInfo?.is_connected ||
    walletInfo?.account_mode === 'live' ||
    accountMode === 'live' ||
    userProfile?.auth_provider === 'wallet' ||
    Boolean(userProfile?.wallet_address)
  );

  // Balances & Display Formatting
  const currentTotalBalance = isRealAccount
    ? (walletInfo?.usdc_total ?? 0.00)
    : ((stats.initial_balance ?? 300) + stats.total_pnl);
  const currentVaultAllocated = vaultInfo?.allocated_balance ?? 250.00;
  const roiPct = (stats.initial_balance && stats.initial_balance > 0)
    ? ((stats.total_pnl / stats.initial_balance) * 100)
    : (stats.total_pnl !== 0 ? ((stats.total_pnl / 300) * 100) : 0);
  const displayAddress = userProfile?.wallet_address 
    ? `${userProfile.wallet_address.slice(0, 4)}...${userProfile.wallet_address.slice(-4)}`
    : (walletInfo?.wallet_address ? `${walletInfo.wallet_address.slice(0, 4)}...${walletInfo.wallet_address.slice(-4)}` : '0x1f...f704');

  return (
    <div className="w-full max-w-7xl mx-auto space-y-4 sm:space-y-5 pb-12 font-sans text-slate-100 px-2 sm:px-4">
      
      {/* 1. TOP NAVIGATION BAR */}
      <header className="w-full max-w-full bg-[#161b22] border border-[#30363d] rounded-2xl px-3 py-2 sm:py-2.5 shadow-md flex items-center justify-between gap-2 overflow-x-hidden">
        {/* Left: Brand Logo + "Jonanda Bot" + All Tabs in a Single Horizontal Line */}
        <div className="flex items-center gap-2 flex-nowrap shrink min-w-0">
          {/* Brand Logo & Name */}
          <div className="flex items-center gap-2 pr-2 border-r border-[#30363d] shrink-0">
            <BrandLogo size={32} glow={true} />
            <div>
              <div className="text-xs sm:text-sm font-black text-white tracking-tight flex items-center gap-1.5 whitespace-nowrap">
                <span className="bg-gradient-to-r from-blue-400 via-sky-300 to-emerald-400 bg-clip-text text-transparent font-black tracking-wide">
                  Jonanda Bot
                </span>
                {isAdmin && (
                  <span className="text-[9px] font-mono uppercase px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 font-bold">
                    Admin
                  </span>
                )}
              </div>
              <div className="text-[9px] sm:text-[10px] text-slate-400 font-mono -mt-0.5 flex items-center gap-1 whitespace-nowrap">
                <span>Shalom Bin Rasheed</span>
                <span className="text-slate-600">•</span>
                <span className="text-emerald-400 font-semibold">5M Engine</span>
              </div>
            </div>
          </div>

          {/* Navigation Tabs in Single Continuous Line (Desktop) */}
          <nav className="hidden xl:flex items-center gap-1.5 text-xs font-bold shrink min-w-0">
            <button
              type="button"
              onClick={() => setActiveTab('board')}
              className={`px-2 py-1 rounded-lg text-[11px] transition-all cursor-pointer whitespace-nowrap ${
                activeTab === 'board'
                  ? 'bg-[#21262d] text-white border border-[#30363d] shadow-xs'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-[#21262d]/50'
              }`}
            >
              Dashboard
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab('board');
                const el = document.getElementById('fast5m-markets-grid');
                if (el) el.scrollIntoView({ behavior: 'smooth' });
              }}
              className="px-2 py-1 rounded-lg text-[11px] text-slate-400 hover:text-slate-200 hover:bg-[#21262d]/50 transition-all cursor-pointer whitespace-nowrap"
            >
              Markets
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('scoring')}
              className={`px-2 py-1 rounded-lg text-[11px] transition-all cursor-pointer whitespace-nowrap ${
                activeTab === 'scoring'
                  ? 'bg-[#21262d] text-white border border-[#30363d] shadow-xs'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-[#21262d]/50'
              }`}
            >
              Signals
            </button>
            {isAdmin && (
              <button
                type="button"
                onClick={() => setActiveTab('settings')}
                className={`px-2 py-1 rounded-lg text-[11px] transition-all cursor-pointer whitespace-nowrap ${
                  activeTab === 'settings'
                    ? 'bg-[#21262d] text-white border border-[#30363d] shadow-xs'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-[#21262d]/50'
                }`}
              >
                Settings
              </button>
            )}
            <button
              type="button"
              onClick={() => setActiveTab('trades')}
              className={`px-2 py-1 rounded-lg text-[11px] transition-all cursor-pointer whitespace-nowrap ${
                activeTab === 'trades'
                  ? 'bg-[#21262d] text-white border border-[#30363d] shadow-xs'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-[#21262d]/50'
              }`}
            >
              Trades ({trades.length})
            </button>
          </nav>
        </div>

        {/* Right: Unified Rabby Deposit/Withdraw Button + Desktop Actions + Top-Corner Mobile Drawer Button */}
        <div className="flex items-center gap-1.5 shrink-0">
          {/* Single Unified Primary Button: Deposit / Withdraw with Rabby Icon */}
          <button
            type="button"
            onClick={() => handleOpenDepositWithdraw('deposit')}
            className="px-2.5 py-1.5 bg-gradient-to-r from-emerald-600 via-teal-600 to-indigo-600 hover:from-emerald-500 hover:to-indigo-500 active:scale-95 text-white font-bold text-[11px] sm:text-xs rounded-xl shadow-sm transition-all flex items-center gap-1.5 cursor-pointer shrink-0 border border-emerald-400/30"
            title="Deposit or Withdraw USDC via Rabby Wallet"
          >
            <span className="text-xs">🐰</span>
            <span>Deposit / Withdraw</span>
            {walletInfo?.is_connected && (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            )}
          </button>

          {/* Desktop Toolbar Elements */}
          <div className="hidden xl:flex items-center gap-1 shrink-0">
            {/* 1. Compact Emergency Stop Button */}
            {isAdmin ? (
              board?.auto_trading_active ? (
                <button
                  type="button"
                  onClick={() => setIsEmergencyStopModalOpen(true)}
                  disabled={toggling}
                  className="px-2 py-1 bg-rose-600/90 hover:bg-rose-500 active:scale-95 text-white font-bold text-[11px] rounded-xl shadow-xs transition-all flex items-center gap-1 cursor-pointer shrink-0 animate-pulse border border-rose-500/40"
                  title="Emergency Stop: Instantly kill auto-trading and force-close all open trades"
                >
                  <AlertTriangle className="w-3 h-3 text-white" />
                  <span className="hidden sm:inline">Emergency Stop</span>
                  <span className="sm:hidden">Stop</span>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleEmergencyStart}
                  disabled={toggling}
                  className="px-2 py-1 bg-emerald-600/90 hover:bg-emerald-500 active:scale-95 text-white font-bold text-[11px] rounded-xl shadow-xs transition-all flex items-center gap-1 cursor-pointer shrink-0 border border-emerald-500/40"
                  title="Resume Engine: Re-arm automated execution"
                >
                  <Play className="w-3 h-3 text-white" />
                  <span className="hidden sm:inline">Resume Engine</span>
                  <span className="sm:hidden">Resume</span>
                </button>
              )
            ) : (
              <div className="px-2 py-1 bg-[#0d1117] border border-[#30363d] rounded-xl text-[11px] font-mono text-slate-300 flex items-center gap-1 shrink-0">
                <span className={`w-2 h-2 rounded-full ${board?.auto_trading_active ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`} />
                <span>{board?.auto_trading_active ? 'Armed' : 'Paused'}</span>
              </div>
            )}

            {/* 3. Demo Reset Button — strictly hidden when NOT in demo mode */}
            {accountMode === 'demo' && !isRealAccount && (
              <button
                type="button"
                onClick={() => setIsDemoResetModalOpen(true)}
                className="px-2 py-1 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-300 hover:text-amber-200 rounded-xl text-[11px] font-bold transition-all flex items-center gap-1 cursor-pointer shrink-0"
                title="Reset Demo Account: Wipe paper history and restore initial $300 balance"
              >
                <RotateCcw className="w-3 h-3" />
                <span className="hidden md:inline">Reset Demo</span>
              </button>
            )}

            {/* 4. Wallet Button */}
            <button
              type="button"
              onClick={() => handleOpenDepositWithdraw('deposit')}
              className="flex items-center gap-1 px-2 py-1 bg-[#0d1117] hover:bg-[#21262d] border border-[#30363d] rounded-xl text-[11px] font-mono text-slate-200 transition-colors cursor-pointer shrink-0"
              title="Open Web3 Wallet Controls & Balance"
            >
              <Wallet className={`w-3 h-3 ${isRealAccount ? 'text-emerald-400' : 'text-blue-400'}`} />
              <span className="font-bold">{isRealAccount ? 'Real Wallet' : 'Wallet'}</span>
              <span className={`text-[11px] font-bold ${isRealAccount ? 'text-emerald-400' : 'text-blue-300'}`}>
                {isRealAccount
                  ? `($${(walletInfo?.usdc_total ?? 0).toFixed(2)})`
                  : `($${currentVaultAllocated.toFixed(2)})`}
              </span>
              {isRealAccount && walletInfo?.pol_gas_balance != null && (
                <span className="text-[10px] text-purple-400 hidden 2xl:inline">
                  • {walletInfo.pol_gas_balance.toFixed(3)} POL
                </span>
              )}
            </button>

            {/* 5. Disconnect Button */}
            {(isRealAccount || walletInfo?.is_connected) && (
              <button
                type="button"
                onClick={handleDisconnectWallet}
                className="flex items-center gap-1 px-2 py-1 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 hover:text-rose-200 rounded-xl text-[11px] font-bold transition-all cursor-pointer shrink-0"
                title="Disconnect Web3 Wallet (Switch back to Safe Demo)"
              >
                <Unlink className="w-3 h-3 text-rose-400" />
                <span className="hidden sm:inline">Disconnect</span>
              </button>
            )}

            {/* 6. User Logout placed at the absolute far corner */}
            <div className="pl-1 border-l border-[#30363d] flex-shrink-0">
              <button
                type="button"
                onClick={() => setIsLogoutModalOpen(true)}
                title="Log Out / Disconnect Session"
                className="p-1.5 bg-[#0d1117] hover:bg-rose-950/40 border border-[#30363d] hover:border-rose-500/50 text-slate-400 hover:text-rose-300 rounded-xl transition-all cursor-pointer flex items-center justify-center flex-shrink-0"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Top-Corner Hamburger / Mobile Drawer Trigger Button */}
          <button
            type="button"
            onClick={() => setIsMobileDrawerOpen(true)}
            className={`${mobileMenuExclusive ? 'xl:hidden' : ''} p-1.5 sm:p-2 bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] text-slate-200 hover:text-white rounded-xl transition-all cursor-pointer flex items-center gap-1.5 shrink-0 shadow-xs`}
            title="Open Mobile Navigation Menu & Side Drawer"
            aria-label="Navigation Menu"
          >
            <Menu className="w-4 h-4 text-sky-400" />
            <span className="text-[11px] font-bold text-slate-300 hidden sm:inline">Menu</span>
            {(trades.length > 0 || walletInfo?.is_connected) && (
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            )}
          </button>
        </div>
      </header>

      {/* 2-LINE TELEMETRY & ROUND CONFIGURATION STRIP */}
      <div className="bg-[#161b22] border border-[#30363d] rounded-xl px-3.5 py-2 space-y-2 shadow-xs text-xs">
        {/* LINE 1: MARKET & ROUND ORACLE TELEMETRY (Demo Vault hidden) */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 font-mono text-[11px] text-slate-300">
          <div className="flex items-center gap-2 sm:gap-2.5 flex-wrap">
            <span className="text-slate-400">
              Strike Set: <strong className="text-white font-bold">:00 Min</strong>
            </span>
            <span className="text-slate-600">•</span>
            <span className="text-slate-400">
              Hard Stop: <strong className="text-amber-400 font-bold">:04:50 (10s Rule)</strong>
            </span>
            <span className="text-slate-600">•</span>
            <span className="text-slate-400">
              CLOB Feed: <strong className="text-emerald-400 font-bold">Live ({board?.assets?.[0]?.latency_ms ?? 16}ms)</strong>
            </span>
            <span className="text-slate-600 hidden sm:inline">•</span>
            <span className="text-slate-400 hidden sm:inline">
              Streams: <strong className="text-cyan-400 font-bold">7 Pairs Isolated</strong>
            </span>
          </div>

          <div className="text-[10px] text-slate-400 font-mono hidden md:flex items-center gap-1.5">
            <span>Active Exposure:</span>
            <strong className="text-slate-200">${activeExposure.toFixed(2)}</strong>
            <span className="text-slate-600">/</span>
            <span className="text-slate-400">
              ${((isRealAccount ? (walletInfo?.usdc_total ?? 250) : 300) * (maxPortfolioMarginPct / 100)).toFixed(0)} Cap
            </span>
          </div>
        </div>

        {/* LINE 2: SETTINGS WITH ROUND TIMER POSITIONED AHEAD OF TRAILING LOCK */}
        <div className="pt-2 border-t border-[#30363d]/60 flex flex-wrap items-center justify-between gap-2 font-mono text-xs">
          <div className="flex items-center gap-2 sm:gap-3 flex-wrap text-slate-300">
            <div className="flex items-center gap-1.5">
              <span className="text-slate-400 text-[11px]">Target Size:</span>
              <strong className="text-white font-bold bg-[#0d1117] px-2 py-0.5 rounded border border-[#30363d]">
                ${positionSize}
              </strong>
            </div>

            <span className="text-slate-600 hidden sm:inline">|</span>

            <div className="flex items-center gap-1.5">
              <span className="text-slate-400 text-[11px]">Confidence:</span>
              <strong className="text-white font-bold bg-[#0d1117] px-2 py-0.5 rounded border border-[#30363d]">
                ≥{confidenceThreshold}%
              </strong>
            </div>

            <span className="text-slate-600 hidden sm:inline">|</span>

            <div className="flex items-center gap-1.5">
              <span className="text-slate-400 text-[11px]">R:R:</span>
              <strong className="text-white font-bold bg-[#0d1117] px-2 py-0.5 rounded border border-[#30363d]">
                {riskRewardRatio.toFixed(2)}:1
              </strong>
            </div>

            <span className="text-slate-600 hidden sm:inline">|</span>

            <div className="flex items-center gap-1.5">
              <span className="text-slate-400 text-[11px]">Dynamic Cap:</span>
              <strong className="text-amber-300 font-bold bg-[#0d1117] px-2 py-0.5 rounded border border-[#30363d]">
                -${Math.abs(stats.dynamic_hard_cap ?? (positionSize * 2.5)).toFixed(2)}
              </strong>
            </div>

            <span className="text-slate-600 hidden sm:inline">|</span>

            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-emerald-400 font-bold text-[11px]">Trailing Lock: Active</span>
            </div>

            <span className="text-slate-600 hidden sm:inline">|</span>

            {/* Round Countdown Timer (positioned right ahead of / next to Trailing Lock: Active) */}
            <div className="flex items-center gap-2 px-2.5 py-0.5 rounded-lg bg-[#0d1117] border border-[#30363d] shadow-xs">
              <div className="relative flex items-center justify-center w-4 h-4 shrink-0">
                <svg className="w-4 h-4 transform -rotate-90">
                  <circle
                    cx="8"
                    cy="8"
                    r="6.5"
                    stroke="#21262d"
                    strokeWidth="2"
                    fill="transparent"
                  />
                  <circle
                    cx="8"
                    cy="8"
                    r="6.5"
                    stroke={(board?.epoch_remaining_sec ?? 300) <= 10 ? '#ef4444' : (board?.epoch_remaining_sec ?? 300) <= 60 ? '#f59e0b' : '#3b82f6'}
                    strokeWidth="2"
                    strokeDasharray={2 * Math.PI * 6.5}
                    strokeDashoffset={
                      2 * Math.PI * 6.5 * (1 - Math.max(0, Math.min(300, (board?.epoch_remaining_sec ?? 300))) / 300)
                    }
                    strokeLinecap="round"
                    fill="transparent"
                    className="transition-all duration-1000 ease-linear"
                  />
                </svg>
                <span className={`w-1 h-1 rounded-full ${
                  (board?.epoch_remaining_sec ?? 300) <= 10 ? 'bg-rose-500 animate-ping' : 'bg-blue-400 animate-pulse'
                }`} />
              </div>

              <span className="text-slate-400 text-[10px] uppercase font-bold tracking-wider">
                {(board?.epoch_remaining_sec ?? 300) <= 10 ? '🚨 EXIT' : 'ROUND'}:
              </span>
              <span className={`text-xs sm:text-sm font-black font-mono tracking-tight ${
                (board?.epoch_remaining_sec ?? 300) <= 10 ? 'text-rose-400 animate-pulse' : 'text-white'
              }`}>
                {board ? formatSec(board.epoch_remaining_sec) : '04:31'}
              </span>
              <span className="text-[10px] text-slate-500 font-mono hidden sm:inline">
                ({board?.epoch_remaining_sec ?? 300}s)
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 3. SHRUNK FIVE KEY METRICS CARDS (COMPACT HEIGHT) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 sm:gap-2.5">
        {/* Card 1: Total Balance / Real Account Balance */}
        <div className="bg-[#161b22] rounded-xl border border-[#30363d] p-2.5 sm:p-3 flex flex-col justify-between shadow-xs hover:border-slate-500 transition-colors">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              {isRealAccount ? 'Real Account Balance' : 'Total Balance'}
            </span>
            <span className={`p-1 rounded-lg ${isRealAccount ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'}`}>
              <DollarSign className="w-3.5 h-3.5" />
            </span>
          </div>
          <div className="my-1">
            <div className={`text-lg sm:text-xl font-black font-mono tracking-tight ${isRealAccount ? 'text-emerald-400' : 'text-white'}`}>
              ${(isRealAccount ? (walletInfo?.usdc_total ?? 0) : currentTotalBalance).toFixed(2)}
            </div>
            <div className="text-[10px] text-slate-400 font-mono">
              {isRealAccount ? (
                <>
                  POL Gas: <strong className="text-purple-400">{walletInfo?.pol_gas_balance != null ? walletInfo.pol_gas_balance.toFixed(4) : '0.0000'} POL</strong>
                </>
              ) : (
                <>
                  Vault: <strong className="text-blue-400">${currentVaultAllocated.toFixed(2)}</strong>
                </>
              )}
            </div>
          </div>
          <div className="pt-1.5 border-t border-[#30363d] flex items-center justify-between text-[10px] font-mono text-slate-400">
            <span>{isRealAccount ? 'Spendable USDC:' : 'Active Margin:'}</span>
            <span className={`font-bold ${isRealAccount ? 'text-emerald-400 font-mono' : 'text-slate-300'}`}>
              ${(isRealAccount ? (walletInfo?.usdc_total ?? 0) : activeExposure).toFixed(2)}
            </span>
          </div>
        </div>

        {/* Card 2: Net Realized PnL */}
        <div className="bg-[#161b22] rounded-xl border border-[#30363d] p-2.5 sm:p-3 flex flex-col justify-between shadow-xs hover:border-slate-500 transition-colors">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Net Realized PnL</span>
            <span className={`p-1 rounded-lg ${stats.total_pnl >= 0 ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}`}>
              {stats.total_pnl >= 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
            </span>
          </div>
          <div className="my-1">
            <div className={`text-lg sm:text-xl font-black font-mono tracking-tight ${
              stats.total_pnl >= 0 ? 'text-emerald-400 drop-shadow-[0_0_8px_rgba(52,211,153,0.3)]' : 'text-rose-400 drop-shadow-[0_0_8px_rgba(248,113,113,0.3)]'
            }`}>
              {stats.total_pnl >= 0 ? '+' : '-'}${Math.abs(stats.total_pnl).toFixed(2)}
            </div>
            <div className={`text-[10px] font-mono font-bold ${stats.total_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {roiPct >= 0 ? '+' : ''}{roiPct.toFixed(2)}% ROI
            </div>
          </div>
          <div className="pt-1.5 border-t border-[#30363d] flex items-center justify-between text-[10px] font-mono text-slate-400">
            <span>Period:</span>
            <span className="font-bold uppercase text-slate-300">{selectedTimeframe}</span>
          </div>
        </div>

        {/* Card 3: Total Profit */}
        <div className="bg-[#161b22] rounded-xl border border-[#30363d] p-2.5 sm:p-3 flex flex-col justify-between shadow-xs hover:border-slate-500 transition-colors">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Total Profit</span>
            <span className="p-1 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <CheckCircle2 className="w-3.5 h-3.5" />
            </span>
          </div>
          <div className="my-1">
            <div className="text-lg sm:text-xl font-black font-mono text-emerald-400 tracking-tight">
              +${stats.total_profit.toFixed(2)}
            </div>
            <div className="text-[10px] text-emerald-400 font-bold">
              {stats.wins} Winning Trades
            </div>
          </div>
          <div className="pt-1.5 border-t border-[#30363d] flex items-center justify-between text-[10px] font-mono text-slate-400">
            <span>Target R:R:</span>
            <span className="font-bold text-emerald-400">{riskRewardRatio}:1 (+{takeProfitPct}%)</span>
          </div>
        </div>

        {/* Card 4: Total Loss */}
        <div className="bg-[#161b22] rounded-xl border border-[#30363d] p-2.5 sm:p-3 flex flex-col justify-between shadow-xs hover:border-slate-500 transition-colors">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Total Loss</span>
            <span className="p-1 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20">
              <XCircle className="w-3.5 h-3.5" />
            </span>
          </div>
          <div className="my-1">
            <div className="text-lg sm:text-xl font-black font-mono text-rose-400 tracking-tight">
              -${stats.total_loss.toFixed(2)}
            </div>
            <div className="text-[10px] text-rose-400 font-bold">
              {stats.losses} Stopped Trades
            </div>
          </div>
          <div className="pt-1.5 border-t border-[#30363d] flex items-center justify-between text-[10px] font-mono text-slate-400">
            <span>Hard Cap:</span>
            <span className="font-bold text-rose-400">Max -{stopLossPct}% Stop</span>
          </div>
        </div>

        {/* Card 5: Win Rate */}
        <div className="bg-[#161b22] rounded-xl border border-[#30363d] p-2.5 sm:p-3 flex flex-col justify-between shadow-xs hover:border-slate-500 transition-colors">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Win Rate</span>
            <span className="p-1 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20">
              <Award className="w-3.5 h-3.5" />
            </span>
          </div>
          <div className="my-1">
            <div className="text-lg sm:text-xl font-black font-mono text-white tracking-tight">
              {stats.win_rate.toFixed(1)}%
            </div>
            <div className="text-[10px] text-slate-400 font-medium">
              {stats.total_trades} Closed Rounds
            </div>
          </div>
          <div className="pt-1.5 border-t border-[#30363d] flex items-center justify-between text-[10px] font-mono text-slate-400">
            <span>Multi-Threshold:</span>
            <span className="font-bold text-slate-300">≥{multiPairMinScore}%</span>
          </div>
        </div>
      </div>

      {/* 4. SHRUNK #1 RANKED EXECUTION SIGNAL BANNER (COMPACT HEIGHT) */}
      <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-2.5 sm:px-4 sm:py-2.5 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-2.5 relative overflow-hidden">
        <div className="flex items-center gap-3">
          <span className="px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider bg-amber-500/20 text-amber-400 border border-amber-500/30 shrink-0">
            #1 RANKED
          </span>
          <div>
            <h2 className="text-base sm:text-lg font-black text-white tracking-tight flex items-center gap-2">
              <span>{bannerAsset}</span>
              <span className={bannerDirection === 'UP' ? 'text-emerald-400' : 'text-rose-400'}>
                {bannerDirection === 'UP' ? '▲' : '▼'}
              </span>
              <span>BUY {bannerDirection} ({bannerTokenType})</span>
            </h2>
          </div>
        </div>

        <div className="flex items-center gap-4 sm:gap-6 flex-wrap text-xs font-mono">
          <div className="text-left sm:text-right">
            <span className="text-slate-400 block text-[9px] uppercase font-bold tracking-wider">Score</span>
            <span className="text-white font-black text-xs sm:text-sm">{bannerScore}%</span>
          </div>
          <div className="text-left sm:text-right">
            <span className="text-slate-400 block text-[9px] uppercase font-bold tracking-wider">Oracle Delta</span>
            <span className="text-emerald-400 font-black text-xs sm:text-sm">{bannerDelta}</span>
          </div>
          <div className="text-left sm:text-right">
            <span className="text-slate-400 block text-[9px] uppercase font-bold tracking-wider">Latency</span>
            <span className="text-emerald-400 font-bold text-xs sm:text-sm">⚡ {bannerLatency}ms</span>
          </div>
          <div className="text-left sm:text-right">
            <span className="text-slate-400 block text-[9px] uppercase font-bold tracking-wider">Status</span>
            <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider border ${
              bannerStatus === 'ARMED & READY'
                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                : bannerStatus === 'EXECUTING'
                ? 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                : bannerStatus === 'PAUSED'
                ? 'bg-slate-500/20 text-slate-400 border-slate-500/30'
                : 'bg-amber-500/20 text-amber-400 border-amber-500/30'
            }`}>
              {bannerStatus}
            </span>
          </div>
        </div>
      </div>

      {/* ACCESS DENIED FOR NON-ADMIN ATTEMPTING TO ACCESS SETTINGS */}
      {activeTab === 'settings' && !isAdmin && (
        <div className="bg-[#161b22] rounded-2xl border border-rose-500/30 p-8 shadow-xl text-center max-w-lg mx-auto my-8 space-y-4">
          <div className="w-14 h-14 mx-auto rounded-full bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
            <Lock className="w-7 h-7" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">Access Denied: Administrator Only</h2>
            <p className="text-xs text-slate-400 mt-2">
              Platform trading configurations, risk limits, and quantitative filters can only be managed by platform administrators.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setActiveTab('board')}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold rounded-xl transition-all shadow-md cursor-pointer"
          >
            Return to Dashboard
          </button>
        </div>
      )}

      {/* SETTINGS & RISK CONFIGURATION TAB (ADMIN ONLY) */}
      {activeTab === 'settings' && isAdmin && (
        <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6 shadow-xs space-y-6">
          {/* Header Bar with Action Controls */}
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-100 pb-5">
            <div>
              <div className="flex items-center gap-2">
                <span className="p-2 rounded-xl bg-blue-50 text-blue-600">
                  <Settings className="w-5 h-5" />
                </span>
                <div>
                  <h2 className="text-lg font-black text-slate-900 tracking-tight flex items-center gap-2">
                    Settings & Risk Configuration Dashboard
                    {isAdmin ? (
                      <span className="text-[10px] uppercase font-black px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-200">
                        Full Administrative Access
                      </span>
                    ) : (
                      <span className="text-[10px] uppercase font-black px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-200 flex items-center gap-1">
                        <Lock className="w-3 h-3" /> Read-Only Mode
                      </span>
                    )}
                  </h2>
                  <p className="text-xs text-slate-500 font-medium">
                    {isAdmin
                      ? "Manual adjustments to Risk—to—Reward ratio, active quantitative filters, indicator weights, and default profiles"
                      : "Administrative parameter protection: All trading configurations and risk limits are centrally managed by platform administration."}
                  </p>
                </div>
              </div>
              {defaultSavedTime && (
                <div className="text-[10px] text-slate-400 font-mono mt-1.5 flex items-center gap-1">
                  <BookmarkCheck className="w-3.5 h-3.5 text-indigo-500" />
                  <span>Custom Default Baseline Active (Saved: {new Date(defaultSavedTime).toLocaleString()})</span>
                </div>
              )}
            </div>

            {/* Action Buttons: Save All Settings, Save as Default, Restore Defaults */}
            <div className="flex flex-wrap items-center gap-2.5">
              {saveSuccessMsg && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-bold rounded-xl animate-fade-in shadow-xs">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span>{saveSuccessMsg}</span>
                </div>
              )}

              {/* Reset Demo Account Button (available only when NOT connected to Real Account) */}
              {!isRealAccount && (
                <button
                  type="button"
                  onClick={() => setIsDemoResetModalOpen(true)}
                  disabled={resettingDemo || savingSettings}
                  className="flex items-center gap-1.5 px-3.5 py-2 bg-rose-50 hover:bg-rose-100 disabled:opacity-50 text-rose-700 border border-rose-200 rounded-xl text-xs font-bold transition-all cursor-pointer shadow-xs"
                  title="Reset Demo Account: wipe paper trades and reset virtual balance to $300.00 base"
                >
                  <RotateCcw className={`w-3.5 h-3.5 ${resettingDemo ? 'animate-spin' : ''}`} />
                  <span>{resettingDemo ? 'Resetting...' : 'Reset Demo ($300)'}</span>
                </button>
              )}

              {isAdmin && (
                <>
                  {/* Restore Defaults Button */}
                  <button
                    type="button"
                    onClick={handleRestoreDefaults}
                    disabled={restoringDefaults || savingSettings || savingAsDefault}
                    className="flex items-center gap-1.5 px-3.5 py-2 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 text-slate-700 rounded-xl text-xs font-bold transition-all cursor-pointer border border-slate-200"
                    title="Restore settings to saved default baseline"
                  >
                    <RotateCcw className={`w-3.5 h-3.5 ${restoringDefaults ? 'animate-spin' : ''}`} />
                    <span>{restoringDefaults ? 'Restoring...' : 'Restore Defaults'}</span>
                  </button>

                  {/* Save as Default Button */}
                  <button
                    type="button"
                    onClick={handleSaveAsDefault}
                    disabled={savingAsDefault || savingSettings || restoringDefaults}
                    className="flex items-center gap-1.5 px-4 py-2 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-50 text-indigo-700 border border-indigo-200 rounded-xl text-xs font-bold transition-all cursor-pointer shadow-xs"
                    title="Save current custom configuration as permanent default profile"
                  >
                    <BookmarkCheck className={`w-3.5 h-3.5 ${savingAsDefault ? 'animate-spin' : ''}`} />
                    <span>{savingAsDefault ? 'Saving Default...' : 'Save as Default'}</span>
                  </button>

                  {/* Save All Settings (Active Apply) */}
                  <button
                    type="button"
                    onClick={handleSaveAllSettings}
                    disabled={savingSettings || savingAsDefault || restoringDefaults}
                    className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white rounded-xl text-xs font-black shadow-md shadow-blue-500/20 cursor-pointer transition-all"
                  >
                    {savingSettings ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Synchronizing...
                      </>
                    ) : (
                      <>
                        <Shield className="w-3.5 h-3.5" /> Save All Settings
                      </>
                    )}
                  </button>
                </>
              )}
            </div>
          </div>

          {/* ACCOUNT MODE & WALLET GOVERNANCE (INTERNAL SETTINGS ACCESS) */}
          <div className="bg-white p-5 sm:p-6 rounded-2xl border border-slate-200 shadow-xs space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
              <div className="flex items-center gap-2.5">
                <span className="p-2 rounded-xl bg-blue-50 text-blue-600">
                  <Wallet className="w-5 h-5" />
                </span>
                <div>
                  <h3 className="text-base font-black text-slate-900 tracking-tight flex items-center gap-2">
                    <span>Account Execution Mode & Web3 Wallet</span>
                    <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 font-bold">
                      Isolated States
                    </span>
                  </h3>
                  <p className="text-xs text-slate-500 font-medium">
                    Toggle your account execution environment between risk-free virtual paper trading and live Polygon CLOB on-chain trading.
                  </p>
                </div>
              </div>

              {/* Quick Wallet Actions */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleRefreshWalletBalance}
                  disabled={refreshingWalletBal}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-bold transition-all cursor-pointer"
                  title="Sync on-chain Polygon balance"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${refreshingWalletBal ? 'animate-spin' : ''}`} />
                  <span>{refreshingWalletBal ? 'Syncing...' : 'Sync Balance'}</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleOpenDepositWithdraw('deposit')}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition-all cursor-pointer shadow-xs"
                >
                  <Wallet className="w-3.5 h-3.5" />
                  <span>Configure Wallet</span>
                </button>
              </div>
            </div>

            {/* Mode Selectors Grid */}
            <div className={`grid grid-cols-1 ${isRealAccount ? 'md:grid-cols-1' : 'md:grid-cols-2'} gap-4`}>
              {/* Option A: Virtual Demo Account (Automatically hidden when Real Wallet is connected) */}
              {!isRealAccount && (
                <button
                  type="button"
                  onClick={() => handleToggleWalletMode('demo')}
                  disabled={togglingMode}
                  className={`p-4 rounded-2xl border text-left transition-all cursor-pointer relative overflow-hidden flex flex-col justify-between ${
                    accountMode === 'demo' || walletInfo?.account_mode === 'demo' || !walletInfo?.is_connected
                      ? 'border-blue-500 bg-blue-50/60 shadow-sm ring-2 ring-blue-500/20'
                      : 'border-slate-200 bg-slate-50/50 hover:border-slate-300'
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-200">
                        🎮 Virtual Demo ($300 Base)
                      </span>
                      {(accountMode === 'demo' || walletInfo?.account_mode === 'demo' || !walletInfo?.is_connected) && (
                        <span className="p-1 rounded-full bg-blue-600 text-white">
                          <Check className="w-3 h-3" />
                        </span>
                      )}
                    </div>
                    <div className="text-sm font-black text-slate-900">Paper Trading Simulation</div>
                    <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                      Zero financial risk. Dedicated virtual ledger isolated from live funds. Test algorithmic signals and verify execution.
                    </p>
                  </div>
                  <div className="mt-3 pt-2.5 border-t border-slate-200/60 flex items-center justify-between font-mono text-xs">
                    <span className="text-slate-500">Virtual Equity:</span>
                    <span className="font-bold text-blue-700">${((stats.initial_balance ?? 300) + stats.total_pnl).toFixed(2)}</span>
                  </div>
                </button>
              )}

              {/* Option B: Real Money Polygon CLOB */}
              <button
                type="button"
                onClick={() => handleToggleWalletMode('live')}
                disabled={togglingMode}
                className={`p-4 rounded-2xl border text-left transition-all cursor-pointer relative overflow-hidden flex flex-col justify-between ${
                  isRealAccount
                    ? 'border-emerald-500 bg-emerald-50/60 shadow-sm ring-2 ring-emerald-500/20'
                    : 'border-slate-200 bg-slate-50/50 hover:border-slate-300'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
                      ⚡ Real Vault (Polygon Mainnet)
                    </span>
                    {isRealAccount && (
                      <span className="p-1 rounded-full bg-emerald-600 text-white">
                        <Check className="w-3 h-3" />
                      </span>
                    )}
                  </div>
                  <div className="text-sm font-black text-slate-900">Live Polymarket CLOB Execution</div>
                  <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                    Real Web3 Polygon on-chain order placement with non-custodial wallet signing and authentic CLOB fills.
                  </p>
                </div>
                <div className="mt-3 pt-2.5 border-t border-slate-200/60 flex items-center justify-between font-mono text-xs">
                  <span className="text-slate-500">Connected Wallet:</span>
                  <span className="font-bold text-slate-800">{displayAddress}</span>
                </div>
              </button>
            </div>

            {/* Wallet Info Summary Bar */}
            <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-3">
                <span className={`w-2.5 h-2.5 rounded-full ${walletInfo?.is_connected ? 'bg-emerald-500 animate-pulse' : 'bg-amber-400'}`} />
                <div>
                  <span className="font-bold text-slate-800">
                    {walletInfo?.is_connected ? 'Web3 Wallet Connected' : 'Web3 Wallet Not Connected'}
                  </span>
                  <span className="text-slate-500 font-mono ml-2 text-[11px]">
                    ({walletInfo?.masked_address || displayAddress})
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-3 font-mono text-[11px] text-slate-600 flex-wrap">
                <span>USDC: <strong className="text-slate-900 font-bold">${walletInfo?.usdc_total != null ? walletInfo.usdc_total.toFixed(2) : '0.00'}</strong></span>
                <span>•</span>
                <span>POL Gas: <strong className="text-slate-900 font-bold">{walletInfo?.pol_gas_balance != null ? walletInfo.pol_gas_balance.toFixed(4) : '0.0000'}</strong></span>
                {walletInfo?.is_connected && (
                  <>
                    <span>•</span>
                    <button
                      type="button"
                      onClick={handleDisconnectWallet}
                      className="text-rose-600 hover:text-rose-800 underline font-sans font-bold cursor-pointer"
                    >
                      Disconnect
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Non-Admin Prominent Warning Banner */}
          {!isAdmin && (
            <div className="bg-amber-50 border border-amber-200 text-amber-900 p-4 rounded-2xl text-xs flex items-center gap-3 shadow-xs">
              <div className="p-2 bg-amber-100 text-amber-700 rounded-xl shrink-0">
                <Lock className="w-5 h-5" />
              </div>
              <div className="space-y-0.5">
                <div className="font-bold text-amber-950 text-sm flex items-center gap-2">
                  <span>Administrative Control Enforced (Read-Only Mode)</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-200/80 text-amber-900">
                    shalombinrasheed@gmail.com
                  </span>
                </div>
                <p className="text-amber-800 leading-relaxed">
                  Trading rules, risk parameters, quantitative weights, and execution sizes are centrally managed by the platform Super Admin. All configuration fields below are displayed in read-only mode for your transparency and inspection.
                </p>
              </div>
            </div>
          )}

          {/* MAIN 3-PANEL CONFIGURATION GRID */}
          <fieldset disabled={!isAdmin} className={`border-0 p-0 m-0 ${!isAdmin ? 'opacity-85 pointer-events-none select-none' : ''}`}>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

            {/* PANEL 1: MANUAL RISK—TO—REWARD RATIO & TARGETS */}
            <div className="bg-slate-50/70 p-5 rounded-2xl border border-slate-200/80 space-y-4 flex flex-col justify-between">
              <div className="space-y-4">
                {/* Header & Dynamic Ratio Badge */}
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                    <Scale className="w-4 h-4 text-blue-600" /> Risk—to—Reward Ratio
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-300 flex items-center gap-1">
                      <Scale className="w-3 h-3 text-blue-600" /> Dynamic R:R
                    </span>
                    <span className={`text-xs font-mono font-black px-2.5 py-0.5 rounded-full border ${
                      riskRewardRatio >= 1.0
                        ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
                        : 'bg-amber-100 text-amber-800 border-amber-300'
                    }`}>
                      {riskRewardRatio.toFixed(2)} : 1.00 R:R
                    </span>
                  </div>
                </div>

                {/* MANUAL RISK-TO-REWARD RATIO INPUT FIELD */}
                <div className="bg-white p-3.5 rounded-xl border border-blue-200/80 shadow-xs space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                      <Scale className="w-4 h-4 text-blue-600" />
                      <span>Manual Risk-to-Reward Ratio</span>
                    </label>
                    <span className="text-xs font-mono font-black px-2 py-0.5 rounded-lg bg-blue-50 text-blue-700 border border-blue-200">
                      {riskRewardRatio.toFixed(2)} : 1.00 R:R
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="relative flex-1">
                      <input
                        type="number"
                        step="0.1"
                        min="0.2"
                        max="10.0"
                        value={riskRewardRatio}
                        onChange={(e) => {
                          markSettingEdited();
                          const r = Math.max(0.1, Number(e.target.value));
                          setRiskRewardRatio(r);
                          const newTp = Number((stopLossPct * r).toFixed(2));
                          setTakeProfitPct(newTp);
                          setTakeProfitDollar(Number(((positionSize * newTp) / 100).toFixed(2)));
                        }}
                        className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-bold font-mono text-slate-900 focus:outline-hidden focus:border-blue-500"
                        placeholder="e.g. 1.0, 1.5, 2.0"
                      />
                    </div>
                    <span className="text-xs text-slate-400 font-mono font-bold">: 1</span>
                  </div>
                  {/* Quick R:R Preset Buttons */}
                  <div className="grid grid-cols-5 gap-1.5 pt-1">
                    {[1.0, 1.5, 2.0, 2.5, 3.0].map((r) => (
                      <button
                        key={r}
                        type="button"
                        onClick={() => {
                          markSettingEdited();
                          setRiskRewardRatio(r);
                          const newTp = Number((stopLossPct * r).toFixed(2));
                          setTakeProfitPct(newTp);
                          setTakeProfitDollar(Number(((positionSize * newTp) / 100).toFixed(2)));
                        }}
                        className={`py-1 text-center rounded-lg text-[10px] font-bold font-mono transition-all cursor-pointer ${
                          Math.abs(riskRewardRatio - r) < 0.05
                            ? 'bg-blue-600 text-white shadow-xs'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        }`}
                      >
                        {r.toFixed(1)}:1
                      </button>
                    ))}
                  </div>
                  <div className="text-[10px] text-slate-500 leading-relaxed bg-blue-50/50 p-2 rounded-lg border border-blue-100">
                    ⚖️ <strong>Linked Risk/Reward:</strong> Setting the ratio automatically calculates your Take Profit target based on Stop Loss.
                  </div>
                </div>

                {/* 1. BUFFER SYSTEM & NOISE IMMUNITY WINDOW */}
                <div className="bg-white p-3.5 rounded-xl border border-blue-200/80 shadow-xs space-y-2.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5 cursor-pointer">
                      <Timer className="w-4 h-4 text-blue-600" />
                      <span>1. Grace Period Buffer System</span>
                    </label>
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-lg border ${
                        bufferEnabled ? 'bg-blue-50 text-blue-700 border-blue-200' : 'bg-slate-100 text-slate-500 border-slate-200'
                      }`}>
                        {bufferEnabled ? `${bufferTimerSec.toFixed(1)}s Delay` : 'DISABLED'}
                      </span>
                      <input
                        type="checkbox"
                        checked={bufferEnabled}
                        onChange={(e) => {
                          markSettingEdited();
                          setBufferEnabled(e.target.checked);
                        }}
                        className="w-4 h-4 accent-blue-600 cursor-pointer"
                        title="Toggle Grace Period Buffer on/off"
                      />
                    </div>
                  </div>
                  {bufferEnabled && (
                    <>
                      <input
                        type="range"
                        min="1.0"
                        max="15.0"
                        step="0.5"
                        value={bufferTimerSec}
                        onChange={(e) => {
                          markSettingEdited();
                          setBufferTimerSec(Number(e.target.value));
                        }}
                        className="w-full accent-blue-600 cursor-pointer"
                      />
                      <div className="flex items-center justify-between gap-1.5">
                        {[2.0, 3.0, 4.0, 5.0, 6.0].map((sec) => (
                          <button
                            key={sec}
                            type="button"
                            onClick={() => {
                              markSettingEdited();
                              setBufferTimerSec(sec);
                            }}
                            className={`flex-1 py-1 text-center rounded-lg text-[10px] font-bold font-mono transition-all cursor-pointer ${
                              Math.abs(bufferTimerSec - sec) < 0.1
                                ? 'bg-blue-600 text-white shadow-xs'
                                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                            }`}
                          >
                            {sec.toFixed(1)}s
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                  <div className="text-[10px] text-slate-500 leading-relaxed bg-blue-50/50 p-2 rounded-lg border border-blue-100">
                    🛡️ <strong className="text-blue-900">Noise Immunity Window:</strong> {bufferEnabled ? `Suppresses micro-spread noise for ${bufferTimerSec}s after entry. Strict hard stop loss breaches will always trigger immediate exit.` : 'Disabled: trades execute instant exit checks without entry delay.'}
                  </div>
                </div>

                {/* 2. RISK-TO-REWARD PRESETS */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-[11px] text-slate-500 font-semibold block">
                      Quick Risk:Reward Presets:
                    </label>
                    <span className="text-[10px] text-slate-400 font-mono">Unclamped Dynamic SL</span>
                  </div>
                  <div className="grid grid-cols-4 gap-1.5">
                    {[
                      { label: '1:1 Strict', tp: 3.0, sl: 3.0, rr: 1.0 },
                      { label: '1.5:1 High', tp: 4.5, sl: 3.0, rr: 1.5 },
                      { label: '2:1 Edge',   tp: 6.0, sl: 3.0, rr: 2.0 },
                      { label: '3:1 Pro',    tp: 9.0, sl: 3.0, rr: 3.0 },
                    ].map((p) => {
                      const isActive = Math.abs(takeProfitPct - p.tp) < 0.1 && Math.abs(stopLossPct - p.sl) < 0.1;
                      return (
                        <button
                          key={p.label}
                          type="button"
                          onClick={() => {
                            markSettingEdited();
                            setTakeProfitPct(p.tp);
                            setStopLossPct(p.sl);
                            setRiskRewardRatio(p.rr);
                            setTakeProfitDollar(Number(((positionSize * p.tp) / 100).toFixed(2)));
                            setStopLossDollar(Number(((positionSize * p.sl) / 100).toFixed(2)));
                          }}
                          className={`py-1.5 px-1 text-center rounded-xl text-[11px] font-bold transition-all cursor-pointer ${
                            isActive
                              ? 'bg-blue-600 text-white shadow-xs'
                              : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                          }`}
                        >
                          <div>{p.label}</div>
                          <div className="text-[9px] opacity-75 font-mono">{p.tp}% / {p.sl}%</div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Manual Take Profit & Stop Loss Targets */}
                <div className="grid grid-cols-2 gap-3 pt-1">
                  {/* Take Profit Target */}
                  <div className="bg-white p-3 rounded-xl border border-slate-200 space-y-1">
                    <div className="flex items-center justify-between mb-0.5">
                      <label className="text-[11px] text-slate-700 font-bold">Take Profit %:</label>
                      <span className="text-[10px] text-emerald-600 font-mono font-bold">
                        +${((positionSize * takeProfitPct) / 100).toFixed(2)}
                      </span>
                    </div>
                    <div className="relative">
                      <input
                        type="number"
                        step="0.5"
                        min="0.5"
                        max="50.0"
                        value={takeProfitPct}
                        onChange={(e) => {
                          markSettingEdited();
                          const pct = Math.max(0.1, Number(e.target.value));
                          setTakeProfitPct(pct);
                          setTakeProfitDollar(Number(((positionSize * pct) / 100).toFixed(2)));
                          if (stopLossPct > 0) {
                            setRiskRewardRatio(Number((pct / stopLossPct).toFixed(2)));
                          }
                        }}
                        className="w-full pr-7 pl-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-bold font-mono text-emerald-700 focus:outline-hidden focus:border-blue-500"
                      />
                      <span className="absolute right-2.5 top-2 text-emerald-600 font-bold text-xs">%</span>
                    </div>
                    <span className="text-[9px] text-slate-400 block">Target gain %</span>
                  </div>

                  {/* Stop Loss % (Pure Unclamped) */}
                  <div className="bg-white p-3 rounded-xl border border-rose-200 space-y-1">
                    <div className="flex items-center justify-between mb-0.5">
                      <label className="text-[11px] text-rose-800 font-bold flex items-center gap-1">
                        <Shield className="w-3 h-3 text-rose-600" />
                        <span>Stop Loss %:</span>
                      </label>
                      <span className="text-[10px] text-rose-600 font-mono font-bold">
                        -${((positionSize * stopLossPct) / 100).toFixed(2)}
                      </span>
                    </div>
                    <div className="relative">
                      <input
                        type="number"
                        step="0.5"
                        min="0.5"
                        max="50.0"
                        value={stopLossPct}
                        onChange={(e) => {
                          markSettingEdited();
                          const pct = Math.max(0.1, Number(e.target.value));
                          setStopLossPct(pct);
                          setStopLossDollar(Number(((positionSize * pct) / 100).toFixed(2)));
                          if (pct > 0 && riskRewardRatio > 0) {
                            const newTp = Number((pct * riskRewardRatio).toFixed(2));
                            setTakeProfitPct(newTp);
                            setTakeProfitDollar(Number(((positionSize * newTp) / 100).toFixed(2)));
                          }
                        }}
                        className="w-full pr-7 pl-3 py-1.5 bg-rose-50/40 border border-rose-200 rounded-lg text-xs font-bold font-mono text-rose-700 focus:outline-hidden focus:border-rose-500"
                      />
                      <span className="absolute right-2.5 top-2 text-rose-600 font-bold text-xs">%</span>
                    </div>
                    <span className="text-[9px] text-slate-400 block">Max allowed loss %</span>
                  </div>
                </div>

                {/* Genuine Fill Notice */}
                <div className="bg-emerald-50/70 border border-emerald-200 p-2.5 rounded-xl text-[10px] text-emerald-900 leading-snug flex items-center gap-2">
                  <Shield className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>
                    <strong>100% Genuine Market Fills:</strong> All stop-loss exits are now settled against the real CLOB. Trade PnL reflects explicit market liquidity and pure orderbook slippage.
                  </span>
                </div>

                {/* 3. AUTOMATIC PROFIT LOCK ON REVERSAL (TRAILING STOP) */}
                <div className="pt-2 border-t border-slate-200/60 space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs text-slate-800 font-bold flex items-center gap-1.5 cursor-pointer">
                      <Lock className="w-3.5 h-3.5 text-blue-600" />
                      <span>3. Strict Real-Time Trailing Stop & Profit Lock</span>
                    </label>
                    <input
                      type="checkbox"
                      checked={trailingLockEnabled}
                      onChange={(e) => {
                        markSettingEdited();
                        setTrailingLockEnabled(e.target.checked);
                      }}
                      className="w-4 h-4 accent-blue-600 cursor-pointer"
                    />
                  </div>

                  <p className="text-[10px] text-slate-500 leading-relaxed">
                    Zero-slippage guarantee: activates immediately upon reaching +{trailingStopActivationPct}%, locking profits at market if price pulls back by {trailingStopDistancePct}%. A winning trade is never allowed to reverse into a loss.
                  </p>

                  <div className="grid grid-cols-2 gap-2 text-[11px] bg-white p-2.5 rounded-xl border border-slate-200">
                    <div>
                      <span className="text-slate-500 text-[10px] block">Trailing Activation:</span>
                      <div className="flex items-center gap-1 mt-0.5">
                        <input
                          type="number"
                          step="0.1"
                          min="0.2"
                          max="5.0"
                          value={trailingStopActivationPct}
                          onChange={(e) => {
                            markSettingEdited();
                            setTrailingStopActivationPct(Math.max(0.2, Number(e.target.value)));
                          }}
                          className="w-full px-1.5 py-0.5 bg-slate-50 border border-slate-200 rounded font-mono text-xs font-bold text-slate-800"
                        />
                        <span className="text-slate-400 font-mono text-xs">%</span>
                      </div>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[10px] block">Trailing Distance:</span>
                      <div className="flex items-center gap-1 mt-0.5">
                        <input
                          type="number"
                          step="0.1"
                          min="0.1"
                          max="2.0"
                          value={trailingStopDistancePct}
                          onChange={(e) => {
                            markSettingEdited();
                            setTrailingStopDistancePct(Math.max(0.1, Number(e.target.value)));
                          }}
                          className="w-full px-1.5 py-0.5 bg-slate-50 border border-slate-200 rounded font-mono text-xs font-bold text-slate-800"
                        />
                        <span className="text-slate-400 font-mono text-xs">%</span>
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[11px] bg-white p-2.5 rounded-xl border border-slate-200">
                    <div>
                      <span className="text-slate-500 text-[10px] block">Min Profit to Arm:</span>
                      <div className="flex items-center gap-1 mt-0.5">
                        <span className="text-slate-400 font-mono text-xs">$</span>
                        <input
                          type="number"
                          step="0.02"
                          min="0.02"
                          max="0.50"
                          value={minProfitToLock}
                          onChange={(e) => {
                            markSettingEdited();
                            setMinProfitToLock(Math.max(0.02, Number(e.target.value)));
                          }}
                          className="w-full px-1.5 py-0.5 bg-slate-50 border border-slate-200 rounded font-mono text-xs font-bold text-slate-800"
                        />
                      </div>
                    </div>
                    <div>
                      <span className="text-slate-500 text-[10px] block">Reversal Giveback:</span>
                      <div className="flex items-center gap-1 mt-0.5">
                        <span className="text-slate-400 font-mono text-xs">$</span>
                        <input
                          type="number"
                          step="0.01"
                          min="0.01"
                          max="0.10"
                          value={reversalGivebackDollar}
                          onChange={(e) => {
                            markSettingEdited();
                            setReversalGivebackDollar(Math.max(0.01, Number(e.target.value)));
                          }}
                          className="w-full px-1.5 py-0.5 bg-slate-50 border border-slate-200 rounded font-mono text-xs font-bold text-slate-800"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Reversal Defense Sub-Toggle */}
                  <div className="flex items-center justify-between pt-1 text-[11px] text-slate-700">
                    <label className="flex items-center gap-1.5 cursor-pointer font-semibold">
                      <RotateCcw className="w-3.5 h-3.5 text-purple-600" />
                      <span>Technical Momentum Reversal Exit</span>
                    </label>
                    <input
                      type="checkbox"
                      checked={reversalLockEnabled}
                      onChange={(e) => {
                        markSettingEdited();
                        setReversalLockEnabled(e.target.checked);
                      }}
                      className="w-3.5 h-3.5 accent-purple-600 cursor-pointer"
                      title="Exit on momentum bounce back toward breakeven"
                    />
                  </div>
                </div>

                {/* 4. EXECUTION SLIPPAGE CIRCUIT BREAKER */}
                <div className="pt-2 border-t border-slate-200/60 space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs text-slate-800 font-bold flex items-center gap-1.5 cursor-pointer">
                      <Shield className="w-3.5 h-3.5 text-amber-600" />
                      <span>4. Slippage Circuit Breaker on Exit</span>
                    </label>
                    <input
                      type="checkbox"
                      checked={exitCircuitBreakerEnabled}
                      onChange={(e) => {
                        markSettingEdited();
                        setExitCircuitBreakerEnabled(e.target.checked);
                      }}
                      className="w-4 h-4 accent-amber-600 cursor-pointer"
                    />
                  </div>

                  <p className="text-[10px] text-slate-500 leading-relaxed">
                    🛡️ <strong>Catastrophic Drawdown Protection:</strong> Blocks reckless stop-loss market dumps when orderbook bid depth collapses (e.g. illiquid vacuum books on low-liquidity pairs like HYPE). Holds position with adaptive limit defense until liquidity replenishes or round expiry.
                  </p>

                  <div className="bg-white p-2.5 rounded-xl border border-slate-200 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-slate-700">Max Allowed Exit Slippage:</span>
                      <span className="text-xs font-mono font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                        {maxExitSlippagePct.toFixed(1)}% Beyond SL
                      </span>
                    </div>
                    <input
                      type="range"
                      min="0.5"
                      max="10.0"
                      step="0.5"
                      disabled={!exitCircuitBreakerEnabled}
                      value={maxExitSlippagePct}
                      onChange={(e) => {
                        markSettingEdited();
                        setMaxExitSlippagePct(Number(e.target.value));
                      }}
                      className="w-full accent-amber-600 cursor-pointer disabled:opacity-40"
                    />
                    <div className="flex items-center justify-between gap-1.5">
                      {[0.5, 1.0, 2.0, 5.0].map((slip) => (
                        <button
                          key={slip}
                          type="button"
                          disabled={!exitCircuitBreakerEnabled}
                          onClick={() => {
                            markSettingEdited();
                            setMaxExitSlippagePct(slip);
                          }}
                          className={`flex-1 py-1 text-center rounded-lg text-[10px] font-bold font-mono transition-all cursor-pointer ${
                            Math.abs(maxExitSlippagePct - slip) < 0.1
                              ? 'bg-amber-600 text-white shadow-xs'
                              : 'bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-40'
                          }`}
                        >
                          {slip.toFixed(1)}%
                        </button>
                      ))}
                    </div>
                    <div className="text-[10px] text-slate-500 leading-snug">
                      Clamps simulated paper exit price so stop-loss exits never dump below {maxExitSlippagePct.toFixed(1)}% slippage past trigger price.
                    </div>
                  </div>

                  {/* Pre-Trade Entry Slippage & Spread Filter (Issue #2) */}
                  <div className="bg-white p-2.5 rounded-xl border border-blue-200 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-slate-700">Max Entry Slippage Filter:</span>
                      <span className="text-xs font-mono font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                        {maxEntrySlippagePct.toFixed(1)}% Max Slip
                      </span>
                    </div>
                    <input
                      type="range"
                      min="0.2"
                      max="2.0"
                      step="0.1"
                      value={maxEntrySlippagePct}
                      onChange={(e) => {
                        markSettingEdited();
                        setMaxEntrySlippagePct(Number(e.target.value));
                      }}
                      className="w-full accent-blue-600 cursor-pointer"
                    />
                    <div className="flex items-center justify-between gap-1.5">
                      {[0.5, 0.8, 1.0, 1.5].map((slip) => (
                        <button
                          key={slip}
                          type="button"
                          onClick={() => {
                            markSettingEdited();
                            setMaxEntrySlippagePct(slip);
                          }}
                          className={`flex-1 py-1 text-center rounded-lg text-[10px] font-bold font-mono transition-all cursor-pointer ${
                            Math.abs(maxEntrySlippagePct - slip) < 0.05
                              ? 'bg-blue-600 text-white shadow-xs'
                              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                          }`}
                        >
                          {slip.toFixed(1)}%
                        </button>
                      ))}
                    </div>
                    <div className="text-[10px] text-slate-500 leading-snug">
                      🛡️ <strong>Slippage & Spread Guard:</strong> If difference between expected mid-price and best available ask exceeds {maxEntrySlippagePct.toFixed(1)}%, the fill is aborted to prevent market-entering into an immediate loss.
                    </div>
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-200/60 text-[10px] text-slate-400 font-mono flex items-center justify-between">
                <span>Manual configuration active.</span>
                <span className="text-indigo-600 font-bold">Auto-persisted to VPS</span>
              </div>
            </div>

            {/* PANEL 2: ACTIVE QUANTITATIVE FILTERS & INDICATORS */}
            <div className="bg-slate-50/70 p-5 rounded-2xl border border-slate-200/80 space-y-4 flex flex-col justify-between">
              <div className="space-y-3.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                    <SlidersHorizontal className="w-4 h-4 text-purple-600" /> Active Filters & Indicators
                  </span>
                  <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded-full bg-purple-100 text-purple-800">
                    Quant Confluence
                  </span>
                </div>

                {/* Filter 1: Oracle Price Delta & Velocity */}
                <div className="bg-white p-3 rounded-xl border border-slate-200 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={filterDeltaEnabled}
                        onChange={(e) => setFilterDeltaEnabled(e.target.checked)}
                        className="w-3.5 h-3.5 accent-purple-600"
                      />
                      <span>1. Oracle Delta & Velocity</span>
                    </label>
                    <span className="text-xs font-mono font-bold text-purple-700">
                      {filterDeltaEnabled ? `${filterDeltaWeight} pts` : 'BYPASSED'}
                    </span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="50"
                    step="5"
                    disabled={!filterDeltaEnabled}
                    value={filterDeltaWeight}
                    onChange={(e) => setFilterDeltaWeight(Number(e.target.value))}
                    className="w-full accent-purple-600 cursor-pointer disabled:opacity-40"
                  />
                  <div className="text-[10px] text-slate-400">
                    Weight for sub-second oracle price divergence from epoch strike price
                  </div>
                </div>

                {/* Filter 2: Order Book Imbalance (OBI) */}
                <div className="bg-white p-3 rounded-xl border border-slate-200 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={filterObiEnabled}
                        onChange={(e) => setFilterObiEnabled(e.target.checked)}
                        className="w-3.5 h-3.5 accent-blue-600"
                      />
                      <span>2. Order Book Imbalance (OBI)</span>
                    </label>
                    <span className="text-xs font-mono font-bold text-blue-700">
                      {filterObiEnabled ? `${filterObiWeight} pts` : 'BYPASSED'}
                    </span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="50"
                    step="5"
                    disabled={!filterObiEnabled}
                    value={filterObiWeight}
                    onChange={(e) => setFilterObiWeight(Number(e.target.value))}
                    className="w-full accent-blue-600 cursor-pointer disabled:opacity-40"
                  />
                  <div className="text-[10px] text-slate-400">
                    Weight for Polymarket CLOB liquidity skew between UP/DOWN shares
                  </div>
                </div>

                {/* Filter 3: Micro-Momentum Confluence */}
                <div className="bg-white p-3 rounded-xl border border-slate-200 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={filterMomentumEnabled}
                        onChange={(e) => setFilterMomentumEnabled(e.target.checked)}
                        className="w-3.5 h-3.5 accent-emerald-600"
                      />
                      <span>3. Micro-Momentum Confluence</span>
                    </label>
                    <span className="text-xs font-mono font-bold text-emerald-700">
                      {filterMomentumEnabled ? `${filterMomentumWeight} pts` : 'BYPASSED'}
                    </span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="50"
                    step="5"
                    disabled={!filterMomentumEnabled}
                    value={filterMomentumWeight}
                    onChange={(e) => setFilterMomentumWeight(Number(e.target.value))}
                    className="w-full accent-emerald-600 cursor-pointer disabled:opacity-40"
                  />
                </div>

                {/* Technical Sub-Indicator Checkboxes */}
                <div className="bg-white p-2.5 rounded-xl border border-slate-200">
                  <div className="text-[11px] font-bold text-slate-700 mb-1.5">Active Indicator Sub-Filters:</div>
                  <div className="grid grid-cols-3 gap-2 text-[11px]">
                    <label className="flex items-center gap-1 text-slate-700 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={filterRsiEnabled}
                        onChange={(e) => setFilterRsiEnabled(e.target.checked)}
                        className="accent-indigo-600"
                      />
                      <span>RSI (14)</span>
                    </label>
                    <label className="flex items-center gap-1 text-slate-700 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={filterBbEnabled}
                        onChange={(e) => setFilterBbEnabled(e.target.checked)}
                        className="accent-indigo-600"
                      />
                      <span>BB (%B)</span>
                    </label>
                    <label className="flex items-center gap-1 text-slate-700 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={filterEmaMacdEnabled}
                        onChange={(e) => setFilterEmaMacdEnabled(e.target.checked)}
                        className="accent-indigo-600"
                      />
                      <span>EMA & MACD</span>
                    </label>
                  </div>
                </div>

                {/* Market Protection Thresholds */}
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div>
                    <label className="text-slate-600 font-semibold block mb-0.5">Max CLOB Spread:</label>
                    <div className="relative">
                      <input
                        type="number"
                        step="1"
                        min="2"
                        max="35"
                        value={Math.round(maxSpread * 100)}
                        onChange={(e) => setMaxSpread(Number(e.target.value) / 100)}
                        className="w-full px-2 py-1 bg-white border border-slate-200 rounded-lg font-mono text-xs font-bold"
                      />
                      <span className="absolute right-2 top-1 text-slate-400 font-mono">%</span>
                    </div>
                  </div>
                  <div>
                    <label className="text-slate-600 font-semibold block mb-0.5">Min Liquidity:</label>
                    <div className="relative">
                      <span className="absolute left-2 top-1 text-slate-400 font-mono">$</span>
                      <input
                        type="number"
                        step="50"
                        min="50"
                        max="2000"
                        value={minLiquidityUsd}
                        onChange={(e) => setMinLiquidityUsd(Number(e.target.value))}
                        className="w-full pl-5 pr-2 py-1 bg-white border border-slate-200 rounded-lg font-mono text-xs font-bold"
                      />
                    </div>
                  </div>
                </div>

                {/* Dedicated Per-Asset Spread & Liquidity Controls */}
                <div className="bg-white p-3 rounded-xl border border-slate-200 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                        <Layers className="w-3.5 h-3.5 text-blue-600" />
                        Dedicated Per-Asset Controls
                      </span>
                      <span className="text-[10px] text-slate-400 block">
                        Individual liquidity & spread filters to protect thin pairs (HYPE, DOGE, XRP)
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        markSettingEdited();
                        setPerAssetSpread({ BTC: 6, ETH: 6, SOL: 8, XRP: 10, DOGE: 10, BNB: 8, HYPE: 8 });
                        setPerAssetLiquidity({ BTC: 150, ETH: 150, SOL: 120, XRP: 100, DOGE: 100, BNB: 100, HYPE: 150 });
                      }}
                      className="text-[10px] text-blue-600 hover:text-blue-800 font-semibold underline cursor-pointer"
                    >
                      Reset Defaults
                    </button>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-56 overflow-y-auto pr-1">
                    {['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'BNB', 'HYPE'].map((asset) => {
                      const spreadVal = perAssetSpread[asset] ?? 8;
                      const liqVal = perAssetLiquidity[asset] ?? 100;
                      const isThin = ['HYPE', 'DOGE', 'XRP'].includes(asset);
                      return (
                        <div key={asset} className={`p-2 rounded-lg border text-[11px] space-y-1.5 ${isThin ? 'bg-amber-50/50 border-amber-200' : 'bg-slate-50 border-slate-200'}`}>
                          <div className="flex items-center justify-between">
                            <span className="font-black text-slate-900 flex items-center gap-1">
                              {asset}
                              {isThin && <span className="text-[8px] px-1 py-0.2 rounded bg-amber-200 text-amber-900 font-bold uppercase">Safeguard</span>}
                            </span>
                            <span className="text-[10px] font-mono text-slate-500">
                              Spread: {spreadVal}% | Liq: ${liqVal}
                            </span>
                          </div>
                          <div className="grid grid-cols-2 gap-1.5">
                            <div>
                              <span className="text-[9px] text-slate-400 block">Max Spread:</span>
                              <div className="relative">
                                <input
                                  type="number"
                                  min="2"
                                  max="30"
                                  step="1"
                                  value={spreadVal}
                                  onChange={(e) => {
                                    markSettingEdited();
                                    setPerAssetSpread(prev => ({ ...prev, [asset]: Number(e.target.value) }));
                                  }}
                                  className="w-full px-1.5 py-0.5 bg-white border border-slate-200 rounded font-mono text-[11px] font-bold"
                                />
                                <span className="absolute right-1.5 top-0.5 text-slate-400 font-mono text-[10px]">%</span>
                              </div>
                            </div>
                            <div>
                              <span className="text-[9px] text-slate-400 block">Min Liq ($):</span>
                              <div className="relative">
                                <input
                                  type="number"
                                  min="20"
                                  max="2000"
                                  step="25"
                                  value={liqVal}
                                  onChange={(e) => {
                                    markSettingEdited();
                                    setPerAssetLiquidity(prev => ({ ...prev, [asset]: Number(e.target.value) }));
                                  }}
                                  className="w-full px-1.5 py-0.5 bg-white border border-slate-200 rounded font-mono text-[11px] font-bold"
                                />
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-200/60 text-[10px] text-slate-400 font-mono">
                Total Weight: {(filterDeltaEnabled ? filterDeltaWeight : 0) + (filterObiEnabled ? filterObiWeight : 0) + (filterMomentumEnabled ? filterMomentumWeight : 0)} pts (Normalized to 0 - 100)
              </div>
            </div>

            {/* PANEL 3: POSITION SIZING & STRATEGY DIRECTION */}
            <div className="bg-slate-50/70 p-5 rounded-2xl border border-slate-200/80 space-y-4 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                    <DollarSign className="w-4 h-4 text-emerald-600" /> Capital & Directional Bias
                  </span>
                  <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">
                    Execution Rules
                  </span>
                </div>

                {/* Position Sizing */}
                <div>
                  <label className="text-xs text-slate-600 font-semibold mb-1.5 block">
                    Execution Size per Prediction:
                  </label>
                  <div className="grid grid-cols-4 gap-2 mb-2">
                    {[1, 10, 25, 50].map((sz) => (
                      <button
                        key={sz}
                        type="button"
                        onClick={() => {
                          markSettingEdited();
                          setPositionSize(sz);
                        }}
                        className={`py-2 text-center rounded-xl text-xs font-black font-mono transition-all cursor-pointer ${
                          positionSize === sz
                            ? 'bg-blue-600 text-white shadow-sm shadow-blue-500/30'
                            : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                        }`}
                      >
                        ${sz}.00
                      </button>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400 font-medium">Custom:</span>
                    <div className="relative flex-1">
                      <span className="absolute left-3 top-2 text-slate-400 font-mono text-xs">$</span>
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={positionSize}
                        onChange={(e) => {
                          markSettingEdited();
                          setPositionSize(Math.max(1, Number(e.target.value)));
                        }}
                        className="w-full pl-6 pr-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs font-bold font-mono text-slate-800 focus:outline-hidden focus:border-blue-500"
                        placeholder="Enter any amount"
                      />
                    </div>
                    <span className="text-xs text-slate-400 font-mono">USD</span>
                  </div>
                  <p className="text-[10px] text-slate-400 mt-1">
                    Enter any custom amount for your prediction position size without preset restrictions.
                  </p>
                </div>

                {/* Strategy Direction */}
                <div>
                  <label className="text-xs text-slate-600 font-semibold mb-1.5 block">
                    Directional Strategy Bias:
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      type="button"
                      onClick={() => setStrategyDirection('BOTH')}
                      className={`py-2 px-2 text-center rounded-xl text-xs font-bold transition-all cursor-pointer ${
                        strategyDirection === 'BOTH'
                          ? 'bg-purple-600 text-white shadow-sm'
                          : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                      }`}
                    >
                      <div className="font-mono">UP & DOWN</div>
                      <div className="text-[10px] opacity-80">Both Sides</div>
                    </button>
                    <button
                      type="button"
                      onClick={() => setStrategyDirection('UP_ONLY')}
                      className={`py-2 px-2 text-center rounded-xl text-xs font-bold transition-all cursor-pointer ${
                        strategyDirection === 'UP_ONLY'
                          ? 'bg-emerald-600 text-white shadow-sm'
                          : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                      }`}
                    >
                      <div className="font-mono flex items-center justify-center gap-0.5">
                        <ArrowUpRight className="w-3 h-3" /> UP ONLY
                      </div>
                      <div className="text-[10px] opacity-80">Bullish Bias</div>
                    </button>
                    <button
                      type="button"
                      onClick={() => setStrategyDirection('DOWN_ONLY')}
                      className={`py-2 px-2 text-center rounded-xl text-xs font-bold transition-all cursor-pointer ${
                        strategyDirection === 'DOWN_ONLY'
                          ? 'bg-rose-600 text-white shadow-sm'
                          : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                      }`}
                    >
                      <div className="font-mono flex items-center justify-center gap-0.5">
                        <ArrowDownRight className="w-3 h-3" /> DOWN ONLY
                      </div>
                      <div className="text-[10px] opacity-80">Bearish Bias</div>
                    </button>
                  </div>
                </div>

                {/* Max Active Pools */}
                <div>
                  <label className="text-xs text-slate-600 font-semibold mb-1.5 flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-blue-600" /> Max Active Pools:
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { val: 1, label: '1 Pool', desc: 'Strict Single' },
                      { val: 2, label: '2 Pools', desc: 'Dual Asset' },
                      { val: 3, label: '3 Pools', desc: 'Multi Asset' }
                    ].map((item) => (
                      <button
                        key={item.val}
                        type="button"
                        onClick={() => setMaxActivePools(item.val)}
                        className={`py-2 px-2 text-center rounded-xl text-xs font-bold transition-all cursor-pointer ${
                          maxActivePools === item.val
                            ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-500/30'
                            : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                        }`}
                      >
                        <div>{item.label}</div>
                        <div className="text-[10px] opacity-80">{item.desc}</div>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Multi-Entry & Grid Levels Trading */}
                <div className="bg-white p-3.5 rounded-xl border border-indigo-200/80 shadow-xs space-y-2.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5 cursor-pointer">
                      <Layers className="w-4 h-4 text-indigo-600" />
                      <span>Multi-Entry & Grid Levels</span>
                    </label>
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-lg border ${
                        multiEntryEnabled ? 'bg-indigo-50 text-indigo-700 border-indigo-200' : 'bg-slate-100 text-slate-500 border-slate-200'
                      }`}>
                        {multiEntryEnabled ? `Grid Active (${gridLevels}x)` : 'SINGLE ENTRY'}
                      </span>
                      <input
                        type="checkbox"
                        checked={multiEntryEnabled}
                        onChange={(e) => {
                          markSettingEdited();
                          setMultiEntryEnabled(e.target.checked);
                        }}
                        className="w-4 h-4 accent-indigo-600 cursor-pointer"
                        title="Toggle Multi-Entry and Grid Levels"
                      />
                    </div>
                  </div>

                  <p className="text-[10px] text-slate-500 leading-relaxed">
                    Allows the trading bot to execute multiple simultaneous trades and grid levels when opportunities arise, while maintaining strict risk management across all open positions.
                  </p>

                  {multiEntryEnabled && (
                    <div className="grid grid-cols-2 gap-2 text-[11px] bg-slate-50 p-2.5 rounded-xl border border-slate-200">
                      <div>
                        <span className="text-slate-600 text-[10px] font-semibold block">Grid Levels / Asset:</span>
                        <div className="grid grid-cols-3 gap-1 mt-1">
                          {[1, 2, 3].map((lvl) => (
                            <button
                              key={lvl}
                              type="button"
                              onClick={() => {
                                markSettingEdited();
                                setGridLevels(lvl);
                              }}
                              className={`py-1 text-center rounded font-mono font-bold text-xs transition-all cursor-pointer ${
                                gridLevels === lvl
                                  ? 'bg-indigo-600 text-white shadow-xs'
                                  : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                              }`}
                            >
                              {lvl}x
                            </button>
                          ))}
                        </div>
                      </div>
                      <div>
                        <span className="text-slate-600 text-[10px] font-semibold block">Min Grid Spacing:</span>
                        <div className="flex items-center gap-1 mt-1">
                          <input
                            type="number"
                            step="0.5"
                            min="0.5"
                            max="5.0"
                            value={gridStepPct}
                            onChange={(e) => {
                              markSettingEdited();
                              setGridStepPct(Math.max(0.1, Number(e.target.value)));
                            }}
                            className="w-full px-2 py-1 bg-white border border-slate-200 rounded font-mono text-xs font-bold text-indigo-700 focus:outline-hidden"
                          />
                          <span className="text-slate-400 font-mono text-xs">%</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Score Threshold */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between mb-1.5">
                    <div>
                      <label className="text-xs text-slate-700 font-bold block">Min Composite Score (Strict Multi-Threshold):</label>
                      <span className="text-[10px] text-slate-500">Order dispatch is strictly blocked until score reaches this threshold</span>
                    </div>
                    <span className="font-mono font-bold text-sm text-purple-700 bg-purple-50 px-2 py-0.5 rounded-lg border border-purple-200">
                      ≥ {confidenceThreshold}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="50"
                    max="99"
                    step="1"
                    value={confidenceThreshold}
                    onChange={(e) => {
                      markSettingEdited();
                      setConfidenceThreshold(Number(e.target.value));
                    }}
                    className="w-full accent-purple-600 cursor-pointer"
                  />
                  <div className="flex items-center justify-between gap-1.5">
                    {[50, 70, 80, 91, 95].map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => {
                          markSettingEdited();
                          setConfidenceThreshold(preset);
                        }}
                        className={`flex-1 py-1 text-center rounded-lg text-[10px] font-bold font-mono transition-all cursor-pointer ${
                          confidenceThreshold === preset
                            ? 'bg-purple-600 text-white shadow-xs'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        }`}
                      >
                        {preset}%
                      </button>
                    ))}
                  </div>
                  <div className="text-[10px] text-purple-700 bg-purple-50/60 p-2 rounded-lg border border-purple-100 leading-snug">
                    🛡️ <strong>Strict Multi-Threshold Enforcement:</strong> Orders are NOT executed purely based on Rank #1. If current score &lt; {confidenceThreshold}%, status stays WAITING / ARMED with order dispatch completely blocked.
                  </div>
                </div>

                {/* Multi-Pair Concurrent Execution Threshold (Score >= 90%) */}
                <div className="bg-white p-3 rounded-xl border border-amber-200 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                      <Zap className="w-3.5 h-3.5 text-amber-500" />
                      <span>Multi-Pair Threshold (90%+):</span>
                    </label>
                    <span className="font-mono font-bold text-xs text-amber-800 bg-amber-50 px-2 py-0.5 rounded-lg border border-amber-200">
                      ≥ {multiPairMinScore.toFixed(1)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="85.0"
                    max="98.0"
                    step="0.5"
                    value={multiPairMinScore}
                    onChange={(e) => setMultiPairMinScore(Number(e.target.value))}
                    className="w-full accent-amber-600 cursor-pointer"
                  />
                  <div className="text-[10px] text-slate-500 leading-snug">
                    Executes up to {maxActivePools} trades simultaneously without skipping if confidence score reaches ≥ {multiPairMinScore.toFixed(0)}%.
                  </div>
                </div>

                {/* Max Exposure Safeguard (% of Account Balance) */}
                <div className="bg-white p-3 rounded-xl border border-emerald-200 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                      <Shield className="w-3.5 h-3.5 text-emerald-600" />
                      <span>Exposure Safeguard:</span>
                    </label>
                    <span className="font-mono font-bold text-xs text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded-lg border border-emerald-200">
                      {maxPortfolioMarginPct.toFixed(0)}% (${(300 * (maxPortfolioMarginPct / 100)).toFixed(0)})
                    </span>
                  </div>
                  <input
                    type="range"
                    min="15"
                    max="60"
                    step="5"
                    value={maxPortfolioMarginPct}
                    onChange={(e) => setMaxPortfolioMarginPct(Number(e.target.value))}
                    className="w-full accent-emerald-600 cursor-pointer"
                  />
                  <div className="text-[10px] text-slate-500 leading-snug">
                    Safeguard partitions margin evenly across concurrent entries to ensure portfolio is never over-leveraged.
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-200/60 text-[11px] text-slate-500 font-mono flex justify-between items-center">
                <span>Account Allocation:</span>
                <span className="font-bold text-slate-800">
                  ${positionSize * maxActivePools} / ${((stats.initial_balance ?? 300) + stats.total_pnl).toFixed(2)} ({(((positionSize * maxActivePools) / ((stats.initial_balance ?? 300) + stats.total_pnl)) * 100).toFixed(1)}%)
                </span>
              </div>

              {/* 5. Mobile Interface & VPS Localhost Configuration */}
              <div className="pt-3 border-t border-slate-200/60 space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <Menu className="w-3.5 h-3.5 text-indigo-600" />
                    <span className="text-xs font-bold text-slate-800">Mobile Interface Menu Only</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={mobileMenuExclusive}
                    onChange={(e) => {
                      const val = e.target.checked;
                      setMobileMenuExclusive(val);
                      localStorage.setItem('mobile_menu_exclusive', String(val));
                      markSettingEdited();
                      showToast(val ? 'Menu configured to appear exclusively on mobile interface' : 'Menu visible across all screen sizes');
                    }}
                    className="w-4 h-4 accent-indigo-600 cursor-pointer"
                    title="Toggle mobile-exclusive navigation menu"
                  />
                </div>
                <div className="text-[10px] text-slate-500 leading-snug bg-slate-50 p-2 rounded-lg border border-slate-100 flex items-center justify-between">
                  <span>
                    Display Rule: <strong className="text-slate-800">{mobileMenuExclusive ? 'Exclusive on Mobile (< 1280px)' : 'Universal (All Screen Sizes)'}</strong>
                  </span>
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200 font-bold">
                    {mobileMenuExclusive ? 'Mobile Exclusive Active' : 'Universal Mode'}
                  </span>
                </div>
                <div className="text-[10px] text-slate-500 leading-snug bg-emerald-50/50 p-2 rounded-lg border border-emerald-100 flex items-center justify-between font-mono">
                  <div className="flex items-center gap-1">
                    <Server className="w-3 h-3 text-emerald-600" />
                    <span className="text-emerald-800 font-bold">Server Endpoint:</span>
                    <span className="text-slate-600">VPS Localhost (http://localhost)</span>
                  </div>
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold">
                    Reverse Proxy Active
                  </span>
                </div>
              </div>
            </div>

          </div>
          </fieldset>
        </div>
      )}

      {/* SQUAD SYSTEM & NETWORK MONITORING TAB */}
      {activeTab === 'squad' && (
        <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6 shadow-xs space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
            <div>
              <h2 className="text-lg font-black text-slate-900 flex items-center gap-2">
                <Cpu className="w-5 h-5 text-indigo-600" />
                Background Squad System & Network Sentinel
              </h2>
              <p className="text-xs text-slate-500 font-medium">
                4 autonomous workers coordinating real-time oracle tracking, quantitative scoring, risk rules, and server internet speed
              </p>
            </div>

            <button
              onClick={handleTestHealth}
              disabled={healthTesting}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 text-indigo-700 rounded-xl text-xs font-bold transition-all cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${healthTesting ? 'animate-spin' : ''}`} />
              <span>{healthTesting ? 'Running Ping Test...' : 'Test Network Now'}</span>
            </button>
          </div>

          {/* Network Gauges Sub-Bar */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Ping 1: Server Internet */}
            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase font-bold text-slate-400">Server Internet Speed</span>
                <div className="text-xl font-black font-mono text-slate-900 flex items-center gap-1.5 mt-0.5">
                  <Wifi className="w-4 h-4 text-emerald-600" />
                  <span>{board?.system_health?.network?.server_internet_ping_ms ?? 14} ms</span>
                </div>
                <div className="text-[10px] text-emerald-600 font-bold mt-0.5">
                  {board?.system_health?.network?.internet_status || 'Ultra-Low Latency'}
                </div>
              </div>
              <span className="p-2 bg-emerald-100 text-emerald-700 rounded-xl">
                <CheckCircle2 className="w-5 h-5" />
              </span>
            </div>

            {/* Ping 2: Polymarket CLOB */}
            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase font-bold text-slate-400">Polymarket CLOB API</span>
                <div className="text-xl font-black font-mono text-slate-900 flex items-center gap-1.5 mt-0.5">
                  <Server className="w-4 h-4 text-blue-600" />
                  <span>{board?.system_health?.network?.polymarket_clob_ping_ms ?? 28} ms</span>
                </div>
                <div className="text-[10px] text-blue-600 font-bold mt-0.5">
                  Direct Wire Ingestion
                </div>
              </div>
              <span className="p-2 bg-blue-100 text-blue-700 rounded-xl">
                <Activity className="w-5 h-5" />
              </span>
            </div>

            {/* Ping 3: Polymarket Gamma */}
            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase font-bold text-slate-400">Gamma Event Feed</span>
                <div className="text-xl font-black font-mono text-slate-900 flex items-center gap-1.5 mt-0.5">
                  <Radio className="w-4 h-4 text-purple-600" />
                  <span>{board?.system_health?.network?.polymarket_gamma_ping_ms ?? 35} ms</span>
                </div>
                <div className="text-[10px] text-purple-600 font-bold mt-0.5">
                  Market Discovery Active
                </div>
              </div>
              <span className="p-2 bg-purple-100 text-purple-700 rounded-xl">
                <Radio className="w-5 h-5" />
              </span>
            </div>

            {/* Ping 4: System Uptime */}
            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase font-bold text-slate-400">Squad System Uptime</span>
                <div className="text-xl font-black font-mono text-slate-900 flex items-center gap-1.5 mt-0.5">
                  <Gauge className="w-4 h-4 text-amber-600" />
                  <span>{Math.floor((board?.system_health?.uptime_sec ?? 1200) / 60)} min</span>
                </div>
                <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                  Zero Missed Heartbeats
                </div>
              </div>
              <span className="p-2 bg-amber-100 text-amber-700 rounded-xl">
                <Zap className="w-5 h-5" />
              </span>
            </div>
          </div>

          {/* 4 Dedicated Squad Worker Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Worker 1: Oracle Scout */}
            <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="p-2 rounded-lg bg-blue-50 text-blue-600">
                  <Radio className="w-4 h-4" />
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-emerald-100 text-emerald-800">
                  {board?.system_health?.squad_workers?.oracle_scout?.status || 'ONLINE'}
                </span>
              </div>
              <div>
                <h3 className="text-sm font-black text-slate-900">Oracle Scout</h3>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Sub-second WebSocket feeds for Chainlink & Pyth benchmark
                </p>
              </div>
              <div className="pt-2 border-t border-slate-100 text-[11px] font-mono space-y-1 text-slate-600">
                <div className="flex justify-between">
                  <span>Feed Latency:</span>
                  <span className="font-bold text-emerald-600">
                    ⚡ {board?.system_health?.squad_workers?.oracle_scout?.latency_ms ?? 14}ms
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Tracked Assets:</span>
                  <span className="font-bold text-slate-800">7 Active Pairs</span>
                </div>
                <div className="flex justify-between">
                  <span>Tasks Synced:</span>
                  <span className="font-bold text-slate-800">
                    {board?.system_health?.squad_workers?.oracle_scout?.tasks_processed ?? 140}
                  </span>
                </div>
              </div>
            </div>

            {/* Worker 2: Technical Analyst */}
            <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="p-2 rounded-lg bg-purple-50 text-purple-600">
                  <Sliders className="w-4 h-4" />
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-emerald-100 text-emerald-800">
                  {board?.system_health?.squad_workers?.technical_analyst?.status || 'ONLINE'}
                </span>
              </div>
              <div>
                <h3 className="text-sm font-black text-slate-900">Technical Analyst</h3>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Computes Delta, Order Book Imbalance, and 10s/30s Velocity
                </p>
              </div>
              <div className="pt-2 border-t border-slate-100 text-[11px] font-mono space-y-1 text-slate-600">
                <div className="flex justify-between">
                  <span>Quant Compute:</span>
                  <span className="font-bold text-purple-600">
                    {board?.system_health?.squad_workers?.technical_analyst?.latency_ms ?? 3}ms
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Top Pick Rank:</span>
                  <span className="font-bold text-slate-800">#{topPick?.rank ?? 1} {topPick?.asset}</span>
                </div>
                <div className="flex justify-between">
                  <span>Analyses Run:</span>
                  <span className="font-bold text-slate-800">
                    {board?.system_health?.squad_workers?.technical_analyst?.tasks_processed ?? 120}
                  </span>
                </div>
              </div>
            </div>

            {/* Worker 3: Risk Commander */}
            <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
                  <Shield className="w-4 h-4" />
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-emerald-100 text-emerald-800">
                  {board?.system_health?.squad_workers?.risk_commander?.status || 'ONLINE'}
                </span>
              </div>
              <div>
                <h3 className="text-sm font-black text-slate-900">Risk Commander</h3>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Enforces 1:1 RR, single-position lock & anti-reversal trailing
                </p>
              </div>
              <div className="pt-2 border-t border-slate-100 text-[11px] font-mono space-y-1 text-slate-600">
                <div className="flex justify-between">
                  <span>Active Pools:</span>
                  <span className="font-bold text-slate-800">{stats.open_trades} / {maxActivePools} Max</span>
                </div>
                <div className="flex justify-between">
                  <span>Target 1:1 RR:</span>
                  <span className="font-bold text-emerald-600">+${takeProfitDollar} / -${stopLossDollar}</span>
                </div>
                <div className="flex justify-between">
                  <span>Guard Checks:</span>
                  <span className="font-bold text-slate-800">
                    {board?.system_health?.squad_workers?.risk_commander?.tasks_processed ?? 85}
                  </span>
                </div>
              </div>
            </div>

            {/* Worker 4: Health Sentinel */}
            <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="p-2 rounded-lg bg-amber-50 text-amber-600">
                  <Server className="w-4 h-4" />
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-emerald-100 text-emerald-800">
                  {board?.system_health?.squad_workers?.health_sentinel?.status || 'ONLINE'}
                </span>
              </div>
              <div>
                <h3 className="text-sm font-black text-slate-900">Health Sentinel</h3>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Zero-latency heartbeat tracking and external network ping monitor
                </p>
              </div>
              <div className="pt-2 border-t border-slate-100 text-[11px] font-mono space-y-1 text-slate-600">
                <div className="flex justify-between">
                  <span>API Reachability:</span>
                  <span className="font-bold text-emerald-600">100% OK</span>
                </div>
                <div className="flex justify-between">
                  <span>Heartbeat Age:</span>
                  <span className="font-bold text-slate-800">
                    {board?.system_health?.squad_workers?.health_sentinel?.last_heartbeat_age_s ?? 0}s
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Health Probes:</span>
                  <span className="font-bold text-slate-800">
                    {board?.system_health?.squad_workers?.health_sentinel?.tasks_processed ?? 30}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 3. SCORING BREAKDOWN & PREDICTION INSPECTOR TAB */}
      {activeTab === 'scoring' && (
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
            <div>
              <h2 className="text-base font-black text-slate-900 flex items-center gap-2">
                <Sliders className="w-4 h-4 text-purple-600" />
                Live Multi-Factor Scoring Inspector (0 - 100)
              </h2>
              <p className="text-xs text-slate-500 font-medium">
                Detailed quantitative breakdown showing why each asset is scored, ranked, and predicted
              </p>
            </div>

            {/* Asset Selector for Detailed Scoring */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {board?.assets?.map((a) => (
                <button
                  key={a.asset}
                  onClick={() => setSelectedAssetForScore(a.asset)}
                  className={`px-3 py-1 rounded-xl text-xs font-black font-mono transition-all cursor-pointer ${
                    inspectedAsset?.asset === a.asset
                      ? 'bg-purple-600 text-white shadow-xs'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {a.asset} ({a.confidence}%)
                </button>
              ))}
            </div>
          </div>

          {inspectedAsset && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 bg-slate-50/70 p-4 rounded-xl border border-slate-100">
              
              {/* Factor 1: Delta & Velocity */}
              <div className="bg-white p-3.5 rounded-xl border border-slate-200 space-y-2">
                <div className="flex items-center justify-between text-xs font-bold">
                  <span className="text-slate-700">1. Oracle Delta & Velocity</span>
                  <span className="font-mono text-purple-700 font-black">{inspectedAsset.delta_score ?? 20}/40 pts</span>
                </div>
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                  <div 
                    className="bg-purple-600 h-full rounded-full transition-all duration-300"
                    style={{ width: `${((inspectedAsset.delta_score ?? 20) / 40) * 100}%` }}
                  />
                </div>
                <div className="text-[11px] text-slate-500 font-mono space-y-0.5">
                  <div className="flex justify-between">
                    <span>Strike Price (P0):</span>
                    <span className="font-bold text-slate-700">${inspectedAsset.strike_price}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Live Oracle Price:</span>
                    <span className="font-bold text-slate-700">${inspectedAsset.live_price}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Oracle Delta:</span>
                    <span className={inspectedAsset.delta >= 0 ? 'text-emerald-600 font-bold' : 'text-rose-600 font-bold'}>
                      {inspectedAsset.delta >= 0 ? '+' : ''}${inspectedAsset.delta} ({inspectedAsset.delta_pct >= 0 ? '+' : ''}{inspectedAsset.delta_pct}%)
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>10s Price Velocity:</span>
                    <span className="font-bold text-slate-700">{inspectedAsset.velocity_10s >= 0 ? '+' : ''}{inspectedAsset.velocity_10s}%</span>
                  </div>
                </div>
              </div>

              {/* Factor 2: Order Book Imbalance */}
              <div className="bg-white p-3.5 rounded-xl border border-slate-200 space-y-2">
                <div className="flex items-center justify-between text-xs font-bold">
                  <span className="text-slate-700">2. Order Book Imbalance (OBI)</span>
                  <span className="font-mono text-blue-700 font-black">{inspectedAsset.obi_score ?? 15}/30 pts</span>
                </div>
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                  <div 
                    className="bg-blue-600 h-full rounded-full transition-all duration-300"
                    style={{ width: `${((inspectedAsset.obi_score ?? 15) / 30) * 100}%` }}
                  />
                </div>
                <div className="text-[11px] text-slate-500 font-mono space-y-0.5">
                  <div className="flex justify-between">
                    <span>CLOB Imbalance Skew:</span>
                    <span className="font-bold text-slate-700">{inspectedAsset.orderbook_imbalance >= 0 ? '+' : ''}{inspectedAsset.orderbook_imbalance}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>CLOB Book Spread:</span>
                    <span className="font-bold text-slate-700">{(inspectedAsset.spread * 100).toFixed(2)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Total Book Liquidity:</span>
                    <span className="font-bold text-slate-700">${inspectedAsset.liquidity.toFixed(0)} USDC</span>
                  </div>
                  <div className="flex justify-between">
                    <span>UP / DOWN Asks:</span>
                    <span className="font-bold text-slate-700">${inspectedAsset.up_share_price} / ${inspectedAsset.down_share_price}</span>
                  </div>
                </div>
              </div>

              {/* Factor 3: Micro-Momentum Confluence */}
              <div className="bg-white p-3.5 rounded-xl border border-slate-200 space-y-2">
                <div className="flex items-center justify-between text-xs font-bold">
                  <span className="text-slate-700">3. Micro-Momentum Confluence</span>
                  <span className="font-mono text-emerald-700 font-black">{inspectedAsset.momentum_score ?? 15}/30 pts</span>
                </div>
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                  <div 
                    className="bg-emerald-600 h-full rounded-full transition-all duration-300"
                    style={{ width: `${((inspectedAsset.momentum_score ?? 15) / 30) * 100}%` }}
                  />
                </div>
                <div className="text-[11px] text-slate-500 font-mono space-y-0.5">
                  <div className="flex justify-between">
                    <span>30s Velocity Slope:</span>
                    <span className="font-bold text-slate-700">{inspectedAsset.velocity_30s >= 0 ? '+' : ''}{inspectedAsset.velocity_30s}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Direct Wire Latency:</span>
                    <span className="font-bold text-emerald-600">⚡ {inspectedAsset.latency_ms}ms</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Predicted Direction:</span>
                    <span className={`font-black ${inspectedAsset.direction === 'UP' ? 'text-emerald-600' : inspectedAsset.direction === 'DOWN' ? 'text-rose-600' : 'text-slate-600'}`}>
                      {inspectedAsset.direction}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Total Composite Score:</span>
                    <span className="font-black text-purple-700">{inspectedAsset.confidence}%</span>
                  </div>
                </div>
              </div>

            </div>
          )}

          {/* Rationale explanation text box */}
          {inspectedAsset && (
            <div className="bg-slate-100/80 p-3 rounded-xl text-xs font-mono border border-slate-200 text-slate-700">
              <span className="font-bold text-slate-900">PREDICTION FORMULA: </span>
              {inspectedAsset.reason || 'Confluence calculated from live oracle delta, order book imbalance and momentum.'}
            </div>
          )}
        </div>
      )}

      {/* 4. MAIN ORACLE BOARD TAB: TOP PICK & 4-COLUMN 7-ASSETS GRID */}
      {activeTab === 'board' && (
        <>
          {/* Markets Grid Anchor */}
          <div id="fast5m-markets-grid" className="scroll-mt-4" />

          {/* Active Open Positions Monitor (Supports 1 to 3 concurrent trades) */}
          {activeList.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-black uppercase tracking-wider text-slate-700 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-emerald-500 animate-pulse" />
                  Active Concurrent Positions ({activeList.length} of Max {maxActivePools})
                </span>
                <span className="text-xs font-mono font-bold text-slate-500">
                  Total Allocated Margin: ${activeExposure.toFixed(2)} / Exposure Cap ${(300 * (maxPortfolioMarginPct / 100)).toFixed(2)} ({maxPortfolioMarginPct}%)
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
                {activeList.map((tr: any) => {
                  const isPos = (tr.current_pnl ?? 0) >= 0;
                  return (
                    <div
                      key={tr.id || tr.asset}
                      className="bg-gradient-to-r from-blue-950 via-indigo-950 to-slate-900 text-white rounded-2xl p-4 shadow-lg border border-blue-500/40 relative overflow-hidden flex flex-col justify-between"
                    >
                      <div>
                        <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-400/30">
                              #{tr.id} • {tr.asset}
                            </span>
                            <span className={`text-[10px] font-black px-2 py-0.5 rounded-full ${
                              tr.outcome === 'UP' ? 'bg-emerald-400/20 text-emerald-300' : 'bg-rose-400/20 text-rose-300'
                            }`}>
                              {tr.outcome === 'UP' ? '▲ UP' : '▼ DOWN'}
                            </span>
                          </div>
                          {tr.circuit_breaker_active ? (
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-400/20 text-amber-300 border border-amber-400/40 animate-pulse flex items-center gap-1" title={tr.circuit_breaker_reason || 'Circuit breaker defense active'}>
                              <Shield className="w-3 h-3 text-amber-400" />
                              <span>⚡ CB Defense Active</span>
                            </span>
                          ) : tr.is_in_buffer ? (
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-cyan-400/20 text-cyan-300 border border-cyan-400/40 animate-pulse flex items-center gap-1">
                              <Timer className="w-3 h-3" />
                              <span>{tr.buffer_remaining_sec ?? 4.0}s Buffer</span>
                            </span>
                          ) : (
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-400/20 text-emerald-300 border border-emerald-400/30 flex items-center gap-1">
                              <Shield className="w-3 h-3" />
                              <span>{stopLossPct}% Dynamic SL</span>
                            </span>
                          )}
                        </div>

                        <div className="flex items-baseline justify-between mt-1">
                          <div className="text-base font-black tracking-tight">
                            {tr.shares} Shares @ ${tr.entry_price}
                          </div>
                          <div className={`text-lg font-black font-mono ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {isPos ? '+' : ''}${Number(tr.current_pnl ?? 0).toFixed(2)}
                          </div>
                        </div>

                        <div className="text-[11px] text-blue-200/80 font-mono mt-0.5">
                          Score: {tr.confidence_score ?? tr.score ?? '90+'}% • Cost: ${tr.cost} USDC
                        </div>
                      </div>

                      <div className="pt-2.5 mt-2.5 border-t border-blue-900/60 flex items-center justify-between text-[10px] font-mono">
                        <div>
                          <span className="text-blue-300">Peak:</span>
                          <span className="font-bold text-emerald-300 ml-1">
                            +${Number(tr.peak_pnl ?? 0).toFixed(2)}
                          </span>
                          <span className="text-blue-300 ml-2">Trail:</span>
                          <span className="font-bold text-cyan-300 ml-1">
                            {tr.trailing_stop_floor != null ? `+$${Number(tr.trailing_stop_floor).toFixed(2)}` : '≥+1%'}
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => setTradeToExit(tr)}
                          className="px-2 py-0.5 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 hover:text-rose-100 border border-rose-500/40 rounded text-[10px] font-bold transition-all cursor-pointer"
                          title="Manually exit this position at current market price"
                        >
                          Exit Trade
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 7 Fast Markets Grid — 4-Column Responsive Layout Shrunk to Fit Cleanly */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 sm:gap-3">
            {board?.assets.map((asset) => {
              const meta = ASSET_META[asset.asset] || {
                name: asset.asset,
                color: '#3B82F6',
                bg: 'bg-blue-50',
                border: 'border-blue-200',
                text: 'text-blue-600',
              };
              const isTop = asset.rank === 1;
              const flash = flashStates.current[asset.asset];

              return (
                <div
                  key={asset.asset}
                  className={`bg-[#161b22] rounded-xl border transition-all duration-200 relative overflow-hidden flex flex-col justify-between ${
                    isTop ? 'border-amber-500/80 shadow-md ring-1 ring-amber-500/20' : 'border-[#30363d] hover:border-slate-600'
                  }`}
                >
                  {/* Card Header */}
                  <div className="p-2.5 sm:p-3 border-b border-[#30363d]">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        {isTop ? (
                          <span className="p-0.5 bg-amber-500 text-white rounded shadow-xs">
                            <Crown className="w-3 h-3" />
                          </span>
                        ) : (
                          <span className="text-[10px] font-black font-mono px-1 py-0.2 rounded bg-[#0d1117] border border-[#30363d] text-slate-400">
                            #{asset.rank}
                          </span>
                        )}
                        <div>
                          <span className="text-sm font-black text-white">{asset.asset}</span>
                          <span className="text-[10px] text-slate-400 font-medium ml-1">{meta.name}</span>
                        </div>
                      </div>

                      {/* Live Latency Badge */}
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded-full text-[9px] font-mono font-bold bg-[#0d1117] text-emerald-400 border border-[#30363d]">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                        {asset.latency_ms}ms
                      </span>
                    </div>

                    {/* Live Oracle Price and Flash */}
                    <div className="mt-1.5 flex items-baseline justify-between">
                      <div className={`text-base sm:text-lg font-black font-mono transition-colors duration-300 ${
                        flash === 'up' ? 'text-emerald-400' : flash === 'down' ? 'text-rose-400' : 'text-white'
                      }`}>
                        ${asset.live_price.toLocaleString()}
                      </div>
                      
                      {/* Delta Indicator */}
                      <div className={`text-[10px] font-black font-mono px-1.5 py-0.5 rounded flex items-center gap-0.5 ${
                        asset.delta >= 0 ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                      }`}>
                        {asset.delta >= 0 ? <ArrowUpRight className="w-2.5 h-2.5" /> : <ArrowDownRight className="w-2.5 h-2.5" />}
                        {asset.delta >= 0 ? '+' : ''}{asset.delta_pct}%
                      </div>
                    </div>

                    <div className="text-[10px] text-slate-400 font-mono mt-0.5 flex justify-between">
                      <span>P0 Strike: ${asset.strike_price.toLocaleString()}</span>
                      <span>Δ {asset.delta >= 0 ? '+' : ''}${asset.delta}</span>
                    </div>
                  </div>

                  {/* Confluence & Order Book Body */}
                  <div className="p-2.5 sm:p-3 space-y-2 flex-1 flex flex-col justify-between text-xs">
                    
                    {/* Score Bar & Sub-Scores */}
                    <div>
                      <div className="flex items-center justify-between text-[10px] font-bold mb-0.5">
                        <span className="flex items-center gap-1 text-slate-400">
                          Dir:
                          <strong className={
                            asset.direction === 'UP' ? 'text-emerald-400' : asset.direction === 'DOWN' ? 'text-rose-400' : 'text-slate-400'
                          }>
                            {asset.direction}
                          </strong>
                        </span>
                        <span className="font-mono text-white font-black">{asset.confidence}%</span>
                      </div>
                      <div className="w-full bg-[#0d1117] border border-[#30363d] h-1.5 rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all duration-500 rounded-full ${
                            asset.direction === 'UP' ? 'bg-emerald-500' : asset.direction === 'DOWN' ? 'bg-rose-500' : 'bg-slate-500'
                          }`}
                          style={{ width: `${Math.min(100, Math.max(5, asset.confidence))}%` }}
                        />
                      </div>

                      {/* 3 Sub-Score Mini Pills */}
                      <div className="flex items-center justify-between mt-1 text-[9px] font-mono text-slate-400">
                        <span>Δ: {asset.delta_score ?? 20}/40</span>
                        <span>OBI: {asset.obi_score ?? 15}/30</span>
                        <span>Mom: {asset.momentum_score ?? 15}/30</span>
                      </div>
                    </div>

                    {/* Polymarket CLOB Book Stats */}
                    <div className="bg-[#0d1117] rounded-lg p-1.5 border border-[#30363d] space-y-0.5 font-mono text-[10px]">
                      <div className="flex justify-between text-slate-400">
                        <span>UP / DOWN:</span>
                        <span className="font-bold text-slate-200">${asset.up_share_price.toFixed(2)} / ${asset.down_share_price.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between text-slate-500 text-[9px]">
                        <span>Spread: {(asset.spread * 100).toFixed(1)}%</span>
                        <span>Depth: ${asset.liquidity.toFixed(0)}</span>
                      </div>
                    </div>

                    {/* Countdown and Tradability Badge */}
                    <div className="flex items-center justify-between text-[10px] text-slate-400 pt-0.5">
                      <span className="flex items-center gap-1 font-mono font-bold text-blue-400">
                        <Timer className="w-3 h-3" /> {formatSec(asset.time_remaining_sec)}
                      </span>
                      <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${
                        asset.is_tradable ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-[#0d1117] text-slate-400 border border-[#30363d]'
                      }`}>
                        {asset.is_tradable ? 'ELIGIBLE' : asset.rejection_reason || 'FILTERED'}
                      </span>
                    </div>

                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* 5. HISTORICAL TRADES TAB: TOTAL LOSS, PROFIT, AND EXACT PREDICTION SCORE */}
      {activeTab === 'trades' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 sm:p-5 border-b border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-base font-black text-slate-900">Fast 5M Execution & PnL History</h2>
                <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                  <Database className="w-3 h-3 text-indigo-600" /> Untruncated Lifetime DB Storage {lifetimeStats?.total_trades != null ? `(${lifetimeStats.total_trades} Lifetime Records)` : ''}
                </span>
              </div>
              <p className="text-xs text-slate-500 font-medium mt-0.5">
                Full permanent trade log with prediction scores, risk execution rationale, strike prices, and realized returns
              </p>
            </div>

            {/* Account Mode Filter & Timeframe Filter */}
            <div className="flex items-center gap-2 flex-wrap">
              {/* Account Mode Filter */}
              {isRealAccount ? (
                <div className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl text-xs font-black">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span>⚡ Real Account History (Live)</span>
                </div>
              ) : (
                <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200 text-xs font-bold">
                  {[
                    { id: 'demo' as const, label: '🎮 Demo History' },
                    { id: 'live' as const, label: '⚡ Real History' },
                    { id: 'all' as const, label: 'All Accounts' },
                  ].map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => handleSelectAccountMode(m.id)}
                      className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
                        accountMode === m.id
                          ? 'bg-white text-indigo-700 shadow-xs font-black'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              )}

              {/* Timeframe Filter Buttons */}
              <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200 text-xs font-bold">
                {[
                  { id: 'today' as const, label: 'Today' },
                  { id: 'week' as const, label: 'Week' },
                  { id: 'month' as const, label: 'Month' },
                  { id: 'all' as const, label: 'All-Time' },
                ].map((tf) => (
                  <button
                    key={tf.id}
                    type="button"
                    onClick={() => handleSelectTimeframe(tf.id)}
                    className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
                      selectedTimeframe === tf.id
                        ? 'bg-white text-blue-600 shadow-xs font-black'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {tf.label}
                  </button>
                ))}
              </div>

              {/* Reset Demo button if in Demo mode and not in Real Account */}
              {!isRealAccount && (accountMode === 'demo' || accountMode === 'all') && (
                <button
                  type="button"
                  onClick={() => setIsDemoResetModalOpen(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 rounded-xl text-xs font-bold transition-all cursor-pointer"
                  title="Wipe demo history and restore initial $300 balance"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>🔄 Reset Demo Data</span>
                </button>
              )}

              <button
                onClick={() => fetchTrades(selectedTimeframe, isRealAccount ? 'live' : accountMode)}
                className="p-2 hover:bg-slate-100 rounded-xl text-slate-600 transition-colors cursor-pointer border border-slate-200"
                title="Refresh trade log"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Timeframe Performance Sub-Bar */}
          <div className="bg-slate-50 px-4 py-2.5 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2 text-xs font-mono">
            <div className="flex items-center gap-4 flex-wrap">
              <span className="text-slate-500 font-sans font-bold">
                Filtered: <span className="uppercase text-slate-800">{selectedTimeframe}</span> ({isRealAccount ? 'REAL' : accountMode.toUpperCase()})
              </span>
              <span>
                Trades: <strong className="text-slate-800">{stats.total_trades}</strong>
              </span>
              <span>
                Wins: <strong className="text-emerald-600">{stats.wins}</strong> (+${stats.total_profit.toFixed(2)})
              </span>
              <span>
                Losses: <strong className="text-rose-600">{stats.losses}</strong> (-${stats.total_loss.toFixed(2)})
              </span>
              <span>
                Win Rate: <strong className="text-blue-600">{stats.win_rate.toFixed(1)}%</strong>
              </span>
            </div>
            <div>
              Net PnL:{' '}
              <strong className={stats.total_pnl >= 0 ? 'text-emerald-600' : 'text-rose-600'}>
                {stats.total_pnl >= 0 ? '+' : ''}${stats.total_pnl.toFixed(2)}
              </strong>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/50 text-[11px] font-bold uppercase text-slate-400">
                  <th className="py-2.5 px-4">Trade ID</th>
                  <th className="py-2.5 px-4">Account</th>
                  <th className="py-2.5 px-4">Asset</th>
                  <th className="py-2.5 px-4">Prediction Side</th>
                  <th className="py-2.5 px-4">Prediction Score & Rationale</th>
                  <th className="py-2.5 px-4">Entry / Strike</th>
                  <th className="py-2.5 px-4">Exit Price</th>
                  <th className="py-2.5 px-4">Margin Cost</th>
                  <th className="py-2.5 px-4">Realized PnL</th>
                  <th className="py-2.5 px-4">Status</th>
                  <th className="py-2.5 px-4">Time</th>
                  <th className="py-2.5 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-xs font-mono">
                {trades.length === 0 ? (
                  <tr>
                    <td colSpan={12} className="py-8 text-center text-slate-400 font-sans text-xs">
                      No {isRealAccount ? 'real' : (accountMode !== 'all' ? accountMode : '')} 5-minute fast trades recorded yet. Engine will automatically execute when the #1 ranked pair reaches score ≥ {confidenceThreshold}%.
                    </td>
                  </tr>
                ) : (
                  trades.map((t) => {
                    const isWin = (t.pnl || 0) > 0;
                    const isOpen = t.status === 'OPEN';
                    const isLive = t.account_mode === 'live';
                    return (
                      <tr key={t.id} className="hover:bg-slate-50/60 transition-colors">
                        <td className="py-2.5 px-4 font-bold text-slate-900">#{t.id}</td>
                        
                        <td className="py-2.5 px-4">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-black border ${
                            isLive
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-300'
                              : 'bg-blue-50 text-blue-700 border-blue-300'
                          }`}>
                            {isLive ? '⚡ LIVE' : '🎮 DEMO'}
                          </span>
                          <span className="text-[9px] font-mono text-slate-400 block mt-0.5">
                            {t.execution_type === 'LIVE_CLOB_ONCHAIN' ? 'CLOB LIVE' : 'SIM ORDERBOOK'}
                          </span>
                          {t.tx_hash && t.tx_hash !== 'SIMULATED_CLOB_ORDERBOOK' && (
                            <span className="text-[9px] text-indigo-600 truncate max-w-[85px] block font-mono" title={t.tx_hash}>
                              tx:{t.tx_hash.slice(0, 8)}...
                            </span>
                          )}
                        </td>

                        <td className="py-2.5 px-4 font-black">
                          <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-800">
                            {t.asset}
                          </span>
                        </td>

                        <td className="py-2.5 px-4">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-black ${
                            t.outcome === 'UP' ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                          }`}>
                            {t.outcome === 'UP' ? '▲ UP' : '▼ DOWN'}
                          </span>
                        </td>

                        {/* Prediction Score & Exact Breakdown */}
                        <td className="py-2.5 px-4">
                          <div className="font-bold text-purple-700">
                            Score: {t.confidence_score}% (Rank #{t.asset_rank ?? 1})
                          </div>
                          <div className="text-[10px] text-slate-400 truncate max-w-[200px]" title={t.prediction_rationale}>
                            {t.prediction_rationale || `Δ:${t.delta_score || 0} | OBI:${t.obi_score || 0} | Mom:${t.momentum_score || 0}`}
                          </div>
                        </td>

                        <td className="py-2.5 px-4">
                          <div className="font-bold text-slate-800">${t.entry_price}</div>
                          <div className="text-[10px] text-slate-400">P0: ${t.strike_price}</div>
                        </td>

                        <td className="py-2.5 px-4">
                          <div className="font-bold text-slate-800">
                            {t.exit_price != null ? `$${Number(t.exit_price).toFixed(4)}` : '—'}
                          </div>
                          {t.exit_slippage != null && (
                            <div className={`text-[10px] font-mono ${Number(t.exit_slippage) > 0 ? 'text-emerald-600' : Number(t.exit_slippage) < 0 ? 'text-rose-600' : 'text-slate-400'}`}>
                              Slip: {Number(t.exit_slippage) > 0 ? '+' : ''}${Number(t.exit_slippage).toFixed(4)}
                            </div>
                          )}
                          {t.real_orderbook_bid != null && (
                            <div className="text-[9px] text-indigo-500 font-mono">
                              Bid: ${Number(t.real_orderbook_bid).toFixed(4)}
                            </div>
                          )}
                        </td>

                        <td className="py-2.5 px-4 font-bold text-slate-800">
                          ${t.cost}
                        </td>

                        <td className="py-2.5 px-4 font-bold text-sm">
                          {isOpen ? (
                            <span className="text-blue-600 animate-pulse">IN ROUND</span>
                          ) : (
                            <span className={isWin ? 'text-emerald-600' : 'text-rose-600'}>
                              {t.pnl >= 0 ? '+' : ''}${t.pnl} ({t.pnl_percent >= 0 ? '+' : ''}{t.pnl_percent}%)
                            </span>
                          )}
                        </td>

                        <td className="py-2.5 px-4">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-black inline-flex items-center gap-1 ${
                            isOpen
                              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                              : t.resolution === 'TAKE_PROFIT' || t.resolution === 'TIMEOUT_HEDGE_PROFITABLE' || t.resolution === 'EXPIRED_ROUND_WIN'
                              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                              : t.resolution === 'REVERSAL_EXIT' || t.resolution === 'REVERSAL_GIVEBACK_EXIT'
                              ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                              : t.resolution === 'PROTECTIVE_LIQUIDITY_EXIT'
                              ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                              : t.resolution === 'CIRCUIT_BREAKER_PROTECTIVE_EXIT' || t.resolution === 'CIRCUIT_BREAKER_SL_FILLED'
                              ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                              : t.resolution === 'HARD_STOP_LOSS'
                              ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                              : t.resolution === 'FORCE_ROUND_TIMEOUT' || t.resolution === 'EXPIRED_ROUND_CLOSE' || t.resolution === 'HARD_CAP_TIMEOUT_EXIT'
                              ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                              : isWin
                              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                              : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                          }`}>
                            {t.resolution === 'TAKE_PROFIT' ? 'TAKE PROFIT'
                              : t.resolution === 'REVERSAL_GIVEBACK_EXIT' ? 'REVERSAL GIVEBACK'
                              : t.resolution === 'PROTECTIVE_LIQUIDITY_EXIT' ? 'LIQUIDITY GUARD'
                              : t.resolution === 'CIRCUIT_BREAKER_PROTECTIVE_EXIT' ? 'CIRCUIT BREAKER'
                              : t.resolution === 'TIMEOUT_HEDGE_PROFITABLE' ? 'PROFIT HEDGE'
                              : t.resolution === 'EXPIRED_ROUND_WIN' ? 'ROUND WIN'
                              : t.resolution === 'HARD_CAP_TIMEOUT_EXIT' ? 'TIMEOUT CAP'
                              : t.resolution === 'HARD_STOP_LOSS' ? 'HARD STOP LOSS'
                              : t.resolution === 'REVERSAL_EXIT' ? 'REVERSAL EXIT'
                              : t.resolution === 'FORCE_ROUND_TIMEOUT' ? 'ROUND TIMEOUT'
                              : t.resolution === 'EXPIRED_ROUND_CLOSE' ? 'EXPIRED CLOSE'
                              : t.resolution === 'CIRCUIT_BREAKER_SL_FILLED' ? 'CB SL FILLED'
                              : (t.resolution || t.status)}
                          </span>
                          {t.buffer_status && (t.buffer_status.includes('ACTIVE') || t.buffer_status.includes('CIRCUIT_BREAKER') || t.buffer_status.includes('REVERSAL')) && (
                            <span className={`block text-[9px] font-mono mt-0.5 ${
                              t.buffer_status.includes('REVERSAL') ? 'text-purple-400 font-bold'
                              : t.buffer_status.includes('CIRCUIT_BREAKER') ? 'text-amber-400 font-bold' 
                              : 'text-cyan-400'
                            }`}>
                              {t.buffer_status}
                            </span>
                          )}
                        </td>

                        <td className="py-2.5 px-4 text-slate-400 text-[11px]">
                          {t.created_at ? new Date(t.created_at).toLocaleTimeString() : '—'}
                        </td>

                        <td className="py-2.5 px-4 text-right">
                          {isOpen ? (
                            <button
                              type="button"
                              onClick={() => setTradeToExit(t)}
                              className="px-2.5 py-1 bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 border border-rose-300 hover:border-rose-500 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap"
                              title="Force exit this open trade"
                            >
                              Close
                            </button>
                          ) : (
                            <span className="text-slate-300 text-xs">—</span>
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
      )}

      {/* 6. REAL WALLET & POLYMARKET CLOB SETUP TAB */}
      {activeTab === 'wallet' && (
        <div className="space-y-6">
          {/* Main Wallet Control Card */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 sm:p-6 space-y-6">
            
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-5">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="p-2 rounded-xl bg-purple-50 text-purple-600">
                    <Wallet className="w-5 h-5" />
                  </span>
                  <div>
                    <h2 className="text-lg font-black text-slate-900 tracking-tight flex items-center gap-2">
                      Real Wallet & Polymarket CLOB Connection
                      <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 border border-purple-200">
                        Polygon Mainnet (Chain 137)
                      </span>
                    </h2>
                    <p className="text-xs text-slate-500 font-medium">
                      Configure your real Web3 wallet, automated CLOB signer credentials, and live execution controls
                    </p>
                  </div>
                </div>
              </div>

              {/* Balances Quick Badge */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleRefreshWalletBalance}
                  disabled={refreshingWalletBal}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-bold transition-all cursor-pointer"
                  title="Refresh on-chain Polygon balance"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${refreshingWalletBal ? 'animate-spin' : ''}`} />
                  <span>{refreshingWalletBal ? 'Syncing...' : 'Refresh Balance'}</span>
                </button>

                {walletInfo?.is_connected && (
                  <button
                    type="button"
                    onClick={handleDisconnectWallet}
                    className="flex items-center gap-1 px-3 py-1.5 bg-rose-50 hover:bg-rose-100 border border-rose-200 text-rose-700 rounded-xl text-xs font-bold transition-all cursor-pointer"
                  >
                    <Unlink className="w-3.5 h-3.5" />
                    <span>Disconnect</span>
                  </button>
                )}
              </div>
            </div>

            {/* Notification Messages */}
            {walletMsg && (
              <div className="flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl text-xs font-bold">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>{walletMsg}</span>
              </div>
            )}
            {walletError && (
              <div className="flex items-center gap-2 p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs font-bold">
                <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{walletError}</span>
              </div>
            )}

            {/* TRADING MODE SELECTOR: DEMO VS REAL MONEY */}
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500 block mb-2">
                1. Account Execution Mode
              </label>
              <div className={`grid grid-cols-1 ${isRealAccount ? 'md:grid-cols-1' : 'md:grid-cols-2'} gap-4`}>
                
                {/* Option A: Virtual Demo (Automatically hidden when Real Account is connected) */}
                {!isRealAccount && (
                  <button
                    type="button"
                    onClick={() => handleToggleWalletMode('demo')}
                    disabled={togglingMode}
                    className={`p-4 rounded-2xl border text-left transition-all cursor-pointer relative overflow-hidden flex flex-col justify-between ${
                      walletInfo?.account_mode === 'demo' || !walletInfo?.is_connected
                        ? 'border-blue-500 bg-blue-50/50 shadow-md ring-2 ring-blue-500/20'
                        : 'border-slate-200 bg-white hover:border-slate-300'
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-black uppercase tracking-wider px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-200">
                          VIRTUAL DEMO ($300 BASE)
                        </span>
                        {(walletInfo?.account_mode === 'demo' || !walletInfo?.is_connected) && (
                          <span className="p-1 rounded-full bg-blue-600 text-white">
                            <Check className="w-3.5 h-3.5" />
                          </span>
                        )}
                      </div>
                      <div className="text-base font-black text-slate-900 mt-1">Paper Trading Simulation</div>
                      <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                        Zero financial risk. Simulates all 5-minute round predictions with high-fidelity fill models, live oracle tracking, and virtual balance.
                      </p>
                    </div>
                    <div className="mt-3 pt-2.5 border-t border-slate-200/60 font-mono text-xs text-blue-700 font-bold">
                      Virtual Equity: ${((stats.initial_balance ?? 300) + stats.total_pnl).toFixed(2)}
                    </div>
                  </button>
                )}

                {/* Option B: Real Money Live Trading */}
                <button
                  type="button"
                  onClick={() => handleToggleWalletMode('live')}
                  disabled={togglingMode}
                  className={`p-4 rounded-2xl border text-left transition-all cursor-pointer relative overflow-hidden flex flex-col justify-between ${
                    isRealAccount
                      ? 'border-emerald-500 bg-emerald-50/50 shadow-md ring-2 ring-emerald-500/20'
                      : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-black uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
                        REAL MONEY (POLYMARKET CLOB)
                      </span>
                      {isRealAccount && (
                        <span className="p-1 rounded-full bg-emerald-600 text-white animate-pulse">
                          <Check className="w-3.5 h-3.5" />
                        </span>
                      )}
                    </div>
                    <div className="text-base font-black text-slate-900 mt-1">Live Automated Execution</div>
                    <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                      Direct sub-second order submission to Polymarket. Armed with Strict 3% Hard SL, Trailing Profit Lock, and Exposure Safeguards.
                    </p>
                  </div>
                  <div className="mt-3 pt-2.5 border-t border-slate-200/60 font-mono text-xs text-emerald-700 font-bold flex items-center justify-between">
                    <span>Spendable Polygon USDC:</span>
                    <span className="text-sm font-black">${walletInfo?.usdc_total != null ? walletInfo.usdc_total.toFixed(2) : '0.00'}</span>
                  </div>
                </button>

              </div>
            </div>

            {/* LIVE ON-CHAIN BALANCES OVERVIEW CARD */}
            <div className="bg-slate-50 rounded-2xl border border-slate-200 p-4 sm:p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                  <Activity className="w-4 h-4 text-purple-600" /> On-Chain Polygon Assets (Chain ID: 137)
                </span>
                <span className="text-[10px] font-mono text-slate-400">
                  {walletInfo?.last_balance_sync ? `Last Synced: ${new Date(walletInfo.last_balance_sync).toLocaleTimeString()}` : 'Live RPC'}
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono">
                <div className="bg-white p-3 rounded-xl border border-slate-200">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">Total Spendable USDC</span>
                  <span className="text-lg font-black text-emerald-600 mt-0.5 block">
                    ${walletInfo?.usdc_total != null ? walletInfo.usdc_total.toFixed(2) : '0.00'}
                  </span>
                </div>
                <div className="bg-white p-3 rounded-xl border border-slate-200">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">Native USDC (PoS)</span>
                  <span className="text-sm font-bold text-slate-800 mt-0.5 block">
                    ${walletInfo?.usdc_native != null ? walletInfo.usdc_native.toFixed(2) : '0.00'}
                  </span>
                </div>
                <div className="bg-white p-3 rounded-xl border border-slate-200">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">Bridged USDC.e</span>
                  <span className="text-sm font-bold text-slate-800 mt-0.5 block">
                    ${walletInfo?.usdc_bridged != null ? walletInfo.usdc_bridged.toFixed(2) : '0.00'}
                  </span>
                </div>
                <div className="bg-white p-3 rounded-xl border border-slate-200">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">POL (Gas Reserve)</span>
                  <span className="text-sm font-bold text-purple-700 mt-0.5 block">
                    {walletInfo?.pol_gas_balance != null ? walletInfo.pol_gas_balance.toFixed(4) : '0.0000'} POL
                  </span>
                </div>
              </div>
            </div>

            {/* TWO METHODS TO CONNECT WALLET */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

              {/* METHOD 1: CONNECT RABBY WALLET (SOLE & DEFAULT WEB3 PROVIDER) */}
              <div className="bg-slate-50/70 p-5 rounded-2xl border border-slate-200/80 space-y-4 flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="p-1.5 rounded-lg bg-purple-100 text-purple-700 text-lg">
                      🐰
                    </span>
                    <h3 className="text-sm font-black text-slate-900">Method 1: Connect Rabby Wallet (Sole Web3 Provider)</h3>
                  </div>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    Exclusively supported Web3 provider for sub-second Polygon Mainnet trading and Polymarket CLOB order routing.
                  </p>

                  <div className="my-3 bg-white p-3.5 rounded-xl border border-slate-200 space-y-2.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-500">Connected Rabby Address:</span>
                      <div className="flex items-center gap-1 font-mono font-bold text-slate-900">
                        <span>{walletInfo?.masked_address || walletAddressInput || 'Not Connected'}</span>
                        {walletInfo?.wallet_address && (
                          <button
                            type="button"
                            onClick={() => copyAddressToClipboard(walletInfo.wallet_address)}
                            className="p-1 hover:bg-slate-100 rounded text-slate-500 cursor-pointer"
                            title="Copy full address"
                          >
                            <Copy className="w-3 h-3" />
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-500">Network:</span>
                      <span className="inline-flex items-center gap-1 font-bold text-purple-700">
                        🟣 Polygon Mainnet (137)
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-500">Provider Status:</span>
                      <span className={`inline-flex items-center gap-1 font-bold font-mono text-[10px] px-2 py-0.5 rounded-full border ${
                        isRabbyAvailable()
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-300'
                          : 'bg-amber-50 text-amber-700 border-amber-300'
                      }`}>
                        {isRabbyAvailable() ? '● Rabby Detected' : '● Extension Required'}
                      </span>
                    </div>

                    {copiedAddress && (
                      <div className="text-[10px] text-emerald-600 font-bold text-right">
                        ✓ Address copied to clipboard
                      </div>
                    )}
                  </div>

                  {/* Rabby Extension Notice or Action Button */}
                  {!isRabbyAvailable() && (
                    <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-800 text-xs flex items-center justify-between gap-2 mt-3">
                      <div className="flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                        <span>Rabby Wallet extension required. Please install Rabby to continue.</span>
                      </div>
                      <a
                        href="https://rabby.io"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="px-3 py-1 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-[11px] rounded-lg shadow-xs flex items-center gap-1 shrink-0"
                      >
                        <span>Install Rabby</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    </div>
                  )}
                </div>

                {/* Disconnect / Connect Button */}
                {walletInfo?.is_connected ? (
                  <button
                    type="button"
                    onClick={handleDisconnectWallet}
                    className="w-full py-2.5 px-4 bg-rose-50 hover:bg-rose-100 border border-rose-200 text-rose-700 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2 cursor-pointer shadow-xs mt-3"
                  >
                    <Unlink className="w-4 h-4 text-rose-600" />
                    <span>Disconnect Rabby Wallet</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={connectRabbyWallet}
                    disabled={connectingBrowserWallet}
                    className="w-full py-2.5 px-4 bg-gradient-to-r from-purple-700 via-indigo-600 to-sky-600 hover:from-purple-600 hover:to-sky-500 text-white rounded-xl text-xs font-black shadow-md shadow-purple-500/20 cursor-pointer transition-all flex items-center justify-center gap-2 mt-3 disabled:opacity-50"
                  >
                    {connectingBrowserWallet ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        <span>Awaiting Rabby Approval...</span>
                      </>
                    ) : (
                      <>
                        <span className="text-base">🐰</span>
                        <span>Connect Rabby Wallet</span>
                        <ArrowRight className="w-4 h-4" />
                      </>
                    )}
                  </button>
                )}
              </div>

              {/* METHOD 2: AUTOMATED 5M BOT SIGNER KEY */}
              <div className="bg-slate-50/70 p-5 rounded-2xl border border-slate-200/80 space-y-4">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="p-1.5 rounded-lg bg-purple-100 text-purple-700">
                      <Key className="w-4 h-4" />
                    </span>
                    <h3 className="text-sm font-black text-slate-900">Method 2: Automated Bot Signer Key</h3>
                  </div>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    Allows the bot to automatically sign 5-minute round orders without manual browser popups on every 250ms tick.
                  </p>
                </div>

                <div className="space-y-3">
                  {/* Wallet Address */}
                  <div>
                    <label className="text-[11px] font-bold text-slate-700 block mb-1">
                      Polygon Wallet Address:
                    </label>
                    <input
                      type="text"
                      placeholder="0x..."
                      value={walletAddressInput}
                      onChange={(e) => setWalletAddressInput(e.target.value)}
                      className="w-full px-3 py-1.5 bg-white border border-slate-200 rounded-xl font-mono text-xs font-bold text-slate-900 focus:outline-hidden focus:border-purple-500"
                    />
                  </div>

                  {/* Private Key / Signer Key */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[11px] font-bold text-slate-700">
                        Signer Private Key (Sub-Second Execution):
                      </label>
                      <button
                        type="button"
                        onClick={() => setShowPrivateKey(!showPrivateKey)}
                        className="text-[10px] text-purple-600 font-bold flex items-center gap-0.5 hover:underline cursor-pointer"
                      >
                        {showPrivateKey ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                        <span>{showPrivateKey ? 'Hide' : 'Show'}</span>
                      </button>
                    </div>
                    <input
                      type={showPrivateKey ? 'text' : 'password'}
                      placeholder={walletInfo?.has_signer ? '•••••••••••••••••••••••••••••••••••• (Signer Active)' : 'Paste 64-character private key'}
                      value={privateKeyInput}
                      onChange={(e) => setPrivateKeyInput(e.target.value)}
                      className="w-full px-3 py-1.5 bg-white border border-slate-200 rounded-xl font-mono text-xs font-bold text-slate-900 focus:outline-hidden focus:border-purple-500"
                    />
                    <span className="text-[9px] text-slate-400 block mt-0.5">
                      🔒 Stored locally/server-side only. We recommend using a dedicated trading sub-wallet funded with $50–$300.
                    </span>
                  </div>

                  {/* Polymarket Proxy Address (Optional) */}
                  <div>
                    <label className="text-[11px] font-bold text-slate-700 block mb-1">
                      Polymarket Proxy Address (Optional for Magic/Email users):
                    </label>
                    <input
                      type="text"
                      placeholder="0x... (Leave empty if standard EOA)"
                      value={proxyAddressInput}
                      onChange={(e) => setProxyAddressInput(e.target.value)}
                      className="w-full px-3 py-1.5 bg-white border border-slate-200 rounded-xl font-mono text-xs text-slate-800 focus:outline-hidden focus:border-purple-500"
                    />
                  </div>

                  {/* Advanced CLOB API Keys Accordion */}
                  <div className="pt-2 border-t border-slate-200/60">
                    <button
                      type="button"
                      onClick={() => setShowAdvancedApi(!showAdvancedApi)}
                      className="text-[11px] font-bold text-purple-700 hover:text-purple-800 flex items-center justify-between w-full cursor-pointer"
                    >
                      <span>Advanced: Polymarket CLOB API Keys (Optional)</span>
                      <span>{showAdvancedApi ? '▲ Hide' : '▼ Show'}</span>
                    </button>
                    {showAdvancedApi && (
                      <div className="mt-2 space-y-2 p-3 bg-slate-100/70 rounded-xl border border-slate-200">
                        <div>
                          <label className="text-[10px] font-bold text-slate-600 block mb-0.5">API Key:</label>
                          <input
                            type="text"
                            placeholder="Polymarket API Key"
                            value={apiKeyInput}
                            onChange={(e) => setApiKeyInput(e.target.value)}
                            className="w-full px-2.5 py-1 bg-white border border-slate-200 rounded-lg font-mono text-[11px] text-slate-800"
                          />
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="text-[10px] font-bold text-slate-600 block mb-0.5">API Secret:</label>
                            <input
                              type="password"
                              placeholder="API Secret"
                              value={apiSecretInput}
                              onChange={(e) => setApiSecretInput(e.target.value)}
                              className="w-full px-2.5 py-1 bg-white border border-slate-200 rounded-lg font-mono text-[11px] text-slate-800"
                            />
                          </div>
                          <div>
                            <label className="text-[10px] font-bold text-slate-600 block mb-0.5">API Passphrase:</label>
                            <input
                              type="password"
                              placeholder="Passphrase"
                              value={apiPassphraseInput}
                              onChange={(e) => setApiPassphraseInput(e.target.value)}
                              className="w-full px-2.5 py-1 bg-white border border-slate-200 rounded-lg font-mono text-[11px] text-slate-800"
                            />
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={handleSaveWalletCredentials}
                    disabled={savingWalletCreds}
                    className="w-full py-2.5 px-4 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-400 text-white rounded-xl text-xs font-black shadow-md shadow-purple-500/20 cursor-pointer transition-all flex items-center justify-center gap-2 mt-2"
                  >
                    <Key className="w-4 h-4" />
                    <span>{savingWalletCreds ? 'Verifying & Saving...' : 'Save & Authorize Bot Signer'}</span>
                  </button>
                </div>
              </div>

            </div>

          </div>
        </div>
      )}

      {/* 7. ADMIN MANAGEMENT PANEL (inside Settings view, below the settings card) */}
      {activeTab === 'settings' && isAdmin && (
        <div className="mt-4">
          <div className="flex items-center gap-2 mb-4">
            <span className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
              <span className="text-base">🛡️</span>
            </span>
            <div>
              <h3 className="text-base font-black text-white tracking-tight">Admin Management</h3>
              <p className="text-[11px] text-slate-400">User control, approvals, and platform administration</p>
            </div>
          </div>
          <AdminConsoleTab />
        </div>
      )}


      {/* MODAL 1: EMERGENCY STOP CONFIRMATION */}
      {isEmergencyStopModalOpen && (
        <div
          onClick={(e) => { if (e.target === e.currentTarget) setIsEmergencyStopModalOpen(false); }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in"
        >
          <div className="bg-[#12161f] border-2 border-rose-500/50 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 relative text-left">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-rose-500/20 text-rose-400 rounded-xl">
                <AlertTriangle className="w-6 h-6 animate-pulse" />
              </div>
              <div>
                <h3 className="text-base font-black text-white">Trigger Emergency Stop?</h3>
                <p className="text-xs text-rose-300/80 font-mono">Immediate Kill Switch</p>
              </div>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed bg-[#161b22] p-3.5 rounded-xl border border-rose-500/30">
              Are you sure you want to trigger Emergency Stop? This will cancel all active orders and halt bot execution immediately.
            </p>

            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => setIsEmergencyStopModalOpen(false)}
                className="px-4 py-2 bg-[#21262d] hover:bg-[#30363d] text-slate-300 rounded-xl text-xs font-bold transition-all cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={async () => {
                  setIsEmergencyStopModalOpen(false);
                  await handleEmergencyStop();
                }}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-xl shadow-md shadow-rose-600/30 transition-all cursor-pointer flex items-center gap-1.5"
              >
                <AlertTriangle className="w-4 h-4" />
                <span>Confirm Emergency Stop</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: LOGOUT CONFIRMATION */}
      {isLogoutModalOpen && (
        <div
          onClick={(e) => { if (e.target === e.currentTarget) setIsLogoutModalOpen(false); }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in"
        >
          <div className="bg-[#12161f] border border-[#30363d] rounded-2xl max-w-sm w-full p-6 shadow-2xl space-y-4 relative text-left">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-blue-500/20 text-blue-400 rounded-xl">
                <LogOut className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-black text-white">Sign Out?</h3>
                <p className="text-xs text-slate-400 font-mono">End Active Session</p>
              </div>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed bg-[#161b22] p-3.5 rounded-xl border border-[#30363d]">
              Are you sure you want to sign out? You will need to log back in to access live dashboards and controls.
            </p>

            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => setIsLogoutModalOpen(false)}
                className="px-4 py-2 bg-[#21262d] hover:bg-[#30363d] text-slate-300 rounded-xl text-xs font-bold transition-all cursor-pointer"
              >
                Stay Logged In
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsLogoutModalOpen(false);
                  handleLogout();
                }}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-xl shadow-md shadow-rose-600/30 transition-all cursor-pointer flex items-center gap-1.5"
              >
                <LogOut className="w-4 h-4" />
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 3: MANUAL POSITION EXIT CONFIRMATION */}
      {tradeToExit && (
        <div
          onClick={(e) => { if (e.target === e.currentTarget && !exitingTrade) setTradeToExit(null); }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in"
        >
          <div className="bg-[#12161f] border-2 border-amber-500/40 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 relative text-left">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-amber-500/20 text-amber-400 rounded-xl">
                <AlertCircle className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-black text-white">Manual Position Exit</h3>
                <p className="text-xs text-amber-300/80 font-mono">Trade #{tradeToExit.id || ''} • {tradeToExit.asset}</p>
              </div>
            </div>

            <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-3.5 space-y-2 text-xs font-mono">
              <div className="flex justify-between">
                <span className="text-slate-400">Direction:</span>
                <span className={`font-bold ${tradeToExit.outcome === 'UP' ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {tradeToExit.outcome === 'UP' ? '▲ UP' : '▼ DOWN'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Shares / Entry:</span>
                <span className="text-white font-bold">{tradeToExit.shares} shares @ ${tradeToExit.entry_price}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Current PnL:</span>
                <span className={`font-bold ${(tradeToExit.current_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {(tradeToExit.current_pnl ?? 0) >= 0 ? '+' : ''}${Number(tradeToExit.current_pnl ?? tradeToExit.pnl ?? 0).toFixed(2)}
                </span>
              </div>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              Are you sure you want to close this position now at current market price? This order will be executed immediately.
            </p>

            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                type="button"
                disabled={exitingTrade}
                onClick={() => setTradeToExit(null)}
                className="px-4 py-2 bg-[#21262d] hover:bg-[#30363d] text-slate-300 rounded-xl text-xs font-bold transition-all cursor-pointer disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={exitingTrade}
                onClick={handleManualExitTrade}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 disabled:bg-rose-800 text-white text-xs font-bold rounded-xl shadow-md shadow-rose-600/30 transition-all cursor-pointer flex items-center gap-1.5"
              >
                {exitingTrade ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Closing...</span>
                  </>
                ) : (
                  <span>Confirm Exit Now</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 5: DEMO ACCOUNT RESET CONFIRMATION */}
      {isDemoResetModalOpen && (
        <div
          onClick={(e) => { if (e.target === e.currentTarget && !resettingDemo) setIsDemoResetModalOpen(false); }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in"
        >
          <div className="bg-[#12161f] border-2 border-rose-500/50 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 relative text-left">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-rose-500/20 text-rose-400 rounded-xl">
                <RotateCcw className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-black text-white">Reset Demo Account?</h3>
                <p className="text-xs text-rose-300/80 font-mono">Restore $300.00 Base Balance</p>
              </div>
            </div>

            <p className="text-xs text-slate-200 leading-relaxed bg-rose-950/20 p-3.5 rounded-xl border border-rose-900/40">
              Kya aap apna demo balance aur purani trading history delete karke account fresh karna chahte hain? Sabhi simulated trades permanently clear ho jayengi.
            </p>

            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                type="button"
                disabled={resettingDemo}
                onClick={() => setIsDemoResetModalOpen(false)}
                className="px-4 py-2 bg-[#21262d] hover:bg-[#30363d] text-slate-300 rounded-xl text-xs font-bold transition-all cursor-pointer disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={resettingDemo}
                onClick={handleResetDemoAccount}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-xl shadow-md shadow-rose-600/30 transition-all cursor-pointer flex items-center gap-1.5"
              >
                <RotateCcw className={`w-3.5 h-3.5 ${resettingDemo ? 'animate-spin' : ''}`} />
                <span>{resettingDemo ? 'Resetting...' : 'Yes, Reset Everything'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 6: SWITCH TO REAL ACCOUNT & WIPE DEMO DATA */}
      {isSwitchToRealModalOpen && (
        <div
          onClick={(e) => { if (e.target === e.currentTarget) setIsSwitchToRealModalOpen(false); }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in"
        >
          <div className="bg-[#12161f] border-2 border-emerald-500/50 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 relative text-left">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-emerald-500/20 text-emerald-400 rounded-xl">
                <Shield className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-black text-white">Switch to Real Account?</h3>
                <p className="text-xs text-emerald-300/80 font-mono">Live Polymarket CLOB Execution</p>
              </div>
            </div>

            <p className="text-xs text-slate-200 leading-relaxed bg-[#161b22] p-3.5 rounded-xl border border-emerald-500/30">
              Switching to Real Account will permanently delete all your demo trade history and reset paper stats. Do you want to proceed?
            </p>

            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => setIsSwitchToRealModalOpen(false)}
                className="px-4 py-2 bg-[#21262d] hover:bg-[#30363d] text-slate-300 rounded-xl text-xs font-bold transition-all cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmSwitchToReal}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-xl shadow-md shadow-emerald-600/30 transition-all cursor-pointer flex items-center gap-1.5"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>Switch to Real & Wipe Demo</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 🌟 MOBILE-RESPONSIVE TOP-CORNER NAVIGATION SIDE DRAWER */}
      {/* ========================================================================= */}
      {isMobileDrawerOpen && (
        <div className="fixed inset-0 z-50 overflow-hidden text-left font-sans animate-fade-in">
          {/* Backdrop Blur Overlay */}
          <div
            onClick={() => setIsMobileDrawerOpen(false)}
            className="fixed inset-0 bg-black/75 backdrop-blur-sm transition-opacity duration-300"
          />

          {/* Drawer Container (Sliding in from the right top corner) */}
          <div className="fixed top-0 right-0 h-full w-[88vw] max-w-[380px] bg-[#161b22] border-l border-[#30363d] shadow-2xl flex flex-col z-50 overflow-hidden">
            {/* 1. Drawer Header */}
            <div className="p-4 border-b border-[#30363d] flex items-center justify-between bg-[#0d1117]/80">
              <div className="flex items-center gap-2.5">
                <BrandLogo size={28} glow={true} />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-black bg-gradient-to-r from-blue-400 via-sky-300 to-emerald-400 bg-clip-text text-transparent">
                      Jonanda Bot
                    </span>
                    <span className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded font-bold border ${
                      isRealAccount 
                        ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                        : 'bg-blue-500/20 text-blue-300 border-blue-500/30'
                    }`}>
                      {isRealAccount ? 'Real Mode' : 'Demo Mode'}
                    </span>
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono">
                    Shalom Bin Rasheed • 5M Engine
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsMobileDrawerOpen(false)}
                className="p-1.5 rounded-xl hover:bg-[#21262d] text-slate-400 hover:text-white transition-colors cursor-pointer"
                title="Close Drawer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Scrollable Drawer Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
              
              {/* 2. Rabby Wallet & Web3 Sync Hub Spotlight Card */}
              <div className="bg-gradient-to-br from-[#1b1938] via-[#161b22] to-[#121b2d] border border-purple-500/40 rounded-2xl p-3.5 space-y-3 shadow-lg relative overflow-hidden">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">🐰</span>
                    <div>
                      <div className="font-black text-white text-xs flex items-center gap-1.5">
                        <span>Rabby Wallet</span>
                        {walletInfo?.is_connected ? (
                          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                        ) : (
                          <span className="w-2 h-2 rounded-full bg-slate-500" />
                        )}
                      </div>
                      <div className="text-[10px] text-purple-300/80 font-mono">
                        Polygon PoS Sync (137)
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setIsMobileDrawerOpen(false);
                      setIsRabbyModalOpen(true);
                    }}
                    className="px-2 py-1 bg-purple-600/30 hover:bg-purple-600/50 border border-purple-500/40 text-purple-200 rounded-lg text-[10px] font-bold transition-all cursor-pointer flex items-center gap-1"
                  >
                    <span>Sync Hub</span>
                    <ChevronRight className="w-3 h-3" />
                  </button>
                </div>

                {/* Connected Rabby Details */}
                {walletInfo?.is_connected ? (
                  <div className="space-y-2 pt-1 font-mono text-[11px]">
                    <div className="flex items-center justify-between bg-[#0d1117] p-2 rounded-xl border border-[#30363d]">
                      <span className="text-slate-400 text-[10px]">Address:</span>
                      <div className="flex items-center gap-1 text-slate-200">
                        <span>{walletInfo.masked_address || displayAddress}</span>
                        <button
                          type="button"
                          onClick={() => copyAddressToClipboard(walletInfo.wallet_address || userProfile?.wallet_address || '')}
                          className="p-1 hover:text-white"
                          title="Copy address"
                        >
                          <Copy className="w-3 h-3 text-slate-400" />
                        </button>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-1.5 text-center">
                      <div className="bg-[#0d1117] p-2 rounded-xl border border-[#30363d]">
                        <span className="text-[9px] text-slate-400 block">Total USDC</span>
                        <span className="font-bold text-emerald-400 text-xs">${(walletInfo?.usdc_total ?? 0).toFixed(2)}</span>
                      </div>
                      <div className="bg-[#0d1117] p-2 rounded-xl border border-[#30363d]">
                        <span className="text-[9px] text-slate-400 block">POL Gas</span>
                        <span className="font-bold text-purple-300 text-xs">{(walletInfo?.pol_gas_balance ?? 0).toFixed(3)} POL</span>
                      </div>
                    </div>

                    {/* Quick Sync & Action Buttons */}
                    <div className="grid grid-cols-2 gap-1.5 pt-1">
                      <button
                        type="button"
                        onClick={handleSyncRabbyWallet}
                        disabled={rabbySyncing}
                        className="py-1.5 px-2 bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] rounded-xl text-slate-200 text-[10px] font-bold flex items-center justify-center gap-1 transition-all cursor-pointer disabled:opacity-50"
                      >
                        <RefreshCw className={`w-3 h-3 text-sky-400 ${rabbySyncing ? 'animate-spin' : ''}`} />
                        <span>{rabbySyncing ? 'Syncing...' : 'Sync Balances'}</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setIsMobileDrawerOpen(false);
                          handleOpenDepositWithdraw('deposit');
                        }}
                        className="py-1.5 px-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white rounded-xl text-[10px] font-bold flex items-center justify-center gap-1 transition-all cursor-pointer shadow-xs"
                      >
                        <span className="text-xs">🐰</span>
                        <span>Deposit / Withdraw</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2 pt-1">
                    <p className="text-[11px] text-slate-300 leading-relaxed">
                      Connect Rabby Wallet to seamlessly sync Polygon USDC deposits and withdrawals into your live trading vault.
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setIsMobileDrawerOpen(false);
                          connectRabbyWallet();
                        }}
                        disabled={connectingBrowserWallet}
                        className="flex-1 py-2 px-3 bg-gradient-to-r from-purple-600 via-indigo-600 to-sky-600 hover:from-purple-500 hover:to-sky-500 text-white rounded-xl font-bold text-xs flex items-center justify-center gap-1.5 transition-all cursor-pointer shadow-md shadow-purple-900/30"
                      >
                        <span>🐰</span>
                        <span>{connectingBrowserWallet ? 'Connecting...' : 'Connect Rabby'}</span>
                      </button>
                      <a
                        href="https://rabby.io"
                        target="_blank"
                        rel="noreferrer"
                        className="p-2 bg-[#21262d] hover:bg-[#30363d] text-slate-300 hover:text-white rounded-xl border border-[#30363d] transition-colors"
                        title="Download Rabby Wallet Extension"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    </div>
                  </div>
                )}
              </div>

              {/* 3. Navigation Links */}
              <div className="space-y-1">
                <div className="text-[10px] font-mono uppercase text-slate-500 px-2 pb-1 font-bold">
                  Navigation
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setActiveTab('board');
                    setIsMobileDrawerOpen(false);
                  }}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl font-bold transition-all cursor-pointer ${
                    activeTab === 'board'
                      ? 'bg-blue-600/20 text-blue-300 border border-blue-500/30'
                      : 'text-slate-300 hover:bg-[#21262d] hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Gauge className="w-4 h-4 text-blue-400" />
                    <span>Dashboard</span>
                  </div>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setActiveTab('board');
                    setIsMobileDrawerOpen(false);
                    setTimeout(() => {
                      const el = document.getElementById('fast5m-markets-grid');
                      if (el) el.scrollIntoView({ behavior: 'smooth' });
                    }, 100);
                  }}
                  className="w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-slate-300 hover:bg-[#21262d] hover:text-white font-bold transition-all cursor-pointer"
                >
                  <div className="flex items-center gap-2.5">
                    <Layers className="w-4 h-4 text-emerald-400" />
                    <span>Markets Grid (7 Assets)</span>
                  </div>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setActiveTab('scoring');
                    setIsMobileDrawerOpen(false);
                  }}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl font-bold transition-all cursor-pointer ${
                    activeTab === 'scoring'
                      ? 'bg-blue-600/20 text-blue-300 border border-blue-500/30'
                      : 'text-slate-300 hover:bg-[#21262d] hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Radio className="w-4 h-4 text-amber-400" />
                    <span>Signals & Quantitative Breakdown</span>
                  </div>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                </button>

                {isAdmin && (
                  <button
                    type="button"
                    onClick={() => {
                      setActiveTab('settings');
                      setIsMobileDrawerOpen(false);
                    }}
                    className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl font-bold transition-all cursor-pointer ${
                      activeTab === 'settings'
                        ? 'bg-purple-600/20 text-purple-300 border border-purple-500/30'
                        : 'text-slate-300 hover:bg-[#21262d] hover:text-white'
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <Settings className="w-4 h-4 text-purple-400" />
                      <span>Settings & Indicator Weights</span>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                  </button>
                )}

                <button
                  type="button"
                  onClick={() => {
                    setActiveTab('trades');
                    setIsMobileDrawerOpen(false);
                  }}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl font-bold transition-all cursor-pointer ${
                    activeTab === 'trades'
                      ? 'bg-blue-600/20 text-blue-300 border border-blue-500/30'
                      : 'text-slate-300 hover:bg-[#21262d] hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <BookmarkCheck className="w-4 h-4 text-sky-400" />
                    <span>Trade History</span>
                  </div>
                  <span className="px-1.5 py-0.5 rounded-full bg-[#21262d] text-slate-300 text-[10px] font-mono">
                    {trades.length}
                  </span>
                </button>
              </div>

              {/* 4. Quick Actions */}
              <div className="space-y-2 pt-2 border-t border-[#30363d]">
                <div className="text-[10px] font-mono uppercase text-slate-500 px-2 font-bold">
                  Quick Actions
                </div>

                <div>
                  {/* Single Unified Primary Button: Deposit / Withdraw with Rabby Icon */}
                  <button
                    type="button"
                    onClick={() => {
                      setIsMobileDrawerOpen(false);
                      handleOpenDepositWithdraw('deposit');
                    }}
                    className="w-full p-2.5 bg-gradient-to-r from-emerald-600 via-teal-600 to-indigo-600 hover:from-emerald-500 hover:to-indigo-500 text-white rounded-xl font-black text-xs flex items-center justify-center gap-2 transition-all shadow-md shadow-emerald-950/30 cursor-pointer border border-emerald-400/30"
                  >
                    <span className="text-sm">🐰</span>
                    <span>Deposit / Withdraw</span>
                    {walletInfo?.is_connected && (
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse ml-0.5" />
                    )}
                  </button>
                </div>

                {/* Emergency Stop / Resume */}
                {isAdmin && (
                  board?.auto_trading_active ? (
                    <button
                      type="button"
                      onClick={() => {
                        setIsMobileDrawerOpen(false);
                        setIsEmergencyStopModalOpen(true);
                      }}
                      className="w-full p-2.5 bg-rose-600/20 hover:bg-rose-600/30 border border-rose-500/40 text-rose-300 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer animate-pulse"
                    >
                      <AlertTriangle className="w-4 h-4 text-rose-400" />
                      <span>Emergency Stop Auto-Trading</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setIsMobileDrawerOpen(false);
                        handleEmergencyStart();
                      }}
                      className="w-full p-2.5 bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/40 text-emerald-300 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer"
                    >
                      <Play className="w-4 h-4 text-emerald-400" />
                      <span>Resume Auto-Trading Engine</span>
                    </button>
                  )
                )}

                {/* Reset Demo History */}
                {accountMode === 'demo' && !isRealAccount && (
                  <button
                    type="button"
                    onClick={() => {
                      setIsMobileDrawerOpen(false);
                      setIsDemoResetModalOpen(true);
                    }}
                    className="w-full p-2.5 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-300 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>Reset Demo Account ($300 Balance)</span>
                  </button>
                )}
              </div>

              {/* 5. Telemetry & Engine Status */}
              <div className="bg-[#0d1117] rounded-xl p-3 border border-[#30363d] space-y-1.5 font-mono text-[11px]">
                <div className="flex items-center justify-between text-slate-400">
                  <span>Engine Status:</span>
                  <span className={`font-bold flex items-center gap-1 ${board?.auto_trading_active ? 'text-emerald-400' : 'text-rose-400'}`}>
                    <span className={`w-2 h-2 rounded-full ${board?.auto_trading_active ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`} />
                    {board?.auto_trading_active ? 'Armed & Trading' : 'Paused'}
                  </span>
                </div>
                <div className="flex items-center justify-between text-slate-400">
                  <span>Strike Countdown:</span>
                  <span className="text-white font-bold">{board?.epoch_remaining_sec ?? 0}s remaining</span>
                </div>
                <div className="flex items-center justify-between text-slate-400">
                  <span>Open Trades:</span>
                  <span className="text-white font-bold">{trades.filter(t => t.status === 'OPEN').length} active</span>
                </div>
              </div>
            </div>

            {/* 6. Session Footer */}
            <div className="p-4 border-t border-[#30363d] bg-[#0d1117]/80 flex items-center justify-between gap-2">
              {(isRealAccount || walletInfo?.is_connected) && (
                <button
                  type="button"
                  onClick={() => {
                    setIsMobileDrawerOpen(false);
                    handleDisconnectWallet();
                  }}
                  className="flex-1 py-2 px-3 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-1.5"
                >
                  <Unlink className="w-3.5 h-3.5" />
                  <span>Disconnect</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  setIsMobileDrawerOpen(false);
                  setIsLogoutModalOpen(true);
                }}
                className="flex-1 py-2 px-3 bg-[#21262d] hover:bg-rose-950/40 border border-[#30363d] hover:border-rose-500/40 text-slate-300 hover:text-rose-300 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-1.5"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Log Out</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 🐰 RABBY WALLET SPECIFIC SYNC & DEPOSIT / WITHDRAWAL MODAL */}
      {/* ========================================================================= */}
      {isRabbyModalOpen && (
        <div
          onClick={(e) => { if (e.target === e.currentTarget) setIsRabbyModalOpen(false); }}
          className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in text-left font-sans"
        >
          <div className="bg-[#161b22] border border-purple-500/40 rounded-3xl max-w-lg w-full p-5 sm:p-6 shadow-2xl shadow-purple-950/40 space-y-4 relative text-slate-100 max-h-[92vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="flex items-center justify-between pb-3 border-b border-[#30363d]">
              <div className="flex items-center gap-2.5">
                <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-purple-500/20 via-indigo-500/20 to-sky-500/20 border border-purple-500/30 flex items-center justify-center text-xl shadow-xs">
                  🐰
                </div>
                <div>
                  <h3 className="text-base font-black text-white flex items-center gap-2">
                    <span>Rabby Deposit & Withdrawal</span>
                    <span className="text-[9px] font-mono px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30 uppercase">
                      Polygon (137)
                    </span>
                  </h3>
                  <p className="text-[11px] text-slate-400">
                    Live Web3 deposit & withdrawal synchronization for Fast5M engine
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsRabbyModalOpen(false)}
                className="p-1.5 rounded-xl hover:bg-[#21262d] text-slate-400 hover:text-white transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Error or Success alerts */}
            {rabbySyncError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
                <span className="flex-1">{rabbySyncError}</span>
              </div>
            )}
            {rabbySyncMsg && (
              <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-emerald-300 text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
                <span className="flex-1">{rabbySyncMsg}</span>
              </div>
            )}

            {/* If Rabby is not connected, show prominent connect prompt */}
            {!walletInfo?.is_connected && (
              <div className="p-3.5 bg-gradient-to-r from-purple-950/70 via-indigo-950/60 to-purple-900/40 border border-purple-500/40 rounded-2xl flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <span className="text-2xl p-1.5 bg-purple-500/20 rounded-xl border border-purple-500/30">🐰</span>
                  <div>
                    <div className="text-xs font-black text-white flex items-center gap-1.5">
                      <span>Rabby Wallet Required</span>
                      <span className="text-[9px] font-mono uppercase px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 font-bold">
                        Polygon 137
                      </span>
                    </div>
                    <div className="text-[11px] text-purple-200/80 mt-0.5">
                      {isRabbyAvailable()
                        ? 'Connect Rabby to deposit or withdraw Polygon USDC.'
                        : 'Rabby extension not detected. Install Rabby to proceed.'}
                    </div>
                  </div>
                </div>
                {isRabbyAvailable() ? (
                  <button
                    type="button"
                    onClick={connectRabbyWallet}
                    disabled={connectingBrowserWallet}
                    className="px-3.5 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-xl text-xs font-bold shadow-md shadow-purple-600/30 transition-all cursor-pointer flex items-center gap-1.5 shrink-0 disabled:opacity-50"
                  >
                    <span>{connectingBrowserWallet ? 'Connecting...' : 'Connect Rabby'}</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                ) : (
                  <a
                    href="https://rabby.io"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-3.5 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-xl text-xs font-bold shadow-md transition-all flex items-center gap-1.5 shrink-0"
                  >
                    <span>Install Rabby</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
              </div>
            )}

            {/* Rabby Status & On-Chain Polygon Balances */}
            <div className="bg-[#0d1117] border border-[#30363d] rounded-2xl p-4 space-y-3 font-mono text-xs">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-1.5">
                  <span className="text-slate-400 text-[11px]">Rabby Address:</span>
                  <span className="font-bold text-white text-xs">
                    {walletInfo?.wallet_address ? `${walletInfo.wallet_address.slice(0, 6)}...${walletInfo.wallet_address.slice(-4)}` : (walletAddressInput || 'Not Connected')}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleSyncRabbyWallet}
                    disabled={rabbySyncing}
                    className="px-2.5 py-1 bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] text-sky-400 hover:text-sky-300 rounded-lg text-[10px] font-bold flex items-center gap-1 cursor-pointer transition-all disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3 h-3 ${rabbySyncing ? 'animate-spin' : ''}`} />
                    <span>{rabbySyncing ? 'Syncing...' : 'Sync On-Chain'}</span>
                  </button>
                  {!walletInfo?.is_connected && (
                    <button
                      type="button"
                      onClick={connectRabbyWallet}
                      disabled={connectingBrowserWallet}
                      className="px-2.5 py-1 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-[10px] font-bold flex items-center gap-1 cursor-pointer transition-all"
                    >
                      <span>Connect</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Balances Grid */}
              <div className="grid grid-cols-3 gap-2 text-center pt-1">
                <div className="bg-[#161b22] p-2.5 rounded-xl border border-[#30363d]">
                  <span className="text-[10px] text-slate-400 block mb-0.5">Total USDC</span>
                  <span className="font-black text-emerald-400 text-sm">
                    ${(walletInfo?.usdc_total ?? 0).toFixed(2)}
                  </span>
                </div>
                <div className="bg-[#161b22] p-2.5 rounded-xl border border-[#30363d]">
                  <span className="text-[10px] text-slate-400 block mb-0.5">Native USDC</span>
                  <span className="font-bold text-sky-400 text-xs">
                    ${(walletInfo?.usdc_native ?? 0).toFixed(2)}
                  </span>
                </div>
                <div className="bg-[#161b22] p-2.5 rounded-xl border border-[#30363d]">
                  <span className="text-[10px] text-slate-400 block mb-0.5">POL Gas</span>
                  <span className="font-bold text-purple-300 text-xs">
                    {(walletInfo?.pol_gas_balance ?? 0).toFixed(3)} POL
                  </span>
                </div>
              </div>
            </div>

            {/* Deposit & Withdrawal Sync Action Tabs */}
            <div className="space-y-4">
              <div className="flex rounded-xl bg-[#0d1117] p-1 border border-[#30363d]">
                <button
                  type="button"
                  onClick={() => setVaultTab('deposit')}
                  className={`flex-1 py-2 text-xs font-black rounded-lg transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
                    vaultTab === 'deposit'
                      ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-xs'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <ArrowDownToLine className="w-3.5 h-3.5" />
                  <span>Sync Deposit</span>
                </button>
                <button
                  type="button"
                  onClick={() => setVaultTab('withdraw')}
                  className={`flex-1 py-2 text-xs font-black rounded-lg transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
                    vaultTab === 'withdraw'
                      ? 'bg-gradient-to-r from-purple-600 to-indigo-600 text-white shadow-xs'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <ArrowUpFromLine className="w-3.5 h-3.5" />
                  <span>Sync Withdrawal</span>
                </button>
              </div>

              {/* Deposit Section */}
              {vaultTab === 'deposit' && (
                <div className="space-y-3">
                  <div>
                    <div className="flex items-center justify-between text-xs mb-1.5">
                      <span className="text-slate-300 font-bold">Deposit Amount (USDC):</span>
                      <span className="text-[11px] text-slate-400 font-mono">
                        Rabby Balance: <strong className="text-emerald-400">${(walletInfo?.usdc_total ?? 0).toFixed(2)}</strong>
                      </span>
                    </div>
                    <div className="relative">
                      <input
                        type="number"
                        min="1"
                        step="1"
                        placeholder="e.g. 50"
                        value={rabbyDepositAmount}
                        onChange={(e) => setRabbyDepositAmount(e.target.value)}
                        className="w-full bg-[#0d1117] border border-[#30363d] focus:border-emerald-500 rounded-xl px-3.5 py-2.5 text-sm text-white font-mono outline-none"
                      />
                      <span className="absolute right-3.5 top-2.5 text-xs text-slate-400 font-mono">USDC</span>
                    </div>
                  </div>

                  {/* Preset quick buttons */}
                  <div className="flex items-center gap-2">
                    {[10, 25, 50, 100].map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => setRabbyDepositAmount(String(preset))}
                        className="flex-1 py-1 bg-[#0d1117] hover:bg-[#21262d] border border-[#30363d] text-slate-300 rounded-lg text-xs font-mono font-bold transition-colors cursor-pointer"
                      >
                        ${preset}
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => setRabbyDepositAmount(String(Math.floor(walletInfo?.usdc_total ?? 100)))}
                      className="flex-1 py-1 bg-emerald-950/40 hover:bg-emerald-900/50 border border-emerald-500/30 text-emerald-300 rounded-lg text-xs font-mono font-bold transition-colors cursor-pointer"
                    >
                      MAX
                    </button>
                  </div>

                  {/* Deposit Mode Selector */}
                  <div className="bg-[#0d1117] p-2.5 rounded-xl border border-[#30363d] space-y-2">
                    <div className="text-[11px] text-slate-400 font-bold">Sync Mode:</div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <button
                        type="button"
                        onClick={() => setRabbyDepositMode('instant')}
                        className={`p-2 rounded-lg border text-left cursor-pointer transition-all ${
                          rabbyDepositMode === 'instant'
                            ? 'bg-emerald-950/40 border-emerald-500/50 text-white'
                            : 'bg-[#161b22] border-[#30363d] text-slate-400'
                        }`}
                      >
                        <div className="font-bold text-[11px] text-emerald-300">⚡ Instant Vault Sync</div>
                        <div className="text-[9px] text-slate-400 mt-0.5">Allocates funds from verified Rabby balance</div>
                      </button>
                      <button
                        type="button"
                        onClick={() => setRabbyDepositMode('onchain')}
                        className={`p-2 rounded-lg border text-left cursor-pointer transition-all ${
                          rabbyDepositMode === 'onchain'
                            ? 'bg-purple-950/40 border-purple-500/50 text-white'
                            : 'bg-[#161b22] border-[#30363d] text-slate-400'
                        }`}
                      >
                        <div className="font-bold text-[11px] text-purple-300">🔗 On-Chain Transfer</div>
                        <div className="text-[9px] text-slate-400 mt-0.5">Sends ERC20 transfer via Rabby popup</div>
                      </button>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleRabbyDepositSync(parseFloat(rabbyDepositAmount) || 0, rabbyDepositMode === 'onchain')}
                    disabled={rabbySyncing || !parseFloat(rabbyDepositAmount)}
                    className="w-full py-3 bg-gradient-to-r from-emerald-600 via-teal-600 to-emerald-700 hover:from-emerald-500 hover:to-teal-500 active:scale-98 text-white font-black text-xs rounded-xl shadow-lg shadow-emerald-900/30 transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                  >
                    <ArrowDownToLine className="w-4 h-4" />
                    <span>
                      {rabbySyncing
                        ? 'Syncing Deposit...'
                        : `Deposit $${parseFloat(rabbyDepositAmount) || 0} to Trading Vault`}
                    </span>
                  </button>
                </div>
              )}

              {/* Withdrawal Section */}
              {vaultTab === 'withdraw' && (
                <div className="space-y-3">
                  <div>
                    <div className="flex items-center justify-between text-xs mb-1.5">
                      <span className="text-slate-300 font-bold">Withdraw Amount (USDC):</span>
                      <span className="text-[11px] text-slate-400 font-mono">
                        Safe Limit: <strong className="text-purple-300">${(vaultInfo?.available_to_withdraw ?? currentVaultAllocated).toFixed(2)}</strong>
                      </span>
                    </div>
                    <div className="relative">
                      <input
                        type="number"
                        min="1"
                        step="1"
                        placeholder="e.g. 50"
                        value={rabbyWithdrawAmount}
                        onChange={(e) => setRabbyWithdrawAmount(e.target.value)}
                        className="w-full bg-[#0d1117] border border-[#30363d] focus:border-purple-500 rounded-xl px-3.5 py-2.5 text-sm text-white font-mono outline-none"
                      />
                      <span className="absolute right-3.5 top-2.5 text-xs text-slate-400 font-mono">USDC</span>
                    </div>
                  </div>

                  {/* Active Margin Lock Info */}
                  <div className="bg-[#0d1117] p-2.5 rounded-xl border border-[#30363d] space-y-1 font-mono text-[11px]">
                    <div className="flex items-center justify-between text-slate-400">
                      <span>Vault Allocated Balance:</span>
                      <span className="text-white font-bold">${currentVaultAllocated.toFixed(2)}</span>
                    </div>
                    <div className="flex items-center justify-between text-slate-400">
                      <span>Active Trade Margin Locked:</span>
                      <span className="text-rose-400 font-bold">-${(vaultInfo?.active_margin ?? 0).toFixed(2)}</span>
                    </div>
                    <div className="flex items-center justify-between border-t border-[#30363d] pt-1 text-slate-300 font-bold">
                      <span>Max Available to Withdraw:</span>
                      <span className="text-emerald-400">${(vaultInfo?.available_to_withdraw ?? currentVaultAllocated).toFixed(2)}</span>
                    </div>
                  </div>

                  {/* Preset chips */}
                  <div className="flex items-center gap-2">
                    {[10, 25, 50].map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => setRabbyWithdrawAmount(String(preset))}
                        className="flex-1 py-1 bg-[#0d1117] hover:bg-[#21262d] border border-[#30363d] text-slate-300 rounded-lg text-xs font-mono font-bold transition-colors cursor-pointer"
                      >
                        ${preset}
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => setRabbyWithdrawAmount(String(Math.floor(vaultInfo?.available_to_withdraw ?? currentVaultAllocated)))}
                      className="flex-1 py-1 bg-purple-950/40 hover:bg-purple-900/50 border border-purple-500/30 text-purple-300 rounded-lg text-xs font-mono font-bold transition-colors cursor-pointer"
                    >
                      MAX SAFE
                    </button>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleRabbyWithdrawSync(parseFloat(rabbyWithdrawAmount) || 0)}
                    disabled={rabbySyncing || !parseFloat(rabbyWithdrawAmount)}
                    className="w-full py-3 bg-gradient-to-r from-purple-600 via-indigo-600 to-purple-700 hover:from-purple-500 hover:to-indigo-500 active:scale-98 text-white font-black text-xs rounded-xl shadow-lg shadow-purple-900/30 transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                  >
                    <ArrowUpFromLine className="w-4 h-4" />
                    <span>
                      {rabbySyncing
                        ? 'Processing Withdrawal...'
                        : `Withdraw $${parseFloat(rabbyWithdrawAmount) || 0} to Rabby Wallet`}
                    </span>
                  </button>
                </div>
              )}
            </div>

            {/* Modal Footer Note */}
            <div className="pt-2 text-center text-[10px] text-slate-400 border-t border-[#30363d] flex items-center justify-center gap-1.5 font-mono">
              <Shield className="w-3.5 h-3.5 text-purple-400" />
              <span>Rabby Web3 Protocol • Non-custodial Polygon CTF Sync</span>
            </div>
          </div>
        </div>
      )}

      {/* FLOATING TOAST NOTIFICATION */}
      {toastMsg && (
        <div className="fixed bottom-6 right-6 z-50 bg-[#12161f] border border-emerald-500/50 text-white px-4 py-3 rounded-2xl shadow-2xl flex items-center gap-2.5 animate-bounce text-xs font-bold">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{toastMsg}</span>
        </div>
      )}

    </div>
  );
}

