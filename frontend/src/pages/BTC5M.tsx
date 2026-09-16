import React, { useState, useEffect } from 'react';
import { useApi } from '../hooks/useApi';
import { RefreshCw, Clock, BookOpen, Shield } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';

class ErrorBoundary extends React.Component<{children: React.ReactNode}, {hasError: boolean, error: any}> {
  constructor(props: any) { super(props); this.state = { hasError: false, error: null }; }
  static getDerivedStateFromError(error: any) { return { hasError: true, error }; }
  render() {
    if (this.state.hasError) return <div className="p-8 bg-red-50 text-red-900 border border-red-200 rounded-xl m-8"><h1 className="text-2xl font-bold mb-4">React Crashed</h1><pre className="whitespace-pre-wrap font-mono text-xs">{this.state.error?.toString() + '\n' + this.state.error?.stack}</pre></div>;
    return this.props.children;
  }
}

function fmt4(v: number | null | undefined) { return v != null ? v.toFixed(4) : '—'; }
function fmtPct(v: number | null | undefined) { return v != null ? `${v.toFixed(2)}%` : '—'; }
function fmtUsd(v: number | null | undefined) {
  if (v == null) return '—';
  return (v >= 0 ? '+$' : '-$') + Math.abs(v).toFixed(2);
}
function fmtCurrency(v: number | null | undefined) {
  if (v == null) return '—';
  return '$' + v.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function LoadingState() {
  return (
    <div className="flex justify-center items-center h-64 bg-white rounded-xl border border-slate-200">
      <RefreshCw className="w-8 h-8 text-blue-500 animate-spin" />
    </div>
  );
}

// Stats Components
function StatsHeader({ data, tradeUnrealized }: { data: any, tradeUnrealized: number }) {
    if (!data) return null;
    const total_pnl = data.realized_pnl + tradeUnrealized;
    const stats = [
      { label: 'TOTAL TRADES', value: data.total_trades ?? 0 },
      { label: 'OPEN TRADES', value: data.open_trades ?? 0 },
      { label: 'CLOSED TRADES', value: data.closed_trades ?? 0 },
      { label: 'WINS', value: data.wins ?? 0 },
      { label: 'LOSSES', value: data.losses ?? 0 },
      { label: 'WIN RATE', value: data.closed_trades > 0 ? fmtPct(data.win_rate) : '—' },
      { label: 'AVG WIN', value: '+' + fmtUsd(Math.abs(data.avg_winning_trade)).replace('+','').replace('-',''), isString: true },
      { label: 'AVG LOSS', value: '-' + fmtUsd(Math.abs(data.avg_losing_trade)).replace('+','').replace('-',''), isString: true },
      { label: 'ACTUAL R:R', value: data.actual_historical_rr ? `1:${data.actual_historical_rr.toFixed(2)}` : '—', isString: true },
      { label: 'PROFIT FACTOR', value: data.profit_factor ? data.profit_factor.toFixed(2) : '—', isString: true },
      { label: 'EXPECTANCY', value: fmtUsd(data.expectancy), isString: true },
      { label: 'TOTAL P&L', value: fmtUsd(total_pnl), isString: true },
    ];
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-12 gap-3 mb-6">
        {stats.map((s, i) => (
            <div key={i} className="bg-white p-3 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
              <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1">{s.label}</span>
              <span className={`text-lg font-black tracking-tight ${s.isString ? (s.value.toString().startsWith('-') ? 'text-rose-600' : (s.value.toString().startsWith('+') ? 'text-emerald-600' : 'text-slate-800')) : 'text-slate-800'}`}>
                {s.value}
              </span>
            </div>
        ))}
      </div>
    );
}

// Chainlink RPC Hook for BTC Price
function useChainlinkLive(currentMarketStartTime: string | undefined, backendBtcPrice: number | null, backendPriceToBeat: number | null) {
  const [btcChartData, setBtcChartData] = useState<any[]>([]);
  const [lastUpdate, setLastUpdate] = useState<number>(Date.now());

  useEffect(() => {
    setBtcChartData([]);
  }, [currentMarketStartTime]);

  useEffect(() => {
    if (backendBtcPrice !== null && backendBtcPrice !== undefined) {
      const t = setInterval(() => {
        setLastUpdate(Date.now());
        setBtcChartData(old => {
          const now = new Date().toLocaleTimeString();
          const last = old[old.length - 1];
          if (last && last.time === now) {
              const updatedLast = { ...last, price: backendBtcPrice };
              const newOld = [...old];
              newOld[newOld.length - 1] = updatedLast;
              return newOld;
          }
          return [...old.slice(-60), { time: now, price: backendBtcPrice }];
        });
      }, 1000);
      return () => clearInterval(t);
    }
  }, [backendBtcPrice]);

  return { btcPrice: backendBtcPrice, priceToBeat: backendPriceToBeat, btcChartData, lastUpdate };
}

