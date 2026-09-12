import { useState, useEffect } from 'react';
import client from '../api/client';
import { AlertTriangle, Wallet, ShieldAlert, BarChart3, Crosshair } from 'lucide-react';
import { Link } from 'react-router-dom';

export function Portfolio() {
  const [data, setData] = useState<any>(null);
  
  useEffect(() => {
    client.get('/users/portfolio').then((r: any) => setData(r.data)).catch(console.error);
  }, []);
  
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Portfolio</h1>
      {!data ? <div className="text-slate-500">Loading...</div> : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 bg-white rounded shadow-sm border border-slate-200">
            <p className="text-sm text-slate-500">Balance</p>
            <p className="text-xl font-bold">${data.current_balance?.toFixed(2)}</p>
          </div>
          <div className="p-4 bg-white rounded shadow-sm border border-slate-200">
            <p className="text-sm text-slate-500">Equity</p>
            <p className="text-xl font-bold">${data.equity?.toFixed(2)}</p>
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
  const [markets, setMarkets] = useState<any[]>([]);
  
  useEffect(() => {
    client.get('/markets').then((r: any) => setMarkets(r.data.markets)).catch(console.error);
  }, []);
  
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Tracked Markets</h1>
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 divide-y overflow-hidden">
        {markets.length === 0 ? (
           <p className="p-6 text-slate-500 text-center">No active markets tracked.</p>
        ) : (
          markets.map(m => (
            <Link key={m.market_id} to={`/app/markets/${m.market_id}`} className="block p-4 hover:bg-slate-50">
              <p className="font-semibold">{m.question}</p>
              <p className="text-sm text-slate-500">Token: {m.token}</p>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

export function MarketDetail({ id }: { id?: string }) {
  const [market, setMarket] = useState<any>(null);
  
  useEffect(() => {
    // In real router, use useParams
    const targetId = id || window.location.pathname.split('/').pop();
    client.get(`/markets/${targetId}`).then((r: any) => setMarket(r.data)).catch(console.error);
  }, [id]);
  
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Market Detail</h1>
      {!market ? <p className="text-slate-500">Loading...</p> : (
        <div className="bg-white p-6 rounded shadow-sm border border-slate-200 space-y-4">
          <h2 className="text-xl font-bold">{market.market.question}</h2>
          <p className="text-slate-500">ID: {market.market.market_id}</p>
          <div className="bg-slate-50 p-4 rounded border border-slate-100">
            <h3 className="font-semibold mb-2">Latest Snapshot Data:</h3>
            {!market.latest_snapshot ? <p>No snapshots yet.</p> : (
               <pre className="text-xs text-slate-600">{JSON.stringify(market.latest_snapshot, null, 2)}</pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function Positions() {
  const [positions, setPositions] = useState<any[]>([]);
  useEffect(() => { client.get('/users/positions').then((r: any) => setPositions(r.data.positions)).catch(console.error); }, []);
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Open Positions</h1>
      {positions.length === 0 ? (
        <div className="bg-slate-50 p-12 text-center rounded border border-slate-200">
           <AlertTriangle className="mx-auto text-slate-400 mb-2 w-8 h-8" />
           <p className="text-slate-500 font-medium">NO OPEN POSITIONS</p>
        </div>
      ) : (
        <pre>{JSON.stringify(positions, null, 2)}</pre>
      )}
    </div>
  );
}

export function Trades() {
  const [trades, setTrades] = useState<any[]>([]);
  useEffect(() => { client.get('/users/trades').then((r: any) => setTrades(r.data.trades)).catch(console.error); }, []);
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Trade History</h1>
      {trades.length === 0 ? (
        <div className="bg-slate-50 p-12 text-center rounded border border-slate-200">
           <Wallet className="mx-auto text-slate-400 mb-2 w-8 h-8" />
           <p className="text-slate-500 font-medium">NO PAPER TRADES YET</p>
        </div>
      ) : (
        <pre>{JSON.stringify(trades, null, 2)}</pre>
      )}
    </div>
  );
}

export function Signals() {
  const [signals, setSignals] = useState<any[]>([]);
  useEffect(() => { client.get('/signals').then((r: any) => setSignals(r.data.signals)).catch(console.error); }, []);
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Actionable Signals</h1>
      {signals.length === 0 ? (
        <div className="bg-slate-50 p-12 text-center rounded border border-slate-200">
           <Crosshair className="mx-auto text-slate-400 mb-2 w-8 h-8" />
           <p className="text-slate-500 font-medium">NO ACTIONABLE SIGNALS</p>
           <p className="text-sm text-slate-400 mt-2">The model is waiting for profitable edges...</p>
        </div>
      ) : (
        <pre>{JSON.stringify(signals, null, 2)}</pre>
      )}
    </div>
  );
}

export function Performance() {
  const [perf, setPerf] = useState<any>(null);
  useEffect(() => { client.get('/users/performance').then((r: any) => setPerf(r.data)).catch(console.error); }, []);
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Performance</h1>
      {!perf ? <p>Loading...</p> : perf.trades === 0 ? (
        <div className="bg-slate-50 p-12 text-center rounded border border-slate-200">
           <BarChart3 className="mx-auto text-slate-400 mb-2 w-8 h-8" />
           <p className="text-slate-500 font-medium">INSUFFICIENT DATA</p>
           <p className="text-sm text-slate-400 mt-2">Cannot calculate profitability without statistical sample.</p>
        </div>
      ) : (
        <pre>{JSON.stringify(perf, null, 2)}</pre>
      )}
    </div>
  );
}

export function Risk() {
  const [risk, setRisk] = useState<any>(null);
  useEffect(() => { client.get('/users/risk').then((r: any) => setRisk(r.data)).catch(console.error); }, []);
  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-3xl font-extrabold">Risk Management</h1>
      {!risk ? <p>Loading...</p> : (
        <div className="bg-white p-6 rounded shadow-sm border border-slate-200 space-y-2">
           <p>Status: <span className="font-bold">{risk.status}</span></p>
           <p>Current Exposure: ${risk.current_exposure}</p>
           <p>Exposure Percent: {risk.exposure_percent}%</p>
           <p>Max Position Risk: {risk.max_position_risk * 100}%</p>
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
         <p className="text-slate-500 mb-4">You are currently using the isolated Paper Sandbox environment.</p>
         <button className="px-4 py-2 bg-emerald-600 text-white rounded font-semibold text-sm" disabled>Upgrade to Live (Disabled)</button>
      </div>
    </div>
  );
}
