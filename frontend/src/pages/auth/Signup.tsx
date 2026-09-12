import { Link } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';

export default function Signup() {
  return (
    <div>
      <h2 className="text-2xl font-bold text-slate-900 mb-2">Create Account</h2>
      <p className="text-slate-500 text-sm mb-6">Start paper trading with a $500 virtual portfolio.</p>
      
      <div className="bg-rose-50 border border-rose-200 rounded-lg p-3 mb-6 flex items-start gap-3">
        <ShieldAlert className="w-5 h-5 text-rose-600 mt-0.5" />
        <div className="text-xs text-rose-800 leading-relaxed">
          <strong>Notice:</strong> This platform operates strictly in PAPER TRADING mode. Virtual capital cannot be withdrawn or monetized. Real money execution is completely disabled.
        </div>
      </div>

      <form className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Full Name</label>
          <input type="text" className="w-full border border-slate-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-blue-600 focus:border-transparent outline-none" placeholder="John Doe" />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
          <input type="email" className="w-full border border-slate-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-blue-600 focus:border-transparent outline-none" placeholder="name@company.com" />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
          <input type="password" className="w-full border border-slate-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-blue-600 focus:border-transparent outline-none" placeholder="••••••••" />
        </div>
        
        <Link to="/app" className="w-full bg-blue-600 text-white rounded-lg px-4 py-3 font-bold text-sm hover:bg-blue-700 transition-colors mt-6 block text-center shadow-sm">
          Create Account
        </Link>
      </form>
      
      <div className="mt-8 text-center text-sm text-slate-600">
        Already have an account? <Link to="/login" className="text-blue-600 font-bold hover:underline">Sign in</Link>
      </div>
    </div>
  );
}
