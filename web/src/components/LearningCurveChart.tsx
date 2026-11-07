import React from 'react';
import { TrendingUp, Award } from 'lucide-react';

export const LearningCurveChart: React.FC = () => {
  // Active learning calibration progression
  const points = [
    { corrections: 0, accuracy: 85, threshold: 'Safe Gate (1.00)' },
    { corrections: 2, accuracy: 86.6, threshold: 'Safe Gate (1.00)' },
    { corrections: 5, accuracy: 89, threshold: 'Safe Gate (1.00)' },
    { corrections: 10, accuracy: 93, threshold: 'Safe Gate (1.00)' },
    { corrections: 15, accuracy: 97, threshold: '0.92' },
    { corrections: 20, accuracy: 99, threshold: '0.85' },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white tracking-tight">Active Learning & Policy Adaptation</h2>
        <p className="text-sm text-slate-400">Accuracy vs explicit user corrections (learned only from explicit approvals, never silence).</p>
      </div>

      <div className="p-6 bg-slate-900/80 border border-slate-800 rounded-xl space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-indigo-400" />
            <span className="text-sm font-semibold text-white">Held-Out Intent Accuracy vs Corrections</span>
          </div>
          <span className="px-3 py-1 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-bold rounded-full flex items-center gap-1.5">
            <Award className="w-3.5 h-3.5" />
            99.0% Top Accuracy
          </span>
        </div>

        {/* Visual Progress Bar Chart */}
        <div className="space-y-3">
          {points.map((pt) => (
            <div key={pt.corrections} className="space-y-1">
              <div className="flex justify-between text-xs text-slate-300 font-mono">
                <span>N = {pt.corrections} corrections</span>
                <span className="text-emerald-400 font-bold">{pt.accuracy}% accuracy</span>
              </div>
              <div className="w-full h-3 bg-slate-950 rounded-full overflow-hidden p-0.5 border border-slate-800">
                <div
                  className="h-full bg-gradient-to-r from-indigo-500 via-indigo-400 to-emerald-400 rounded-full transition-all duration-500"
                  style={{ width: `${pt.accuracy}%` }}
                />
              </div>
              <div className="text-[10px] text-slate-500 text-right">
                Auto-approve threshold: <span className="text-slate-400 font-mono">{pt.threshold}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
