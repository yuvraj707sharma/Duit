import React, { useState, useEffect } from 'react';
import {
  fetchPendingApprovals,
  fetchAuditLogs,
  fetchMetrics,
  PendingApproval,
  AuditLog as AuditLogType,
  MetricsData
} from './services/api';
import { ApprovalsList } from './components/ApprovalsList';
import { ActionLog } from './components/ActionLog';
import { StatsDashboard } from './components/StatsDashboard';
import { LearningCurveChart } from './components/LearningCurveChart';
import { WhatsAppConnect } from './components/WhatsAppConnect';
import {
  CheckSquare,
  Activity,
  History,
  TrendingUp,
  Smartphone,
  Zap,
  RefreshCw
} from 'lucide-react';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'approvals' | 'stats' | 'logs' | 'learning' | 'connect'>('approvals');
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [logs, setLogs] = useState<AuditLogType[]>([]);
  const [metrics, setMetrics] = useState<MetricsData>({
    total_requests: 0,
    tokens_saved: 0,
    cost_saved_usd: 0,
    intent_distribution: {},
    stage_latencies_ms: {}
  });
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setIsRefreshing(true);
    try {
      const [apprs, lgs, mtrs] = await Promise.all([
        fetchPendingApprovals(),
        fetchAuditLogs(),
        fetchMetrics()
      ]);
      setApprovals(apprs);
      setLogs(lgs);
      setMetrics(mtrs);
      setError(null);
    } catch (err: any) {
      setError(err?.message || 'Error loading dashboard data');
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  const pendingCount = approvals.filter(a => a.status === 'pending').length;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Header */}
      <header className="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-lg text-white tracking-tight">FastAgent</span>
                <span className="px-2 py-0.5 text-[10px] font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 rounded-full">
                  v1.0 • 4-Stage Cascade
                </span>
              </div>
              <p className="text-[11px] text-slate-400 hidden sm:block">Deterministic Safety, Laya Sub-5ms Routing & Active Learning</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={loadData}
              disabled={isRefreshing}
              className="p-2 text-slate-400 hover:text-white bg-slate-800/50 hover:bg-slate-800 rounded-lg border border-slate-700/60 transition-all active:scale-95"
              title="Refresh Data"
            >
              <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin text-indigo-400' : ''}`} />
            </button>

            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-emerald-400 text-xs font-semibold">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              Stack Healthy
            </div>
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <div className="border-b border-slate-800/60 bg-slate-900/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex space-x-1 sm:space-x-4 overflow-x-auto py-2">
          <button
            onClick={() => setActiveTab('approvals')}
            className={`px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg flex items-center gap-2 transition-all shrink-0 ${
              activeTab === 'approvals'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <CheckSquare className="w-4 h-4" />
            Approvals Queue
            {pendingCount > 0 && (
              <span className="ml-1 px-1.5 py-0.5 text-[10px] font-bold bg-amber-400 text-slate-950 rounded-full">
                {pendingCount}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('stats')}
            className={`px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg flex items-center gap-2 transition-all shrink-0 ${
              activeTab === 'stats'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <Activity className="w-4 h-4" />
            Latency & Telemetry
          </button>

          <button
            onClick={() => setActiveTab('logs')}
            className={`px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg flex items-center gap-2 transition-all shrink-0 ${
              activeTab === 'logs'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <History className="w-4 h-4" />
            Audit Log
          </button>

          <button
            onClick={() => setActiveTab('learning')}
            className={`px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg flex items-center gap-2 transition-all shrink-0 ${
              activeTab === 'learning'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <TrendingUp className="w-4 h-4" />
            Learning Curve
          </button>

          <button
            onClick={() => setActiveTab('connect')}
            className={`px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg flex items-center gap-2 transition-all shrink-0 ${
              activeTab === 'connect'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <Smartphone className="w-4 h-4" />
            Connect Channels
          </button>
        </div>
      </div>

      {/* Main Content View */}
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        {activeTab === 'approvals' && <ApprovalsList approvals={approvals} onRefresh={loadData} error={error} />}
        {activeTab === 'stats' && <StatsDashboard metrics={metrics} />}
        {activeTab === 'logs' && <ActionLog logs={logs} />}
        {activeTab === 'learning' && <LearningCurveChart />}
        {activeTab === 'connect' && <WhatsAppConnect />}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/60 py-6 text-center text-xs text-slate-500">
        FastAgent • Hackathon 2026 • Deterministic Cascade Architecture
      </footer>
    </div>
  );
};
