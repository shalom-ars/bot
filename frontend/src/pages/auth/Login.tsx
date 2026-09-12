import { Link } from 'react-router-dom';

export default function Login() {
  return (
    <div>
      <h2 className="text-2xl font-bold text-slate-900 mb-2">Sign In</h2>
      <p className="text-slate-500 text-sm mb-8">Access your virtual portfolio and analytics.</p>
      
      <form className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
          <input type="email" className="w-full border border-slate-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-blue-600 focus:border-transparent outline-none" placeholder="name@company.com" />
        </div>
        <div>
          <div className="flex justify-between items-center mb-1">
            <label className="block text-sm font-medium text-slate-700">Password</label>
            <a href="#" className="text-xs text-blue-600 hover:underline">Forgot password?</a>
          </div>
          <input type="password" className="w-full border border-slate-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-blue-600 focus:border-transparent outline-none" placeholder="••••••••" />
        </div>
        <Link to="/app" className="w-full bg-blue-600 text-white rounded-lg px-4 py-3 font-bold text-sm hover:bg-blue-700 transition-colors mt-6 block text-center">
          Sign In
        </Link>
      </form>
      
      <div className="mt-8 text-center text-sm text-slate-600">
        Don't have an account? <Link to="/signup" className="text-blue-600 font-bold hover:underline">Sign up</Link>
      </div>
    </div>
  );
}
