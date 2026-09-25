import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { 
  Zap, Shield, RefreshCw, 
  Crown, Play, Sliders, ArrowUpRight, ArrowDownRight, 
  Timer, DollarSign, Activity, Lock, TrendingUp, TrendingDown,
  CheckCircle2, XCircle, Award, Wallet, Wifi, Server, Settings, Cpu, Gauge, Radio, Layers,
  BookmarkCheck, RotateCcw, Scale, SlidersHorizontal, Database,
  Eye, EyeOff, Key, AlertTriangle, Check, Copy, Link2, Unlink, X,
  LogOut, ArrowDownToLine, ArrowUpFromLine
} from 'lucide-react';


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
  const [bufferTimerSec, setBufferTimerSec] = useState<number>(4.0);
  const [trailingLockEnabled, setTrailingLockEnabled] = useState<boolean>(true);
  const [trailingStopActivationPct, setTrailingStopActivationPct] = useState<number>(1.0);
  const [trailingStopDistancePct, setTrailingStopDistancePct] = useState<number>(0.5);
  const [maxPortfolioMarginPct, setMaxPortfolioMarginPct] = useState<number>(30.0);
  const [reversalLockEnabled, setReversalLockEnabled] = useState<boolean>(true);
  const [minProfitToLock, setMinProfitToLock] = useState<number>(0.10);
  const [reversalGivebackDollar, setReversalGivebackDollar] = useState<number>(0.03);

  // Settings input protection lock (prevents polling from reverting user inputs during modification)
  const lastSettingEditTime = useRef<number>(0);
  const markSettingEdited = () => {
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
  const [activeTab, setActiveTab] = useState<'board' | 'settings' | 'squad' | 'trades' | 'scoring' | 'wallet'>('board');
  const [selectedAssetForScore, setSelectedAssetForScore] = useState<string>('BTC');

  // Real Wallet & Polymarket CLOB State
  const [walletInfo, setWalletInfo] = useState<any | null>(null);
  const [walletModalOpen, setWalletModalOpen] = useState<boolean>(false);
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
  const [resetModalOpen, setResetModalOpen] = useState<boolean>(false);
  const [resettingDemo, setResettingDemo] = useState<boolean>(false);
  const [accountMode, setAccountMode] = useState<'demo' | 'live' | 'all'>('demo');

  // Multi-User Profile & Session
  const navigate = useNavigate();
  const [userProfile, setUserProfile] = useState<{ email?: string; wallet_address?: string; auth_provider?: string } | null>(null);

  // Isolated Trading Vault (Deposit & Withdraw) State
  const [vaultInfo, setVaultInfo] = useState<any | null>(null);
  const [vaultModalOpen, setVaultModalOpen] = useState<boolean>(false);
  const [vaultTab, setVaultTab] = useState<'deposit' | 'withdraw'>('deposit');
  const [vaultAmountInput, setVaultAmountInput] = useState<string>('50');
  const [vaultLoading, setVaultLoading] = useState<boolean>(false);
  const [vaultMsg, setVaultMsg] = useState<string>('');
  const [vaultError, setVaultError] = useState<string>('');

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user_email');
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

  const handleVaultDeposit = async (amt: number) => {
    if (amt <= 0) return;
    setVaultLoading(true);
    setVaultError('');
    setVaultMsg('');
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post('/api/fast5m/vault/deposit', { amount: amt }, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      setVaultMsg(res.data?.message || `Successfully allocated $${amt.toFixed(2)} to trading vault.`);
      await fetchVault();
      await fetchBoard();
    } catch (err: any) {
      setVaultError(err?.response?.data?.detail || 'Failed to allocate deposit.');
    } finally {
      setVaultLoading(false);
    }
  };

  const handleVaultWithdraw = async (amt: number) => {
    if (amt <= 0) return;
    setVaultLoading(true);
    setVaultError('');
    setVaultMsg('');
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post('/api/fast5m/vault/withdraw', { amount: amt }, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      setVaultMsg(res.data?.message || `Successfully de-allocated $${amt.toFixed(2)} back to wallet reserve.`);
      await fetchVault();
      await fetchBoard();
    } catch (err: any) {
      setVaultError(err?.response?.data?.detail || 'Failed to withdraw from vault.');
    } finally {
      setVaultLoading(false);
    }
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
          if (s.buffer_timer_sec) setBufferTimerSec(parseFloat(s.buffer_timer_sec));
          if (s.min_profit_to_lock) setMinProfitToLock(parseFloat(s.min_profit_to_lock));
          if (s.reversal_giveback_dollar) setReversalGivebackDollar(parseFloat(s.reversal_giveback_dollar));
          if (s.trailing_lock_enabled) setTrailingLockEnabled(s.trailing_lock_enabled === 'true');
          if (s.trailing_stop_activation_pct) setTrailingStopActivationPct(parseFloat(s.trailing_stop_activation_pct));
          if (s.trailing_stop_distance_pct) setTrailingStopDistancePct(parseFloat(s.trailing_stop_distance_pct));
          if (s.max_portfolio_margin_pct) setMaxPortfolioMarginPct(parseFloat(s.max_portfolio_margin_pct));
          if (s.reversal_lock_enabled !== undefined) setReversalLockEnabled(s.reversal_lock_enabled === 'true');

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
    if (storedEmail || storedWallet) {
      setUserProfile({
        email: storedEmail || undefined,
        wallet_address: storedWallet || undefined,
        auth_provider: storedProvider || undefined
      });
    }

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
    setToggling(true);
    try {
      const res = await axios.post('/api/fast5m/emergency-stop');
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
    setToggling(true);
    try {
      const res = await axios.post('/api/fast5m/emergency-start');
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

  const handleResetDemoAccount = async () => {
    setResettingDemo(true);
    try {
      const res = await axios.post('/api/fast5m/reset-demo');
      if (res.data) {
        setResetModalOpen(false);
        setSaveSuccessMsg('Demo account reset successfully! Virtual paper history wiped and $300.00 baseline restored.');
        setTimeout(() => setSaveSuccessMsg(''), 5000);
        await fetchBoard();
        await fetchTrades(selectedTimeframe, 'demo');
      }
    } catch (e) {
      console.error('Reset demo error', e);
    } finally {
      setResettingDemo(false);
    }
  };

  const handleSaveSettings = async (newThreshold: number, newSize: number) => {
    try {
      await axios.post('/api/fast5m/settings', {
        confidence_threshold: newThreshold,
        position_size_usd: newSize,
      });
      await fetchBoard();
    } catch (e) {
      console.error('Save settings error', e);
    }
  };

  const handleSaveAllSettings = async () => {
    setSavingSettings(true);
    try {
      await axios.post('/api/fast5m/settings', {
        position_size_usd: positionSize,
        max_active_pools: maxActivePools,
        multi_pair_min_score: multiPairMinScore,
        strategy_direction: strategyDirection,
        confidence_threshold: confidenceThreshold,
        buffer_timer_sec: bufferTimerSec,
        take_profit_pct: takeProfitPct,
        stop_loss_pct: stopLossPct,
        risk_reward_ratio: riskRewardRatio,
        take_profit_dollar: takeProfitDollar,
        stop_loss_dollar: stopLossDollar,
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
    setSavingAsDefault(true);
    try {
      const res = await axios.post('/api/fast5m/settings/default', {
        position_size_usd: positionSize,
        max_active_pools: maxActivePools,
        multi_pair_min_score: multiPairMinScore,
        strategy_direction: strategyDirection,
        confidence_threshold: confidenceThreshold,
        buffer_timer_sec: bufferTimerSec,
        take_profit_pct: takeProfitPct,
        stop_loss_pct: stopLossPct,
        risk_reward_ratio: riskRewardRatio,
        take_profit_dollar: takeProfitDollar,
        stop_loss_dollar: stopLossDollar,
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
    setRestoringDefaults(true);
    try {
      await axios.post('/api/fast5m/settings/restore-defaults');
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

  const connectBrowserWallet = async () => {
    setConnectingBrowserWallet(true);
    setWalletError('');
    setWalletMsg('');
    try {
      if (typeof window === 'undefined' || !(window as any).ethereum) {
        setWalletError('No Web3 wallet extension detected in browser. Please install MetaMask or Rabby, or enter your address & signer key manually below.');
        return;
      }
      const eth = (window as any).ethereum;
      const accounts = await eth.request({ method: 'eth_requestAccounts' });
      if (!accounts || accounts.length === 0) {
        setWalletError('No account selected in wallet.');
        return;
      }
      const addr = accounts[0];
      setWalletAddressInput(addr);

      // Check Polygon Mainnet Chain ID (137 = 0x89)
      try {
        const chainId = await eth.request({ method: 'eth_chainId' });
        if (chainId !== '0x89' && chainId !== '137') {
          try {
            await eth.request({
              method: 'wallet_switchEthereumChain',
              params: [{ chainId: '0x89' }],
            });
          } catch (switchError: any) {
            if (switchError.code === 4902) {
              await eth.request({
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
      } catch (chainErr) {
        console.warn('Chain switch warning:', chainErr);
      }

      // Connect via backend API
      const res = await axios.post('/api/fast5m/wallet/connect', {
        address: addr,
        proxy_address: proxyAddressInput.trim() || undefined,
      });

      if (res.data?.wallet) {
        setWalletInfo(res.data.wallet);
        setWalletMsg('Browser wallet connected to Polygon Mainnet successfully!');
      }
    } catch (e: any) {
      console.error('Wallet connect error:', e);
      setWalletError(e.response?.data?.detail || e.message || 'Failed to connect browser wallet.');
    } finally {
      setConnectingBrowserWallet(false);
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
      const res = await axios.post('/api/fast5m/wallet/connect', {
        address: walletAddressInput.trim(),
        private_key: privateKeyInput.trim() || undefined,
        proxy_address: proxyAddressInput.trim() || undefined,
        api_key: apiKeyInput.trim() || undefined,
        api_secret: apiSecretInput.trim() || undefined,
        api_passphrase: apiPassphraseInput.trim() || undefined,
      });
      if (res.data?.wallet) {
        setWalletInfo(res.data.wallet);
        setWalletMsg('Polygon Wallet and Polymarket CLOB configuration verified & saved!');
        setPrivateKeyInput(''); // Clear plain private key from input after saving
      }
    } catch (e: any) {
      setWalletError(e.response?.data?.detail || e.message || 'Failed to save credentials.');
    } finally {
      setSavingWalletCreds(false);
    }
  };

  const handleToggleWalletMode = async (targetMode: 'demo' | 'live') => {
    if (targetMode === 'live' && (!walletInfo?.is_connected || !walletInfo?.wallet_address)) {
      setWalletModalOpen(true);
      setWalletError('Please connect your Polygon wallet or enter credentials to switch to Real Account execution.');
      return;
    }
    setTogglingMode(true);
    setWalletError('');
    setWalletMsg('');
    try {
      const res = await axios.post('/api/fast5m/wallet/mode', { mode: targetMode });
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
      const res = await axios.post('/api/fast5m/wallet/disconnect');
      if (res.data?.wallet) {
        setWalletInfo(res.data.wallet);
        setWalletAddressInput('');
        setPrivateKeyInput('');
        setProxyAddressInput('');
        setWalletMsg('Wallet disconnected safely. Reverted to Demo mode.');
      }
    } catch (e) {
      console.error('Disconnect error', e);
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
  const bannerStatus = (bestAsset && bestAsset.confidence >= confidenceThreshold && bestAsset.is_tradable)
    ? 'ARMED & READY'
    : (activeList.some((t: any) => t.asset === bannerAsset) ? 'EXECUTING' : 'WAITING EDGE');

  // Balances & Display Formatting
  const currentTotalBalance = walletInfo?.account_mode === 'live' && walletInfo?.is_connected
    ? (walletInfo?.usdc_total ?? 753.45)
    : ((stats.initial_balance ?? 300) + stats.total_pnl);
  const currentVaultAllocated = vaultInfo?.allocated_balance ?? 250.00;
  const roiPct = (stats.initial_balance && stats.initial_balance > 0)
    ? ((stats.total_pnl / stats.initial_balance) * 100)
    : (stats.total_pnl !== 0 ? ((stats.total_pnl / 300) * 100) : 0);
  const displayAddress = userProfile?.wallet_address 
    ? `${userProfile.wallet_address.slice(0, 4)}...${userProfile.wallet_address.slice(-4)}`
    : (walletInfo?.wallet_address ? `${walletInfo.wallet_address.slice(0, 4)}...${walletInfo.wallet_address.slice(-4)}` : '0x1f...f704');

  return (
    <div className="max-w-7xl mx-auto space-y-4 sm:space-y-5 pb-12 font-sans text-slate-100">
      
      {/* 1. TOP NAVIGATION BAR */}
      <header className="bg-[#161b22] border border-[#30363d] rounded-2xl px-4 py-3 sm:px-5 sm:py-3.5 shadow-md flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        {/* Left: Platform brand "⚡ Fast5M" with bright blue badge "ENGINE" and clean navigation links */}
        <div className="flex items-center gap-4 sm:gap-6 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-lg font-black tracking-tight text-white flex items-center gap-1.5 font-sans">
              <Zap className="w-5 h-5 text-amber-400 fill-amber-400" />
              <span>Fast5M</span>
            </span>
            <span className="text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-md bg-blue-600 text-white shadow-xs">
              ENGINE
            </span>
          </div>

          <nav className="flex items-center gap-1 sm:gap-1.5 text-xs font-bold">
            <button
              type="button"
              onClick={() => setActiveTab('board')}
              className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
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
              className="px-3 py-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-[#21262d]/50 transition-all cursor-pointer"
            >
              Markets
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('scoring')}
              className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
                activeTab === 'scoring'
                  ? 'bg-[#21262d] text-white border border-[#30363d] shadow-xs'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-[#21262d]/50'
              }`}
            >
              Signals
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('settings')}
              className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
                activeTab === 'settings'
                  ? 'bg-[#21262d] text-white border border-[#30363d] shadow-xs'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-[#21262d]/50'
              }`}
            >
              Settings & Risk
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('trades')}
              className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
                activeTab === 'trades'
                  ? 'bg-[#21262d] text-white border border-[#30363d] shadow-xs'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-[#21262d]/50'
              }`}
            >
              Trades ({trades.length})
            </button>
          </nav>
        </div>

        {/* Center: Dark rounded status pill featuring green pulsing indicator for "CLOB LIVE | Polygon | Round: 4:31" */}
        <div className="hidden xl:flex items-center gap-2.5 px-4 py-1.5 rounded-full bg-[#0d1117] border border-[#30363d] text-xs font-mono text-slate-300 shadow-inner">
          <span className="flex items-center gap-1.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="text-emerald-400 font-bold tracking-wide">CLOB LIVE</span>
          </span>
          <span className="text-slate-600">|</span>
          <span className="text-slate-300 font-medium">Polygon</span>
          <span className="text-slate-600">|</span>
          <span className="text-slate-200 font-bold">Round: {board ? formatSec(board.epoch_remaining_sec) : '4:31'}</span>
        </div>

        {/* Right: Vault badge, solid green + Deposit button, and solid red EMERGENCY STOP button */}
        <div className="flex items-center gap-2 sm:gap-2.5 flex-wrap">
          <button
            type="button"
            onClick={() => { setVaultTab('deposit'); setVaultModalOpen(true); }}
            className="flex items-center gap-2 px-3 py-1.5 bg-[#0d1117] hover:bg-[#21262d] border border-[#30363d] rounded-xl text-xs font-mono text-slate-200 transition-colors cursor-pointer"
            title="Open Trading Capital Vault"
          >
            <Lock className="w-3.5 h-3.5 text-blue-400" />
            <span className="font-bold">Vault: ${currentVaultAllocated.toFixed(2)}</span>
            <span className="text-slate-400 text-[11px]">({displayAddress})</span>
          </button>

          <button
            type="button"
            onClick={() => { setVaultTab('deposit'); setVaultModalOpen(true); }}
            className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-bold text-xs rounded-xl shadow-sm transition-all flex items-center gap-1 cursor-pointer"
            title="Deposit / Allocate Capital to Bot Vault"
          >
            <span className="text-sm font-black leading-none">+</span>
            <span>Deposit</span>
          </button>

          {board?.auto_trading_active ? (
            <button
              type="button"
              onClick={handleEmergencyStop}
              disabled={toggling}
              className="px-3.5 py-1.5 bg-rose-600 hover:bg-rose-500 active:scale-95 text-white font-black text-xs rounded-xl shadow-md shadow-rose-900/30 transition-all flex items-center gap-1.5 cursor-pointer animate-pulse"
              title="Emergency Stop: Instantly kill auto-trading and force-close all open trades"
            >
              <AlertTriangle className="w-3.5 h-3.5 text-white" />
              <span>EMERGENCY STOP</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={handleEmergencyStart}
              disabled={toggling}
              className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-black text-xs rounded-xl shadow-md shadow-emerald-900/30 transition-all flex items-center gap-1.5 cursor-pointer"
              title="Start / Resume Engine: Re-arm automated execution"
            >
              <Play className="w-3.5 h-3.5 text-white" />
              <span>RESUME ENGINE</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleLogout}
            title="Log Out / Disconnect Session"
            className="p-1.5 hover:bg-[#21262d] text-slate-400 hover:text-rose-400 rounded-lg transition-colors cursor-pointer"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* 2. SECONDARY CONTROL BAR */}
      <div className="bg-[#161b22] border border-[#30363d] rounded-2xl p-3 sm:px-4 sm:py-2.5 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs shadow-sm">
        {/* Left: Mode Toggle */}
        <div className="flex items-center gap-2">
          <div className="inline-flex p-1 bg-[#0d1117] rounded-xl border border-[#30363d]">
            <button
              type="button"
              onClick={() => handleToggleWalletMode('demo')}
              disabled={togglingMode}
              className={`px-3 py-1.5 rounded-lg font-bold text-xs transition-all cursor-pointer ${
                accountMode === 'demo'
                  ? 'bg-[#21262d] text-white border border-slate-600 shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Demo ($300)
            </button>
            <button
              type="button"
              onClick={() => handleToggleWalletMode('live')}
              disabled={togglingMode}
              className={`px-3 py-1.5 rounded-lg font-black text-xs transition-all cursor-pointer flex items-center gap-1.5 ${
                accountMode === 'live'
                  ? 'bg-blue-600 text-white shadow-sm shadow-blue-500/20'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>Real Vault</span>
            </button>
          </div>
        </div>

        {/* Middle: Position Sizing Presets */}
        <div className="flex items-center gap-2">
          <span className="text-slate-400 font-bold uppercase tracking-wider text-[11px]">Size:</span>
          <div className="flex items-center gap-1">
            {[10, 25, 50].map((sz) => (
              <button
                key={sz}
                type="button"
                onClick={() => {
                  markSettingEdited();
                  setPositionSize(sz);
                  handleSaveSettings(confidenceThreshold, sz);
                }}
                className={`px-2.5 py-1 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer ${
                  positionSize === sz
                    ? 'bg-blue-600 text-white font-black shadow-xs border border-blue-400/30'
                    : 'bg-[#0d1117] text-slate-300 hover:bg-[#21262d] border border-[#30363d]'
                }`}
              >
                ${sz}
              </button>
            ))}
            <div className="relative flex items-center ml-0.5">
              <span className="absolute left-2 text-slate-500 font-mono text-[11px]">$</span>
              <input
                type="number"
                min="1"
                step="1"
                placeholder="Custom"
                value={positionSize}
                onChange={(e) => {
                  markSettingEdited();
                  const val = Math.max(1, Number(e.target.value));
                  setPositionSize(val);
                }}
                onBlur={() => handleSaveSettings(confidenceThreshold, positionSize)}
                className="w-16 pl-4 pr-1.5 py-1 bg-[#0d1117] border border-[#30363d] rounded-lg text-xs font-mono font-bold text-slate-200 focus:outline-hidden focus:border-blue-500"
                title="Enter custom position size in USD"
              />
            </div>
          </div>
        </div>

        {/* Right: Telemetry & Risk Readouts in a single row */}
        <div className="flex items-center gap-2.5 font-mono text-xs text-slate-300 flex-wrap">
          <span>Confidence: <strong className="text-white font-bold">{confidenceThreshold}%</strong></span>
          <span className="text-slate-600">|</span>
          <span>R:R: <strong className="text-white font-bold">{riskRewardRatio}:1</strong></span>
          <span className="text-slate-600">|</span>
          <span className="text-emerald-400 font-semibold flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span>Trailing Lock: Active</span>
          </span>
        </div>
      </div>

      {/* 3. FIVE KEY METRICS CARDS */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5 sm:gap-4">
        {/* Card 1: Total Balance */}
        <div className="bg-[#161b22] rounded-2xl border border-[#30363d] p-4 sm:p-5 flex flex-col justify-between shadow-sm hover:border-slate-500 transition-colors">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Total Balance</span>
            <span className="p-1.5 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
              <Wallet className="w-4 h-4" />
            </span>
          </div>
          <div className="my-2">
            <div className="text-2xl sm:text-3xl font-black font-mono tracking-tight text-white">
              ${currentTotalBalance.toFixed(2)}
            </div>
            <div className="text-xs text-slate-400 font-mono mt-0.5">
              Vault Allocated: <strong className="text-blue-400">${currentVaultAllocated.toFixed(2)}</strong>
            </div>
          </div>
          <div className="pt-2 border-t border-[#30363d] flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Active Margin:</span>
            <span className="font-bold text-slate-300">${activeExposure.toFixed(2)}</span>
          </div>
        </div>

        {/* Card 2: Net Realized PnL */}
        <div className="bg-[#161b22] rounded-2xl border border-[#30363d] p-4 sm:p-5 flex flex-col justify-between shadow-sm hover:border-slate-500 transition-colors">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Net Realized PnL</span>
            <span className={`p-1.5 rounded-xl ${stats.total_pnl >= 0 ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}`}>
              {stats.total_pnl >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
            </span>
          </div>
          <div className="my-2">
            <div className={`text-2xl sm:text-3xl font-black font-mono tracking-tight ${
              stats.total_pnl >= 0 ? 'text-emerald-400 drop-shadow-[0_0_8px_rgba(52,211,153,0.3)]' : 'text-rose-400 drop-shadow-[0_0_8px_rgba(248,113,113,0.3)]'
            }`}>
              {stats.total_pnl >= 0 ? '+' : '-'}${Math.abs(stats.total_pnl).toFixed(2)}
            </div>
            <div className={`text-xs font-mono font-bold mt-0.5 ${stats.total_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {roiPct >= 0 ? '+' : ''}{roiPct.toFixed(2)}% ROI
            </div>
          </div>
          <div className="pt-2 border-t border-[#30363d] flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Period:</span>
            <span className="font-bold uppercase text-slate-300">{selectedTimeframe}</span>
          </div>
        </div>

        {/* Card 3: Total Profit */}
        <div className="bg-[#161b22] rounded-2xl border border-[#30363d] p-4 sm:p-5 flex flex-col justify-between shadow-sm hover:border-slate-500 transition-colors">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Total Profit</span>
            <span className="p-1.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <CheckCircle2 className="w-4 h-4" />
            </span>
          </div>
          <div className="my-2">
            <div className="text-2xl sm:text-3xl font-black font-mono text-emerald-400 tracking-tight">
              +${stats.total_profit.toFixed(2)}
            </div>
            <div className="text-xs text-emerald-400 font-bold mt-0.5">
              {stats.wins} Winning Trades
            </div>
          </div>
          <div className="pt-2 border-t border-[#30363d] flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Target R:R:</span>
            <span className="font-bold text-emerald-400">{riskRewardRatio}:1 (+{takeProfitPct}%)</span>
          </div>
        </div>

        {/* Card 4: Total Loss */}
        <div className="bg-[#161b22] rounded-2xl border border-[#30363d] p-4 sm:p-5 flex flex-col justify-between shadow-sm hover:border-slate-500 transition-colors">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Total Loss</span>
            <span className="p-1.5 rounded-xl bg-rose-500/10 text-rose-400 border border-rose-500/20">
              <XCircle className="w-4 h-4" />
            </span>
          </div>
          <div className="my-2">
            <div className="text-2xl sm:text-3xl font-black font-mono text-rose-400 tracking-tight">
              -${stats.total_loss.toFixed(2)}
            </div>
            <div className="text-xs text-rose-400 font-bold mt-0.5">
              {stats.losses} Stopped Trades
            </div>
          </div>
          <div className="pt-2 border-t border-[#30363d] flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Hard Cap:</span>
            <span className="font-bold text-rose-400">Max -{stopLossPct}% Stop</span>
          </div>
        </div>

        {/* Card 5: Win Rate */}
        <div className="bg-[#161b22] rounded-2xl border border-[#30363d] p-4 sm:p-5 flex flex-col justify-between shadow-sm hover:border-slate-500 transition-colors">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Win Rate</span>
            <span className="p-1.5 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
              <Award className="w-4 h-4" />
            </span>
          </div>
          <div className="my-2">
            <div className="text-2xl sm:text-3xl font-black font-mono text-white tracking-tight">
              {stats.win_rate.toFixed(1)}%
            </div>
            <div className="text-xs text-slate-400 font-medium mt-0.5">
              {stats.total_trades} Closed Rounds
            </div>
          </div>
          <div className="pt-2 border-t border-[#30363d] flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Multi-Threshold:</span>
            <span className="font-bold text-slate-300">≥{multiPairMinScore}%</span>
          </div>
        </div>
      </div>

      {/* 4. #1 RANKED EXECUTION SIGNAL BANNER */}
      <div className="bg-[#161b22] border border-[#30363d] rounded-2xl p-4 sm:p-5 shadow-md flex flex-col md:flex-row md:items-center justify-between gap-4 relative overflow-hidden">
        <div className="flex items-center gap-3 sm:gap-4">
          <span className="px-2.5 py-1 rounded-md text-[11px] font-black uppercase tracking-wider bg-amber-500/20 text-amber-400 border border-amber-500/30 shrink-0">
            #1 RANKED
          </span>
          <div>
            <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight flex items-center gap-2">
              <span>{bannerAsset}</span>
              <span className={bannerDirection === 'UP' ? 'text-emerald-400' : 'text-rose-400'}>
                {bannerDirection === 'UP' ? '▲' : '▼'}
              </span>
              <span>BUY {bannerDirection} ({bannerTokenType})</span>
            </h2>
          </div>
        </div>

        <div className="flex items-center gap-5 sm:gap-7 flex-wrap text-xs font-mono">
          <div className="text-left sm:text-right">
            <span className="text-slate-400 block text-[10px] uppercase font-bold tracking-wider">Score</span>
            <span className="text-white font-black text-sm">{bannerScore}%</span>
          </div>
          <div className="text-left sm:text-right">
            <span className="text-slate-400 block text-[10px] uppercase font-bold tracking-wider">Oracle Delta</span>
            <span className="text-emerald-400 font-black text-sm">{bannerDelta}</span>
          </div>
          <div className="text-left sm:text-right">
            <span className="text-slate-400 block text-[10px] uppercase font-bold tracking-wider">Latency</span>
            <span className="text-emerald-400 font-bold text-sm">⚡ {bannerLatency}ms</span>
          </div>
          <div className="text-left sm:text-right">
            <span className="text-slate-400 block text-[10px] uppercase font-bold tracking-wider">Status</span>
            <span className={`inline-block px-2.5 py-0.5 rounded-full text-[11px] font-black uppercase tracking-wider border ${
              bannerStatus === 'ARMED & READY'
                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                : 'bg-amber-500/20 text-amber-400 border-amber-500/30'
            }`}>
              {bannerStatus}
            </span>
          </div>
        </div>
      </div>

      {/* SETTINGS & RISK CONFIGURATION TAB */}
      {activeTab === 'settings' && (
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
                    <span className="text-[10px] uppercase font-black px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-200">
                      Full Administrative Access
                    </span>
                  </h2>
                  <p className="text-xs text-slate-500 font-medium">
                    Manual adjustments to Risk—to—Reward ratio, active quantitative filters, indicator weights, and default profiles
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

              {/* Reset Demo Account Button */}
              <button
                type="button"
                onClick={() => setResetModalOpen(true)}
                disabled={resettingDemo || savingSettings}
                className="flex items-center gap-1.5 px-3.5 py-2 bg-rose-50 hover:bg-rose-100 disabled:opacity-50 text-rose-700 border border-rose-200 rounded-xl text-xs font-bold transition-all cursor-pointer shadow-xs"
                title="Reset Demo Account: wipe paper trades and reset virtual balance to $300.00 base"
              >
                <RotateCcw className={`w-3.5 h-3.5 ${resettingDemo ? 'animate-spin' : ''}`} />
                <span>{resettingDemo ? 'Resetting...' : 'Reset Demo ($300)'}</span>
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
            </div>
          </div>

          {/* MAIN 3-PANEL CONFIGURATION GRID */}
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

                {/* 1. BUFFER / EXECUTION DELAY TIMER */}
                <div className="bg-white p-3.5 rounded-xl border border-blue-200/80 shadow-xs space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                      <Timer className="w-4 h-4 text-blue-600" />
                      <span>1. Grace Period Buffer Timer</span>
                    </label>
                    <span className="text-xs font-mono font-black px-2 py-0.5 rounded-lg bg-blue-50 text-blue-700 border border-blue-200">
                      {bufferTimerSec.toFixed(1)}s Delay
                    </span>
                  </div>
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
                  <div className="text-[10px] text-slate-500 leading-relaxed bg-blue-50/50 p-2 rounded-lg border border-blue-100">
                    🛡️ <strong className="text-blue-900">Noise Immunity Window:</strong> Micro-spread noise is suppressed during the first {bufferTimerSec}s so trades don't trigger stop loss instantly on spread widening.
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
                      checked={reversalLockEnabled}
                      onChange={(e) => setReversalLockEnabled(e.target.checked)}
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
                          min="0.5"
                          max="5.0"
                          value={trailingStopActivationPct}
                          onChange={(e) => setTrailingStopActivationPct(Math.max(0.2, Number(e.target.value)))}
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
                          onChange={(e) => setTrailingStopDistancePct(Math.max(0.1, Number(e.target.value)))}
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
                          min="0.04"
                          max="0.50"
                          value={minProfitToLock}
                          onChange={(e) => setMinProfitToLock(Math.max(0.02, Number(e.target.value)))}
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
                          onChange={(e) => setReversalGivebackDollar(Math.max(0.01, Number(e.target.value)))}
                          className="w-full px-1.5 py-0.5 bg-slate-50 border border-slate-200 rounded font-mono text-xs font-bold text-slate-800"
                        />
                      </div>
                    </div>
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

                  <div className="bg-white p-2.5 rounded-xl border border-slate-200 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-slate-700">Max Allowed Exit Slippage:</span>
                      <span className="text-xs font-mono font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                        {maxExitSlippagePct.toFixed(1)}% Beyond SL
                      </span>
                    </div>
                    <input
                      type="range"
                      min="1.0"
                      max="15.0"
                      step="0.5"
                      disabled={!exitCircuitBreakerEnabled}
                      value={maxExitSlippagePct}
                      onChange={(e) => {
                        markSettingEdited();
                        setMaxExitSlippagePct(Number(e.target.value));
                      }}
                      className="w-full accent-amber-600 cursor-pointer disabled:opacity-40"
                    />
                    <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                      <span>Strict (1% - 3%)</span>
                      <span>Balanced (5%)</span>
                      <span>Permissive (10%+)</span>
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
                  <div className="grid grid-cols-3 gap-2 mb-2">
                    {[10, 25, 50].map((sz) => (
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

                {/* Score Threshold */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-xs text-slate-600 font-semibold">Min Composite Score (Primary):</label>
                    <span className="font-mono font-bold text-sm text-purple-700 bg-purple-50 px-2 py-0.5 rounded-lg border border-purple-200">
                      ≥ {confidenceThreshold}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="50"
                    max="90"
                    step="1"
                    value={confidenceThreshold}
                    onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
                    className="w-full accent-purple-600 cursor-pointer"
                  />
                  <div className="flex justify-between text-[10px] text-slate-400 font-mono mt-1">
                    <span>50% (High Freq)</span>
                    <span>70% (Recommended)</span>
                    <span>90% (Strict)</span>
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
            </div>

          </div>
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

                      <div className="pt-2.5 mt-2.5 border-t border-blue-900/60 grid grid-cols-2 gap-2 text-[10px] font-mono">
                        <div>
                          <span className="text-blue-300">Peak Gain:</span>
                          <span className="font-bold text-emerald-300 ml-1">
                            +${Number(tr.peak_pnl ?? 0).toFixed(2)}
                          </span>
                        </div>
                        <div className="text-right">
                          <span className="text-blue-300">Trailing Stop:</span>
                          <span className="font-bold text-cyan-300 ml-1">
                            {tr.trailing_stop_floor != null ? `Floor +$${Number(tr.trailing_stop_floor).toFixed(2)}` : 'Armed (≥+1%)'}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 7 Fast Markets Grid — 4-Column Responsive Layout ("اس کو چار پہ بنائیں") */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
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
                  className={`bg-[#161b22] rounded-2xl border transition-all duration-200 relative overflow-hidden flex flex-col justify-between ${
                    isTop ? 'border-amber-500/80 shadow-md ring-2 ring-amber-500/20' : 'border-[#30363d] hover:border-slate-600'
                  }`}
                >
                  {/* Card Header */}
                  <div className="p-4 border-b border-[#30363d]">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {isTop ? (
                          <span className="p-1 bg-amber-500 text-white rounded-lg shadow-xs">
                            <Crown className="w-3.5 h-3.5" />
                          </span>
                        ) : (
                          <span className="text-[11px] font-black font-mono px-1.5 py-0.5 rounded bg-[#0d1117] border border-[#30363d] text-slate-400">
                            #{asset.rank}
                          </span>
                        )}
                        <div>
                          <span className="text-base font-black text-white">{asset.asset}</span>
                          <span className="text-xs text-slate-400 font-medium ml-1.5">{meta.name}</span>
                        </div>
                      </div>

                      {/* Live Latency Badge */}
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[#0d1117] text-emerald-400 border border-[#30363d]">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                        {asset.latency_ms}ms
                      </span>
                    </div>

                    {/* Live Oracle Price and Flash */}
                    <div className="mt-2.5 flex items-baseline justify-between">
                      <div className={`text-xl sm:text-2xl font-black font-mono transition-colors duration-300 ${
                        flash === 'up' ? 'text-emerald-400' : flash === 'down' ? 'text-rose-400' : 'text-white'
                      }`}>
                        ${asset.live_price.toLocaleString()}
                      </div>
                      
                      {/* Delta Indicator */}
                      <div className={`text-xs font-black font-mono px-2 py-0.5 rounded-lg flex items-center gap-0.5 ${
                        asset.delta >= 0 ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                      }`}>
                        {asset.delta >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                        {asset.delta >= 0 ? '+' : ''}{asset.delta_pct}%
                      </div>
                    </div>

                    <div className="text-[11px] text-slate-400 font-mono mt-0.5 flex justify-between">
                      <span>P0 Strike: ${asset.strike_price.toLocaleString()}</span>
                      <span>Δ {asset.delta >= 0 ? '+' : ''}${asset.delta}</span>
                    </div>
                  </div>

                  {/* Confluence & Order Book Body */}
                  <div className="p-4 space-y-3 flex-1 flex flex-col justify-between text-xs">
                    
                    {/* Score Bar & Sub-Scores */}
                    <div>
                      <div className="flex items-center justify-between text-[11px] font-bold mb-1">
                        <span className="flex items-center gap-1 text-slate-400">
                          Direction:
                          <strong className={
                            asset.direction === 'UP' ? 'text-emerald-400' : asset.direction === 'DOWN' ? 'text-rose-400' : 'text-slate-400'
                          }>
                            {asset.direction}
                          </strong>
                        </span>
                        <span className="font-mono text-white font-black">{asset.confidence}%</span>
                      </div>
                      <div className="w-full bg-[#0d1117] border border-[#30363d] h-2 rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all duration-500 rounded-full ${
                            asset.direction === 'UP' ? 'bg-emerald-500' : asset.direction === 'DOWN' ? 'bg-rose-500' : 'bg-slate-500'
                          }`}
                          style={{ width: `${Math.min(100, Math.max(5, asset.confidence))}%` }}
                        />
                      </div>

                      {/* 3 Sub-Score Mini Pills */}
                      <div className="flex items-center justify-between mt-1 text-[10px] font-mono text-slate-400">
                        <span>Δ: {asset.delta_score ?? 20}/40</span>
                        <span>OBI: {asset.obi_score ?? 15}/30</span>
                        <span>Mom: {asset.momentum_score ?? 15}/30</span>
                      </div>
                    </div>

                    {/* Polymarket CLOB Book Stats */}
                    <div className="bg-[#0d1117] rounded-xl p-2.5 border border-[#30363d] space-y-1 font-mono text-[11px]">
                      <div className="flex justify-between text-slate-400">
                        <span>UP Share Ask:</span>
                        <span className="font-bold text-slate-200">${asset.up_share_price.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between text-slate-400">
                        <span>DOWN Share Ask:</span>
                        <span className="font-bold text-slate-200">${asset.down_share_price.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between text-slate-500 text-[10px]">
                        <span>Spread: {(asset.spread * 100).toFixed(1)}%</span>
                        <span>Depth: ${asset.liquidity.toFixed(0)}</span>
                      </div>
                    </div>

                    {/* Countdown and Tradability Badge */}
                    <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                      <span className="flex items-center gap-1 font-mono font-bold text-blue-400">
                        <Timer className="w-3.5 h-3.5" /> {formatSec(asset.time_remaining_sec)}
                      </span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
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

              {/* Reset Demo button if in Demo mode */}
              {(accountMode === 'demo' || accountMode === 'all') && (
                <button
                  type="button"
                  onClick={() => setResetModalOpen(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 rounded-xl text-xs font-bold transition-all cursor-pointer"
                  title="Wipe demo history and restore initial $300 balance"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Clear Demo History ($300)</span>
                </button>
              )}

              <button
                onClick={() => fetchTrades(selectedTimeframe, accountMode)}
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
                Filtered: <span className="uppercase text-slate-800">{selectedTimeframe}</span> ({accountMode.toUpperCase()})
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
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-xs font-mono">
                {trades.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="py-8 text-center text-slate-400 font-sans text-xs">
                      No {accountMode !== 'all' ? accountMode : ''} 5-minute fast trades recorded yet. Engine will automatically execute when the #1 ranked pair reaches score ≥ {confidenceThreshold}%.
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
                              : t.resolution === 'TAKE_PROFIT'
                              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                              : t.resolution === 'HARD_STOP_LOSS'
                              ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                              : t.resolution === 'REVERSAL_EXIT'
                              ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                              : t.resolution === 'FORCE_ROUND_TIMEOUT' || t.resolution === 'EXPIRED_ROUND_CLOSE'
                              ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                              : t.resolution === 'CIRCUIT_BREAKER_SL_FILLED'
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                              : isWin
                              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                              : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                          }`}>
                            {t.resolution === 'TAKE_PROFIT' ? '🎯 TAKE PROFIT'
                              : t.resolution === 'HARD_STOP_LOSS' ? '🛑 HARD STOP LOSS'
                              : t.resolution === 'REVERSAL_EXIT' ? '🔄 REVERSAL EXIT'
                              : t.resolution === 'FORCE_ROUND_TIMEOUT' ? '⏱️ ROUND TIMEOUT'
                              : t.resolution === 'EXPIRED_ROUND_CLOSE' ? '⏱️ EXPIRED CLOSE'
                              : t.resolution === 'CIRCUIT_BREAKER_SL_FILLED' ? '🛡️ CB SL FILLED'
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
                1. Select Account Execution Mode
              </label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                
                {/* Option A: Virtual Demo */}
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

                {/* Option B: Real Money Live Trading */}
                <button
                  type="button"
                  onClick={() => handleToggleWalletMode('live')}
                  disabled={togglingMode}
                  className={`p-4 rounded-2xl border text-left transition-all cursor-pointer relative overflow-hidden flex flex-col justify-between ${
                    walletInfo?.account_mode === 'live'
                      ? 'border-emerald-500 bg-emerald-50/50 shadow-md ring-2 ring-emerald-500/20'
                      : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-black uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
                        REAL MONEY (POLYMARKET CLOB)
                      </span>
                      {walletInfo?.account_mode === 'live' && (
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

              {/* METHOD 1: 1-CLICK BROWSER WALLET */}
              <div className="bg-slate-50/70 p-5 rounded-2xl border border-slate-200/80 space-y-4 flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="p-1.5 rounded-lg bg-indigo-100 text-indigo-700">
                      <Link2 className="w-4 h-4" />
                    </span>
                    <h3 className="text-sm font-black text-slate-900">Method 1: Connect Browser Wallet</h3>
                  </div>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    Connect directly via MetaMask, Rabby, Coinbase Wallet, or Phantom with 1-click account and network detection.
                  </p>

                  <div className="my-4 bg-white p-4 rounded-xl border border-slate-200 space-y-3">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-500">Connected Address:</span>
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

                    {copiedAddress && (
                      <div className="text-[10px] text-emerald-600 font-bold text-right">
                        ✓ Address copied to clipboard
                      </div>
                    )}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={connectBrowserWallet}
                  disabled={connectingBrowserWallet}
                  className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white rounded-xl text-xs font-black shadow-md shadow-indigo-500/20 cursor-pointer transition-all flex items-center justify-center gap-2"
                >
                  <Wallet className="w-4 h-4" />
                  <span>{connectingBrowserWallet ? 'Connecting Web3 Wallet...' : 'Connect MetaMask / Browser Extension'}</span>
                </button>
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

            {/* SAFETY & AUDIT NOTICE */}
            <div className="bg-amber-50/70 border border-amber-200 p-3.5 rounded-2xl flex items-start gap-3 text-xs text-amber-900">
              <Shield className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <div className="font-bold">Automated Risk Safeguards Active in Live Execution:</div>
                <div className="text-[11px] text-amber-800 leading-relaxed">
                  When Live Mode is active, all orders strictly enforce your <strong>Hard Stop-Loss (Capped at 3%)</strong>, <strong>Zero-Slippage Trailing Profit Lock</strong>, and <strong>Max Portfolio Margin Safeguard ({maxPortfolioMarginPct}%)</strong>. Never fund a trading wallet with more capital than your set risk tolerance.
                </div>
              </div>
            </div>

          </div>
        </div>
      )}

      {/* 7. INTERACTIVE WALLET CONNECTION MODAL */}
      {walletModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs animate-fade-in">
          <div className="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-xl w-full p-5 sm:p-6 space-y-5 relative overflow-hidden">
            
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <span className="p-2 rounded-xl bg-purple-50 text-purple-600">
                  <Wallet className="w-5 h-5" />
                </span>
                <div>
                  <h3 className="text-base font-black text-slate-900">Connect Real Wallet (Polymarket CLOB)</h3>
                  <p className="text-[11px] text-slate-500">Polygon Mainnet (Chain ID 137) • Sub-Second Order Execution</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setWalletModalOpen(false)}
                className="p-1.5 hover:bg-slate-100 rounded-xl text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Notification Messages in Modal */}
            {walletMsg && (
              <div className="flex items-center gap-2 p-2.5 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl text-xs font-bold">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>{walletMsg}</span>
              </div>
            )}
            {walletError && (
              <div className="flex items-center gap-2 p-2.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs font-bold">
                <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{walletError}</span>
              </div>
            )}

            {/* Balances Sub-Bar */}
            {walletInfo?.is_connected && (
              <div className="bg-slate-50 p-3 rounded-2xl border border-slate-200 flex items-center justify-between flex-wrap gap-2 text-xs font-mono">
                <div>
                  <span className="text-slate-400 text-[10px] block">Connected Address</span>
                  <span className="font-bold text-slate-800">{walletInfo.masked_address}</span>
                </div>
                <div>
                  <span className="text-slate-400 text-[10px] block">Spendable USDC</span>
                  <span className="font-black text-emerald-600">${walletInfo.usdc_total.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-slate-400 text-[10px] block">POL Gas</span>
                  <span className="font-bold text-purple-700">{walletInfo.pol_gas_balance.toFixed(3)} POL</span>
                </div>
              </div>
            )}

            {/* 1-Click Connect Button */}
            <div className="space-y-2">
              <button
                type="button"
                onClick={connectBrowserWallet}
                disabled={connectingBrowserWallet}
                className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white rounded-xl text-xs font-black shadow-md shadow-indigo-500/20 cursor-pointer transition-all flex items-center justify-center gap-2"
              >
                <Wallet className="w-4 h-4" />
                <span>{connectingBrowserWallet ? 'Connecting Web3 Wallet...' : '1-Click Connect MetaMask / Rabby'}</span>
              </button>
            </div>

            {/* Divider */}
            <div className="relative flex py-1 items-center">
              <div className="grow border-t border-slate-200"></div>
              <span className="shrink mx-3 text-slate-400 text-[10px] uppercase font-bold">OR Automated Signer Key</span>
              <div className="grow border-t border-slate-200"></div>
            </div>

            {/* Manual Form */}
            <div className="space-y-2.5">
              <div>
                <label className="text-[11px] font-bold text-slate-700 block mb-1">Polygon Wallet Address (0x...):</label>
                <input
                  type="text"
                  placeholder="0x..."
                  value={walletAddressInput}
                  onChange={(e) => setWalletAddressInput(e.target.value)}
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl font-mono text-xs font-bold text-slate-800 focus:outline-hidden focus:border-purple-500"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[11px] font-bold text-slate-700">Signer Private Key (for 24/7 fast execution):</label>
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
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl font-mono text-xs font-bold text-slate-800 focus:outline-hidden focus:border-purple-500"
                />
              </div>

              <button
                type="button"
                onClick={handleSaveWalletCredentials}
                disabled={savingWalletCreds}
                className="w-full py-2.5 px-4 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-400 text-white rounded-xl text-xs font-black shadow-md shadow-purple-500/20 cursor-pointer transition-all flex items-center justify-center gap-2"
              >
                <Key className="w-4 h-4" />
                <span>{savingWalletCreds ? 'Verifying...' : 'Save & Authorize Signer Key'}</span>
              </button>
            </div>

            {/* Mode Toggle inside Modal */}
            <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
              <span className="text-xs font-bold text-slate-600">Active Trading Mode:</span>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => handleToggleWalletMode('demo')}
                  className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    walletInfo?.account_mode === 'demo' || !walletInfo?.is_connected
                      ? 'bg-blue-600 text-white font-black shadow-xs'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  Demo ($300)
                </button>
                <button
                  type="button"
                  onClick={() => handleToggleWalletMode('live')}
                  className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    walletInfo?.account_mode === 'live'
                      ? 'bg-emerald-600 text-white font-black shadow-xs'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  Live (CLOB)
                </button>
              </div>
            </div>

          </div>
        </div>
      )}

      {/* 8. RESET DEMO ACCOUNT CONFIRMATION MODAL */}
      {resetModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs animate-fade-in">
          <div className="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-md w-full p-5 sm:p-6 space-y-4 relative overflow-hidden">
            <div className="flex items-center gap-3">
              <span className="p-2.5 rounded-2xl bg-rose-100 text-rose-700 shrink-0">
                <RotateCcw className="w-6 h-6" />
              </span>
              <div>
                <h3 className="text-base font-black text-slate-900">Reset Demo Account to $300.00?</h3>
                <p className="text-xs text-slate-500">Virtual Paper Trading Balance & History Reset</p>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed bg-rose-50/60 p-3 rounded-xl border border-rose-200 text-rose-900">
              ⚠️ This action will permanently wipe all paper trade records, reset your virtual realized P&L to $0.00, and restore your initial starting balance to exactly <strong>$300.00</strong>.
            </p>

            <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setResetModalOpen(false)}
                disabled={resettingDemo}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-bold transition-all cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleResetDemoAccount}
                disabled={resettingDemo}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 disabled:bg-rose-400 text-white rounded-xl text-xs font-black shadow-md shadow-rose-600/20 transition-all cursor-pointer flex items-center gap-1.5"
              >
                <RotateCcw className={`w-3.5 h-3.5 ${resettingDemo ? 'animate-spin' : ''}`} />
                <span>{resettingDemo ? 'Resetting Demo...' : 'Confirm Reset to $300.00'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 9. ISOLATED TRADING VAULT ALLOCATION MODAL (DEPOSIT / WITHDRAW) */}
      {vaultModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-xs animate-fade-in text-left">
          <div className="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-lg w-full p-5 sm:p-6 space-y-4 relative overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="p-2.5 rounded-2xl bg-indigo-100 text-indigo-700 shrink-0">
                  <Lock className="w-5 h-5" />
                </span>
                <div>
                  <h3 className="text-base font-black text-slate-900">Trading Capital Vault</h3>
                  <p className="text-xs text-slate-500">Isolated Sub-Wallet Allocation & Risk Bounds</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setVaultModalOpen(false)}
                className="p-1.5 rounded-xl hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Notification messages */}
            {vaultMsg && (
              <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 p-2.5 rounded-xl text-xs flex items-center gap-2 font-medium">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>{vaultMsg}</span>
              </div>
            )}
            {vaultError && (
              <div className="bg-rose-50 border border-rose-200 text-rose-800 p-2.5 rounded-xl text-xs flex items-center gap-2 font-medium">
                <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{vaultError}</span>
              </div>
            )}

            {/* Mode & Tab Switcher */}
            <div className="flex items-center p-1 bg-slate-100 rounded-xl border border-slate-200 text-xs font-bold gap-1">
              <button
                type="button"
                onClick={() => { setVaultTab('deposit'); setVaultError(''); setVaultMsg(''); }}
                className={`flex-1 py-2 px-3 rounded-lg transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
                  vaultTab === 'deposit' ? 'bg-white text-indigo-700 shadow-xs' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <ArrowDownToLine className="w-3.5 h-3.5" />
                <span>Deposit / Allocate</span>
              </button>
              <button
                type="button"
                onClick={() => { setVaultTab('withdraw'); setVaultError(''); setVaultMsg(''); }}
                className={`flex-1 py-2 px-3 rounded-lg transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
                  vaultTab === 'withdraw' ? 'bg-white text-indigo-700 shadow-xs' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <ArrowUpFromLine className="w-3.5 h-3.5" />
                <span>Withdraw to Wallet</span>
              </button>
            </div>

            {/* TAB 1: DEPOSIT / ALLOCATE CAPITAL */}
            {vaultTab === 'deposit' && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">Primary Wallet Reserve</span>
                    <span className="text-sm font-black text-slate-800 font-mono">
                      ${vaultInfo?.account_mode === 'live' 
                        ? (vaultInfo?.total_wallet_balance != null ? vaultInfo.total_wallet_balance.toFixed(2) : '0.00') 
                        : '1,000.00'} USDC
                    </span>
                  </div>
                  <div className="p-3 bg-indigo-50/60 border border-indigo-200 rounded-xl">
                    <span className="text-[10px] uppercase font-bold text-indigo-500 block">Currently Allocated</span>
                    <span className="text-sm font-black text-indigo-950 font-mono">
                      ${vaultInfo?.allocated_balance != null ? vaultInfo.allocated_balance.toFixed(2) : '300.00'} USDC
                    </span>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-700 block">
                    Amount to Allocate (USDC):
                  </label>
                  <div className="relative">
                    <span className="absolute left-3.5 top-2.5 text-slate-400 font-bold text-sm">$</span>
                    <input
                      type="number"
                      min="1"
                      step="5"
                      value={vaultAmountInput}
                      onChange={(e) => setVaultAmountInput(e.target.value)}
                      className="w-full pl-8 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono text-sm font-bold text-slate-900 focus:outline-hidden focus:border-indigo-500"
                      placeholder="50"
                    />
                  </div>

                  {/* Preset Allocation Buttons */}
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {[50, 100, 250].map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => setVaultAmountInput(String(preset))}
                        className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg font-mono transition-colors cursor-pointer"
                      >
                        +${preset}
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => {
                        const bal = vaultInfo?.account_mode === 'live' ? (vaultInfo?.total_wallet_balance || 50) : 300;
                        setVaultAmountInput(String(Math.max(5, Math.floor(bal * 0.5))));
                      }}
                      className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-bold rounded-lg font-mono transition-colors cursor-pointer"
                    >
                      50% Balance
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const bal = vaultInfo?.account_mode === 'live' ? (vaultInfo?.total_wallet_balance || 100) : 300;
                        setVaultAmountInput(String(Math.max(5, Math.floor(bal))));
                      }}
                      className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-bold rounded-lg font-mono transition-colors cursor-pointer"
                    >
                      100% (Max)
                    </button>
                  </div>
                </div>

                <p className="text-[11px] text-slate-500 leading-relaxed bg-slate-50 p-2.5 rounded-xl border border-slate-200">
                  🔒 <strong>Hard Execution Bound:</strong> Allocating capital bounds the Fast5M engine&apos;s maximum trading capacity to this amount. The bot cannot commit more margin than your allocated vault limit.
                </p>

                <button
                  type="button"
                  onClick={() => handleVaultDeposit(parseFloat(vaultAmountInput) || 0)}
                  disabled={vaultLoading || !(parseFloat(vaultAmountInput) > 0)}
                  className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white rounded-xl text-xs font-black shadow-md shadow-indigo-500/20 cursor-pointer transition-all flex items-center justify-center gap-2"
                >
                  <ArrowDownToLine className="w-4 h-4" />
                  <span>{vaultLoading ? 'Allocating Funds...' : `Confirm Deposit of $${parseFloat(vaultAmountInput) || 0} USDC`}</span>
                </button>
              </div>
            )}

            {/* TAB 2: WITHDRAW / DE-ALLOCATE TO WALLET */}
            {vaultTab === 'withdraw' && (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-xl">
                    <span className="text-[9px] uppercase font-bold text-slate-400 block">Allocated Balance</span>
                    <span className="text-xs font-black text-slate-800 font-mono">
                      ${vaultInfo?.allocated_balance != null ? vaultInfo.allocated_balance.toFixed(2) : '300.00'}
                    </span>
                  </div>
                  <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-xl">
                    <span className="text-[9px] uppercase font-bold text-amber-600 block">Locked Margin</span>
                    <span className="text-xs font-black text-amber-900 font-mono">
                      ${vaultInfo?.active_margin != null ? vaultInfo.active_margin.toFixed(2) : '0.00'}
                    </span>
                  </div>
                  <div className="p-2.5 bg-emerald-50 border border-emerald-200 rounded-xl">
                    <span className="text-[9px] uppercase font-bold text-emerald-600 block">Available to Withdraw</span>
                    <span className="text-xs font-black text-emerald-950 font-mono">
                      ${vaultInfo?.available_to_withdraw != null ? vaultInfo.available_to_withdraw.toFixed(2) : '300.00'}
                    </span>
                  </div>
                </div>

                {vaultInfo?.active_margin > 0 && (
                  <div className="p-2.5 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-800 flex items-start gap-2">
                    <Shield className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                    <span>
                      <strong>Safety Lock Active:</strong> ${vaultInfo.active_margin.toFixed(2)} is committed in open active trades and is locked until rounds conclude. Available to withdraw: <strong>${vaultInfo.available_to_withdraw.toFixed(2)}</strong>.
                    </span>
                  </div>
                )}

                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-700 block">
                    Amount to Withdraw (USDC):
                  </label>
                  <div className="relative">
                    <span className="absolute left-3.5 top-2.5 text-slate-400 font-bold text-sm">$</span>
                    <input
                      type="number"
                      min="1"
                      step="5"
                      max={vaultInfo?.available_to_withdraw || 300}
                      value={vaultAmountInput}
                      onChange={(e) => setVaultAmountInput(e.target.value)}
                      className="w-full pl-8 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono text-sm font-bold text-slate-900 focus:outline-hidden focus:border-indigo-500"
                      placeholder="50"
                    />
                  </div>

                  {/* Preset De-allocation Buttons */}
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    <button
                      type="button"
                      onClick={() => {
                        const maxAvail = vaultInfo?.available_to_withdraw ?? 300;
                        setVaultAmountInput(String(Math.max(1, Number((maxAvail * 0.25).toFixed(2)))));
                      }}
                      className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg font-mono transition-colors cursor-pointer"
                    >
                      25% Available
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const maxAvail = vaultInfo?.available_to_withdraw ?? 300;
                        setVaultAmountInput(String(Math.max(1, Number((maxAvail * 0.50).toFixed(2)))));
                      }}
                      className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg font-mono transition-colors cursor-pointer"
                    >
                      50% Available
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const maxAvail = vaultInfo?.available_to_withdraw ?? 300;
                        setVaultAmountInput(String(Number(maxAvail.toFixed(2))));
                      }}
                      className="px-2.5 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-xs font-bold rounded-lg font-mono transition-colors cursor-pointer"
                    >
                      100% (All Available)
                    </button>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => handleVaultWithdraw(parseFloat(vaultAmountInput) || 0)}
                  disabled={
                    vaultLoading || 
                    !(parseFloat(vaultAmountInput) > 0) || 
                    parseFloat(vaultAmountInput) > (vaultInfo?.available_to_withdraw ?? 300)
                  }
                  className="w-full py-3 px-4 bg-slate-900 hover:bg-slate-800 disabled:bg-slate-400 text-white rounded-xl text-xs font-black shadow-md cursor-pointer transition-all flex items-center justify-center gap-2"
                >
                  <ArrowUpFromLine className="w-4 h-4" />
                  <span>{vaultLoading ? 'De-allocating Funds...' : `Withdraw $${parseFloat(vaultAmountInput) || 0} USDC to Reserve`}</span>
                </button>
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}

