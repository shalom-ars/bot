import { Outlet } from 'react-router-dom';
import BrandLogo from './BrandLogo';

export default function AuthLayout() {
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-xl border border-slate-100 overflow-hidden">
        <div className="bg-slate-900 p-6 text-center flex flex-col items-center justify-center">
          <BrandLogo size={44} glow={true} className="mb-2.5" />
          <h1 className="text-2xl font-extrabold text-white tracking-tight">JONANDA BOT</h1>
          <p className="text-slate-400 text-xs mt-0.5 uppercase tracking-wider font-mono">BTC 5M Quantitative Intelligence</p>
        </div>
        <div className="p-8">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
