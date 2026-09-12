import { useState, useEffect } from 'react';
import { Activity, TrendingUp, AlertTriangle, ArrowUpRight, ArrowDownRight, FileTerminal } from 'lucide-react';
import { Link } from 'react-router-dom';
import client from '../api/client';

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [perf, setPerf] = useState<any>(null);

  useEffect(() => {
    client.get('/users/portfolio').then((r: any) => setData(r.data)).catch(console.error);
    client.get('/users/performance').then((r: any) => setPerf(r.data)).catch(console.error);
  }, []);

  return (
    <div className="space-y-6 max-w-7xl">
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

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card title="Virtual Balance" value={`$${data?.current_balance?.toFixed(2) ?? '0.00'}`} icon={WalletIcon} />
        <Card title="Total PnL" value={`$${data?.realized_pnl?.toFixed(2) ?? '0.00'}`} icon={TrendingUp} trend={0} />
        <Card title="Win Rate" value={`${perf?.win_rate ?? 0}%`} icon={Activity} />
        <Card title="Trades" value={data?.trades ?? 0} icon={AlertTriangle} />
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
             <div className="text-center py-8">
               <Activity className="w-8 h-8 text-slate-300 mx-auto mb-3" />
               <p className="text-sm text-slate-500">No recent activity.</p>
             </div>
          </div>
        </div>
      </div>
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

function WalletIcon(props: any) {
  return <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4Z"/></svg>;
}
