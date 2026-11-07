import React from 'react';
import { AuditLog } from '../services/api';
import { History } from 'lucide-react';

interface Props {
  logs: AuditLog[];
}

export const ActionLog: React.FC<Props> = ({ logs }) => {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold text-white tracking-tight">Append-Only Audit Log</h2>
        <p className="text-sm text-slate-400">Immutable record of every decision, confidence score, and stage latency.</p>
      </div>

      {logs.length === 0 ? (
        <div className="p-8 text-center bg-slate-900/40 border border-slate-800 rounded-xl">
          <History className="w-8 h-8 text-slate-600 mx-auto mb-2" />
          <p className="text-slate-400 text-sm">No action logs recorded yet.</p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {logs.map((log, idx) => (
            <div
              key={log.request_id || idx}
              className="p-4 bg-slate-900/60 border border-slate-800/80 rounded-xl flex items-center justify-between gap-4 text-xs font-mono"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-indigo-400 font-semibold">{log.intent}</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    log.status === 'executed'
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                      : log.status === 'pending_confirmation'
                      ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                      : 'bg-slate-800 text-slate-400'
                  }`}>
                    {log.status.toUpperCase()}
                  </span>
                  <span className="text-slate-500 font-sans">User: {log.user_id}</span>
                </div>
                <div className="text-slate-400 font-sans flex items-center gap-3">
                  <span>Confidence: {(log.confidence * 100).toFixed(0)}%</span>
                  <span>Risk: {log.risk}</span>
                </div>
              </div>

              <div className="text-right text-slate-400 text-[11px] space-y-0.5">
                {Object.entries(log.latencies || {}).map(([stage, ms]) => (
                  <div key={stage} className="text-slate-500">
                    {stage.replace('stage_', '')}: <span className="text-slate-300 font-bold">{ms.toFixed(1)}ms</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
