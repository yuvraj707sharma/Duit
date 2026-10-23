import React, { useEffect, useState } from 'react';
import { AlertCircle, XCircle, CheckCircle2 } from 'lucide-react';

export interface OverlayState {
  heardText: string;
  doingAction: string;
  countdownSeconds: number; // 2.0
  active: boolean;
  status: 'pending_cancel' | 'executing' | 'completed' | 'cancelled';
}

interface StatusOverlayProps {
  overlay: OverlayState;
  onCancel: () => void;
}

export const StatusOverlay: React.FC<StatusOverlayProps> = ({ overlay, onCancel }) => {
  const [progress, setProgress] = useState(100);

  useEffect(() => {
    if (!overlay.active || overlay.status !== 'pending_cancel') {
      setProgress(100);
      return;
    }

    const interval = 50; // ms
    const totalMs = 2000;
    const decrement = (interval / totalMs) * 100;

    const timer = setInterval(() => {
      setProgress((prev) => {
        const next = prev - decrement;
        return next <= 0 ? 0 : next;
      });
    }, interval);

    return () => clearInterval(timer);
  }, [overlay.active, overlay.status]);

  if (!overlay.active) return null;

  return (
    <div style={{
      background: 'rgba(15, 23, 42, 0.96)',
      border: '1px solid rgba(239, 68, 68, 0.4)',
      borderRadius: '12px',
      padding: '16px',
      boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)',
      backdropFilter: 'blur(12px)',
      marginBottom: '12px',
      color: '#f8fafc'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.78rem', fontWeight: 700, color: '#f87171', textTransform: 'uppercase' }}>
          <AlertCircle size={15} />
          <span>FastAgent Voice Action</span>
        </div>
        {overlay.status === 'pending_cancel' && (
          <span style={{ fontSize: '0.75rem', fontFamily: 'var(--mono)', color: '#94a3b8' }}>
            {(progress / 50).toFixed(1)}s cancel window
          </span>
        )}
      </div>

      <div style={{ fontSize: '0.88rem', marginBottom: '6px' }}>
        <span style={{ color: '#94a3b8' }}>Heard: </span>
        <strong style={{ color: '#ffffff' }}>"{overlay.heardText}"</strong>
      </div>

      <div style={{ fontSize: '0.88rem', marginBottom: '12px' }}>
        <span style={{ color: '#94a3b8' }}>Doing: </span>
        <strong style={{ color: '#60a5fa' }}>{overlay.doingAction}</strong>
      </div>

      {overlay.status === 'pending_cancel' && (
        <>
          {/* 2-Second Countdown Bar */}
          <div style={{ height: '4px', background: 'rgba(255, 255, 255, 0.1)', borderRadius: '2px', overflow: 'hidden', marginBottom: '12px' }}>
            <div style={{
              height: '100%',
              width: `${progress}%`,
              background: 'linear-gradient(90deg, #ef4444, #f59e0b)',
              transition: 'width 50ms linear'
            }} />
          </div>

          <button
            onClick={onCancel}
            style={{
              width: '100%',
              padding: '8px 12px',
              background: '#ef4444',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontWeight: 700,
              fontSize: '0.82rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              cursor: 'pointer'
            }}
          >
            <XCircle size={16} />
            <span>Cancel Action (2s window)</span>
          </button>
        </>
      )}

      {overlay.status === 'completed' && (
        <div style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.82rem', fontWeight: 600 }}>
          <CheckCircle2 size={16} />
          <span>Action executed successfully</span>
        </div>
      )}

      {overlay.status === 'cancelled' && (
        <div style={{ color: '#f87171', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.82rem', fontWeight: 600 }}>
          <XCircle size={16} />
          <span>Action cancelled by user</span>
        </div>
      )}
    </div>
  );
};