// Polymarket CLOB WebSocket Hook
function usePolymarketLive(yesToken: string | undefined, noToken: string | undefined) {
  const [livePrices, setLivePrices] = useState<{ yes: number | null, no: number | null, suspended: boolean }>({ yes: null, no: null, suspended: false });
  const [chartData, setChartData] = useState<any[]>([]);

  useEffect(() => {
    setChartData([]);
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
              setChartData(old => {
                const now = new Date().toLocaleTimeString();
                const last = old[old.length - 1];
                if (last && last.time === now) {
                   const updatedLast = { ...last, YES: yes, NO: no };
                   const newOld = [...old];
                   newOld[newOld.length - 1] = updatedLast;
                   return newOld;
                }
                const next = [...old, { time: now, YES: yes, NO: no }];
                return next.slice(-60);
              });
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
      clearInterval(keepAlive);
      if (ws) ws.close();
    };
  }, [yesToken, noToken]);
  return { livePrices, probChartData: chartData };
}

function BtcChart({ data, p2b }: { data: any[], p2b: number | null }) {
  if (!data || data.length === 0) return <div className="text-slate-400 text-xs text-center py-4">Waiting for Chainlink feed...</div>;
  const minPrice = Math.min(...data.map(d => d.price));
  const maxPrice = Math.max(...data.map(d => d.price));
  const domainMin = p2b ? Math.min(minPrice, p2b) - 10 : minPrice - 10;
  const domainMax = p2b ? Math.max(maxPrice, p2b) + 10 : maxPrice + 10;
  return (
    <div className="h-48 w-full mt-2">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
          <XAxis dataKey="time" hide />
          <YAxis domain={[domainMin, domainMax]} tick={{ fontSize: 10, fill: '#94a3b8' }} tickCount={5} tickFormatter={(v) => '$'+v.toFixed(0)} />
          <Tooltip contentStyle={{ fontSize: '12px', borderRadius: '8px' }} formatter={(val: any) => '$' + Number(val).toFixed(2)} />
          {p2b && <ReferenceLine y={p2b} stroke="#fbbf24" strokeDasharray="3 3" label={{ position: 'top', value: 'Price to Beat', fill: '#fbbf24', fontSize: 10 }} />}
          <Line type="monotone" dataKey="price" name="BTC/USD" stroke="#3b82f6" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function ProbChart({ data }: { data: any[] }) {
  if (!data || data.length === 0) return <div className="text-slate-400 text-xs text-center py-4">Waiting for live CLOB stream...</div>;
  return (
    <div className="h-40 w-full mt-2">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
          <XAxis dataKey="time" hide />
          <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: '#94a3b8' }} tickCount={5} />
          <Tooltip contentStyle={{ fontSize: '12px', borderRadius: '8px' }} />
          <ReferenceLine y={0.5} stroke="#cbd5e1" strokeDasharray="3 3" />
          <Line type="stepAfter" dataKey="YES" name="YES (UP) Prob" stroke="#10b981" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line type="stepAfter" dataKey="NO" name="NO (DOWN) Prob" stroke="#ef4444" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function useBTC5MStatus() {
  const [data, setData] = useState<any>({ current_market: null, next_market: null, open_trade: null });
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let mounted = true;
    const fetchStatus = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/btc5m/status');
        const json = await res.json();
        if (mounted) { setData(json); setLoading(false); }
      } catch (e) {
        if (mounted) setLoading(false);
      }
    };
    fetchStatus();
    const timer = setInterval(fetchStatus, 1000);
    return () => { mounted = false; clearInterval(timer); };
  }, []);
  return { statusData: data, statusLoading: loading };
}

