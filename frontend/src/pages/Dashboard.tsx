import { useState, useEffect } from 'react';
import { Activity, TrendingUp, AlertTriangle, ArrowUpRight, ArrowDownRight, FileTerminal, RefreshCw, Wallet } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useApi } from '../hooks/useApi';
import { PaperTradingControl } from '../components/PaperTradingControl';
import SelfLearningLogsWidget from '../components/SelfLearningLogsWidget';

export default function Dashboard() {
  const { data: portfolio, loading: portLoading, error: portError } = useApi<any>('/users/portfolio', null);
  const { data: perf, loading: perfLoading, error: perfError } = useApi<any>('/users/performance', null);
  const { data: tradesData } = useApi<any>('/users/trades?limit=5', { trades: [] });
  const { data: positionsData } = useApi<any>('/users/positions', { positions: [] });
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

  const unrealizedPnl = (positionsData?.positions || []).reduce((acc: number, pos: any) => {
     const currentPrice = livePrices[pos.market_id] || pos.entry_price;
     let posPnl = 0;
     if (pos.side === 'BUY_YES' || pos.side === 'BUY') {
         posPnl = (currentPrice - pos.entry_price) * pos.quantity;
     } else {
         posPnl = ((1.0 - currentPrice) - pos.entry_price) * pos.quantity;
     }
     return acc + posPnl;
  }, 0);

  const totalPnl = (portfolio?.realized_pnl || 0) + unrealizedPnl;

  const loading = portLoading || perfLoading;
  const error = portError || perfError;

  return (
    <div className="space-y-6 max-w-7xl">
      <PaperTradingControl />
      
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Welcome back</h1>
          <p className="text-slate-500 mt-1">Here's your prediction-market portfolio at a glance.</p>
        </div>
        <Link to="/app/research" className="bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 rounded-lg text-sm font-semibold flex items-center gap-2 transition-colors shadow-sm">
          <FileTerminal className="w-4 h-4" />
          Research Terminal
        </Link>
      </div>

      {error && (
        <div className="bg-red-50 p-12 text-center rounded border border-red-200">
          <AlertTriangle className="mx-auto text-red-500 mb-2 w-8 h-8" />
          <p className="text-red-700 font-bold mb-2">BACKEND CONNECTION ERROR</p>
          <p className="text-sm text-red-600 mb-4">Failed to load dashboard data.</p>
          <button onClick={() => window.location.reload()} className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded font-medium flex items-center mx-auto gap-2">
            <RefreshCw className="w-4 h-4" /> Retry Connection
          </button>
        </div>
      )}

      {loading ? (
        <div className="p-12 text-center text-slate-500 flex flex-col items-center">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-500 mb-4" />
          <p>Loading portfolio data...</p>
        </div>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card title="Virtual Balance" value={`$${portfolio?.current_balance?.toFixed(2) ?? '0.00'}`} icon={Wallet} />
            <Card title="Total PnL" value={`$${totalPnl.toFixed(2)}`} icon={TrendingUp} trend={totalPnl} />
            <Card title="Win Rate" value={`${perf?.win_rate ?? 0}%`} icon={Activity} />
            <Card title="Trades" value={portfolio?.trades ?? 0} icon={AlertTriangle} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Chart Area */}
            <div className="lg:col-span-2 bg-white border border-slate-200 rounded-xl shadow-sm p-6">
              <div className="flex justify-between items-center mb-6">
                <h3 className="text-lg font-bold text-slate-900">Equity Curve</h3>
                <div className="flex bg-slate-100 rounded-lg p-1">
                  {['7D', '30D', '90D', 'ALL'].map(t => (
                    <button key={t} className={`px-3 py-1 text-xs font-semibold rounded-md ${t === '7D' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500'}`}>
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <div className="h-64 flex items-center justify-center border-2 border-dashed border-slate-100 rounded-lg bg-slate-50">
                <p className="text-slate-400 font-medium text-sm">No sufficient trading history yet.</p>
              </div>
            </div>

            {/* Recent Activity */}
            <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6">
              <h3 className="text-lg font-bold text-slate-900 mb-6">Recent Activity</h3>
              <div className="space-y-4">
                 {!tradesData || !tradesData.trades || tradesData.trades.length === 0 ? (
                   <div className="text-center py-8">
                     <Activity className="w-8 h-8 text-slate-300 mx-auto mb-3" />
                     <p className="text-sm text-slate-500">No recent activity.</p>
                   </div>
                 ) : (
                   tradesData.trades.map((trade: any, i: number) => (
                     <div key={i} className="flex justify-between items-center p-3 hover:bg-slate-50 rounded-lg border border-transparent hover:border-slate-100 transition-colors">
                        <div>
                          <div className="text-sm font-bold text-slate-900">{trade.side}</div>
                          <div className="text-xs text-slate-500">{new Date(trade.entry_time).toLocaleTimeString()}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-semibold">${(trade.quantity * trade.entry_price).toFixed(2)}</div>
                          <div className={`text-xs font-medium ${trade.pnl > 0 ? 'text-emerald-500' : trade.pnl < 0 ? 'text-rose-500' : 'text-slate-400'}`}>
                             {trade.status === 'CLOSED' ? (trade.pnl >= 0 ? `+$${trade.pnl?.toFixed(2)}` : `-$${Math.abs(trade.pnl)?.toFixed(2)}`) : 'OPEN'}
                          </div>
                        </div>
                     </div>
                   ))
                 )}
              </div>
            </div>
          </div>
          <div className="mt-6">
            <SelfLearningLogsWidget />
          </div>
        </>
      )}
    </div>
  );
}

function Card({ title, value, icon: Icon, trend }: any) {
  return (
    <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
      <div className="flex justify-between items-start mb-4">
        <div className="p-2 bg-slate-50 rounded-lg border border-slate-100 text-slate-600">
          <Icon className="w-5 h-5" />
        </div>
        {trend !== undefined && (
          <span className={`text-xs font-bold flex items-center gap-1 ${trend >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
            {trend >= 0 ? <ArrowUpRight className="w-3 h-3"/> : <ArrowDownRight className="w-3 h-3"/>}
            {Math.abs(trend)}%
          </span>
        )}
      </div>
      <p className="text-sm text-slate-500 font-medium mb-1">{title}</p>
      <h4 className="text-2xl font-extrabold text-slate-900">{value}</h4>
    </div>
  );
}


