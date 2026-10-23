import React from 'react';
import { ShieldAlert, RefreshCw } from 'lucide-react';

interface KillSwitchIndicatorProps {
  isActive: boolean;
  onTrigger: () => void;
  onReset: () => void;
}

export const KillSwitchIndicator: React.FC<KillSwitchIndicatorProps> = ({ isActive, onTrigger, onReset }) => {
  return (
    <div style={{
      background: isActive ? 'rgba(239, 68, 68, 0.2)' : 'rgba(30, 41, 59, 0.6)',
      border: `1px solid ${isActive ? '#ef4444' : 'rgba(255, 255, 255, 0.1)'}`,
      borderRadius: '8px',
      padding: '10px 14px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: '12px'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <ShieldAlert size={18} color={isActive ? '#ef4444' : '#94a3b8'} />
        <div>
          <div style={{ fontSize: '0.8rem', fontWeight: 700, color: isActive ? '#f87171' : '#f8fafc' }}>
            {isActive ? 'KILL-SWITCH ENGAGED' : 'Kill-Switch Ready'}
          </div>
          <div style={{ fontSize: '0.68rem', color: '#94a3b8' }}>
            Hotkey: <code style={{ color: '#cbd5e1' }}>Ctrl+Shift+K</code>
          </div>
        </div>
      </div>

      {isActive ? (
        <button
          onClick={onReset}
          style={{
            padding: '4px 10px',
            background: '#3b82f6',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            fontSize: '0.75rem',
            fontWeight: 700,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px'
          }}
        >
          <RefreshCw size={12} />
          Reset
        </button>
      ) : (
        <button
          onClick={onTrigger}
          style={{
            padding: '4px 10px',
            background: '#ef4444',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            fontSize: '0.75rem',
            fontWeight: 700,
            cursor: 'pointer'
          }}
        >
          HALT ALL
        </button>
      )}
    </div>
  );
};
