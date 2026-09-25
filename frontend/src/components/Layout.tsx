import { Outlet } from 'react-router-dom';

export default function Layout() {
  return (
    <div className="min-h-screen bg-[#0d1117] text-slate-100 flex flex-col">
      {/* Main Content - Takes Full Width */}
      <main className="flex-1 p-2 sm:p-4 w-full">
        <Outlet />
      </main>
    </div>
  );
}
