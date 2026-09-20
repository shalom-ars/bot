import { Outlet } from 'react-router-dom';

export default function Layout() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
      {/* Main Content - Takes Full Width */}
      <main className="flex-1 p-2 sm:p-4 w-full">
        <Outlet />
      </main>
    </div>
  );
}
