import { Outlet } from 'react-router-dom';

export default function AuthLayout() {
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-xl border border-slate-100 overflow-hidden">
        <div className="bg-slate-900 p-6 text-center">
          <h1 className="text-2xl font-extrabold text-white tracking-tight">JONANDA</h1>
          <p className="text-slate-400 text-sm mt-1">Quantitative Intelligence</p>
        </div>
        <div className="p-8">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
