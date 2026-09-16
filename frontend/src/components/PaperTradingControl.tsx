import { useState, useEffect } from 'react';
import { Play, Pause, Square, AlertOctagon } from 'lucide-react';
import client from '../api/client';

export function PaperTradingControl() {
  const [status, setStatus] = useState<string>('UNKNOWN');
  const [loading, setLoading] = useState(false);

  const fetchStatus = () => {
    client.get('/system/status').then(res => {
      setStatus(res.data.paper_trading_status);
    }).catch(err => {
      console.error(err);
      setStatus('ERROR');
    });
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleAction = async (action: string) => {
    setLoading(true);
    try {
      await client.post('/system/control', { action, reason: 'UI Manual Action' });
      fetchStatus();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const statusColors: any = {
    'RUNNING': 'bg-emerald-500',
    'PAUSED': 'bg-amber-500',
    'STOPPED': 'bg-slate-500',
    'EMERGENCY_STOP': 'bg-red-600',
    'UNKNOWN': 'bg-slate-300',
    'ERROR': 'bg-red-500'
  };

  return (
    <div className="bg-slate-900 text-white p-4 rounded-xl shadow-lg border border-slate-700 flex flex-col md:flex-row justify-between items-center gap-4 mb-8">
      <div className="flex items-center gap-4">
        <div className="flex flex-col">
          <span className="text-xs font-bold text-slate-400 tracking-wider">PAPER TRADING</span>
          <div className="flex items-center gap-2 mt-1">
            <span className={`w-3 h-3 rounded-full ${statusColors[status] || 'bg-slate-500'} ${status === 'RUNNING' ? 'animate-pulse' : ''}`}></span>
            <span className="font-bold text-lg">{status}</span>
          </div>
        </div>
      </div>
      
      <div className="flex flex-wrap gap-2">
        {status !== 'RUNNING' && (
          <button 
            disabled={loading}
            onClick={() => handleAction('START')}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm font-bold transition-colors disabled:opacity-50"
          >
            <Play className="w-4 h-4" /> START
          </button>
        )}
        
        {status === 'RUNNING' && (
          <button 
            disabled={loading}
            onClick={() => handleAction('PAUSE')}
            className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 rounded-lg text-sm font-bold transition-colors disabled:opacity-50"
          >
            <Pause className="w-4 h-4" /> PAUSE
          </button>
        )}

        {(status === 'PAUSED' || status === 'EMERGENCY_STOP') && (
          <button 
            disabled={loading}
            onClick={() => handleAction('RESUME')}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm font-bold transition-colors disabled:opacity-50"
          >
            <Play className="w-4 h-4" /> RESUME
          </button>
        )}

        {status !== 'STOPPED' && status !== 'EMERGENCY_STOP' && (
          <button 
            disabled={loading}
            onClick={() => handleAction('STOP')}
            className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-bold transition-colors disabled:opacity-50"
          >
            <Square className="w-4 h-4" /> STOP
          </button>
        )}

        <button 
          disabled={loading || status === 'EMERGENCY_STOP'}
          onClick={() => handleAction('EMERGENCY_STOP')}
          className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-sm font-bold transition-colors disabled:opacity-50"
        >
          <AlertOctagon className="w-4 h-4" /> E-STOP
        </button>
      </div>
    </div>
  );
}
