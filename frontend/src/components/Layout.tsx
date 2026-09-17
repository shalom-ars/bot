import { Outlet } from 'react-router-dom';
import { ShieldAlert, LogOut } from 'lucide-react';
import BrandLogo from './BrandLogo';

export default function Layout() {
  const handleLogout = () => {
    try {
      localStorage.clear();
      sessionStorage.clear();
    } catch (e) {}
    window.location.href = '/login';
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
      {/* Top Navbar - Full Width, No Sidebar */}
      <header className="bg-white border-b border-slate-200 px-4 sm:px-6 py-2.5 flex justify-between items-center sticky top-0 z-20 shadow-xs">
        {/* Left: Brand Logo & Mode Badge */}
        <div className="flex items-center gap-2.5">
          <BrandLogo size={34} glow={true} />
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-black text-slate-900 tracking-tight leading-tight">JONANDA BOT</span>
              <span className="hidden sm:inline-block text-[9px] bg-blue-100 text-blue-700 font-bold px-1.5 py-0.5 rounded tracking-wider uppercase">
                BTC 5M TERMINAL
              </span>
            </div>
          </div>
          <div className="hidden md:flex items-center gap-1.5 ml-2 pl-3 border-l border-slate-200 text-xs">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
              <ShieldAlert className="w-3 h-3 text-rose-600" />
              <span>PAPER TRADING · $500 SEED</span>
            </span>
          </div>
        </div>

        {/* Right: PRO PLAN Badge, User Avatar & Logout Button */}
        <div className="flex items-center gap-2.5 sm:gap-3">
          <span className="bg-blue-50 text-blue-700 text-xs font-black px-3 py-1 rounded-full border border-blue-200 flex items-center gap-1.5 shadow-xs">
            <span className="w-2 h-2 rounded-full bg-blue-600 animate-pulse"></span>
            PRO PLAN
          </span>
          <div className="w-7 h-7 bg-slate-800 text-white rounded-full flex items-center justify-center font-black text-xs shadow-xs">
            U
          </div>
          <button
            onClick={handleLogout}
            className="px-3 py-1.5 rounded-xl text-xs font-black text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 flex items-center gap-1.5 transition-all shadow-xs cursor-pointer"
            title="Sign out of your session"
          >
            <LogOut className="w-3.5 h-3.5 text-rose-600" />
            <span>LOGOUT</span>
          </button>
        </div>
      </header>

      {/* Main Content - Takes Full Width */}
      <main className="flex-1 p-3 sm:p-5 w-full">
        <Outlet />
      </main>
    </div>
  );
}
