import { Link } from 'react-router-dom';
import { Shield, Activity, Lock, Database, Zap, Wallet, ArrowRight } from 'lucide-react';
import BrandLogo from '../components/BrandLogo';

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans">
      {/* Navigation */}
      <nav className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <div className="flex items-center gap-2.5">
              <BrandLogo size={32} />
              <span className="text-2xl font-extrabold tracking-tighter text-slate-900">FAST5M BOT</span>
            </div>
            <div className="hidden md:flex gap-8 text-sm font-medium text-slate-600">
              <a href="#product" className="hover:text-blue-600 transition-colors">Features</a>
              <a href="#vault" className="hover:text-blue-600 transition-colors">Trading Vault</a>
              <a href="#security" className="hover:text-blue-600 transition-colors">Security</a>
            </div>
            <div className="flex items-center gap-4">
              <Link to="/login" className="text-sm font-semibold text-slate-600 hover:text-slate-900">
                Sign In
              </Link>
              <Link to="/login?mode=real" className="text-sm font-bold bg-emerald-600 text-white px-4 py-2 rounded-lg hover:bg-emerald-700 transition-colors shadow-sm flex items-center gap-1.5">
                <Wallet className="w-4 h-4" />
                <span>Connect Wallet</span>
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <div className="relative overflow-hidden bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-28 text-center">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-blue-50 border border-blue-200 text-blue-700 text-xs font-bold mb-8">
            <Zap className="w-3.5 h-3.5 text-blue-600" /> 
            <span>7-Asset 5-Minute Fast Prediction Engine • Polygon Mainnet CLOB</span>
          </div>
          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-slate-900 mb-6 leading-tight">
            Sub-Second Intelligence <br/><span className="text-blue-600">for 5-Minute Prediction Rounds</span>
          </h1>
          <p className="text-lg md:text-xl text-slate-600 mb-10 max-w-3xl mx-auto leading-relaxed">
            Automate top-ranked binary trades across BTC, ETH, SOL, XRP, DOGE, BNB, and HYPE. Practice with an isolated <strong>$300 virtual demo balance</strong> or connect your Polygon Web3 wallet for live CLOB execution.
          </p>
          <div className="flex flex-col sm:flex-row justify-center gap-4 max-w-md mx-auto">
            <Link 
              to="/login?mode=demo" 
              className="bg-blue-600 text-white px-7 py-3.5 rounded-xl font-black text-base hover:bg-blue-700 transition-all shadow-lg hover:shadow-xl flex items-center justify-center gap-2"
            >
              <Zap className="w-4 h-4" />
              <span>Start Demo ($300 Virtual)</span>
            </Link>
            <Link 
              to="/login?mode=real" 
              className="bg-slate-900 text-white border-2 border-slate-900 px-7 py-3.5 rounded-xl font-black text-base hover:bg-slate-800 transition-all shadow-md flex items-center justify-center gap-2"
            >
              <Wallet className="w-4 h-4 text-emerald-400" />
              <span>Connect Live Wallet</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>

      {/* Features */}
      <div id="product" className="bg-slate-50 py-24 border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-slate-900 mb-4">Enterprise Prediction Architecture</h2>
            <p className="text-slate-600 max-w-2xl mx-auto">Dual authentication, multi-user isolation, sub-second latency feeds, and isolated capital allocation.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { icon: Zap, title: "Sub-Second Pyth & Chainlink", desc: "Real-time oracle telemetry tracking spot price deltas, velocity, and epoch boundaries with zero lag." },
              { icon: Wallet, title: "Web3 Multi-Wallet Support", desc: "Native integration for MetaMask, Coinbase Wallet, Phantom (EVM), Rabby, and WalletConnect with automatic Polygon switching." },
              { icon: Lock, title: "Isolated Trading Vault", desc: "Allocate exact trading capital ($50, $100, $250, custom). Funds locked in open trades cannot be withdrawn until closed." },
              { icon: Activity, title: "Automated #1 Ranked Execution", desc: "Dynamically identifies and executes the single strongest quantitative opportunity across 7 assets concurrently." },
              { icon: Shield, title: "Hard Stop-Loss & Anti-Reversal", desc: "Strict max loss limit enforcement combined with aggressive trailing locks that bank profit on momentum turn." },
              { icon: Database, title: "Strict Multi-User Isolation", desc: "User settings, lifetime trade histories, and allocated balances are strictly partitioned per account." }
            ].map((f, i) => (
              <div key={i} className="bg-white p-8 rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
                <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center text-blue-600 mb-6">
                  <f.icon className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-bold text-slate-900 mb-3">{f.title}</h3>
                <p className="text-slate-600 leading-relaxed text-sm">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-slate-900 text-slate-400 py-12 text-sm border-t border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row justify-between items-center gap-6">
          <div className="flex items-center gap-2.5 text-white font-bold text-xl">
            <BrandLogo size={28} />
            <span>FAST5M PLATFORM</span>
          </div>
          <div className="text-center md:text-right max-w-lg">
            <p className="mb-2">Disclaimer: Fast5M is a high-speed prediction market analytical platform. Prediction markets carry financial risk.</p>
            <p>&copy; 2026 Fast5M Platform. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
