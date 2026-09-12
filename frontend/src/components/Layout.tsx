import { Outlet, Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, LineChart, Activity, Wallet, FileTerminal, LogOut, ShieldAlert } from 'lucide-react';

export default function Layout() {
  const location = useLocation();

  const navItems = [
    { name: 'Overview', path: '/app', icon: LayoutDashboard },
    { name: 'Markets', path: '/app/markets', icon: LineChart },
    { name: 'Signals', path: '/app/signals', icon: Activity },
    { name: 'Portfolio', path: '/app/portfolio', icon: Wallet },
    { name: 'Research Terminal', path: '/app/research', icon: FileTerminal },
  ];

  return (
    <div className="flex h-screen bg-slate-50 text-slate-900">
      {/* Sidebar */}
      <div className="w-64 bg-white border-r border-slate-200 flex flex-col">
        <div className="p-6">
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">JONANDA</h1>
          <p className="text-xs text-slate-500 font-medium tracking-wide mt-1 uppercase">Quant Intelligence</p>
        </div>
        
        <nav className="flex-1 px-4 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.name}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                  isActive 
                    ? 'bg-blue-50 text-blue-700 font-semibold' 
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`}
              >
                <Icon className="w-5 h-5" />
                {item.name}
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-200">
          <div className="bg-rose-50 border border-rose-200 rounded-lg p-3 mb-4">
            <div className="flex items-center gap-2 text-rose-700 font-bold mb-1">
              <ShieldAlert className="w-4 h-4" />
              <span className="text-sm">PAPER TRADING</span>
            </div>
            <p className="text-xs text-rose-600 font-medium">REAL MONEY: DISABLED</p>
          </div>
          <Link to="/" className="flex items-center gap-2 text-slate-500 hover:text-slate-900 px-2 text-sm font-medium">
            <LogOut className="w-4 h-4" />
            Sign Out
          </Link>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto bg-slate-50">
        <header className="bg-white border-b border-slate-200 px-8 py-4 flex justify-between items-center sticky top-0 z-10">
          <h2 className="text-xl font-bold text-slate-800 capitalize">
            {location.pathname.split('/').pop() || 'Overview'}
          </h2>
          <div className="flex items-center gap-4">
            <span className="bg-blue-100 text-blue-800 text-xs font-bold px-3 py-1 rounded-full border border-blue-200">
              PRO PLAN
            </span>
            <div className="w-8 h-8 bg-slate-200 rounded-full flex items-center justify-center text-slate-600 font-bold">
              U
            </div>
          </div>
        </header>
        <main className="p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
