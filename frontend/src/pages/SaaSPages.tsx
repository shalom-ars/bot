import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useApi } from '../hooks/useApi';
import { Wallet, ShieldAlert, Crosshair, AlertTriangle, RefreshCw, TrendingUp, DollarSign, Activity, BookOpen } from 'lucide-react';
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts';

function ErrorState({ message, retry }: { message: string, retry?: () => void }) {
  return (
    <div className="bg-red-50 p-12 text-center rounded border border-red-200">
      <AlertTriangle className="mx-auto text-red-500 mb-2 w-8 h-8" />
      <p className="text-red-700 font-bold mb-2">BACKEND CONNECTION ERROR</p>
      <p className="text-sm text-red-600 mb-4">{message}</p>
      {retry && (
        <button onClick={retry} className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded font-medium flex items-center mx-auto gap-2">
          <RefreshCw className="w-4 h-4" /> Retry Connection
        </button>
      )}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="p-12 text-center text-slate-500 flex flex-col items-center">
      <RefreshCw className="w-8 h-8 animate-spin text-blue-500 mb-4" />
      <p>Loading real data...</p>
    </div>
  );
}

export function Portfolio() {
  const { data, loading, error } = useApi<any>('/users/portfolio', null);
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">SaaS Dashboard</h1>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}
      {!loading && !error && data && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-4 bg-white rounded shadow-sm border border-slate-200">
            <p className="text-sm text-slate-500">Paper Balance</p>
            <p className="text-xl font-bold">${data.current_balance?.toFixed(2)}</p>
          </div>
          <div className="p-4 bg-white rounded shadow-sm border border-slate-200">
            <p className="text-sm text-slate-500">Realized PnL</p>
            <p className="text-xl font-bold">${data.realized_pnl?.toFixed(2)}</p>
          </div>
          <div className="p-4 bg-white rounded shadow-sm border border-slate-200">
            <p className="text-sm text-slate-500">Exposure</p>
            <p className="text-xl font-bold">${data.exposure?.toFixed(2)}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export function Markets() {
  const [skip, setSkip] = useState(0);
  const limit = 50;
  const { data, loading, error } = useApi<{markets: any[], total: number}>(`/markets?skip=${skip}&limit=${limit}`, { markets: [], total: 0 });
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Tracked Markets</h1>
      {loading && skip === 0 && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}
      {!error && data && (
        <>
          <p className="text-slate-500 mb-4">Total active markets tracked: {data.total}</p>
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 divide-y overflow-hidden mb-4">
            {data.markets.length === 0 && !loading ? (
               <p className="p-6 text-slate-500 text-center">No active markets tracked.</p>
            ) : (
              data.markets.map(m => (
                <Link key={m.market_id} to={`/app/markets/${m.market_id}`} className="block p-4 hover:bg-slate-50">
                  <p className="font-semibold">{m.question}</p>
                  <p className="text-sm text-slate-500">Token: {m.token} | Spread: {(m.spread || 0).toFixed(4)}</p>
                </Link>
              ))
            )}
          </div>
          <div className="flex justify-between items-center mt-4">
            <button onClick={() => setSkip(Math.max(0, skip - limit))} disabled={skip === 0 || loading}
              className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded disabled:opacity-50 font-medium text-sm">
              Previous Page
            </button>
            <span className="text-sm text-slate-500">
              Showing {skip + 1} - {Math.min(skip + limit, data.total)} of {data.total}
            </span>
            <button onClick={() => setSkip(skip + limit)} disabled={skip + limit >= data.total || loading}
              className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded disabled:opacity-50 font-medium text-sm">
              Next Page
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export function MarketDetail({ id }: { id?: string }) {
  const targetId = id || window.location.pathname.split('/').pop();
  const { data: market, loading, error } = useApi<any>(`/markets/${targetId}`, null);
  const { data: orderbook } = useApi<any>(`/markets/orderbook/${targetId}`, null);
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Market Detail</h1>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}
      {!loading && !error && market && (
        <div className="space-y-6">
          <div className="bg-white p-6 rounded shadow-sm border border-slate-200 space-y-4">
            <h2 className="text-xl font-bold">{market.market.question}</h2>
            <p className="text-slate-500 text-sm">Market ID: <span className="font-mono text-xs">{market.market.market_id}</span></p>
          </div>
          {orderbook && <OrderBookCard data={orderbook} />}
        </div>
      )}
    </div>
  );
}

/* ============ ORDER BOOK COMPONENT ============ */
function OrderBookCard({ data }: { data: any }) {
  if (!data || data.status === 'NO_DATA') {
    return (
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2"><BookOpen className="w-5 h-5" /> Order Book</h3>
        <div className="bg-slate-50 py-12 text-center rounded-lg border border-dashed border-slate-200">
          <p className="text-slate-400 font-medium">No liquidity / unavailable</p>
          <p className="text-xs text-slate-300 mt-1">No orderbook snapshots for this market</p>
        </div>
      </div>
    );
  }

  const spreadPct = data.spread_pct;
  const freshness = data.timestamp ? new Date(data.timestamp).toLocaleString() : 'N/A';

  return (
    <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2"><BookOpen className="w-5 h-5" /> Order Book</h3>
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-bold ${
            data.liquidity_status === 'HIGH' ? 'bg-emerald-100 text-emerald-700' :
            data.liquidity_status === 'MEDIUM' ? 'bg-amber-100 text-amber-700' :
            data.liquidity_status === 'LOW' ? 'bg-orange-100 text-orange-700' :
            'bg-red-100 text-red-700'
          }`}>{data.liquidity_status}</span>
          {data.trade_eligible ? (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-blue-100 text-blue-700">ELIGIBLE</span>
          ) : (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-slate-100 text-slate-500">INELIGIBLE</span>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <div className="bg-emerald-50 p-3 rounded-lg border border-emerald-100">
          <p className="text-xs text-emerald-600 font-semibold uppercase">Best Bid</p>
          <p className="text-xl font-extrabold text-emerald-700">{data.best_bid != null ? data.best_bid.toFixed(4) : '—'}</p>
          <p className="text-xs text-emerald-500 mt-0.5">Depth: {data.bid_size != null ? `$${data.bid_size.toFixed(0)}` : '—'}</p>
        </div>
        <div className="bg-rose-50 p-3 rounded-lg border border-rose-100">
          <p className="text-xs text-rose-600 font-semibold uppercase">Best Ask</p>
          <p className="text-xl font-extrabold text-rose-700">{data.best_ask != null ? data.best_ask.toFixed(4) : '—'}</p>
          <p className="text-xs text-rose-500 mt-0.5">Depth: {data.ask_size != null ? `$${data.ask_size.toFixed(0)}` : '—'}</p>
        </div>
        <div className="bg-slate-50 p-3 rounded-lg border border-slate-100">
          <p className="text-xs text-slate-500 font-semibold uppercase">Spread</p>
          <p className="text-xl font-extrabold text-slate-800">{data.spread != null ? data.spread.toFixed(4) : '—'}</p>
          <p className="text-xs text-slate-400 mt-0.5">{spreadPct != null ? `${spreadPct.toFixed(2)}%` : '—'}</p>
        </div>
        <div className="bg-slate-50 p-3 rounded-lg border border-slate-100">
          <p className="text-xs text-slate-500 font-semibold uppercase">Mid Price</p>
          <p className="text-xl font-extrabold text-slate-800">{data.price != null ? data.price.toFixed(4) : '—'}</p>
          <p className="text-xs text-slate-400 mt-0.5">Imbalance: {data.imbalance != null ? data.imbalance.toFixed(3) : '—'}</p>
        </div>
      </div>
      <div className="flex items-center justify-between text-xs text-slate-400 border-t border-slate-100 pt-3">
        <span>Last Update: {freshness}</span>
        <span>Latency: {data.latency_ms != null ? `${data.latency_ms}ms` : 'N/A'}</span>
        {data.ineligibility_reason && <span className="text-orange-400">{data.ineligibility_reason}</span>}
      </div>
    </div>
  );
}

export function OrderBook() {
  const { data: marketsData, loading, error } = useApi<{markets: any[]}>('/markets?limit=10', { markets: [] });
  const [selectedMarket, setSelectedMarket] = useState<string | null>(null);
  const { data: orderbook } = useApi<any>(selectedMarket ? `/markets/orderbook/${selectedMarket}` : '/markets/orderbook/none', null);

  useEffect(() => {
    if (marketsData?.markets?.length > 0 && !selectedMarket) {
      setSelectedMarket(marketsData.markets[0].market_id);
    }
  }, [marketsData, selectedMarket]);

  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Order Book</h1>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}
      {!loading && !error && marketsData && (
        <>
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <label className="text-sm font-semibold text-slate-600 block mb-2">Select Market</label>
            <select
              className="w-full p-2 border border-slate-300 rounded-lg text-sm"
              value={selectedMarket || ''}
              onChange={(e) => setSelectedMarket(e.target.value)}
            >
              {marketsData.markets.map(m => (
                <option key={m.market_id} value={m.market_id}>{m.question}</option>
              ))}
            </select>
          </div>
          {orderbook && <OrderBookCard data={orderbook} />}
        </>
      )}
    </div>
  );
}

/* ============ POSITIONS ============ */
export function Positions() {
  const { data, loading, error } = useApi<{positions: any[]}>('/users/positions', { positions: [] });
  const [livePrices, setLivePrices] = useState<Record<string, number>>({});

  useEffect(() => {
    const handleWsMessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'markets' && Array.isArray(msg.data)) {
           const newPrices = {...livePrices};
           msg.data.forEach((m: any) => {
              newPrices[m.market_id] = m.current_price;
           });
           setLivePrices(newPrices);
        }
      } catch (e) {}
    };
    window.addEventListener('ws-message', handleWsMessage as EventListener);
    return () => window.removeEventListener('ws-message', handleWsMessage as EventListener);
  }, [livePrices]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Open Positions</h1>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}
      {!loading && !error && data && (
        data.positions.length === 0 ? (
          <div className="bg-slate-50 py-20 text-center rounded-xl border border-slate-200">
             <Crosshair className="mx-auto text-slate-300 mb-4 w-12 h-12" />
             <p className="text-slate-500 font-bold text-lg tracking-tight">NO OPEN POSITIONS</p>
             <p className="text-sm text-slate-400 mt-1">Currently holding no risk.</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500">
                    <th className="p-4 font-semibold">Market Question</th>
                    <th className="p-4 font-semibold">Side</th>
                    <th className="p-4 font-semibold text-right">Entry</th>
                    <th className="p-4 font-semibold text-right">Current</th>
                    <th className="p-4 font-semibold text-right">Qty</th>
                    <th className="p-4 font-semibold text-right">Invested</th>
                    <th className="p-4 font-semibold text-right">Unrealized P&L</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.positions.map((p: any, i: number) => {
                    const currentPrice = livePrices[p.market_id] || p.current_price || p.entry_price;
                    let pnl = 0;
                    if (p.side === 'BUY_YES' || p.side === 'BUY') {
                        pnl = (currentPrice - p.entry_price) * p.quantity;
                    } else {
                        pnl = ((1.0 - currentPrice) - p.entry_price) * p.quantity;
                    }
                    const invested = p.entry_price * p.quantity;
                    const pnlPercent = invested > 0 ? (pnl / invested) * 100 : 0;
                    return (
                      <tr key={i} className="hover:bg-slate-50">
                        <td className="p-4">
                          <div className="font-semibold text-slate-900 max-w-sm">{p.market_question || 'Unknown Market'}</div>
                          <div className="text-xs text-slate-400 font-mono mt-0.5 truncate max-w-xs" title={p.market_id}>{p.token_id?.substring(0, 12)}...</div>
                        </td>
                        <td className="p-4">
                          <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-bold ${p.side === 'BUY' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
                            {p.side}
                          </span>
                        </td>
                        <td className="p-4 text-right font-medium text-slate-700">${p.entry_price.toFixed(4)}</td>
                        <td className="p-4 text-right font-medium text-slate-700">${currentPrice.toFixed(4)}</td>
                        <td className="p-4 text-right font-medium text-slate-700">{p.quantity.toFixed(2)}</td>
                        <td className="p-4 text-right font-bold text-slate-900">${invested.toFixed(2)}</td>
                        <td className={`p-4 text-right font-bold ${pnl > 0 ? 'text-emerald-500' : pnl < 0 ? 'text-rose-500' : 'text-slate-500'}`}>
                          {pnl > 0 ? '+' : ''}${pnl.toFixed(2)}
                          <span className="text-xs ml-1 font-semibold opacity-75">({pnlPercent > 0 ? '+' : ''}{pnlPercent.toFixed(1)}%)</span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )
      )}
    </div>
  );
}

/* ============ TRADES ============ */
export function Trades() {
  const { data, loading, error } = useApi<{trades: any[]}>('/users/trades', { trades: [] });
  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Trade History</h1>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}
      {!loading && !error && data && (
        data.trades.length === 0 ? (
          <div className="bg-slate-50 py-20 text-center rounded-xl border border-slate-200">
             <Wallet className="mx-auto text-slate-300 mb-4 w-12 h-12" />
             <p className="text-slate-500 font-bold text-lg tracking-tight">NO PAPER TRADES YET</p>
             <p className="text-sm text-slate-400 mt-1">No trades recorded in the database.</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500">
                    <th className="p-4 font-semibold">Time</th>
                    <th className="p-4 font-semibold">Market Question</th>
                    <th className="p-4 font-semibold">Side</th>
                    <th className="p-4 font-semibold text-right">Entry</th>
                    <th className="p-4 font-semibold text-right">Qty</th>
                    <th className="p-4 font-semibold text-center">Status</th>
                    <th className="p-4 font-semibold text-right">P&L</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.trades.map((t: any, i: number) => (
                    <tr key={i} className="hover:bg-slate-50">
                      <td className="p-4 text-sm text-slate-500 whitespace-nowrap">{t.entry_time ? new Date(t.entry_time).toLocaleString() : '—'}</td>
                      <td className="p-4">
                        <div className="font-semibold text-slate-900 max-w-sm">{t.market_question || 'Unknown Market'}</div>
                        <div className="text-xs text-slate-400 font-mono mt-0.5 truncate max-w-xs" title={t.market_id}>{t.token_id?.substring(0, 12)}...</div>
                      </td>
                      <td className="p-4">
                        <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-bold ${t.side === 'BUY' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
                          {t.side}
                        </span>
                      </td>
                      <td className="p-4 text-right font-medium text-slate-700">${t.entry_price?.toFixed(4)}</td>
                      <td className="p-4 text-right font-medium text-slate-700">{t.quantity?.toFixed(2)}</td>
                      <td className="p-4 text-center">
                        <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-bold ${
                          t.status === 'OPEN' ? 'bg-amber-100 text-amber-700' :
                          t.status === 'CLOSED' ? 'bg-emerald-100 text-emerald-700' :
                          'bg-slate-100 text-slate-700'
                        }`}>{t.status}</span>
                      </td>
                      <td className={`p-4 text-right font-bold ${(t.pnl || 0) > 0 ? 'text-emerald-500' : (t.pnl || 0) < 0 ? 'text-rose-500' : 'text-slate-400'}`}>
                        {t.status === 'CLOSED' && t.pnl != null ? (t.pnl > 0 ? `+$${t.pnl.toFixed(2)}` : `$${t.pnl.toFixed(2)}`) : '\u2014'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      )}
    </div>
  );
}

/* ============ SIGNALS ============ */
export function Signals() {
  const { data, loading, error } = useApi<{signals: any[], total: number}>('/signals?limit=50', { signals: [], total: 0 });
  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Signal Log</h1>
      <p className="text-sm text-slate-500">Total signals recorded: {data?.total || 0}</p>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}
      {!loading && !error && (
        data.signals.length === 0 ? (
          <div className="bg-slate-50 p-12 text-center rounded border border-slate-200">
             <Crosshair className="mx-auto text-slate-400 mb-2 w-8 h-8" />
             <p className="text-slate-500 font-medium">NO SIGNALS RECORDED</p>
          </div>
        ) : (
          <div className="space-y-3">
            {data.signals.map((s: any) => (
              <div key={s.id} className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="p-4 border-b border-slate-100 flex items-center justify-between">
                  <div>
                    <p className="font-bold text-slate-900 text-sm">{s.market_question || 'Unknown Market'}</p>
                    <p className="text-xs text-slate-400 mt-0.5">Signal #{s.id} | {s.timestamp ? new Date(s.timestamp).toLocaleString() : 'N/A'}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`inline-flex items-center px-2.5 py-1 rounded text-xs font-bold ${
                      s.signal_type === 'BUY' ? 'bg-emerald-100 text-emerald-700' :
                      s.signal_type === 'SELL' ? 'bg-rose-100 text-rose-700' :
                      'bg-slate-100 text-slate-600'
                    }`}>{s.signal_type}</span>
                    <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-blue-50 text-blue-700">{s.strategy}</span>
                  </div>
                </div>
                <div className="p-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3 text-xs">
                  <div><span className="text-slate-400 block">Market Prob</span><span className="font-bold text-slate-800">{s.market_prob?.toFixed(4) ?? '—'}</span></div>
                  <div><span className="text-slate-400 block">Model Prob</span><span className="font-bold text-slate-800">{s.model_prob?.toFixed(4) ?? '—'}</span></div>
                  <div><span className="text-slate-400 block">Fair Prob</span><span className="font-bold text-slate-800">{s.fair_probability?.toFixed(4) ?? '—'}</span></div>
                  <div><span className="text-slate-400 block">Raw Edge</span><span className={`font-bold ${(s.raw_edge || 0) > 0 ? 'text-emerald-600' : 'text-slate-800'}`}>{s.raw_edge?.toFixed(4) ?? '—'}</span></div>
                  <div><span className="text-slate-400 block">Net Edge</span><span className={`font-bold ${(s.net_edge || 0) > 0 ? 'text-emerald-600' : 'text-slate-800'}`}>{s.net_edge?.toFixed(4) ?? '—'}</span></div>
                  <div><span className="text-slate-400 block">Threshold</span><span className="font-bold text-slate-800">{s.threshold?.toFixed(4) ?? '—'}</span></div>
                  <div><span className="text-slate-400 block">Entry Price</span><span className="font-bold text-slate-800">{s.entry_price?.toFixed(4) ?? '—'}</span></div>
                  <div><span className="text-slate-400 block">Spread Cost</span><span className="font-bold text-slate-800">{s.spread_cost?.toFixed(4) ?? '—'}</span></div>
                  <div><span className="text-slate-400 block">Slippage</span><span className="font-bold text-slate-800">{s.slippage_cost?.toFixed(4) ?? '—'}</span></div>
                  <div><span className="text-slate-400 block">Fees</span><span className="font-bold text-slate-800">{s.fees?.toFixed(4) ?? '—'}</span></div>
                  <div><span className="text-slate-400 block">Confidence</span><span className="font-bold text-slate-800">{s.confidence?.toFixed(3) ?? '—'}</span></div>
                  <div><span className="text-slate-400 block">Uncertainty</span><span className="font-bold text-slate-800">{s.uncertainty?.toFixed(3) ?? '—'}</span></div>
                </div>
                <div className="px-4 pb-3 flex items-center gap-2 text-xs">
                  <span className="text-slate-400">Reason:</span>
                  <span className="text-slate-700 font-medium">{s.reason}</span>
                  <span className="ml-auto text-slate-400">{s.model_version} | Quality: {s.market_quality_status}</span>
                </div>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}

/* ============ PERFORMANCE ============ */
export function Performance() {
  const { data: perf, loading: perfLoading, error: perfError } = useApi<any>('/users/performance', null);
  const { data: portfolio, loading: portLoading, error: portError } = useApi<any>('/users/portfolio', null);
  const { data: tradesData } = useApi<any>('/users/trades?limit=100', { trades: [] });
  const { data: positionsData } = useApi<any>('/users/positions', { positions: [] });
  const [livePrices, setLivePrices] = useState<Record<string, number>>({});

  useEffect(() => {
    const handleWsMessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'markets' && Array.isArray(msg.data)) {
           const newPrices = {...livePrices};
           msg.data.forEach((m: any) => { newPrices[m.market_id] = m.current_price; });
           setLivePrices(newPrices);
        }
      } catch (e) {}
    };
    window.addEventListener('ws-message', handleWsMessage as EventListener);
    return () => window.removeEventListener('ws-message', handleWsMessage as EventListener);
  }, [livePrices]);

  const unrealizedPnl = (positionsData?.positions || []).reduce((acc: number, pos: any) => {
     const currentPrice = livePrices[pos.market_id] || pos.current_price || pos.entry_price;
     let posPnl = 0;
     if (pos.side === 'BUY_YES' || pos.side === 'BUY') {
         posPnl = (currentPrice - pos.entry_price) * pos.quantity;
     } else {
         posPnl = ((1.0 - currentPrice) - pos.entry_price) * pos.quantity;
     }
     return acc + posPnl;
  }, 0);

  const totalPnl = (portfolio?.realized_pnl || 0) + unrealizedPnl;
  const loading = perfLoading || portLoading;
  const error = perfError || portError;
  const pnlData = (tradesData?.trades || []).filter((t: any) => t.status === 'CLOSED').map((t: any, idx: number) => {
    return { name: `Trade ${idx+1}`, pnl: t.pnl };
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Performance Analytics</h1>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}
      {!loading && !error && perf && portfolio && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
             <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                <div className="text-slate-500 text-sm font-medium mb-1 flex items-center gap-2"><DollarSign className="w-4 h-4" /> Current Balance</div>
                <div className="text-2xl font-extrabold">${portfolio.current_balance?.toFixed(2)}</div>
             </div>
             <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                <div className="text-slate-500 text-sm font-medium mb-1 flex items-center gap-2"><TrendingUp className="w-4 h-4" /> Total P&L</div>
                <div className={`text-2xl font-extrabold ${totalPnl > 0 ? 'text-emerald-500' : totalPnl < 0 ? 'text-rose-500' : 'text-slate-900'}`}>
                   {totalPnl > 0 ? '+' : ''}${totalPnl.toFixed(2)}
                </div>
                <div className="text-xs text-slate-400 mt-1">Realized: ${portfolio.realized_pnl?.toFixed(2)} | Unrealized: ${unrealizedPnl.toFixed(2)}</div>
             </div>
             <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                <div className="text-slate-500 text-sm font-medium mb-1 flex items-center gap-2"><TargetIcon className="w-4 h-4" /> Win Rate</div>
                <div className="text-2xl font-extrabold">{perf.closed_trades > 0 ? `${perf.win_rate}%` : '\u2014'}</div>
                <div className="text-xs text-slate-400 mt-1">{perf.wins} Wins, {perf.losses} Losses</div>
             </div>
             <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                <div className="text-slate-500 text-sm font-medium mb-1 flex items-center gap-2"><Activity className="w-4 h-4" /> Trades</div>
                <div className="text-2xl font-extrabold">{perf.trades}</div>
                <div className="text-xs text-slate-400 mt-1">{positionsData?.positions?.length || 0} Open, {perf.closed_trades} Closed</div>
             </div>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
             <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                <h3 className="text-lg font-bold text-slate-900 mb-6">Trade Outcomes (P&L)</h3>
                <div className="h-64">
                   {pnlData.length > 0 ? (
                     <ResponsiveContainer width="100%" height="100%">
                       <BarChart data={pnlData}>
                         <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                         <XAxis dataKey="name" tick={{fontSize: 12, fill: '#64748b'}} axisLine={false} tickLine={false} />
                         <YAxis tick={{fontSize: 12, fill: '#64748b'}} axisLine={false} tickLine={false} tickFormatter={(val) => `$${val}`} />
                         <Tooltip cursor={{fill: '#f8fafc'}} contentStyle={{borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)'}} />
                         <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                           {pnlData.map((entry: any, index: number) => (
                             <Cell key={`cell-${index}`} fill={entry.pnl >= 0 ? '#10b981' : '#f43f5e'} />
                           ))}
                         </Bar>
                       </BarChart>
                     </ResponsiveContainer>
                   ) : (
                     <div className="h-full flex items-center justify-center border-2 border-dashed border-slate-100 rounded-lg bg-slate-50">
                        <p className="text-slate-400 font-medium text-sm">No closed trades yet.</p>
                     </div>
                   )}
                </div>
             </div>
             <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                <h3 className="text-lg font-bold text-slate-900 mb-6">Equity Curve</h3>
                <div className="h-64 flex items-center justify-center border-2 border-dashed border-slate-100 rounded-lg bg-slate-50">
                    <p className="text-slate-400 font-medium text-sm">No sufficient trading history yet.</p>
                </div>
             </div>
          </div>
        </>
      )}
    </div>
  );
}

function TargetIcon(props: any) {
  return <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>;
}

export function Risk() {
  const { data: risk, loading, error } = useApi<any>('/users/risk', null);
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Risk Management</h1>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}
      {!loading && !error && risk && (
        <div className="bg-white p-6 rounded shadow-sm border border-slate-200 space-y-2">
           <p>Status: <span className="font-bold">{risk.status || 'ACTIVE'}</span></p>
           <p>Current Exposure: ${risk.current_exposure || 0}</p>
           <p>Exposure Percent: {risk.exposure_percent || 0}%</p>
           <p>Max Position Risk: {(risk.max_position_risk || 0.05) * 100}%</p>
        </div>
      )}
    </div>
  );
}

export function Alerts() {
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Alerts</h1>
      <div className="bg-slate-50 p-12 text-center rounded border border-slate-200">
         <ShieldAlert className="mx-auto text-slate-400 mb-2 w-8 h-8" />
         <p className="text-slate-500 font-medium">ALL SYSTEMS NORMAL</p>
         <p className="text-sm text-slate-400 mt-2">No API failures or risk rejections detected.</p>
      </div>
    </div>
  );
}

export function Settings() {
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Settings</h1>
      <div className="bg-white p-6 rounded shadow-sm border border-slate-200">
         <p className="text-slate-500 text-sm mb-4">Risk limits are managed globally in Phase 6 Paper Mode.</p>
         <button className="px-4 py-2 bg-slate-900 text-white rounded font-semibold text-sm">Save Preferences</button>
      </div>
    </div>
  );
}

export function Subscription() {
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Subscription</h1>
      <div className="bg-white p-6 rounded shadow-sm border border-slate-200">
         <h2 className="text-xl font-bold mb-2">Paper Trading Tier</h2>
         <p className="text-slate-500 mb-4">You are currently using the isolated Paper Sandbox environment. LIVE TRADING = DISABLED.</p>
         <button className="px-4 py-2 bg-emerald-600 text-white rounded font-semibold text-sm" disabled>Upgrade to Live (Disabled)</button>
      </div>
    </div>
  );
}
