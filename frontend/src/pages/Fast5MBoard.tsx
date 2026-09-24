import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { 
  Zap, Shield, RefreshCw, 
  Crown, Play, Pause, Sliders, ArrowUpRight, ArrowDownRight, 
  Timer, DollarSign, Activity, Lock
} from 'lucide-react';

interface AssetData {
  asset: string;
  direction: 'UP' | 'DOWN' | 'NEUTRAL';
  composite_score: number;
  confidence: number;
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

interface BoardState {
  timestamp: number;
  epoch_bucket: number;
  epoch_remaining_sec: number;
  epoch_progress_pct: number;
  assets: AssetData[];
  top_ranked_pair: AssetData | null;
  active_trade: any | null;
  settings: Record<string, any>;
  auto_trading_active: boolean;
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
  const [confidenceThreshold, setConfidenceThreshold] = useState<number>(70);
  const [positionSize, setPositionSize] = useState<number>(10);
  const [toggling, setToggling] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'board' | 'trades'>('board');

  const prevPrices = useRef<Record<string, number>>({});
  const flashStates = useRef<Record<string, 'up' | 'down' | null>>({});

  // Fetch Board and Trades
  const fetchBoard = async () => {
    try {
      const res = await axios.get('/api/fast5m/board');
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
        if (res.data.settings?.confidence_threshold) {
          setConfidenceThreshold(parseFloat(res.data.settings.confidence_threshold));
        }
        if (res.data.settings?.position_size_usd) {
          setPositionSize(parseFloat(res.data.settings.position_size_usd));
        }
      }
    } catch (e) {
      console.debug('Fast5M board poll error', e);
    }
  };

  const fetchTrades = async () => {
    try {
      const res = await axios.get('/api/fast5m/trades?limit=30');
      if (res.data) setTrades(res.data);
    } catch (e) {
      console.debug('Fast5M trades fetch error', e);
    }
  };

  useEffect(() => {
    fetchBoard();
    fetchTrades();
    const interval = setInterval(() => {
      fetchBoard();
    }, 1000); // 1-second real-time poll
    const tradeInterval = setInterval(() => {
      fetchTrades();
    }, 4000);
    return () => {
      clearInterval(interval);
      clearInterval(tradeInterval);
    };
  }, []);

