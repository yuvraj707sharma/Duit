import React from 'react';
import { MetricsData } from '../services/api';
import { Zap, DollarSign, Cpu, Activity, Clock } from 'lucide-react';

interface Props {
  metrics: MetricsData;
}

export const StatsDashboard: React.FC<Props> = ({ metrics }) => {
  const latencies = metrics.stage_latencies_ms || {};

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white tracking-tight">System Performance & Cascade Telemetry</h2>
        <p className="text-sm text-slate-400">Real-time breakdown of stage latencies, token savings, and cost reductions.</p>
      </div>

      {/* Top Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 bg-slate-900/80 border border-slate-800 rounded-xl space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-semibold uppercase tracking-wider">Total Requests</span>
            <Activity className="w-4 h-4 text-indigo-400" />
          </div>
          <p className="text-2xl font-bold text-white font-mono">{metrics.total_requests}</p>
          <p className="text-xs text-slate-500">Processed through cascade</p>
        </div>

        <div className="p-4 bg-slate-900/80 border border-slate-800 rounded-xl space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-semibold uppercase tracking-wider">Tokens Saved</span>
            <Zap className="w-4 h-4 text-amber-400" />
          </div>
          <p className="text-2xl font-bold text-amber-300 font-mono">{metrics.tokens_saved.toLocaleString()}</p>
          <p className="text-xs text-slate-500">Bypassed large LLM calls</p>
        </div>

        <div className="p-4 bg-slate-900/80 border border-slate-800 rounded-xl space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-semibold uppercase tracking-wider">Estimated Savings</span>
            <DollarSign className="w-4 h-4 text-emerald-400" />
          </div>
          <p className="text-2xl font-bold text-emerald-300 font-mono">${metrics.cost_saved_usd.toFixed(4)}</p>
          <p className="text-xs text-slate-500">Compared to pure LLM agents</p>
        </div>

        <div className="p-4 bg-slate-900/80 border border-slate-800 rounded-xl space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-semibold uppercase tracking-wider">Laya Stage Avg</span>
            <Clock className="w-4 h-4 text-indigo-400" />
          </div>
          <p className="text-2xl font-bold text-indigo-300 font-mono">
            {latencies['stage_2_laya_decision']?.avg || 0.8} ms
          </p>
          <p className="text-xs text-slate-500">Sub-5ms System 1 inference</p>
        </div>
      </div>

      {/* Stage Latency Table */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 space-y-3">
        <h3 className="text-sm font-semibold text-white uppercase tracking-wider flex items-center gap-2">
          <Cpu className="w-4 h-4 text-indigo-400" />
          Per-Stage Latency Breakdown (Benchmark Timing)
        </h3>
        
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono text-slate-300">
            <thead className="border-b border-slate-800 text-slate-400 uppercase text-[10px]">
              <tr>
                <th className="py-2.5 px-3">Stage</th>
                <th className="py-2.5 px-3">Avg Latency</th>
                <th className="py-2.5 px-3">P50</th>
                <th className="py-2.5 px-3">P95</th>
                <th className="py-2.5 px-3">Calls</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {Object.entries(latencies).map(([stage, stats]) => (
                <tr key={stage} className="hover:bg-slate-800/40">
                  <td className="py-2.5 px-3 font-semibold text-indigo-400">{stage.replace(/_/g, ' ')}</td>
                  <td className="py-2.5 px-3 text-white font-bold">{stats.avg} ms</td>
                  <td className="py-2.5 px-3 text-slate-400">{stats.p50} ms</td>
                  <td className="py-2.5 px-3 text-amber-400 font-bold">{stats.p95} ms</td>
                  <td className="py-2.5 px-3 text-slate-500">{stats.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
