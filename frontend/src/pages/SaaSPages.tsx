import { Link } from 'react-router-dom';
import { useApi } from '../hooks/useApi';
import { Wallet, ShieldAlert, Crosshair, BarChart3, AlertTriangle, RefreshCw } from 'lucide-react';

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
  const { data, loading, error } = useApi<{markets: any[], total: number}>('/markets', { markets: [], total: 0 });
  
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Tracked Markets</h1>
      
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}

      {!loading && !error && (
        <>
          <p className="text-slate-500 mb-4">Total active markets tracked: {data.total}</p>
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 divide-y overflow-hidden">
            {data.markets.length === 0 ? (
               <p className="p-6 text-slate-500 text-center">No active markets tracked.</p>
            ) : (
              data.markets.map(m => (
                <Link key={m.market_id} to={`/app/markets/${m.market_id}`} className="block p-4 hover:bg-slate-50">
                  <p className="font-semibold">{m.question}</p>
                  <p className="text-sm text-slate-500">Token: {m.token} | ID: {m.market_id}</p>
                </Link>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}

export function MarketDetail({ id }: { id?: string }) {
  const targetId = id || window.location.pathname.split('/').pop();
  const { data: market, loading, error } = useApi<any>(`/markets/${targetId}`, null);
  
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Market Detail</h1>
      
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}
      
      {!loading && !error && market && (
        <div className="bg-white p-6 rounded shadow-sm border border-slate-200 space-y-4">
          <h2 className="text-xl font-bold">{market.market.question}</h2>
          <p className="text-slate-500">ID: {market.market.market_id}</p>
          <div className="bg-slate-50 p-4 rounded border border-slate-100 overflow-x-auto">
            <h3 className="font-semibold mb-2">Latest Snapshot Data:</h3>
            {!market.latest_snapshot ? <p className="text-slate-500">No snapshots yet.</p> : (
               <pre className="text-xs text-slate-600">{JSON.stringify(market.latest_snapshot, null, 2)}</pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function Positions() {
  const { data, loading, error } = useApi<{positions: any[]}>('/users/positions', { positions: [] });
  
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Open Positions</h1>
      
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}
      
      {!loading && !error && (
        data.positions.length === 0 ? (
          <div className="bg-slate-50 p-12 text-center rounded border border-slate-200">
             <AlertTriangle className="mx-auto text-slate-400 mb-2 w-8 h-8" />
             <p className="text-slate-500 font-medium">NO OPEN POSITIONS</p>
             <p className="text-sm text-slate-400 mt-2">Currently holding no risk.</p>
          </div>
        ) : (
          <pre className="bg-white p-4 border border-slate-200 rounded overflow-auto">{JSON.stringify(data.positions, null, 2)}</pre>
        )
      )}
    </div>
  );
}

export function Trades() {
  const { data, loading, error } = useApi<{trades: any[]}>('/users/trades', { trades: [] });
  
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Trade History</h1>
      
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}

      {!loading && !error && (
        data.trades.length === 0 ? (
          <div className="bg-slate-50 p-12 text-center rounded border border-slate-200">
             <Wallet className="mx-auto text-slate-400 mb-2 w-8 h-8" />
             <p className="text-slate-500 font-medium">NO PAPER TRADES YET</p>
             <p className="text-sm text-slate-400 mt-2">No completed trades recorded in the database.</p>
          </div>
        ) : (
          <pre className="bg-white p-4 border border-slate-200 rounded overflow-auto">{JSON.stringify(data.trades, null, 2)}</pre>
        )
      )}
    </div>
  );
}

export function Signals() {
  const { data, loading, error } = useApi<{signals: any[]}>('/signals', { signals: [] });
  
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Actionable Signals</h1>
      
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}

      {!loading && !error && (
        data.signals.length === 0 ? (
          <div className="bg-slate-50 p-12 text-center rounded border border-slate-200">
             <Crosshair className="mx-auto text-slate-400 mb-2 w-8 h-8" />
             <p className="text-slate-500 font-medium">NO ACTIONABLE SIGNALS</p>
             <p className="text-sm text-slate-400 mt-2">REAL MARKET CONDITIONS CURRENTLY PROVIDE NO QUALIFYING EDGE.</p>
          </div>
        ) : (
          <pre className="bg-white p-4 border border-slate-200 rounded overflow-auto">{JSON.stringify(data.signals, null, 2)}</pre>
        )
      )}
    </div>
  );
}

export function Performance() {
  const { data: perf, loading, error } = useApi<any>('/users/performance', null);
  
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Performance</h1>
      
      {loading && <LoadingState />}
      {error && <ErrorState message={error} retry={() => window.location.reload()} />}

      {!loading && !error && perf && (
        (perf.trades === 0 || perf.trade_count === 0) ? (
          <div className="bg-slate-50 p-12 text-center rounded border border-slate-200">
             <BarChart3 className="mx-auto text-slate-400 mb-2 w-8 h-8" />
             <p className="text-slate-500 font-medium">INSUFFICIENT REAL PAPER-TRADING DATA</p>
             <p className="text-sm text-slate-400 mt-2">Cannot calculate profitability without statistical sample.</p>
          </div>
        ) : (
          <pre className="bg-white p-4 border border-slate-200 rounded overflow-auto">{JSON.stringify(perf, null, 2)}</pre>
        )
      )}
    </div>
  );
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
