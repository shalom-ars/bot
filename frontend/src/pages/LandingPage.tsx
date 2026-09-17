import { Link } from 'react-router-dom';
import { Shield, TrendingUp, Activity, Lock, BarChart3, Database } from 'lucide-react';
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
              <span className="text-2xl font-extrabold tracking-tighter text-slate-900">JONANDA BOT</span>
            </div>
            <div className="hidden md:flex gap-8 text-sm font-medium text-slate-600">
              <a href="#product" className="hover:text-blue-600 transition-colors">Product</a>
              <a href="#research" className="hover:text-blue-600 transition-colors">Research</a>
              <a href="#security" className="hover:text-blue-600 transition-colors">Security</a>
              <a href="#pricing" className="hover:text-blue-600 transition-colors">Pricing</a>
            </div>
            <div className="flex items-center gap-4">
              <Link to="/login" className="text-sm font-semibold text-slate-600 hover:text-slate-900">Sign In</Link>
              <Link to="/signup" className="text-sm font-bold bg-blue-600 text-white px-5 py-2.5 rounded-lg hover:bg-blue-700 transition-colors shadow-sm">
                Get Started
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <div className="relative overflow-hidden bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-24 pb-32 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-rose-50 border border-rose-200 text-rose-700 text-xs font-bold mb-8">
            <Shield className="w-3 h-3" /> PAPER TRADING ONLY. REAL-MONEY TRADING IS CURRENTLY DISABLED.
          </div>
          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-slate-900 mb-8 leading-tight">
            Quantitative Intelligence <br/><span className="text-blue-600">for Prediction Markets</span>
          </h1>
          <p className="text-xl text-slate-600 mb-10 max-w-3xl mx-auto leading-relaxed">
            Turn prediction-market data into structured probabilities, signals, and risk-aware decisions. Practice with a virtual $500 portfolio using real-time Polymarket data.
          </p>
          <div className="flex justify-center gap-4">
            <Link to="/signup" className="bg-blue-600 text-white px-8 py-4 rounded-xl font-bold text-lg hover:bg-blue-700 transition-all shadow-lg hover:shadow-xl">
              Start Paper Trading
            </Link>
            <Link to="/app" className="bg-white text-slate-700 border-2 border-slate-200 px-8 py-4 rounded-xl font-bold text-lg hover:border-slate-300 hover:bg-slate-50 transition-all">
              Explore Demo
            </Link>
          </div>
        </div>
      </div>

      {/* Features */}
      <div id="product" className="bg-slate-50 py-24 border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-slate-900 mb-4">Professional Analytical Tools</h2>
            <p className="text-slate-600 max-w-2xl mx-auto">Everything you need to analyze prediction markets without risking real capital.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { icon: Database, title: "Real-Time Intelligence", desc: "Live ingestion of Polymarket orderbooks and automated feature extraction." },
              { icon: BarChart3, title: "Probability Modeling", desc: "Advanced calibration checking net edge against spread and liquidity slippage." },
              { icon: Activity, title: "Signal Detection", desc: "Real-time TRADE, SKIP, and RESEARCH metrics updated instantly." },
              { icon: Shield, title: "Risk Management", desc: "Sophisticated drawdown, consecutive loss, and daily exposure limits." },
              { icon: TrendingUp, title: "Paper Portfolio", desc: "Execute simulated orders safely with a $500 virtual allocation." },
              { icon: Lock, title: "Security & Isolation", desc: "Multi-tenant architecture isolating your virtual funds and analytical rules." }
            ].map((f, i) => (
              <div key={i} className="bg-white p-8 rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
                <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center text-blue-600 mb-6">
                  <f.icon className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-bold text-slate-900 mb-3">{f.title}</h3>
                <p className="text-slate-600 leading-relaxed">{f.desc}</p>
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
            <span>JONANDA BOT</span>
          </div>
          <div className="text-center md:text-right max-w-lg">
            <p className="mb-2">Disclaimer: Jonanda Bot is a quantitative research and paper-trading platform. No profitability or investment outcome is guaranteed.</p>
            <p>&copy; 2026 Jonanda Bot. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