  const handleToggleAuto = async () => {
    setToggling(true);
    try {
      await axios.post('/api/fast5m/toggle');
      await fetchBoard();
    } catch (e) {
      console.error('Toggle error', e);
    } finally {
      setToggling(false);
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

  const formatSec = (sec: number) => {
    const s = Math.max(0, Math.floor(sec));
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${m}:${rem.toString().padStart(2, '0')}`;
  };

  const topPick = board?.top_ranked_pair;

  return (
    <div className="max-w-7xl mx-auto space-y-4 sm:space-y-6 pb-12 font-sans text-slate-800">
      
      {/* Top Banner / Engine Header */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 sm:p-6 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-br from-blue-50/60 via-indigo-50/30 to-transparent rounded-full blur-3xl pointer-events-none" />
        
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 relative z-10">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="p-2 bg-gradient-to-tr from-blue-600 to-indigo-600 text-white rounded-xl shadow-md shadow-blue-500/20">
                <Zap className="w-5 h-5" />
              </span>
              <div>
                <h1 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2">
                  5-Minute Fast Prediction Engine
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-200">
                    7 Assets • Sub-Second Oracles
                  </span>
                </h1>
                <p className="text-xs sm:text-sm text-slate-500 font-medium">
                  Direct Chainlink / Pyth Benchmark streams • Automated Top-Ranked Pair Execution • 1:1 Symmetrical Risk
                </p>
              </div>
            </div>
          </div>

          {/* Engine Controls & Epoch Countdown */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Round Countdown */}
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl">
              <Timer className="w-4 h-4 text-blue-600 animate-spin" style={{ animationDuration: '4s' }} />
              <div className="text-left">
                <div className="text-[10px] uppercase font-bold text-slate-400">Epoch Remaining</div>
                <div className="text-sm font-black font-mono text-slate-800">
                  {board ? formatSec(board.epoch_remaining_sec) : '--:--'}
                </div>
              </div>
            </div>

            {/* Auto Trading Toggle */}
            <button
              onClick={handleToggleAuto}
              disabled={toggling}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-black transition-all shadow-xs ${
                board?.auto_trading_active
                  ? 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-emerald-500/20'
                  : 'bg-amber-500 hover:bg-amber-600 text-white shadow-amber-500/20'
              }`}
            >
              {board?.auto_trading_active ? (
                <>
                  <Pause className="w-3.5 h-3.5" /> AUTO-EXECUTION ACTIVE
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5" /> ENGINE PAUSED
                </>
              )}
            </button>

            {/* Tab switch */}
            <div className="flex items-center p-1 bg-slate-100 rounded-xl border border-slate-200 text-xs font-bold">
              <button
                onClick={() => setActiveTab('board')}
                className={`px-3 py-1 rounded-lg transition-all ${
                  activeTab === 'board' ? 'bg-white text-blue-600 shadow-xs' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Oracle Board
              </button>
              <button
                onClick={() => setActiveTab('trades')}
                className={`px-3 py-1 rounded-lg transition-all ${
                  activeTab === 'trades' ? 'bg-white text-blue-600 shadow-xs' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Trades ({trades.length})
              </button>
            </div>
          </div>
        </div>

        {/* Global Settings Sub-Bar */}
        <div className="mt-4 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-4 text-xs font-medium text-slate-600">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <Sliders className="w-3.5 h-3.5 text-blue-500" />
              <span>Min Confidence Threshold:</span>
              <div className="flex items-center gap-1.5 font-mono font-bold text-slate-900 bg-slate-100 px-2 py-0.5 rounded-lg border border-slate-200">
                <input
                  type="range"
                  min="55"
                  max="90"
                  step="1"
                  value={confidenceThreshold}
                  onChange={(e) => {
                    const val = Number(e.target.value);
                    setConfidenceThreshold(val);
                    handleSaveSettings(val, positionSize);
                  }}
                  className="w-20 sm:w-24 accent-blue-600 cursor-pointer"
                />
                <span>{confidenceThreshold}%</span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <DollarSign className="w-3.5 h-3.5 text-emerald-500" />
              <span>Position Size:</span>
              <div className="flex items-center gap-1">
                {[10, 25, 50].map((sz) => (
                  <button
                    key={sz}
                    onClick={() => {
                      setPositionSize(sz);
                      handleSaveSettings(confidenceThreshold, sz);
                    }}
                    className={`px-2 py-0.5 rounded text-[11px] font-bold font-mono transition-all ${
                      positionSize === sz
                        ? 'bg-blue-600 text-white shadow-xs'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                  >
                    ${sz}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 text-slate-500 text-[11px]">
            <span className="flex items-center gap-1">
              <Shield className="w-3 h-3 text-blue-500" /> Single-Position Risk Lock
            </span>
            <span className="flex items-center gap-1">
              <Lock className="w-3 h-3 text-purple-500" /> 1:1 $1.00 TP / $1.00 SL Symmetry
            </span>
          </div>
        </div>
      </div>

      {activeTab === 'board' ? (
        <>
          {/* Top-Ranked #1 Opportunity Highlight Banner */}
          {topPick && (
            <div className={`rounded-2xl border p-4 sm:p-5 relative overflow-hidden transition-all ${
              topPick.confidence >= confidenceThreshold && topPick.is_tradable
                ? 'bg-gradient-to-r from-amber-500/10 via-emerald-500/10 to-blue-500/10 border-amber-300 shadow-md'
                : 'bg-slate-50 border-slate-200'
            }`}>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-center gap-3 sm:gap-4">
                  <div className="p-3 bg-amber-500 text-white rounded-2xl shadow-md shadow-amber-500/30 flex items-center justify-center">
                    <Crown className="w-7 h-7" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-black tracking-wider uppercase px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 border border-amber-300">
                        #1 RANKED PAIR ACROSS 7 ASSETS
                      </span>
                      <span className="text-xs text-slate-500 font-mono font-bold">
                        {topPick.asset} / USD 5M Round
                      </span>
                    </div>
                    <div className="flex items-baseline gap-2 mt-0.5">
                      <h2 className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight">
                        {topPick.asset} {topPick.direction === 'UP' ? '▲ BUY UP (YES)' : topPick.direction === 'DOWN' ? '▼ BUY DOWN (NO)' : 'NEUTRAL'}
                      </h2>
                      <span className={`text-sm font-black font-mono px-2 py-0.5 rounded-lg ${
                        topPick.direction === 'UP' ? 'bg-emerald-100 text-emerald-800' : topPick.direction === 'DOWN' ? 'bg-rose-100 text-rose-800' : 'bg-slate-200 text-slate-700'
                      }`}>
                        {topPick.confidence}% CONFIDENCE
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3 sm:gap-4">
                  <div className="text-right">
                    <div className="text-[10px] uppercase font-bold text-slate-400">Oracle Delta</div>
                    <div className={`text-base font-black font-mono ${topPick.delta >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                      {topPick.delta >= 0 ? '+' : ''}{topPick.delta} ({topPick.delta_pct >= 0 ? '+' : ''}{topPick.delta_pct}%)
                    </div>
                  </div>

                  <div className="text-right">
                    <div className="text-[10px] uppercase font-bold text-slate-400">Sync Latency</div>
                    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-mono font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
                      ⚡ {topPick.latency_ms}ms
                    </span>
                  </div>

                  <div className="text-right">
                    <div className="text-[10px] uppercase font-bold text-slate-400">Execution Status</div>
                    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-black ${
                      topPick.confidence >= confidenceThreshold && topPick.is_tradable
                        ? 'bg-emerald-600 text-white animate-pulse'
                        : 'bg-slate-200 text-slate-700'
                    }`}>
                      {topPick.confidence >= confidenceThreshold && topPick.is_tradable ? 'ARMED & READY' : 'WAITING CONFLUENCE'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Active Open Position Card (if any) */}
          {board?.active_trade && (
            <div className="bg-gradient-to-r from-blue-900 to-indigo-950 text-white rounded-2xl p-4 sm:p-5 shadow-lg border border-blue-700 relative overflow-hidden">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-blue-500/20 border border-blue-400/40 rounded-xl text-blue-300">
                    <Activity className="w-5 h-5 animate-pulse" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full bg-blue-500/30 text-blue-200 border border-blue-400/30">
                        ACTIVE OPEN POSITION
                      </span>
                      <span className="text-xs text-blue-200 font-mono">
                        #{board.active_trade.id} • {board.active_trade.asset}
                      </span>
                    </div>
                    <h3 className="text-xl font-black tracking-tight mt-0.5">
                      {board.active_trade.asset} {board.active_trade.outcome} • {board.active_trade.shares} Shares @ ${board.active_trade.entry_price}
                    </h3>
                  </div>
                </div>

                <div className="flex items-center gap-6">
                  <div>
                    <div className="text-[10px] uppercase font-bold text-blue-300">Strike Price</div>
                    <div className="text-sm font-bold font-mono">${board.active_trade.strike_price}</div>
                  </div>

                  <div>
                    <div className="text-[10px] uppercase font-bold text-blue-300">Margin Cost</div>
                    <div className="text-sm font-bold font-mono">${board.active_trade.cost} USDC</div>
                  </div>

                  <div>
                    <div className="text-[10px] uppercase font-bold text-blue-300">Target / Boundary</div>
                    <div className="text-sm font-bold font-mono text-emerald-400">+$1.00 TP / -$1.00 SL</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 7 Fast Markets Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
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
                  className={`bg-white rounded-2xl border transition-all duration-200 relative overflow-hidden flex flex-col justify-between ${
                    isTop ? 'border-amber-400 shadow-md ring-2 ring-amber-400/20' : 'border-slate-200 shadow-xs hover:border-slate-300'
                  }`}
                >
                  {/* Top Header Card */}
                  <div className="p-4 border-b border-slate-100">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {isTop ? (
                          <span className="p-1 bg-amber-400 text-white rounded-lg shadow-xs">
                            <Crown className="w-3.5 h-3.5" />
                          </span>
                        ) : (
                          <span className="text-[11px] font-black font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                            #{asset.rank}
                          </span>
                        )}
                        <div>
                          <span className="text-base font-black text-slate-900">{asset.asset}</span>
                          <span className="text-xs text-slate-400 font-medium ml-1.5">{meta.name}</span>
                        </div>
                      </div>

                      {/* Live Latency Badge */}
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                        {asset.latency_ms}ms
                      </span>
                    </div>

                    {/* Live Oracle Price and Flash */}
                    <div className="mt-2.5 flex items-baseline justify-between">
                      <div className={`text-xl sm:text-2xl font-black font-mono transition-colors duration-300 ${
                        flash === 'up' ? 'text-emerald-500' : flash === 'down' ? 'text-rose-500' : 'text-slate-900'
                      }`}>
                        ${asset.live_price.toLocaleString()}
                      </div>
                      
                      {/* Delta Indicator */}
                      <div className={`text-xs font-black font-mono px-2 py-0.5 rounded-lg flex items-center gap-0.5 ${
                        asset.delta >= 0 ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                      }`}>
                        {asset.delta >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                        {asset.delta >= 0 ? '+' : ''}{asset.delta_pct}%
                      </div>
                    </div>

                    <div className="text-[11px] text-slate-400 font-mono mt-0.5 flex justify-between">
                      <span>Strike (Baseline): ${asset.strike_price.toLocaleString()}</span>
                      <span>Δ {asset.delta >= 0 ? '+' : ''}${asset.delta}</span>
                    </div>
                  </div>

                  {/* Confluence & Order Book Body */}
                  <div className="p-4 space-y-3 flex-1 flex flex-col justify-between text-xs">
                    
                    {/* Score Bar */}
                    <div>
                      <div className="flex items-center justify-between text-[11px] font-bold mb-1">
                        <span className="flex items-center gap-1 text-slate-600">
                          Directional Signal:
                          <strong className={
                            asset.direction === 'UP' ? 'text-emerald-600' : asset.direction === 'DOWN' ? 'text-rose-600' : 'text-slate-500'
                          }>
                            {asset.direction}
                          </strong>
                        </span>
                        <span className="font-mono text-slate-800">{asset.confidence}%</span>
                      </div>
                      <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all duration-500 rounded-full ${
                            asset.direction === 'UP' ? 'bg-emerald-500' : asset.direction === 'DOWN' ? 'bg-rose-500' : 'bg-slate-400'
                          }`}
                          style={{ width: `${Math.min(100, Math.max(5, asset.confidence))}%` }}
                        />
                      </div>
                    </div>

                    {/* Polymarket CLOB Book Stats */}
                    <div className="bg-slate-50 rounded-xl p-2.5 border border-slate-100 space-y-1 font-mono text-[11px]">
                      <div className="flex justify-between text-slate-600">
                        <span>UP Share Ask:</span>
                        <span className="font-bold text-slate-800">${asset.up_share_price.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between text-slate-600">
                        <span>DOWN Share Ask:</span>
                        <span className="font-bold text-slate-800">${asset.down_share_price.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between text-slate-500 text-[10px]">
                        <span>Spread: {(asset.spread * 100).toFixed(1)}%</span>
                        <span>Depth: ${asset.liquidity.toFixed(0)}</span>
                      </div>
                    </div>

                    {/* Confluence Reason & Countdown */}
                    <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1">
                      <span className="flex items-center gap-1 font-mono font-bold text-blue-600">
                        <Timer className="w-3.5 h-3.5" /> {formatSec(asset.time_remaining_sec)}
                      </span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        asset.is_tradable ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
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
      ) : (
        /* Historical Trades Table */
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 sm:p-5 border-b border-slate-100 flex items-center justify-between">
            <div>
              <h2 className="text-base font-black text-slate-900">Fast 5M Execution History</h2>
              <p className="text-xs text-slate-500 font-medium">Authoritative trade settlements and 1:1 risk-reward realizations</p>
            </div>
            <button
              onClick={fetchTrades}
              className="p-2 hover:bg-slate-100 rounded-xl text-slate-600 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/50 text-[11px] font-bold uppercase text-slate-400">
                  <th className="py-2.5 px-4">Trade ID</th>
                  <th className="py-2.5 px-4">Asset</th>
                  <th className="py-2.5 px-4">Outcome</th>
                  <th className="py-2.5 px-4">Entry / Strike</th>
                  <th className="py-2.5 px-4">Exit Price</th>
                  <th className="py-2.5 px-4">Margin Cost</th>
                  <th className="py-2.5 px-4">Realized PnL</th>
                  <th className="py-2.5 px-4">Status / Resolution</th>
                  <th className="py-2.5 px-4">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-xs font-mono">
                {trades.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-8 text-center text-slate-400 font-sans text-xs">
                      No 5-minute fast trades recorded yet. Engine will execute the #1 ranked pair when confidence ≥ {confidenceThreshold}%.
                    </td>
                  </tr>
                ) : (
                  trades.map((t) => {
                    const isWin = (t.pnl || 0) > 0;
                    const isOpen = t.status === 'OPEN';
                    return (
                      <tr key={t.id} className="hover:bg-slate-50/60 transition-colors">
                        <td className="py-2.5 px-4 font-bold text-slate-900">#{t.id}</td>
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
                        <td className="py-2.5 px-4">
                          <div className="font-bold text-slate-800">${t.entry_price}</div>
                          <div className="text-[10px] text-slate-400">P0: ${t.strike_price}</div>
                        </td>
                        <td className="py-2.5 px-4 font-bold">
                          {t.exit_price != null ? `$${t.exit_price.toFixed(2)}` : '—'}
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
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-black ${
                            isOpen
                              ? 'bg-blue-100 text-blue-800 border border-blue-200'
                              : isWin
                              ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                              : 'bg-rose-100 text-rose-800 border border-rose-200'
                          }`}>
                            {t.resolution || t.status}
                          </span>
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

    </div>
  );
}
