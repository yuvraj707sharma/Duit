import React, { useState } from 'react';
import { PendingApproval, resolveApproval } from '../services/api';
import { AlertTriangle, CheckCircle2, XCircle, ShieldAlert, Clock } from 'lucide-react';

interface Props {
  approvals: PendingApproval[];
  onRefresh: () => void;
  error?: string | null;
}

export const ApprovalsList: React.FC<Props> = ({ approvals, onRefresh, error }) => {
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [confirmingHighRiskId, setConfirmingHighRiskId] = useState<string | null>(null);

  const handleAction = async (id: string, decision: 'approve' | 'reject') => {
    setLoadingId(id);
    setConfirmingHighRiskId(null);
    try {
      await resolveApproval(id, decision);
      onRefresh();
    } finally {
      setLoadingId(null);
    }
  };

  const pendingOnly = approvals.filter(a => a.status === 'pending');

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight">Pending Human Approvals</h2>
          <p className="text-sm text-slate-400">Deterministic code gate holds actions until you explicitly approve or reject.</p>
        </div>
        <span className="px-3 py-1 bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-semibold rounded-full flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5" />
          {pendingOnly.length} Pending
        </span>
      </div>

      {error ? (
        <div className="p-6 bg-rose-950/40 border border-rose-500/30 rounded-xl text-center space-y-2">
          <AlertTriangle className="w-8 h-8 text-rose-400 mx-auto" />
          <p className="text-rose-200 font-semibold">{error}</p>
          <button
            onClick={onRefresh}
            className="px-4 py-1.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-medium rounded-lg transition-all"
          >
            Retry Connection
          </button>
        </div>
      ) : pendingOnly.length === 0 ? (
        <div className="p-8 text-center bg-slate-900/40 border border-slate-800 rounded-xl">
          <CheckCircle2 className="w-10 h-10 text-emerald-400/80 mx-auto mb-3" />
          <p className="text-slate-300 font-medium">All caught up!</p>
          <p className="text-xs text-slate-500 mt-1">No pending actions require confirmation right now.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {pendingOnly.map((item) => (
            <div
              key={item.id}
              className="p-5 bg-slate-900/80 border border-slate-800 hover:border-slate-700 rounded-xl shadow-lg transition-all"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1.5 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 text-xs font-mono font-medium rounded">
                      {item.intent}
                    </span>
                    <span className={`px-2 py-0.5 text-xs font-semibold rounded flex items-center gap-1 ${
                      item.risk === 'high'
                        ? 'bg-rose-500/10 border border-rose-500/30 text-rose-400'
                        : 'bg-amber-500/10 border border-amber-500/30 text-amber-400'
                    }`}>
                      <ShieldAlert className="w-3 h-3" />
                      {item.risk.toUpperCase()} RISK
                    </span>
                    <span className="text-xs text-slate-400 font-mono">
                      Conf: {(item.confidence * 100).toFixed(0)}%
                    </span>
                  </div>

                  <p className="text-base text-white font-medium">"{item.query_text}"</p>
                  
                  <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 text-xs font-mono text-slate-300">
                    <p className="text-slate-400 font-semibold mb-1">Extracted Arguments:</p>
                    <pre className="whitespace-pre-wrap overflow-x-auto text-[11px] text-indigo-300">
                      {JSON.stringify(item.arguments, null, 2)}
                    </pre>
                  </div>
                </div>

                <div className="flex flex-col gap-2 min-w-[130px]">
                  {item.risk === 'high' && confirmingHighRiskId === item.id ? (
                    <div className="flex flex-col gap-1.5 p-2 bg-rose-950/60 border border-rose-500/40 rounded-lg">
                      <p className="text-[10px] text-rose-300 font-semibold text-center uppercase tracking-wider">Confirm High Risk</p>
                      <button
                        onClick={() => handleAction(item.id, 'approve')}
                        disabled={loadingId === item.id}
                        className="px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded shadow-sm transition-all"
                      >
                        Confirm
                      </button>
                      <button
                        onClick={() => setConfirmingHighRiskId(null)}
                        className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded transition-all"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <>
                      <button
                        onClick={() => {
                          if (item.risk === 'high') {
                            setConfirmingHighRiskId(item.id);
                          } else {
                            handleAction(item.id, 'approve');
                          }
                        }}
                        disabled={loadingId === item.id}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white text-xs font-semibold rounded-lg shadow-sm flex items-center justify-center gap-1.5 transition-all"
                      >
                        <CheckCircle2 className="w-4 h-4" />
                        Approve
                      </button>
                      <button
                        onClick={() => handleAction(item.id, 'reject')}
                        disabled={loadingId === item.id}
                        className="px-4 py-2 bg-rose-600/20 hover:bg-rose-600/30 border border-rose-500/30 text-rose-300 active:scale-95 text-xs font-semibold rounded-lg shadow-sm flex items-center justify-center gap-1.5 transition-all"
                      >
                        <XCircle className="w-4 h-4" />
                        Reject
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
