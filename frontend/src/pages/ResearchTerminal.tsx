import { useState, useEffect } from 'react'
import { Activity, Wallet, ShieldAlert, Clock, Wifi, WifiOff, Database, FlaskConical } from 'lucide-react'

function StatusBadge({ value, good, warn }: { value: string, good: string[], warn?: string[] }) {
  const isGood = good.includes(value)
  const isWarn = warn?.includes(value)
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-mono font-bold ${
      isGood ? 'bg-emerald-900/60 text-emerald-300' :
      isWarn ? 'bg-yellow-900/60 text-yellow-300' :
      'bg-rose-900/60 text-rose-300'
    }`}>{value}</span>
  )
}

export default function ResearchTerminal() {
  const [status, setStatus] = useState<any>({ status: 'loading' })
  const [health, setHealth] = useState<any>(null)
  const [markets, setMarkets] = useState<any[]>([])
  const [pnl, setPnl] = useState({ realized: 0, unrealized: 0, total: 0 })
  const [strategy, setStrategy] = useState<any>(null)
  const [quality, setQuality] = useState<any>(null)

  useEffect(() => {
    const fetchAll = () => {
      fetch('http://localhost:8000/api/status')
        .then(r => r.json()).then(setStatus).catch(console.error)
      fetch('http://localhost:8000/api/health')
        .then(r => r.json()).then(setHealth).catch(console.error)
      fetch('http://localhost:8000/api/strategy/status')
        .then(r => r.json()).then(setStrategy).catch(console.error)
      fetch('http://localhost:8000/api/research/quality')
        .then(r => r.json()).then(setQuality).catch(console.error)
    }
    fetchAll()
    const interval = setInterval(fetchAll, 5000)

    fetch('http://localhost:8000/api/pnl')
      .then(r => r.json()).then(setPnl).catch(console.error)

    const ws = new WebSocket('ws://localhost:8000/ws/live')
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'markets') setMarkets(data.data)
      if (data.type === 'pnl') setPnl(data.data)
    }
    return () => { clearInterval(interval); ws.close() }
  }, [])

  const polyStatus = health?.poly?.status || 'LOADING'
  const dataQuality = quality?.data_quality || '...'

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 p-6 font-sans flex flex-col gap-6">

      {/* ── Research Mode Banner ──────────────────────────────── */}
      {strategy?.research_mode && (
        <div className="flex items-center gap-3 bg-purple-950/60 border border-purple-700 rounded-xl px-4 py-3">
          <FlaskConical className="w-5 h-5 text-purple-400 shrink-0"/>
          <div className="flex gap-6 text-sm">
            <span className="font-bold text-purple-300">RESEARCH MODE</span>
            <span className="text-slate-400">LIVE DATA: <span className={strategy?.live_data ? 'text-emerald-400' : 'text-rose-400'}>{strategy?.live_data ? 'YES' : 'NO'}</span></span>
            <span className="text-slate-400">NO TRADING: <span className="text-emerald-400">ACTIVE</span></span>
            <span className="text-slate-400">SYNTHETIC: <span className={strategy?.synthetic_enabled ? 'text-yellow-400' : 'text-emerald-400'}>{strategy?.synthetic_enabled ? 'ENABLED' : 'DISABLED'}</span></span>
            <span className="text-slate-400">DATA QUALITY: <StatusBadge value={dataQuality} good={['GOOD']} warn={['WARNING']} /></span>
          </div>
        </div>
      )}

      {health?.mode === 'paper' && (
        <div className="bg-emerald-900/50 border border-emerald-800 text-emerald-300 p-2 text-sm font-semibold flex justify-center items-center gap-2">
          <Activity className="w-4 h-4"/> 
          PAPER TRADING - LIVE DATA ACTIVE
        </div>
      )}

      {/* ── Header ───────────────────────────────────────────── */}
      <header className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <Activity className="text-blue-500 w-8 h-8"/>
          <h1 className="text-2xl font-bold tracking-tight">Polymarket Quant Bot</h1>
          <span className="bg-blue-900/50 text-blue-400 text-xs px-2 py-1 rounded border border-blue-800 ml-4 font-mono">PAPER TRADING MVP</span>
        </div>
        <div className="flex items-center gap-2 bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-700">
          {status.status === 'ok' ? <Wifi className="w-4 h-4 text-emerald-500"/> : <WifiOff className="w-4 h-4 text-rose-500"/>}
          <span className="text-sm font-medium">Backend</span>
        </div>
      </header>

      {/* ── Top Stats ────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex items-center gap-4">
          <div className="bg-slate-800 p-3 rounded-lg"><Wallet className="w-6 h-6 text-emerald-400"/></div>
          <div>
            <p className="text-sm text-slate-400">Total PnL</p>
            <p className={`text-xl font-bold ${pnl.total >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>${pnl.total.toFixed(2)}</p>
          </div>
        </div>

        <div className={`border p-4 rounded-xl flex items-center gap-4 ${polyStatus === 'CONNECTED' ? 'bg-slate-900 border-slate-800' : polyStatus === 'DEGRADED' ? 'bg-yellow-950/30 border-yellow-900' : 'bg-rose-950/30 border-rose-900'}`}>
          <div className={`p-3 rounded-lg ${polyStatus === 'CONNECTED' ? 'bg-slate-800' : 'bg-rose-900'}`}>
            {polyStatus === 'CONNECTED' ? <Wifi className="w-6 h-6 text-blue-400"/> : <WifiOff className="w-6 h-6 text-rose-400"/>}
          </div>
          <div>
            <p className="text-sm text-slate-400">Polymarket Feed</p>
            <p className="text-md font-bold text-slate-100">{polyStatus}</p>
            <p className="text-xs text-slate-500">Valid: {health?.poly?.valid_clob_markets ?? '…'} | Quarantined: {health?.poly?.quarantined_markets ?? '…'}</p>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex items-center gap-4">
          <div className="bg-slate-800 p-3 rounded-lg"><Clock className="w-6 h-6 text-purple-400"/></div>
          <div>
            <p className="text-sm text-slate-400">Latency</p>
            <p className="text-sm font-bold text-slate-100">{health?.poly?.latency ?? 0}ms</p>
            <p className="text-xs text-slate-500 truncate">
              {health?.poly?.last_update ? new Date(health.poly.last_update).toLocaleTimeString() : 'N/A'}
            </p>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex items-center gap-4">
          <div className="bg-slate-800 p-3 rounded-lg"><ShieldAlert className="w-6 h-6 text-amber-400"/></div>
          <div>
            <p className="text-sm text-slate-400">Real Backtest</p>
            <p className={`text-sm font-bold ${quality?.real_backtest_allowed ? 'text-emerald-400' : 'text-rose-400'}`}>
              {quality?.real_backtest_allowed ? 'ALLOWED' : 'BLOCKED'}
            </p>
          </div>
        </div>
      </div>

      {/* ── Main Grid ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1">

        {/* Active Markets */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <div className="p-4 border-b border-slate-800 bg-slate-900/50">
            <h2 className="font-semibold flex items-center gap-2"><Clock className="w-4 h-4"/> Active Markets</h2>
          </div>
          <div className="p-4">
            {markets.length === 0 ? (
              <div className="text-center text-slate-500 py-12">
                <Activity className="w-12 h-12 mx-auto mb-4 opacity-30 animate-pulse"/>
                <p className="text-lg">Waiting for market data…</p>
              </div>
            ) : (
              <div className="space-y-4">
                {markets.map((m, i) => (
                  <div key={i} className="border border-slate-700 p-4 rounded-lg bg-slate-800/50">
                    <div className="flex justify-between items-start mb-2">
                      <h3 className="font-medium text-slate-200 text-sm">{m.question}</h3>
                      <span className="bg-slate-700 px-2 py-1 text-xs rounded text-slate-300">{m.token}</span>
                    </div>
                    <div className="grid grid-cols-4 gap-4 text-sm mt-3">
                      <div><p className="text-slate-500 text-xs">Price</p><p className="font-mono">{m.current_price?.toFixed(3)}</p></div>
                      <div><p className="text-slate-500 text-xs">Spread</p><p className="font-mono text-amber-400">{(m.spread || 0).toFixed(4)}</p></div>
                      <div><p className="text-slate-500 text-xs">Imbalance</p><p className="font-mono text-purple-400">{((m.imbalance || 0) * 100).toFixed(1)}%</p></div>
                      <div><p className="text-slate-500 text-xs">Signal</p><p className="font-mono font-bold text-slate-400">SKIP</p></div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Panel: Strategy + Data Quality */}
        <div className="space-y-6">

          {/* Strategy Status */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex justify-between items-center">
              <h2 className="font-semibold">Strategy</h2>
              {strategy?.research_mode && (
                <span className="bg-purple-900/50 text-purple-400 text-xs px-2 py-1 rounded font-mono">RESEARCH</span>
              )}
            </div>
            <div className="p-4">
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Model',         val: strategy?.model ?? 'N/A', mono: false },
                  { label: 'Total Signals', val: strategy?.total_signals ?? 0, mono: true },
                  { label: 'Paper Trades',  val: strategy?.paper_trades ?? 0,  mono: true },
                  { label: 'Win Rate',      val: `${((strategy?.win_rate ?? 0)*100).toFixed(1)}%`, mono: true },
                  { label: 'Brier Score',   val: strategy?.brier_score ?? '—', mono: true },
                  { label: 'Avg Edge',      val: `${((strategy?.avg_edge_last_100 ?? 0)*100).toFixed(2)}%`, mono: true },
                ].map(({ label, val, mono }) => (
                  <div key={label} className="bg-slate-800/50 p-3 rounded border border-slate-700">
                    <p className="text-xs text-slate-500">{label}</p>
                    <p className={`text-sm font-bold ${mono ? 'font-mono' : ''} text-slate-100`}>{String(val)}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Data Quality Panel */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <h2 className="font-semibold flex items-center gap-2"><Database className="w-4 h-4"/> Data Quality</h2>
              <StatusBadge value={dataQuality} good={['GOOD']} warn={['WARNING']}/>
            </div>
            <div className="p-4 space-y-2 text-sm">
              {[
                { label: 'Snapshots Collected', val: quality?.snapshots_collected ?? 0 },
                { label: 'Unique Markets',       val: quality?.unique_markets ?? 0 },
                { label: 'Resolved Markets',     val: quality?.resolved_markets ?? 0 },
                { label: 'Unresolved Markets',   val: quality?.unresolved_markets ?? 0 },
                { label: 'Valid Train Samples',  val: quality?.valid_training_samples ?? 0 },
                { label: 'Invalid Samples',      val: quality?.invalid_samples ?? 0 },
                { label: 'Feature Completeness', val: quality ? `${(quality.feature_completeness*100).toFixed(1)}%` : '…' },
                { label: 'Class Balance',        val: quality ? `${(quality.class_balance*100).toFixed(1)}%` : '…' },
                { label: 'API Errors',           val: quality?.api_errors ?? 0 },
              ].map(({ label, val }) => (
                <div key={label} className="flex justify-between py-0.5 border-b border-slate-800/60">
                  <span className="text-slate-500">{label}</span>
                  <span className="font-mono text-slate-200">{String(val)}</span>
                </div>
              ))}
              <div className="pt-2 text-xs text-slate-500">
                <div>Started: {quality?.collection_started ? new Date(quality.collection_started).toLocaleString() : 'N/A'}</div>
                <div>Last snapshot: {quality?.last_snapshot ? new Date(quality.last_snapshot).toLocaleString() : 'N/A'}</div>
              </div>
              {quality?.real_backtest_blocked_reasons?.length > 0 && (
                <div className="mt-3 bg-rose-950/40 border border-rose-800 rounded p-3">
                  <p className="text-rose-400 text-xs font-bold mb-1">REAL BACKTEST BLOCKED</p>
                  {quality.real_backtest_blocked_reasons.map((r: string, i: number) => (
                    <p key={i} className="text-rose-300 text-xs">• {r}</p>
                  ))}
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}
