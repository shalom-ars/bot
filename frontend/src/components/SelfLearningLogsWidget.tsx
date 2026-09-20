import { useState } from 'react';
import { Cpu, RefreshCw, FileText } from 'lucide-react';
import { useApi } from '../hooks/useApi';

export default function SelfLearningLogsWidget() {
  const [refresh, setRefresh] = useState(0);
  const { data, loading, error } = useApi<any>(`/btc5m/self-learning-logs?limit=5&instance_id=instance_1&_t=${refresh}`, null);

  if (loading) {
    return <div className="p-4 text-center text-slate-500 animate-pulse">Loading AI logs...</div>;
  }
  if (error) {
    return <div className="p-4 text-center text-rose-500 text-sm">Failed to load AI logs.</div>;
  }

  const logs = data?.recent_logs || [];

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6 overflow-hidden">
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-2">
          <div className="bg-indigo-500/10 p-2 rounded-lg border border-indigo-500/20">
            <Cpu className="w-5 h-5 text-indigo-600" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900 tracking-tight">AI Optimizer Logs</h3>
            <p className="text-xs text-slate-500 font-medium">Gemini 3.1 Pro continuous strategy optimizer</p>
          </div>
        </div>
        <button 
          onClick={() => setRefresh(r => r + 1)}
          className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors border border-transparent hover:border-indigo-100"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <div className="space-y-3">
        {logs.length === 0 ? (
           <div className="text-center py-6 text-slate-400 text-sm flex flex-col items-center">
              <FileText className="w-6 h-6 mb-2 opacity-50" />
              No optimization logs yet.
           </div>
        ) : (
          logs.slice(0, 5).map((log: any, idx: number) => (
            <div key={idx} className="p-3 bg-slate-50 border border-slate-100 rounded-xl hover:border-indigo-100 transition-colors">
              <div className="flex justify-between items-start mb-2">
                 <div className="flex items-center gap-2">
                    <span className="text-[10px] font-black uppercase tracking-wider text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-100 shadow-sm">
                      {log.outcome}
                    </span>
                    <span className="text-[10px] font-mono text-slate-400">
                      {new Date(log.timestamp).toLocaleString()}
                    </span>
                 </div>
                 {log.trade_id && (
                    <span className="text-[10px] font-mono text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200 shadow-sm">
                      Trade #{log.trade_id}
                    </span>
                 )}
              </div>
              
              <div className="text-sm font-bold text-slate-800 mb-1 leading-tight">
                {log.root_cause?.replace(/_/g, ' ')}
              </div>
              <p className="text-xs text-slate-600 mb-2 leading-relaxed">
                {log.error_analysis}
              </p>
              
              {(log.old_value || log.new_value) && (
                 <div className="mt-2 pt-2 border-t border-slate-200/60 flex gap-4 text-[10px] font-mono">
                    <div className="flex-1 overflow-hidden">
                       <span className="text-slate-400 block mb-0.5 uppercase tracking-wider text-[8px] font-sans font-bold">Adjusted Parameters</span>
                       <span className="text-indigo-700 font-bold break-words">{log.parameter_adjusted || 'N/A'}</span>
                    </div>
                    {log.adaptation_delta && (
                      <div className="text-right">
                         <span className="text-slate-400 block mb-0.5 uppercase tracking-wider text-[8px] font-sans font-bold">Impact / Metric</span>
                         <span className="text-emerald-600 font-bold">{log.adaptation_delta}</span>
                      </div>
                    )}
                 </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
