import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useApi } from '../hooks/useApi';
import { 
  RefreshCw, Shield, TrendingUp, 
  Activity, Zap, Lock, History, Calendar, CheckCircle, XCircle,
  AlertTriangle, ShieldAlert,
  LogOut, ChevronDown, ChevronUp, GripVertical, SplitSquareVertical,
  ArrowUpRight, ArrowDownRight, Timer
} from 'lucide-react';
import BrandLogo from '../components/BrandLogo';



class ErrorBoundary extends React.Component<{children: React.ReactNode}, {hasError: boolean, error: any}> {
  constructor(props: any) { super(props); this.state = { hasError: false, error: null }; }
  static getDerivedStateFromError(error: any) { return { hasError: true, error }; }
  render() {
    if (this.state.hasError) return (
      <div className="p-8 bg-red-50 text-red-900 border border-red-200 rounded-xl m-8">
        <h1 className="text-2xl font-bold mb-4">React Error Boundary</h1>
        <pre className="whitespace-pre-wrap font-mono text-xs">{this.state.error?.toString() + '\n' + this.state.error?.stack}</pre>
      </div>
    );
    return this.props.children;
  }
}

function fmt4(v: number | null | undefined) { return v != null ? v.toFixed(4) : '—'; }
function fmtPct(v: number | null | undefined) { return v != null ? `${v.toFixed(2)}%` : '0.00%'; }
function fmtUsd(v: number | null | undefined) {
  if (v == null) return '$0.00';
  return (v >= 0 ? '+$' : '-$') + Math.abs(v).toFixed(2);
}
function fmtCurrency(v: number | null | undefined) {
  if (v == null) return '$0.00';
  return '$' + v.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function fmtDate(iso: string | null | undefined) {
  if (!iso) return '—';
  try {
    const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z');
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  } catch (e) {
    return iso;
  }
}

function LoadingState() {
  return (
    <div className="flex justify-center items-center h-64 bg-white rounded-2xl border border-slate-200 shadow-xs">
      <RefreshCw className="w-8 h-8 text-blue-500 animate-spin" />
    </div>
  );
}

// Real-Time BTC Price Hook: Authoritative Polygon Chainlink Oracle feed via backend
function useChainlinkLive(currentMarketStartTime: string | undefined, backendBtcPrice: number | null, backendPriceToBeat: number | null) {
  const [liveBtc, setLiveBtc] = useState<number | null>(backendBtcPrice);
  const [lastUpdate, setLastUpdate] = useState<number>(Date.now());

  useEffect(() => {
    if (backendBtcPrice !== null && backendBtcPrice !== undefined) {
      setLiveBtc(backendBtcPrice);
      setLastUpdate(Date.now());
    }
  }, [backendBtcPrice, currentMarketStartTime]);

  return { btcPrice: liveBtc || backendBtcPrice, priceToBeat: backendPriceToBeat, lastUpdate };
}

// Polymarket CLOB WebSocket Hook
function usePolymarketLive(yesToken: string | undefined, noToken: string | undefined) {
  const [livePrices, setLivePrices] = useState<{ yes: number | null, no: number | null, suspended: boolean }>({ yes: null, no: null, suspended: false });

  useEffect(() => {
    setLivePrices({ yes: null, no: null, suspended: false });
    if (!yesToken) return;

    let ws: WebSocket;
    let keepAlive: any;

    const connect = () => {
      ws = new WebSocket('wss://ws-subscriptions-clob.polymarket.com/ws/market');
      ws.onopen = () => {
        const tokens = noToken ? [yesToken, noToken] : [yesToken];
        ws.send(JSON.stringify({ assets_ids: tokens, type: "market" }));
        keepAlive = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send("ping"); }, 10000);
      };
      ws.onmessage = (event) => {
        if (event.data === "pong") return;
        try {
          const data = JSON.parse(event.data);
          setLivePrices(prev => {
            let updatedYes = prev.yes;
            let updatedNo = prev.no;
            const updates = Array.isArray(data) ? data : (data.price_changes || [data]);
            for (const item of updates) {
              if (item.asset_id === yesToken) {
                if (item.best_bid !== undefined) updatedYes = parseFloat(item.best_bid);
                else if (item.bids && item.bids.length > 0) updatedYes = parseFloat(item.bids[0].price);
              }
              if (noToken && item.asset_id === noToken) {
                if (item.best_bid !== undefined) updatedNo = parseFloat(item.best_bid);
                else if (item.bids && item.bids.length > 0) updatedNo = parseFloat(item.bids[0].price);
              }
            }
            if (updatedYes !== prev.yes || updatedNo !== prev.no) {
              const yes = updatedYes;
              const no = updatedNo;
              const suspended = (yes === null || yes === 0 || no === null || no === 0);
              return { yes, no, suspended };
            }
            return prev;
          });
        } catch (e) {}
      };
      ws.onclose = () => { setTimeout(connect, 3000); };
    };
    connect();
    return () => {
      if (ws) ws.close();
      if (keepAlive) clearInterval(keepAlive);
    };
  }, [yesToken, noToken]);

  return { livePrices };
}