function InnerBTC5M() {
  const { statusData, statusLoading } = useBTC5MStatus();
  const { data: statsData } = useApi<any>('/btc5m/stats', null);
  const { data: tradesData } = useApi<any>('/btc5m/trades?limit=100', null);
  
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const current = statusData?.current_market;
  const next = statusData?.next_market;
  const trade = statusData?.open_trade;
  
  const { btcPrice, priceToBeat, btcChartData, lastUpdate } = useChainlinkLive(current?.start_time, statusData?.chainlink_btc_usd, statusData?.price_to_beat);
  const { livePrices, probChartData } = usePolymarketLive(current?.yes_token_id, current?.no_token_id);

  // Hooks must always be called before any early returns
  const [isToggling, setIsToggling] = useState(false);

  const toggleTrading = async (targetActive: boolean) => {
    if (isToggling) return;
    setIsToggling(true);
    try {
      await fetch('http://127.0.0.1:8000/api/btc5m/toggle_trading', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: targetActive })
      });
      window.location.reload();
    } catch (e) {
      console.error(e);
    } finally {
      setIsToggling(false);
    }
  };

  if (statusLoading) return <div className="p-12"><LoadingState /></div>;

  let countdownDisplay = 'RESOLVING...';
  if (current?.end_time) {
    const remaining = Math.floor((new Date(current.end_time + "Z").getTime() - now) / 1000);
    if (remaining > 0) {
      const m = Math.floor(remaining / 60);
      const s = Math.floor(remaining % 60);
      countdownDisplay = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
  }

  const isTradingActive = statusData?.trading_active ?? false;


  const dispYes = livePrices.yes !== null ? livePrices.yes : current?.best_bid;
  const dispNo = livePrices.no !== null ? livePrices.no : current?.best_ask;
  
  let tradePrice: number | null = null;
  if (trade && trade.status === 'OPEN') {
      const isYes = trade.side === 'BUY';
      const lp = isYes ? livePrices.yes : livePrices.no;
      if (lp !== null && lp > 0) {
          tradePrice = lp;
      } else if (trade.current_price !== null && trade.current_price > 0) {
          tradePrice = trade.current_price;
      }
  }
  let tradeUnrealized = (tradePrice !== null && trade && trade.status === 'OPEN') ? (tradePrice - trade.entry_price) * trade.quantity : 0;

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      <div className="flex items-start justify-between mb-2">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
            <span className="text-2xl">⚡</span> BTC 5M Real-Time Dashboard
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Polymarket CLOB + Chainlink Oracle Integration
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex bg-slate-100 p-1 rounded-lg border border-slate-200 items-center gap-1">
            <button
              onClick={() => toggleTrading(true)}
              disabled={isTradingActive || isToggling}
              className={`px-4 py-2 rounded-md text-xs font-black tracking-wider flex items-center gap-2 transition-all disabled:opacity-40 disabled:cursor-not-allowed ${isTradingActive ? 'bg-emerald-500 text-white shadow-sm' : 'text-slate-500 hover:bg-white hover:text-slate-800'}`}
            >
              <span className={`w-2 h-2 rounded-full ${isTradingActive ? 'bg-white animate-pulse' : 'bg-slate-400'}`}></span>
              START BOT
            </button>
            <button
              onClick={() => toggleTrading(false)}
              disabled={!isTradingActive || isToggling}
              className={`px-4 py-2 rounded-md text-xs font-black tracking-wider flex items-center gap-2 transition-all disabled:opacity-40 disabled:cursor-not-allowed ${!isTradingActive ? 'bg-rose-500 text-white shadow-sm' : 'text-slate-500 hover:bg-white hover:text-slate-800'}`}
            >
              <span className={`w-2 h-2 rounded-full ${!isTradingActive ? 'bg-white' : 'bg-slate-400'}`}></span>
              STOP BOT
            </button>
          </div>
          <div className={`px-3 py-1.5 rounded-lg text-xs font-black tracking-widest border ${isTradingActive ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-slate-50 border-slate-200 text-slate-500'}`}>
            {isTradingActive ? '● RUNNING' : '● STOPPED'}
          </div>
          <div className="bg-amber-50 border border-amber-200 text-amber-700 px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-2 shadow-sm">
            <Shield className="w-4 h-4" /> LIVE TRADING HARD-DISABLED
          </div>
        </div>
      </div>

      <StatsHeader data={statsData} tradeUnrealized={tradeUnrealized} />

      {current && (
         <div className="bg-blue-50 border border-blue-200 p-4 rounded-xl flex items-center justify-between mb-4">
            <div>
              <p className="text-xs font-bold text-blue-600 uppercase tracking-wider">Currently Active Market</p>
              <p className="text-xl font-bold text-slate-800">{current.question}</p>
            </div>
            <div className="text-right">
              <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Time Remaining</p>
              <p className="text-2xl font-black font-mono tracking-tighter text-blue-900">{countdownDisplay}</p>
            </div>
         </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden p-6 relative flex flex-col justify-between">
          <div>
              <h2 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-4 flex justify-between items-center">
                <span>BTC/USD — LIVE</span>
                <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-bold border border-slate-200">CHAINLINK ORACLE</span>
              </h2>
              <div className="space-y-3 font-mono text-sm">
                <div className="flex justify-between">
                  <span className="text-slate-500">Current BTC Price:</span>
                  <span className="font-bold">{btcPrice ? fmtCurrency(btcPrice) : 'DATA UNAVAILABLE'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Price to Beat (Resolution TWAP):</span>
                  <span className="font-bold text-amber-600">{priceToBeat ? fmtCurrency(priceToBeat) : 'DATA UNAVAILABLE'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Difference:</span>
                  <span className={`font-bold ${(btcPrice && priceToBeat) ? ((btcPrice - priceToBeat) >= 0 ? 'text-emerald-600' : 'text-rose-600') : 'text-slate-400'}`}>
                     {(btcPrice && priceToBeat) ? ((btcPrice - priceToBeat) >= 0 ? '+' : '-') + fmtCurrency(Math.abs(btcPrice - priceToBeat)) : 'DATA UNAVAILABLE'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Direction:</span>
                  <span className={`font-black ${(btcPrice && priceToBeat) ? ((btcPrice - priceToBeat) >= 0 ? 'text-emerald-600' : 'text-rose-600') : 'text-slate-400'}`}>
                     {(btcPrice && priceToBeat) ? ((btcPrice - priceToBeat) >= 0 ? '▲ UP' : '▼ DOWN') : 'DATA UNAVAILABLE'}
                  </span>
                </div>
              </div>
          </div>
          <BtcChart data={btcChartData} p2b={priceToBeat} />
          <div className="mt-4 pt-4 border-t border-slate-100 text-[10px] text-slate-400 text-right uppercase font-bold tracking-wider">
             Updated: {Math.max(0, Math.floor((now - lastUpdate)/1000))} seconds ago
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden p-6 relative">
          <h2 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-4 flex justify-between items-center">
            <span>POLYMARKET PROBABILITY — LIVE</span>
            <span className="text-[10px] bg-purple-100 text-purple-700 px-2 py-0.5 rounded font-bold border border-purple-200 animate-pulse">CLOB WS CONNECTED</span>
          </h2>
          <div className="flex items-center justify-between mb-2 px-8">
             <div className="text-center">
               <p className="text-3xl font-black text-emerald-600 font-mono tracking-tighter">
                 {(!dispYes || dispYes <= 0 || livePrices.suspended) ? 'RES' : fmt4(dispYes)}
               </p>
               <p className="text-xs font-bold text-emerald-600 mt-1">YES / UP</p>
             </div>
             <div className="text-center">
               <p className="text-3xl font-black text-rose-600 font-mono tracking-tighter">
                 {(!dispNo || dispNo <= 0 || livePrices.suspended) ? 'RES' : fmt4(dispNo)}
               </p>
               <p className="text-xs font-bold text-rose-600 mt-1">NO / DOWN</p>
             </div>
          </div>
          <ProbChart data={probChartData} />
        </div>
      </div>
      
      <div className="bg-white rounded-xl border-2 border-emerald-200 shadow-sm p-6 relative">
          <div className="absolute top-0 right-0 p-3">
             <div className="flex items-center gap-2 px-3 py-1 bg-red-100 text-red-700 rounded-full font-extrabold animate-pulse text-[10px]">
               <span className="w-2 h-2 rounded-full bg-red-500"></span> REAL-TIME TRACKING
             </div>
          </div>
          <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-4">ACTIVE PAPER TRADE</h3>
          {trade && trade.status === 'OPEN' ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-8 gap-4 text-sm">
              <div><span className="block text-slate-400 text-[10px] uppercase font-bold">Prediction</span><span className="font-black text-lg text-emerald-600">YES (UP)</span></div>
              <div><span className="block text-slate-400 text-[10px] uppercase font-bold">Entry Price</span><span className="font-bold text-slate-700 text-lg">${fmt4(trade.entry_price)}</span></div>
              <div><span className="block text-slate-400 text-[10px] uppercase font-bold">Current Price</span><span className="font-bold text-slate-700 text-lg">{tradePrice !== null ? '$'+fmt4(tradePrice) : 'RESOLVING'}</span></div>
              <div><span className="block text-slate-400 text-[10px] uppercase font-bold">Quantity</span><span className="font-bold text-slate-700 text-lg">{fmt4(trade.quantity)}</span></div>
              <div><span className="block text-slate-400 text-[10px] uppercase font-bold">Invested</span><span className="font-bold text-slate-700 text-lg">${fmt4(trade.position_size)}</span></div>
              <div><span className="block text-slate-400 text-[10px] uppercase font-bold">Unrealized P&L</span><span className={`font-bold text-lg ${tradeUnrealized >= 0 ? "text-emerald-600" : "text-rose-500"}`}>{fmtUsd(tradeUnrealized)}</span></div>
              <div><span className="block text-slate-400 text-[10px] uppercase font-bold">Time Remaining</span><span className="font-bold text-slate-700 text-lg font-mono">{countdownDisplay}</span></div>
              <div><span className="block text-slate-400 text-[10px] uppercase font-bold">Status</span><span className="font-bold text-blue-600 text-lg">OPEN</span></div>
            </div>
          ) : (
             <div className="text-center py-6 text-slate-400">
                <p className="font-medium text-lg">No active trade for this window.</p>
                <p className="text-xs mt-1">The strategy agent will automatically paper-trade when edge conditions are met.</p>
             </div>
          )}
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
          <h2 className="font-bold text-slate-800 flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-slate-400" /> PERMANENT TRADE HISTORY
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-slate-500 uppercase bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-6 py-3 font-semibold">Time</th>
                <th className="px-6 py-3 font-semibold">Market Window</th>
                <th className="px-6 py-3 font-semibold">Prediction</th>
                <th className="px-6 py-3 font-semibold">Status</th>
                <th className="px-6 py-3 font-semibold text-right">Entry</th>
                <th className="px-6 py-3 font-semibold text-right">Exit</th>
                <th className="px-6 py-3 font-semibold text-right">Invested</th>
                <th className="px-6 py-3 font-semibold text-right">Realized P&L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(!tradesData || !tradesData.trades || tradesData.trades.length === 0) && (
                <tr><td colSpan={8} className="px-6 py-8 text-center text-slate-400">No trades yet.</td></tr>
              )}
              {tradesData?.trades?.map((t: any) => (
                <tr key={t.id} className="hover:bg-slate-50/50 transition-colors">
                  <td className="px-6 py-3 font-mono text-xs text-slate-500">{new Date(t.entry_time + "Z").toLocaleString()}</td>
                  <td className="px-6 py-3 text-slate-700 font-medium truncate max-w-[200px]" title={t.question}>{t.question}</td>
                  <td className="px-6 py-3"><span className="text-xs font-black text-emerald-600 bg-emerald-50 px-2 py-1 rounded">YES (UP)</span></td>
                  <td className="px-6 py-3">
                    <span className={`text-[10px] font-bold px-2 py-1 rounded uppercase ${t.status === 'OPEN' ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-600'}`}>
                      {t.status} {t.status === 'CLOSED' ? (t.pnl > 0 ? 'WIN' : (t.pnl < 0 ? 'LOSS' : '')) : ''}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-right font-mono text-slate-600">${fmt4(t.entry_price)}</td>
                  <td className="px-6 py-3 text-right font-mono text-slate-600">{t.exit_price !== null ? '$'+fmt4(t.exit_price) : '—'}</td>
                  <td className="px-6 py-3 text-right font-mono text-slate-600">${fmt4(t.position_size)}</td>
                  <td className={`px-6 py-3 text-right font-mono font-bold ${t.pnl ? (t.pnl >= 0 ? 'text-emerald-600' : 'text-rose-600') : 'text-slate-400'}`}>
                    {t.pnl !== null ? fmtUsd(t.pnl) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      
      {next && (
         <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex justify-between items-center opacity-75 mt-6">
            <div className="flex items-center gap-3">
               <Clock className="w-5 h-5 text-slate-400" />
               <div>
                 <p className="text-xs font-bold text-slate-500 uppercase">NEXT SCHEDULED MARKET</p>
                 <p className="text-sm font-semibold text-slate-700">{next.question}</p>
               </div>
            </div>
            <p className="text-xs text-slate-400 font-mono bg-white px-2 py-1 border border-slate-200 rounded">
               Starts automatically at {new Date(next.start_time + "Z").toLocaleTimeString()}
            </p>
         </div>
      )}
    </div>
  );
}

export default function BTC5M() {
  return <ErrorBoundary><InnerBTC5M /></ErrorBoundary>;
}