function useBTC5MStatus(instanceId: string = 'instance_1') {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [wsConnected, setWsConnected] = useState<boolean>(false);

  const fetchStatus = async () => {
    try {
      const res = await fetch(`/api/btc5m/status?instance_id=${instanceId}`);
      if (res.ok) {
        const json = await res.json();
        setData(json);
        setLoading(false);
      }
    } catch (e) {
      setLoading(false);
    }
  };

  useEffect(() => {
    // 1. Instant REST fetch on mount and on instanceId change for immediate initial paint (<100ms)
    setLoading(true);
    fetchStatus();

    // 2. High-speed WebSocket connection for real-time live streaming
    let ws: WebSocket | null = null;
    let reconnectTimer: any = null;
    let isMounted = true;

    const connectWs = () => {
      try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/btc5m`;
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          if (!isMounted) return;
          setWsConnected(true);
        };

        ws.onmessage = (event) => {
          if (!isMounted) return;
          if (event.data === 'pong') return;
          try {
            const parsed = JSON.parse(event.data);
            if (parsed.type === 'btc5m_status' && parsed.data) {
              if (!parsed.instance_id || parsed.instance_id === instanceId) {
                setData(parsed.data);
                setLoading(false);
              }
            }
          } catch (err) {}
        };

        ws.onclose = () => {
          if (!isMounted) return;
          setWsConnected(false);
          reconnectTimer = setTimeout(connectWs, 2500);
        };

        ws.onerror = () => {
          if (ws) ws.close();
        };
      } catch (e) {
        if (isMounted) setWsConnected(false);
      }
    };

    connectWs();

    // 3. Resilient fallback: Poll via REST if WebSocket is disconnected
    const fallbackInterval = setInterval(() => {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        fetchStatus();
      }
    }, 3000);

    return () => {
      isMounted = false;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      clearInterval(fallbackInterval);
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [instanceId]);

  return { statusData: data, statusLoading: loading, refetchStatus: fetchStatus, wsConnected };
}

// Categorized Trade History Section (Weekly, Monthly, All)
function TradeHistorySection({ refreshTrigger, instanceId = 'instance_1' }: { refreshTrigger?: number, instanceId?: string }) {
  const [period, setPeriod] = useState<'all' | 'weekly' | 'monthly'>('all');
  const [historyData, setHistoryData] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchTrades = async () => {
    try {
      const res = await fetch(`/api/btc5m/trades?period=${period}&instance_id=${instanceId}`);
      if (res.ok) {
        const json = await res.json();
        setHistoryData(json);
        setLoading(false);
      }
    } catch (e) {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrades();
    const interval = setInterval(fetchTrades, 3000);
    return () => { clearInterval(interval); };
  }, [period, refreshTrigger, instanceId]);

  const trades = historyData?.trades || [];
  const total = historyData?.total ?? 0;
  const wins = historyData?.wins ?? 0;
  const losses = historyData?.losses ?? 0;
  const winRate = historyData?.win_rate ?? 0.0;
  const realizedPnl = historyData?.realized_pnl ?? 0.0;
  const periodIncome = trades.filter((t: any) => (t.pnl || 0) > 0).reduce((sum: number, t: any) => sum + (t.pnl || 0), 0);
  const periodLoss = trades.filter((t: any) => (t.pnl || 0) < 0).reduce((sum: number, t: any) => sum + Math.abs(t.pnl || 0), 0);

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-4 space-y-3">
      {/* Header and Filter Tabs */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600">
            <History className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-black text-slate-900 tracking-tight flex items-center gap-2">
              <span>TRADE AUDIT LOG & SETTLEMENT HISTORY</span>
              <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-bold">
                {total} Records
              </span>
            </h3>
            <p className="text-[11px] text-slate-400">
              Categorized weekly & monthly records with entry/exit snapshots and locked execution details.
            </p>
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200">
          <button
            onClick={() => setPeriod('all')}
            className={`px-3 py-1 rounded-lg text-xs font-black flex items-center gap-1 transition-all ${
              period === 'all'
                ? 'bg-white text-blue-600 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            ALL TRADES
          </button>
          <button
            onClick={() => setPeriod('weekly')}
            className={`px-3 py-1 rounded-lg text-xs font-black flex items-center gap-1 transition-all ${
              period === 'weekly'
                ? 'bg-white text-blue-600 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Calendar className="w-3 h-3" />
            THIS WEEK
          </button>
          <button
            onClick={() => setPeriod('monthly')}
            className={`px-3 py-1 rounded-lg text-xs font-black flex items-center gap-1 transition-all ${
              period === 'monthly'
                ? 'bg-white text-blue-600 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Calendar className="w-3 h-3" />
            THIS MONTH
          </button>
        </div>
      </div>

      {/* Summary Badges for the selected period */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100 min-w-0">
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block truncate">
            {period === 'all' ? 'All Records' : period === 'weekly' ? 'Weekly Volume' : 'Monthly Volume'}
          </span>
          <span className="text-base font-black text-slate-900 font-mono tracking-tight">
            {total} {total === 1 ? 'Trade' : 'Trades'}
          </span>
        </div>
        <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100 min-w-0">
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block truncate">
            Win Rate ({period})
          </span>
          <span className="text-base font-black text-slate-900 font-mono tracking-tight">
            {fmtPct(winRate)}
          </span>
        </div>
        <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100 min-w-0">
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block truncate">
            Wins / Losses
          </span>
          <span className="text-base font-black text-slate-900 font-mono tracking-tight">
            <span className="text-emerald-600">{wins}W</span> - <span className="text-rose-600">{losses}L</span>
          </span>
        </div>
        <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100 min-w-0">
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block truncate">
            Total Income ({period})
          </span>
          <span className="text-base font-black text-emerald-600 font-mono tracking-tight">
            +{fmtCurrency(periodIncome)}
          </span>
        </div>
        <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100 min-w-0">
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block truncate">
            Total Loss ({period})
          </span>
          <span className="text-base font-black text-rose-600 font-mono tracking-tight">
            -{fmtCurrency(periodLoss)}
          </span>
        </div>
        <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100 min-w-0">
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block truncate">
            Realized P&L ({period})
          </span>
          <span className={`text-base font-black font-mono tracking-tight ${realizedPnl >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
            {fmtUsd(realizedPnl)}
          </span>
        </div>
      </div>

      {/* Trades Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-left border-collapse min-w-[700px]">
          <thead>
            <tr className="bg-slate-50/80 border-b border-slate-200 text-[9px] font-black text-slate-500 uppercase tracking-wider">
              <th className="py-2 px-3">Entry Time (UTC)</th>
              <th className="py-2 px-3">Direction (Locked)</th>
              <th className="py-2 px-3">Entry Price</th>
              <th className="py-2 px-3">Exit Price</th>
              <th className="py-2 px-3">Position Size</th>
              <th className="py-2 px-3">Realized P&L</th>
              <th className="py-2 px-3">Result</th>
              <th className="py-2 px-3">Settlement Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-xs font-mono">
            {trades.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-6 text-center text-slate-400 font-sans text-xs">
                  {loading ? 'Loading trade records...' : `No paper trades recorded for this ${period} period yet.`}
                </td>
              </tr>
            ) : (
              trades.map((t: any) => {
                const isBuyYes = t.locked_predicted_side ? t.locked_predicted_side === 'YES' : t.side === 'BUY';
                const isWin = (t.pnl || 0) > 0;
                const isOpen = t.status === 'OPEN';

                return (
                  <tr key={t.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="py-2 px-3 text-slate-600 whitespace-nowrap text-[11px]">
                      {fmtDate(t.entry_time)}
                    </td>
                    <td className="py-2 px-3 whitespace-nowrap">
                      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded font-black text-[10px] ${
                        isBuyYes ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                      }`}>
                        <span>🔒</span> {isBuyYes ? 'BUY YES (UP)' : 'BUY NO (DOWN)'}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-slate-800 font-bold whitespace-nowrap">
                      ${fmt4(t.entry_price)}
                    </td>
                    <td className="py-2 px-3 text-slate-800 font-bold whitespace-nowrap">
                      {t.exit_price != null ? `$${fmt4(t.exit_price)}` : '—'}
                    </td>
                    <td className="py-2 px-3 text-slate-800 font-bold whitespace-nowrap">
                      ${fmt4(t.position_size)}
                    </td>
                    <td className="py-2 px-3 whitespace-nowrap">
                      {isOpen ? (
                        <span className="text-blue-600 font-bold text-xs">IN PROGRESS</span>
                      ) : (
                        <span className={`font-black text-xs ${isWin ? 'text-emerald-600' : 'text-rose-600'}`}>
                          {fmtUsd(t.pnl)}
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3 whitespace-nowrap">
                      {isOpen ? (
                        <span className="px-2 py-0.5 rounded-full text-[9px] font-black bg-blue-100 text-blue-800 border border-blue-200 animate-pulse">
                          OPEN
                        </span>
                      ) : isWin ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-black bg-emerald-100 text-emerald-800 border border-emerald-300">
                          <CheckCircle className="w-2.5 h-2.5 text-emerald-600" /> WIN
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-black bg-rose-100 text-rose-800 border border-rose-300">
                          <XCircle className="w-2.5 h-2.5 text-rose-600" /> LOSS
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-slate-500 font-sans text-[11px] truncate max-w-[200px]">
                      {t.exit_reason || t.resolution || (isOpen ? 'Awaiting candle expiry' : 'Completed')}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Skip Logs & Rejection Audit History Section
function SkipLogsSection({ refreshTrigger }: { refreshTrigger?: number }) {
  const [skips, setSkips] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [filter, setFilter] = useState<'all' | 'consensus' | 'obi' | 'cooldown'>('all');
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const fetchSkips = async () => {
    try {
      const res = await fetch('/api/btc5m/skips?limit=50');
      if (res.ok) {
        const json = await res.json();
        setSkips(json);
        setLoading(false);
      }
    } catch (e) {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSkips();
    const interval = setInterval(fetchSkips, 3000);
    return () => clearInterval(interval);
  }, [refreshTrigger]);

  const filteredSkips = skips.filter((s: any) => {
    if (filter === 'all') return true;
    const reason = (s.skip_reason || '').toLowerCase();
    if (filter === 'consensus') return reason.includes('consensus') || reason.includes('committee') || reason.includes('dissent');
    if (filter === 'obi') return reason.includes('hummingbot') || reason.includes('obi');
    if (filter === 'cooldown') return reason.includes('cooldown') || reason.includes('late-candle') || reason.includes('spread');
    return true;
  });

  const totalSkips = skips.length;
  const consensusVetos = skips.filter((s: any) => (s.skip_reason || '').toLowerCase().includes('consensus') || (s.skip_reason || '').toLowerCase().includes('committee')).length;
  const obiVetos = skips.filter((s: any) => (s.skip_reason || '').toLowerCase().includes('hummingbot') || (s.skip_reason || '').toLowerCase().includes('obi')).length;
  const savedLosses = skips.filter((s: any) => s.hypothetical_outcome === 'LOSS').length;

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-4 space-y-3">
      {/* Header and Filter Tabs */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-600">
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-black text-slate-900 tracking-tight flex items-center gap-2">
              <span>SKIP LOGS & REJECTION AUDIT</span>
              <span className="text-[10px] bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full font-bold">
                {totalSkips} Logged
              </span>
            </h3>
            <p className="text-[11px] text-slate-400">
              Filtered market history with exact indicator thresholds and safety veto triggers.
            </p>
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200 text-xs font-black">
          <button
            onClick={() => setFilter('all')}
            className={`px-2.5 py-1 rounded-lg transition-all ${
              filter === 'all' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            ALL ({totalSkips})
          </button>
          <button
            onClick={() => setFilter('consensus')}
            className={`px-2.5 py-1 rounded-lg transition-all ${
              filter === 'consensus' ? 'bg-white text-purple-700 shadow-xs' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            CONSENSUS ({consensusVetos})
          </button>
          <button
            onClick={() => setFilter('obi')}
            className={`px-2.5 py-1 rounded-lg transition-all ${
              filter === 'obi' ? 'bg-white text-amber-700 shadow-xs' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            OBI ({obiVetos})
          </button>
          <button
            onClick={() => setFilter('cooldown')}
            className={`px-2.5 py-1 rounded-lg transition-all ${
              filter === 'cooldown' ? 'bg-white text-blue-700 shadow-xs' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            COOLDOWN
          </button>
        </div>
      </div>

      {/* Summary Badges */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100 min-w-0">
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block truncate">
            Total Skips
          </span>
          <span className="text-base font-black text-slate-900 font-mono tracking-tight">
            {totalSkips}
          </span>
        </div>
        <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100 min-w-0">
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block truncate">
            AI Consensus Vetos
          </span>
          <span className="text-base font-black text-purple-600 font-mono tracking-tight">
            {consensusVetos}
          </span>
        </div>
        <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100 min-w-0">
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block truncate">
            Hummingbot OBI
          </span>
          <span className="text-base font-black text-amber-600 font-mono tracking-tight">
            {obiVetos}
          </span>
        </div>
        <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100 min-w-0">
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block truncate">
            Saved From Loss
          </span>
          <span className="text-base font-black text-emerald-600 font-mono tracking-tight">
            {savedLosses}
          </span>
        </div>
      </div>

      {/* Skips Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-left border-collapse min-w-[650px]">
          <thead>
            <tr className="bg-slate-50/80 border-b border-slate-200 text-[9px] font-black text-slate-500 uppercase tracking-wider">
              <th className="py-2 px-3">Skip Time (UTC)</th>
              <th className="py-2 px-3">Market / Side</th>
              <th className="py-2 px-3">Primary Reason</th>
              <th className="py-2 px-3">Key Indicators</th>
              <th className="py-2 px-3">Protection Outcome</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-xs font-mono">
            {filteredSkips.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-6 text-center text-slate-400 font-sans text-xs">
                  {loading ? 'Loading skip records...' : 'No skipped market records match current filter.'}
                </td>
              </tr>
            ) : (
              filteredSkips.map((s: any) => {
                const isExpanded = expandedId === s.id;
                const rawReasons = (s.skip_reason || '')
                  .split('|')
                  .map((r: string) => r.trim().replace(/^SKIP\s*-\s*/i, ''))
                  .filter(Boolean);
                const primaryReason = rawReasons[0] || s.skip_reason || 'Criteria not met';
                const marketName = (s.question || 'BTC 5M Market').replace('Bitcoin Up or Down - ', '');

                const isConsensusVeto = (s.skip_reason || '').includes('Committee') || (s.skip_reason || '').includes('Consensus');
                const isObiVeto = (s.skip_reason || '').includes('Hummingbot') || (s.skip_reason || '').includes('OBI');
                const isCooldownVeto = (s.skip_reason || '').includes('Cooldown');

                return (
                  <React.Fragment key={s.id}>
                    <tr
                      onClick={() => setExpandedId(isExpanded ? null : s.id)}
                      className="hover:bg-slate-50/80 transition-colors cursor-pointer"
                    >
                      <td className="py-2 px-3 text-slate-600 whitespace-nowrap text-[11px]">
                        {fmtDate(s.timestamp)}
                      </td>
                      <td className="py-2 px-3 whitespace-nowrap">
                        <div className="font-bold text-slate-800 text-[11px] truncate max-w-[150px]" title={s.question}>
                          {marketName}
                        </div>
                        <div className="flex items-center gap-1 mt-0.5">
                          {s.predicted_side && s.predicted_side !== 'NONE' ? (
                            <span className={`px-1.5 py-0.2 rounded text-[9px] font-black ${
                              s.predicted_side === 'YES' ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                            }`}>
                              {s.predicted_side} (Y:{(s.yes_score ?? 0).toFixed(0)} N:{(s.no_score ?? 0).toFixed(0)})
                            </span>
                          ) : (
                            <span className="px-1.5 py-0.2 rounded text-[9px] font-black bg-slate-100 text-slate-600">
                              NO BIAS (Y:{(s.yes_score ?? 0).toFixed(0)} N:{(s.no_score ?? 0).toFixed(0)})
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-2 px-3 max-w-[220px]">
                        <div className="flex items-center gap-1.5">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-black truncate max-w-[200px] inline-block ${
                            isConsensusVeto
                              ? 'bg-purple-100 text-purple-800 border border-purple-200'
                              : isObiVeto
                              ? 'bg-amber-100 text-amber-800 border border-amber-200'
                              : isCooldownVeto
                              ? 'bg-blue-100 text-blue-800 border border-blue-200'
                              : 'bg-rose-50 text-rose-700 border border-rose-200'
                          }`} title={primaryReason}>
                            {primaryReason}
                          </span>
                        </div>
                        {rawReasons.length > 1 && (
                          <span className="text-[9px] text-blue-600 font-sans font-medium block mt-0.5 flex items-center gap-0.5">
                            +{rawReasons.length - 1} more checks failed {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-3 whitespace-nowrap text-[10px]">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="bg-slate-100 px-1.5 py-0.5 rounded text-slate-700 font-bold" title="Net Edge">
                            Edge: {s.net_edge != null ? `${(s.net_edge * 100).toFixed(1)}%` : '0%'}
                          </span>
                          <span className="bg-slate-100 px-1.5 py-0.5 rounded text-slate-700 font-bold" title="Spread">
                            Sprd: {s.spread != null ? `${(s.spread * 100).toFixed(1)}%` : '—'}
                          </span>
                          <span className="bg-slate-100 px-1.5 py-0.5 rounded text-slate-700 font-bold" title="Time Remaining">
                            {s.time_remaining ? `${Math.round(s.time_remaining)}s left` : '—'}
                          </span>
                        </div>
                      </td>
                      <td className="py-2 px-3 whitespace-nowrap text-[10px]">
                        {s.hypothetical_outcome === 'LOSS' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-black bg-emerald-100 text-emerald-800 border border-emerald-300">
                            🛡️ SAVED LOSS
                          </span>
                        ) : s.hypothetical_outcome === 'WIN' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-black bg-amber-100 text-amber-800 border border-amber-300">
                            MISSED WIN
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full font-black bg-slate-100 text-slate-600">
                            PENDING CANDLE
                          </span>
                        )}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="bg-amber-50/40">
                        <td colSpan={5} className="p-3">
                          <div className="space-y-1.5 text-xs font-sans">
                            <p className="font-black text-slate-800 flex items-center gap-1.5">
                              <ShieldAlert className="w-3.5 h-3.5 text-amber-600" />
                              <span>FAILED GATES & DETAILED REJECTION CRITERIA:</span>
                            </p>
                            <ul className="list-disc pl-5 space-y-1 text-slate-700 font-mono text-[11px]">
                              {rawReasons.map((r: string, idx: number) => (
                                <li key={idx} className="text-rose-800 font-semibold">{r}</li>
                              ))}
                            </ul>
                            <div className="flex items-center gap-3 pt-2 text-[10px] font-mono text-slate-600 border-t border-slate-200/60 flex-wrap">
                              <span>YES Prob: {s.yes_prob != null ? `${(s.yes_prob * 100).toFixed(1)}%` : '—'}</span>
                              <span>NO Prob: {s.no_prob != null ? `${(s.no_prob * 100).toFixed(1)}%` : '—'}</span>
                              <span>Liquidity: ${s.liquidity ? Number(s.liquidity).toLocaleString() : '—'}</span>
                              <span>Market ID: {s.market_id ? s.market_id.slice(0, 16) + '...' : '—'}</span>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Adjustable Split Container for Trade History and Skip Logs
function ResizableHistoryLogsSplit({
  refreshTrigger,
  instanceId
}: {
  refreshTrigger?: number;
  instanceId?: string;
}) {
  const [splitPercent, setSplitPercent] = useState<number>(() => {
    try {
      const saved = localStorage.getItem('btc5m_history_split');
      return saved ? Math.min(Math.max(Number(saved), 18), 82) : 50;
    } catch (e) {
      return 50;
    }
  });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isLargeScreen, setIsLargeScreen] = useState<boolean>(() => {
    return typeof window !== 'undefined' ? window.innerWidth >= 1024 : true;
  });
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleResize = () => {
      setIsLargeScreen(window.innerWidth >= 1024);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleTouchStart = useCallback(() => {
    setIsDragging(true);
  }, []);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const rawPercent = ((e.clientX - rect.left) / rect.width) * 100;
      const clamped = Math.min(Math.max(rawPercent, 18), 82);
      setSplitPercent(clamped);
    };

    const handleTouchMove = (e: TouchEvent) => {
      if (!containerRef.current || !e.touches[0]) return;
      const rect = containerRef.current.getBoundingClientRect();
      const rawPercent = ((e.touches[0].clientX - rect.left) / rect.width) * 100;
      const clamped = Math.min(Math.max(rawPercent, 18), 82);
      setSplitPercent(clamped);
    };

    const handleEnd = () => {
      setIsDragging(false);
      try {
        localStorage.setItem('btc5m_history_split', splitPercent.toString());
      } catch (e) {}
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleEnd);
    window.addEventListener('touchmove', handleTouchMove);
    window.addEventListener('touchend', handleEnd);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleEnd);
      window.removeEventListener('touchmove', handleTouchMove);
      window.removeEventListener('touchend', handleEnd);
    };
  }, [isDragging, splitPercent]);

  const setPreset = (pct: number) => {
    setSplitPercent(pct);
    try {
      localStorage.setItem('btc5m_history_split', pct.toString());
    } catch (e) {}
  };

  return (
    <div className="space-y-2">
      {/* Quick Toolbar for Dynamic Sizing & Preset Ratios */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-2 text-slate-600 font-bold text-xs">
          <SplitSquareVertical className="w-4 h-4 text-blue-600" />
          <span className="hidden sm:inline font-black tracking-tight">ADJUSTABLE DUAL AUDIT VIEW:</span>
          <span className="text-slate-800 font-mono text-[11px] bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
            {Math.round(splitPercent)}% Trades · {Math.round(100 - splitPercent)}% Skip Logs
          </span>
          <span className="hidden md:inline text-[10px] text-slate-400 font-sans">
            (Drag divider bar horizontally to resize)
          </span>
        </div>

        {/* Quick Split Ratio Presets */}
        <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-xl border border-slate-200 text-xs font-black">
          <button
            onClick={() => setPreset(25)}
            title="Expand Skip Logs (25% Trades / 75% Skips)"
            className={`px-2.5 py-1 rounded-lg transition-all cursor-pointer ${
              Math.round(splitPercent) === 25 ? 'bg-white text-blue-600 shadow-xs' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            25 / 75
          </button>
          <button
            onClick={() => setPreset(50)}
            title="Equal 50/50 Split"
            className={`px-2.5 py-1 rounded-lg transition-all cursor-pointer ${
              Math.round(splitPercent) === 50 ? 'bg-white text-blue-600 shadow-xs' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            50 / 50
          </button>
          <button
            onClick={() => setPreset(75)}
            title="Expand Trade History (75% Trades / 25% Skips)"
            className={`px-2.5 py-1 rounded-lg transition-all cursor-pointer ${
              Math.round(splitPercent) === 75 ? 'bg-white text-blue-600 shadow-xs' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            75 / 25
          </button>
        </div>
      </div>

      {/* Resizable Container */}
      <div
        ref={containerRef}
        className={`relative flex flex-col lg:flex-row items-stretch w-full ${
          isDragging ? 'select-none cursor-col-resize' : ''
        }`}
      >
        {/* Left Pane: Trade History */}
        <div
          className="w-full min-w-0"
          style={{
            width: isLargeScreen ? `calc(${splitPercent}% - 8px)` : '100%'
          }}
        >
          <TradeHistorySection refreshTrigger={refreshTrigger} instanceId={instanceId} />
        </div>

        {/* Adjustable Divider (visible on large screens) */}
        <div
          onMouseDown={handleMouseDown}
          onTouchStart={handleTouchStart}
          title="Drag left/right to resize views"
          className={`hidden lg:flex flex-col items-center justify-center w-4 mx-0.5 cursor-col-resize group shrink-0 relative z-10 select-none ${
            isDragging ? 'bg-blue-100 rounded-full' : 'hover:bg-slate-100 rounded-full'
          }`}
        >
          <div
            className={`w-1.5 h-full min-h-[420px] rounded-full transition-all flex items-center justify-center ${
              isDragging ? 'bg-blue-600 shadow-lg shadow-blue-500/40 w-2' : 'bg-slate-200 group-hover:bg-blue-500'
            }`}
          >
            <div
              className={`p-1 rounded-md bg-white border shadow-xs transition-transform ${
                isDragging ? 'border-blue-600 scale-125' : 'border-slate-300 group-hover:border-blue-500 group-hover:scale-110'
              }`}
            >
              <GripVertical
                className={`w-3.5 h-3.5 ${
                  isDragging ? 'text-blue-600' : 'text-slate-400 group-hover:text-blue-600'
                }`}
              />
            </div>
          </div>
        </div>

        {/* Right Pane: Skip Logs History */}
        <div
          className="w-full min-w-0 mt-4 lg:mt-0"
          style={{
            width: isLargeScreen ? `calc(${100 - splitPercent}% - 8px)` : '100%'
          }}
        >
          <SkipLogsSection refreshTrigger={refreshTrigger} />
        </div>
      </div>
    </div>
  );
}

function InnerBTC5M() {
  const [selectedInstance] = useState<'instance_1'>('instance_1');
  const { statusData, statusLoading, refetchStatus } = useBTC5MStatus(selectedInstance);
  const [refreshTrigger, setRefreshTrigger] = useState<number>(0);
  const { data: statsData } = useApi<any>(`/btc5m/stats?instance_id=${selectedInstance}&v=${refreshTrigger}`, null);
  const [isClosing, setIsClosing] = useState<boolean>(false);
  const [closeError, setCloseError] = useState<string | null>(null);
  const [isTogglingTrading, setIsTogglingTrading] = useState<boolean>(false);

  const activeTradeId = statusData?.active_trade?.id ?? null;
  const activeTradeStatus = statusData?.active_trade?.status ?? null;
  useEffect(() => {
    setRefreshTrigger(prev => prev + 1);
  }, [activeTradeId, activeTradeStatus]);

  const handleToggleTrading = async (targetState: boolean) => {
    if (isTogglingTrading) return;
    setIsTogglingTrading(true);
    try {
      const res = await fetch('/api/btc5m/toggle_trading', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: targetState, instance_id: selectedInstance })
      });
      if (res.ok) {
        refetchStatus();
      }
    } catch (err) {
      console.error('Failed to toggle trading status:', err);
    } finally {
      setIsTogglingTrading(false);
    }
  };

  const handleLogout = () => {
    try {
      localStorage.clear();
      sessionStorage.clear();
    } catch (e) {}
    window.location.href = '/login';
  };

  const handleCloseTrade = async () => {
    if (isClosing) return;
    setIsClosing(true);
    setCloseError(null);
    try {
      const res = await fetch(`/api/btc5m/close_trade?instance_id=${selectedInstance}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const json = await res.json();
      if (res.ok && json.status === 'success') {
        refetchStatus();
        setRefreshTrigger(prev => prev + 1);
      } else {
        setCloseError(json?.message || 'Failed to close trade');
      }
    } catch (err: any) {
      setCloseError(err?.message || 'Error closing trade');
    } finally {
      setIsClosing(false);
    }
  };

  
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const current = statusData?.current_market;
  const trade = statusData?.active_trade || statusData?.open_trade;
  
  const { btcPrice, priceToBeat } = useChainlinkLive(current?.start_time, statusData?.chainlink_btc_usd, statusData?.price_to_beat);
  const { livePrices } = usePolymarketLive(current?.yes_token_id, current?.no_token_id);

  if (statusLoading) return <div className="p-6"><LoadingState /></div>;

  let countdownDisplay = '00:00';
  let countdownSeconds = 0;
  let progressPct = 0;
  if (current?.end_time) {
    const endMs = new Date(current.end_time.endsWith('Z') ? current.end_time : current.end_time + 'Z').getTime();
    const startMs = current.start_time ? new Date(current.start_time.endsWith('Z') ? current.start_time : current.start_time + 'Z').getTime() : (endMs - 300000);
    const totalDuration = Math.max(1, (endMs - startMs) / 1000);
    const remaining = Math.floor((endMs - now) / 1000);
    countdownSeconds = Math.max(0, remaining);
    const m = Math.floor(countdownSeconds / 60);
    const s = Math.floor(countdownSeconds % 60);
    countdownDisplay = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    const elapsed = Math.max(0, Math.min(totalDuration, totalDuration - countdownSeconds));
    progressPct = Math.min(100, Math.max(0, (elapsed / totalDuration) * 100));
  }

  const isTradingActive = statusData?.trading_active ?? false;
  const targetSettings = statusData?.targeting_settings;
  const analysis = statusData?.live_market_analysis || statusData?.analysis;

  // Live CLOB / Scanner Prices
  const dispYes = (livePrices.yes && livePrices.yes > 0.05) ? livePrices.yes : (analysis?.yes_prob || current?.best_bid || 0.5);
  const dispNo = (livePrices.no && livePrices.no > 0.05) ? livePrices.no : (analysis?.no_prob || (current?.best_bid ? 1.0 - current.best_bid : (1.0 - dispYes)));

  const yesVal = Math.max(0.01, Math.min(0.99, dispYes));
  const noVal = Math.max(0.01, Math.min(0.99, dispNo));
  const yesPct = Math.round(yesVal * 100);
  const noPct = Math.round(noVal * 100);

  const isTradeOpen = Boolean(trade && trade.status === 'OPEN');
  const lockedSide: 'YES' | 'NO' | null = isTradeOpen 
    ? (trade.locked_predicted_side || (trade.side === 'BUY' ? 'YES' : 'NO')) 
    : null;
  const lockedDir: 'UP' | 'DOWN' | null = isTradeOpen
    ? (trade.locked_direction || (lockedSide === 'YES' ? 'UP' : 'DOWN'))
    : null;
  const isLocked = isTradeOpen;

  const dynamicPredictedSide = analysis?.predicted_side && analysis.predicted_side !== 'NONE'
    ? analysis.predicted_side
    : (dispYes >= dispNo ? 'YES' : 'NO');
  const predictedSide: 'YES' | 'NO' = (isLocked ? lockedSide : dynamicPredictedSide) as 'YES' | 'NO';

  // Probabilities & Scores
  let finalYesPct = yesPct;
  let finalNoPct = noPct;
  let yesScore = analysis?.yes_score ?? (yesVal * 100);
  let noScore = analysis?.no_score ?? (noVal * 100);

  if (isLocked) {
    // Immutable active trade thesis representation
    const fairP = trade.entry_fair_probability || trade.entry_price || 0.65;
    if (lockedSide === 'YES') {
      finalYesPct = Math.round(fairP >= 0.5 ? fairP * 100 : (1 - fairP) * 100);
      if (finalYesPct < 55) finalYesPct = 65;
      finalNoPct = 100 - finalYesPct;
    } else {
      finalNoPct = Math.round(fairP >= 0.5 ? fairP * 100 : (1 - fairP) * 100);
      if (finalNoPct < 55) finalNoPct = 65;
      finalYesPct = 100 - finalNoPct;
    }
    yesScore = trade.entry_yes_score ?? yesScore;
    noScore = trade.entry_no_score ?? noScore;
  }

  const netEdge = trade?.entry_net_edge ?? analysis?.net_edge;

  // Trade PnL & Balance
  let tradePrice: number | null = null;
  if (isTradeOpen) {
      const isYes = lockedSide === 'YES';
      const lp = isYes ? livePrices.yes : livePrices.no;
      if (lp !== null && lp > 0) {
          tradePrice = lp;
      } else if (trade.current_price !== null && trade.current_price > 0) {
          tradePrice = trade.current_price;
      }
  }
  const tradeUnrealized = (tradePrice !== null && isTradeOpen) ? (tradePrice - trade.entry_price) * trade.quantity : 0.0;
  
  const startingBalance = 500.0;
  const realizedPnl = statsData?.realized_pnl ?? 0.0;
  const currentEquity = startingBalance + realizedPnl + tradeUnrealized;
  const totalPnl = realizedPnl + tradeUnrealized;
  const pnlPct = (totalPnl / startingBalance) * 100;

  // Momentum & Price Delta computations
  const rawMomentum = analysis?.momentum ?? 0.0;
  const p2bDiff = (btcPrice && priceToBeat) ? (btcPrice - priceToBeat) : null;
  const p2bPct = (p2bDiff !== null && priceToBeat) ? (p2bDiff / priceToBeat) * 100 : null;
  const isBtcAboveP2B = p2bDiff !== null ? p2bDiff >= 0 : true;

  return (
    <div className="space-y-3.5 max-w-7xl mx-auto pb-4">
      {/* 1. MASTER TOP HEADER */}
      <div className="relative w-full bg-slate-900 border-2 border-slate-800 rounded-2xl p-4 shadow-sm text-white space-y-3">
        {/* Main Row: Left (Genanda Bot + Timer + Bitcoin Up/Down), Right (Uniform Metrics + Adjacent Logout) */}
        <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4">
          
          {/* BOT SECTION: Lowered and centered with logo, Bitcoin Up/Down written small underneath */}
          <div className="flex items-center gap-3.5 min-w-0">
            <div className="shrink-0 p-1 bg-slate-800/90 rounded-2xl border border-slate-700/80 shadow-md">
              <BrandLogo size={46} glow={true} />
            </div>
            <div className="min-w-0 flex flex-col justify-center">
              {/* Jonanda Bot + Pause/Start toggle button */}
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-2xl font-black text-white tracking-tight leading-tight">Jonanda Bot</h1>
                <button
                  onClick={() => handleToggleTrading(!isTradingActive)}
                  disabled={isTogglingTrading}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-black uppercase tracking-wider border transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50 shadow-xs ${
                    isTradingActive
                      ? 'bg-rose-500/20 text-rose-300 border-rose-500/40 hover:bg-rose-500/30'
                      : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/30 animate-pulse'
                  }`}
                >
                  {isTogglingTrading ? 'Updating...' : isTradingActive ? '■ PAUSE BOT' : '▶ START BOT'}
                </button>
              </div>

              {/* Bitcoin Up/Down written small beneath Jonanda Bot */}
              <p className="mt-1 text-xs font-semibold text-slate-400 font-mono tracking-wide flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>Bitcoin Up/Down</span>
              </p>
            </div>
          </div>

          {/* RIGHT METRICS GROUP: COUNTDOWN TIMER (BESIDE TOTAL INCOME) + TOTAL LOSS + VIRTUAL EQUITY + LOGOUT */}
          <div className="flex items-center gap-2.5 self-start xl:self-auto shrink-0 flex-wrap sm:flex-nowrap">
            {/* Countdown Timer (visible beside Total Income) */}
            <div className="w-32 sm:w-36 h-[82px] bg-slate-950/90 border border-slate-800 p-2.5 rounded-xl text-right flex flex-col justify-between shadow-inner">
              <div className="flex items-center justify-between gap-1">
                <span className="text-[9px] font-black text-amber-400 uppercase tracking-wider">TIMER</span>
                <Timer className="w-3.5 h-3.5 text-amber-400" />
              </div>
              <div className="text-xl sm:text-2xl font-black text-amber-400 font-mono tracking-widest leading-none my-auto text-center">
                {countdownDisplay}
              </div>
              <div className="text-[9px] text-slate-400 font-mono font-bold text-center">
                {countdownSeconds > 0 ? `${countdownSeconds}s remaining` : 'Expired'}
              </div>
            </div>

            {/* Total Income */}
            <div className="w-32 sm:w-36 h-[82px] bg-emerald-950/40 border border-emerald-500/30 p-2.5 rounded-xl text-right flex flex-col justify-between">
              <div className="flex items-center justify-between gap-1">
                <span className="text-[9px] font-black text-emerald-400 uppercase tracking-wider">TOTAL INCOME</span>
                <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />
              </div>
              <div className="text-lg font-black text-emerald-400 font-mono tracking-tight">
                +{fmtCurrency(statsData?.total_income ?? 0)}
              </div>
              <div className="text-[9px] text-emerald-500/80 font-mono font-bold">
                Gross Profit ({statsData?.wins ?? 0}W)
              </div>
            </div>

            {/* Total Loss */}
            <div className="w-32 sm:w-36 h-[82px] bg-rose-950/40 border border-rose-500/30 p-2.5 rounded-xl text-right flex flex-col justify-between">
              <div className="flex items-center justify-between gap-1">
                <span className="text-[9px] font-black text-rose-400 uppercase tracking-wider">TOTAL LOSS</span>
                <ArrowDownRight className="w-3.5 h-3.5 text-rose-400" />
              </div>
              <div className="text-lg font-black text-rose-400 font-mono tracking-tight">
                -{fmtCurrency(statsData?.total_loss ?? 0)}
              </div>
              <div className="text-[9px] text-rose-500/80 font-mono font-bold">
                Gross Losses ({statsData?.losses ?? 0}L)
              </div>
            </div>

            {/* Virtual Equity */}
            <div className="w-32 sm:w-36 h-[82px] bg-slate-800/90 border border-slate-700 p-2.5 rounded-xl text-right flex flex-col justify-between">
              <div className="flex items-center justify-between gap-1">
                <span className="text-[9px] font-black text-slate-300 uppercase tracking-wider">VIRTUAL EQUITY</span>
                <Shield className="w-3.5 h-3.5 text-slate-400" />
              </div>
              <div className="text-lg font-black text-white font-mono tracking-tight">
                {fmtCurrency(currentEquity)}
              </div>
              <div className={`text-[9px] font-bold font-mono ${totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {totalPnl >= 0 ? '+' : ''}{fmtCurrency(totalPnl)} P&L
              </div>
            </div>

            {/* Adjacent Logout */}
            <button
              onClick={handleLogout}
              title="Sign out of session"
              className="h-[82px] px-3.5 rounded-xl text-xs font-black text-slate-400 hover:text-rose-300 bg-slate-800/90 hover:bg-rose-500/20 border border-slate-700/80 hover:border-rose-500/40 transition-all flex flex-col items-center justify-center gap-1.5 cursor-pointer shadow-xs hover:shadow-sm"
            >
              <LogOut className="w-4 h-4 text-rose-400" />
              <span className="text-[10px] tracking-wider font-mono">LOGOUT</span>
            </button>
          </div>
        </div>

        {/* 5-Minute Window Full-Width Progress Bar */}
        <div className="space-y-1 pt-1">
          <div className="flex justify-between items-center text-[10px] font-mono text-slate-400">
            <span className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${countdownSeconds > 30 ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400 animate-ping'}`}></span>
              {countdownSeconds > 30 ? 'WINDOW ACTIVE · EVALUATING' : 'SETTLEMENT WINDOW CLOSING'}
            </span>
            <span>
              {countdownSeconds > 0 ? `${countdownSeconds}s remaining (${progressPct.toFixed(1)}% elapsed)` : 'Window closed'}
            </span>
          </div>
          <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden shadow-inner">
            <div 
              className={`h-full transition-all duration-1000 ${
                countdownSeconds > 30 
                  ? 'bg-gradient-to-r from-blue-500 via-emerald-400 to-amber-400' 
                  : 'bg-gradient-to-r from-amber-400 to-rose-500 animate-pulse'
              }`}
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      </div>

      {/* 2. TOP STATS BAR: TOTAL TRADES, WINS, LOSSES, WIN RATE, PROFIT FACTOR, NET RETURN (PROFIT FACTOR NEXT TO WIN RATE) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-xs min-w-0">
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider truncate">TOTAL TRADES</span>
            <Activity className="w-3 h-3 text-blue-500" />
          </div>
          <span className="text-xl font-black text-slate-900 font-mono tracking-tight block">
            {statsData?.total_trades ?? 0}
          </span>
          <span className="text-[9px] text-slate-400 font-mono block truncate">
            {statsData?.open_trades ?? 0} Open · {statsData?.closed_trades ?? 0} Settled
          </span>
        </div>

        <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-xs min-w-0">
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider truncate">WINS</span>
            <CheckCircle className="w-3 h-3 text-emerald-500" />
          </div>
          <span className="text-xl font-black text-emerald-600 font-mono tracking-tight block">
            {statsData?.wins ?? 0}
          </span>
          <span className="text-[9px] text-emerald-600/80 font-mono block truncate font-bold">
            Winning Trades
          </span>
        </div>

        <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-xs min-w-0">
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider truncate">LOSSES</span>
            <XCircle className="w-3 h-3 text-rose-500" />
          </div>
          <span className="text-xl font-black text-rose-600 font-mono tracking-tight block">
            {statsData?.losses ?? 0}
          </span>
          <span className="text-[9px] text-rose-600/80 font-mono block truncate font-bold">
            Loss Trades
          </span>
        </div>

        <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-xs min-w-0">
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider truncate">WIN RATE</span>
            <TrendingUp className="w-3 h-3 text-blue-500" />
          </div>
          <span className="text-xl font-black text-blue-600 font-mono tracking-tight block">
            {statsData?.closed_trades ? fmtPct(statsData?.win_rate) : '0.00%'}
          </span>
          <span className="text-[9px] text-slate-400 font-mono block truncate">
            Target &gt;55%
          </span>
        </div>

        {/* Profit Factor placed next to Win Rate */}
        <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-xs min-w-0">
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider truncate">PROFIT FACTOR</span>
            <Shield className="w-3 h-3 text-amber-500" />
          </div>
          <span className="text-xl font-black text-amber-600 font-mono tracking-tight block">
            {statsData?.profit_factor ? statsData.profit_factor.toFixed(2) : '1.00'}
          </span>
          <span className="text-[9px] text-slate-400 font-mono block truncate">
            Target R:R 1.5:1
          </span>
        </div>

        <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-xs min-w-0">
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider truncate">NET RETURN</span>
            <span className="text-[9px] font-bold text-slate-400">$500 SEED</span>
          </div>
          <span className={`text-xl font-black font-mono tracking-tight block ${totalPnl >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
            {totalPnl >= 0 ? '+' : ''}{fmtCurrency(totalPnl)}
          </span>
          <span className={`text-[9px] font-mono block truncate font-bold ${totalPnl >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
            {totalPnl >= 0 ? '+' : ''}{fmtPct(pnlPct)}
          </span>
        </div>
      </div>

      {/* 3. CORE 3-PANEL GRID:
          - CORNER 1 (LEFT): PRICE TO BEAT & LIVE BTC PRICE
          - CENTER (MIDDLE): PREDICTION PROBABILITIES (YES vs NO)
          - CORNER 2 (RIGHT): ACTIVE TRADE & MARKET MOMENTUM
      */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3.5 items-stretch">
        
        {/* CORNER 1 (LEFT): PRICE TO BEAT & LIVE BTC PRICE */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-4 flex flex-col justify-between">
          <div>
            <div className="flex justify-between items-center mb-2.5">
              <h2 className="text-xs font-black text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-blue-600" />
                <span>PRICE TO BEAT & LIVE BTC</span>
              </h2>
              <span className="text-[10px] bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full font-black border border-emerald-200 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                LIVE 1S TICK
              </span>
            </div>

            {/* Real-Time Price Cards (Contract Box Removed for Compact Corner Layout) */}
            <div className="grid grid-cols-1 gap-2.5 mb-3">
              {/* Reference Price to Beat (Strike) */}
              <div className="bg-amber-50/80 p-3.5 rounded-xl border border-amber-200">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-black text-amber-800 uppercase tracking-wider block">
                    PRICE TO BEAT (P2B)
                  </span>
                  <span className="text-[9px] bg-amber-200/80 text-amber-900 font-black px-1.5 py-0.5 rounded">
                    STRIKE TWAP
                  </span>
                </div>
                <span className="text-2xl sm:text-3xl font-black font-mono text-amber-950 tracking-tight block mt-1">
                  {priceToBeat ? fmtCurrency(priceToBeat) : 'AWAITING P2B'}
                </span>
                <span className="text-[10px] text-amber-800/80 font-mono block mt-0.5">
                  Benchmark strike price for current 5M window
                </span>
              </div>

              {/* Live Real-Time Chainlink / Coinbase BTC Price */}
              <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-black text-slate-600 uppercase tracking-wider block">
                    LIVE BTC/USD PRICE
                  </span>
                  <span className="flex items-center gap-1 text-[9px] font-black text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                    SPOT REAL-TIME
                  </span>
                </div>
                <span className="text-2xl sm:text-3xl font-black font-mono text-slate-950 tracking-tight block mt-1">
                  {btcPrice ? fmtCurrency(btcPrice) : 'UPDATING...'}
                </span>
                <span className="text-[10px] text-slate-500 font-mono block mt-0.5">
                  Live Coinbase & Chainlink sub-second tick
                </span>
              </div>
            </div>

            {/* Real-Time Price Delta Banner */}
            <div className={`p-2.5 rounded-xl border flex items-center justify-between shadow-xs ${isBtcAboveP2B ? 'bg-emerald-50 border-emerald-300 text-emerald-900' : 'bg-rose-50 border-rose-300 text-rose-900'}`}>
              <div>
                <span className="text-[9px] font-bold uppercase tracking-wider block">
                  DELTA VS PRICE TO BEAT
                </span>
                <span className="text-sm font-black font-mono block">
                  {p2bDiff !== null ? `${p2bDiff >= 0 ? '▲ +' : '▼ -'}${fmtCurrency(Math.abs(p2bDiff))} (${p2bPct ? p2bPct.toFixed(3) : '0.000'}%)` : '—'}
                </span>
              </div>
              <span className={`px-2.5 py-1 rounded text-[11px] font-black uppercase tracking-wider shadow-xs ${isBtcAboveP2B ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white'}`}>
                {isBtcAboveP2B ? '▲ ABOVE P2B (YES)' : '▼ BELOW P2B (NO)'}
              </span>
            </div>
          </div>

          <div className="mt-2.5 pt-2 border-t border-slate-100 flex justify-between items-center text-[10px] font-mono text-slate-500">
            <span className="text-slate-400 uppercase font-sans font-bold text-[9px]">Market Condition</span>
            <span className="font-bold text-slate-700">{isBtcAboveP2B ? 'Bullish (Strike Advantage YES)' : 'Bearish (Strike Advantage NO)'}</span>
          </div>
        </div>

        {/* CENTER (MIDDLE): PREDICTION PROBABILITIES (YES vs NO) */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-4 flex flex-col justify-between">
          <div>
            <div className="flex justify-between items-center mb-2.5">
              <h2 className="text-xs font-black text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-blue-500" />
                <span>PREDICTION PROBABILITIES</span>
              </h2>
              {isLocked ? (
                <span className="text-[10px] bg-amber-100 text-amber-900 px-2 py-0.5 rounded font-black border border-amber-300 flex items-center gap-1">
                  <Lock className="w-3 h-3" /> DIRECTION LOCKED (SESSION)
                </span>
              ) : (
                <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-bold border border-slate-200 font-mono">
                  CLOB FEED
                </span>
              )}
            </div>

            {/* YES vs NO Cards */}
            <div className="grid grid-cols-2 gap-2.5 mb-2.5">
              {/* YES / UP Card */}
              <div className={`p-3 rounded-xl border-2 transition-all ${predictedSide === 'YES' ? 'bg-emerald-50/70 border-emerald-400 ring-2 ring-emerald-200' : 'bg-slate-50/60 border-slate-200'}`}>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-[11px] font-black tracking-wider text-emerald-800 uppercase flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                    YES (UP)
                  </span>
                  {predictedSide === 'YES' && (
                    <span className="text-[9px] bg-emerald-600 text-white font-black px-1.5 py-0.5 rounded uppercase flex items-center gap-0.5">
                      {isLocked ? '🔒 LOCKED TARGET' : 'TARGET'}
                    </span>
                  )}
                </div>
                <div className="text-3xl font-black text-emerald-600 font-mono tracking-tight my-0.5">
                  {finalYesPct}%
                </div>
                <div className="mt-2 pt-1.5 border-t border-slate-200/80 flex justify-between text-[10px] font-mono text-slate-500">
                  <span>Price: <strong className="text-slate-800">${fmt4(yesVal)}</strong></span>
                  <span>Score: <strong className="text-emerald-700">{typeof yesScore === 'number' ? yesScore.toFixed(1) : yesScore}</strong></span>
                </div>
              </div>

              {/* NO / DOWN Card */}
              <div className={`p-3 rounded-xl border-2 transition-all ${predictedSide === 'NO' ? 'bg-rose-50/70 border-rose-400 ring-2 ring-rose-200' : 'bg-slate-50/60 border-slate-200'}`}>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-[11px] font-black tracking-wider text-rose-800 uppercase flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span>
                    NO (DOWN)
                  </span>
                  {predictedSide === 'NO' && (
                    <span className="text-[9px] bg-rose-600 text-white font-black px-1.5 py-0.5 rounded uppercase flex items-center gap-0.5">
                      {isLocked ? '🔒 LOCKED TARGET' : 'TARGET'}
                    </span>
                  )}
                </div>
                <div className="text-3xl font-black text-rose-600 font-mono tracking-tight my-0.5">
                  {finalNoPct}%
                </div>
                <div className="mt-2 pt-1.5 border-t border-slate-200/80 flex justify-between text-[10px] font-mono text-slate-500">
                  <span>Price: <strong className="text-slate-800">${fmt4(noVal)}</strong></span>
                  <span>Score: <strong className="text-rose-700">{typeof noScore === 'number' ? noScore.toFixed(1) : noScore}</strong></span>
                </div>
              </div>
            </div>

            {/* Split Ratio Bar */}
            <div className="space-y-1 mb-2.5">
              <div className="flex justify-between text-[10px] font-bold tracking-wider uppercase">
                <span className="text-emerald-700 font-mono">YES {finalYesPct}%</span>
                <span className="text-slate-400 text-[9px]">SPLIT</span>
                <span className="text-rose-700 font-mono">NO {finalNoPct}%</span>
              </div>
              <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden flex shadow-inner">
                <div className="bg-emerald-500 h-full transition-all duration-500" style={{ width: `${finalYesPct}%` }} />
                <div className="bg-rose-500 h-full transition-all duration-500" style={{ width: `${finalNoPct}%` }} />
              </div>
            </div>
          </div>

          {/* Direction Signal Banner */}
          {isLocked ? (
            <div className={`p-2.5 rounded-xl border flex items-center justify-between shadow-xs ${predictedSide === 'YES' ? 'bg-emerald-50 border-emerald-300 text-emerald-900' : 'bg-rose-50 border-rose-300 text-rose-900'}`}>
              <div className="flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5 text-amber-700" />
                <div>
                  <span className="text-[10px] font-black uppercase tracking-wider block">DIRECTION LOCKED</span>
                  <span className="text-[9px] text-slate-500 block">Fixed for session · No switching</span>
                </div>
              </div>
              <span className={`px-2 py-0.5 rounded text-xs font-black uppercase flex items-center gap-1 ${predictedSide === 'YES' ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white'}`}>
                <span>🔒</span> ACTIVE {predictedSide === 'YES' ? 'BUY YES (UP)' : 'BUY NO (DOWN)'}
              </span>
            </div>
          ) : (
            <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-200 flex items-center justify-between">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">DIRECTION SIGNAL</span>
              <span className={`px-2 py-0.5 rounded text-xs font-black uppercase ${predictedSide === 'YES' ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white'}`}>
                PREDICT {predictedSide === 'YES' ? '▲ BUY YES' : '▼ BUY NO'}
              </span>
            </div>
          )}
        </div>

        {/* CORNER 2 (RIGHT): ACTIVE TRADE & MARKET MOMENTUM */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-4 flex flex-col justify-between">
          <div>
            <div className="flex justify-between items-center mb-2.5">
              <h2 className="text-xs font-black text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-emerald-500" />
                <span>ACTIVE TRADE & MOMENTUM</span>
              </h2>
              <span className="text-[10px] bg-blue-50 text-blue-700 px-2 py-0.5 rounded font-bold border border-blue-200 font-mono">
                EXECUTION
              </span>
            </div>

            {/* Active Trade Box */}
            <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 mb-2.5">
              <div className="flex justify-between items-center mb-1">
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">CURRENT POSITION</span>
                {isTradeOpen ? (
                  <span className="px-2 py-0.5 rounded-full text-[9px] font-black bg-blue-100 text-blue-800 border border-blue-200 animate-pulse">
                    ● IN PROGRESS
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-slate-200 text-slate-600">
                    AWAITING ENTRY
                  </span>
                )}
              </div>

              {isTradeOpen ? (
                <div className="space-y-1.5 mt-1 font-mono text-xs">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Direction:</span>
                    <strong className={lockedSide === 'YES' ? 'text-emerald-600 font-black' : 'text-rose-600 font-black'}>
                      🔒 BUY {lockedSide} ({lockedDir})
                    </strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Entry Price:</span>
                    <strong className="text-slate-800">${fmt4(trade.entry_price)}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Stop / Target:</span>
                    <strong className="text-slate-700">${fmt4(trade.entry_stop_price || trade.stop_loss_price)} / ${fmt4(trade.entry_target_price || trade.take_profit_price)}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Position Size:</span>
                    <strong className="text-slate-800">${fmt4(trade.position_size)}</strong>
                  </div>
                  <div className="flex justify-between pt-1 border-t border-slate-200">
                    <span className="text-slate-500">Unrealized P&L:</span>
                    <strong className={tradeUnrealized >= 0 ? 'text-emerald-600 font-black' : 'text-rose-600 font-black'}>
                      {fmtUsd(tradeUnrealized)}
                    </strong>
                  </div>
                  {/* SMART STOP-LOSS / EXIT DECISION STATE BANNER */}
                  {trade.exit_decision_state === 'EXIT_REVIEW' ? (
                    <div className="mt-2 p-2.5 bg-amber-500/10 border border-amber-500/40 rounded-xl font-sans">
                      <div className="flex items-center justify-between text-amber-500 font-black text-[11px] uppercase tracking-wide">
                        <span className="flex items-center gap-1.5">
                          <AlertTriangle className="w-4 h-4 animate-bounce text-amber-500" />
                          <span>⚠️ SOFT STOP TOUCHED — ANALYZING</span>
                        </span>
                        <span className="px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400 font-mono font-black text-[10px] animate-pulse">
                          {trade.confirmation_seconds_elapsed != null ? `${trade.confirmation_seconds_elapsed}s` : '0s'} / {trade.confirmation_seconds_total || 10}s
                        </span>
                      </div>
                      <div className="mt-1 text-[10px] text-amber-700 font-medium">
                        Confirmation grace period in progress. Bot is evaluating noise vs thesis failure.
                      </div>
                      <div className="mt-1 pt-1 border-t border-amber-500/20 flex justify-between items-center text-[9px] font-mono text-amber-800">
                        <span>Failure Score: <strong>{trade.thesis_failure_score != null ? `${trade.thesis_failure_score}/100` : '—'}</strong></span>
                        <span className="truncate max-w-[170px]" title={trade.last_exit_review_reason || 'Soft stop threshold breached'}>
                          {trade.last_exit_review_reason || 'Soft stop breached'}
                        </span>
                      </div>
                    </div>
                  ) : trade.exit_decision_state === 'CONFIRMED_EXIT' ? (
                    <div className="mt-2 p-2.5 bg-rose-500/10 border border-rose-500/40 rounded-xl font-sans">
                      <div className="flex items-center justify-between text-rose-500 font-black text-[11px] uppercase tracking-wide">
                        <span className="flex items-center gap-1.5">
                          <AlertTriangle className="w-4 h-4 text-rose-500" />
                          <span>🚨 THESIS FAILED — EXITING</span>
                        </span>
                        <span className="px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 font-mono font-black text-[10px]">
                          Score: {trade.thesis_failure_score != null ? `${trade.thesis_failure_score}/100` : '>=60'}
                        </span>
                      </div>
                      <div className="mt-1 text-[10px] text-rose-700 font-medium">
                        Persistent thesis invalidation confirmed across multi-factor evaluation.
                      </div>
                    </div>
                  ) : trade.exit_decision_state === 'HARD_EXIT' ? (
                    <div className="mt-2 p-2.5 bg-rose-600/10 border border-rose-600/50 rounded-xl font-sans">
                      <div className="flex items-center justify-between text-rose-600 font-black text-[11px] uppercase tracking-wide">
                        <span className="flex items-center gap-1.5">
                          <ShieldAlert className="w-4 h-4 text-rose-600" />
                          <span>🛑 HARD SAFETY STOP — IMMEDIATE EXIT</span>
                        </span>
                        <span className="px-2 py-0.5 rounded-full bg-rose-600/20 text-rose-500 font-mono font-black text-[10px]">
                          Floor: ${fmt4(trade.hard_stop_price)}
                        </span>
                      </div>
                      <div className="mt-1 text-[10px] text-rose-700 font-medium">
                        Catastrophic risk floor or daily risk budget breach triggered.
                      </div>
                    </div>
                  ) : (
                    <div className="mt-2 p-2 bg-emerald-500/10 border border-emerald-500/30 rounded-xl font-sans">
                      <div className="flex items-center justify-between text-emerald-600 font-bold text-[10px] uppercase tracking-wide">
                        <span className="flex items-center gap-1.5">
                          <Shield className="w-3.5 h-3.5 text-emerald-500" />
                          <span>✅ THESIS STILL VALID — HOLDING</span>
                        </span>
                        <span className="text-[9px] font-mono text-emerald-700 font-semibold">
                          Score: {trade.thesis_failure_score != null ? `${trade.thesis_failure_score}/100` : '0/100'}
                        </span>
                      </div>
                    </div>
                  )}

                  <div className="text-[10px] text-slate-400 font-sans pt-0.5">
                    Thesis locked at {fmtDate(trade.prediction_locked_at || trade.entry_time)}
                  </div>

                  {/* Manual Close Trade Button */}
                  <button
                    onClick={handleCloseTrade}
                    disabled={isClosing}
                    className="mt-2.5 w-full bg-rose-600 hover:bg-rose-700 active:scale-[0.99] disabled:opacity-50 text-white font-black text-xs py-2 px-3 rounded-xl shadow-xs transition-all flex items-center justify-center gap-1.5 cursor-pointer font-sans"
                  >
                    {isClosing ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Closing Position...</span>
                      </>
                    ) : (
                      <>
                        <XCircle className="w-3.5 h-3.5" />
                        <span>CLOSE TRADE NOW</span>
                      </>
                    )}
                  </button>
                  {closeError && (
                    <p className="text-[10px] text-rose-600 font-sans text-center mt-1">
                      {closeError}
                    </p>
                  )}
                </div>
              ) : (
                <div className="py-3 text-center text-slate-400 text-xs font-sans">
                  No active trade right now. Bot evaluates each 5M window for optimal entry edge.
                </div>
              )}
            </div>

            {/* Momentum & Engine Evaluation */}
            <div className="space-y-1.5">
              <div className="p-2 bg-slate-50 rounded-lg border border-slate-100 flex items-center justify-between text-xs">
                <span className="text-[10px] text-slate-500 font-medium">Fast Momentum:</span>
                <span className={`font-black font-mono ${rawMomentum >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {rawMomentum >= 0 ? '▲ +' : '▼ '}{rawMomentum.toFixed(2)}
                </span>
              </div>
              <div className="p-2 bg-slate-50 rounded-lg border border-slate-100 flex items-center justify-between text-xs">
                <span className="text-[10px] text-slate-500 font-medium">Expected Edge:</span>
                <span className="font-black font-mono text-blue-600">
                  {netEdge != null ? fmtPct(netEdge * 100) : '2.84%'}
                </span>
              </div>
            </div>
          </div>

          <div className="mt-2.5 pt-2 border-t border-slate-100 flex justify-between items-center text-[10px] font-mono text-slate-500">
            <span className="text-slate-400 uppercase font-sans font-bold text-[9px]">Execution Mode</span>
            <span className="font-bold text-slate-700">
              Fixed ${targetSettings?.tp_dollar ? Number(targetSettings.tp_dollar).toFixed(2) : '2.00'} TP / ${targetSettings?.sl_dollar ? Number(targetSettings.sl_dollar).toFixed(2) : '10.00'} SL ($10 / trade)
            </span>
          </div>
        </div>

      </div>

      {/* 4. ADJUSTABLE RESIZABLE SPLIT: CATEGORIZED TRADE HISTORY & SKIPPED TRADES AUDIT LOG */}
      <ResizableHistoryLogsSplit refreshTrigger={refreshTrigger} instanceId={selectedInstance} />
    </div>
  );
}

export default function BTC5M() {
  return (
    <ErrorBoundary>
      <InnerBTC5M />
    </ErrorBoundary>
  );
}
