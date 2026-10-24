import React, { useState, useEffect, useRef } from 'react';
import { Mic, MicOff, ChevronLeft, ChevronRight, History, Trash2, Laptop, Wifi, WifiOff } from 'lucide-react';
import { StatusOverlay, OverlayState } from './components/StatusOverlay';
import { KillSwitchIndicator } from './components/KillSwitchIndicator';

declare global {
  interface Window {
    electronAPI?: {
      triggerKillSwitch: () => Promise<{ success: boolean; killSwitchActive: boolean }>;
      resetKillSwitch: () => Promise<{ success: boolean; killSwitchActive: boolean }>;
      toggleSidebar: (isExpanded: boolean) => Promise<boolean>;
      onKillSwitchActivated: (callback: () => void) => void;
    };
  }
}

export const App: React.FC = () => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [isMicToggledOn, setIsMicToggledOn] = useState(true);
  const [isPushToTalkHeld, setIsPushToTalkHeld] = useState(false);
  const [isKillSwitchActive, setIsKillSwitchActive] = useState(false);
  const [isBackendOnline, setIsBackendOnline] = useState(true);
  
  // Context history state
  const [contextSummary, setContextSummary] = useState<string>("Ready for voice or cross-channel commands.");
  const [operations, setOperations] = useState<Array<{ intent: string; target: string; status: string; timestamp: number }>>([
    { intent: 'open_app', target: 'code', status: 'completed', timestamp: Date.now() - 60000 },
    { intent: 'set_volume', target: '75%', status: 'completed', timestamp: Date.now() - 30000 }
  ]);

  // Status overlay state
  const [overlay, setOverlay] = useState<OverlayState>({
    heardText: '',
    doingAction: '',
    countdownSeconds: 2.0,
    active: false,
    status: 'pending_cancel'
  });

  const cancelTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // Listen for global electron kill switch shortcut
    if (window.electronAPI?.onKillSwitchActivated) {
      window.electronAPI.onKillSwitchActivated(() => {
        setIsKillSwitchActive(true);
        handleCancelAction();
      });
    }

    // Ping backend health to update connection status
    const checkBackend = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/health');
        setIsBackendOnline(res.ok);
      } catch {
        setIsBackendOnline(false);
      }
    };
    checkBackend();
    const timer = setInterval(checkBackend, 10000);
    return () => clearInterval(timer);
  }, []);

  const handleToggleSidebar = () => {
    const next = !isExpanded;
    setIsExpanded(next);
    window.electronAPI?.toggleSidebar(next);
  };

  // Push-To-Talk Handlers (Mic open ONLY when toggled ON AND key/button held down)
  const handlePushToTalkStart = () => {
    if (!isMicToggledOn || isKillSwitchActive) return;
    setIsPushToTalkHeld(true);
  };

  const handlePushToTalkEnd = () => {
    if (!isPushToTalkHeld) return;
    setIsPushToTalkHeld(false);
    // Simulate voice recognized sample command
    triggerSimulatedVoiceCommand("open notepad on my laptop", "open_app (notepad)");
  };

  const triggerSimulatedVoiceCommand = (heard: string, action: string) => {
    if (isKillSwitchActive) return;

    setOverlay({
      heardText: heard,
      doingAction: action,
      countdownSeconds: 2.0,
      active: true,
      status: 'pending_cancel'
    });

    if (cancelTimerRef.current) clearTimeout(cancelTimerRef.current);

    // 2-second cancel window before execution dispatch
    cancelTimerRef.current = setTimeout(() => {
      setOverlay((prev) => ({ ...prev, status: 'completed' }));
      setOperations((prev) => [
        ...prev.slice(-19),
        { intent: action, target: heard, status: 'completed', timestamp: Date.now() }
      ]);
      setContextSummary(`Executed ${action}. Context sanitized.`);

      setTimeout(() => {
        setOverlay((prev) => ({ ...prev, active: false }));
      }, 1500);
    }, 2000);
  };

  const handleCancelAction = () => {
    if (cancelTimerRef.current) {
      clearTimeout(cancelTimerRef.current);
      cancelTimerRef.current = null;
    }
    setOverlay((prev) => ({ ...prev, status: 'cancelled' }));
    setTimeout(() => {
      setOverlay((prev) => ({ ...prev, active: false }));
    }, 1200);
  };

  const handleClearHistory = () => {
    setOperations([]);
    setContextSummary("Context history cleared by user.");
  };

  return (
    <div style={{ padding: '8px', width: '100%', height: '100%' }}>
      {/* Collapsed Mini Float Button */}
      {!isExpanded ? (
        <button
          onClick={handleToggleSidebar}
          style={{
            width: '56px',
            height: '56px',
            borderRadius: '28px',
            background: 'linear-gradient(135deg, #1e293b, #0f172a)',
            border: '2px solid #ef4444',
            color: 'white',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            boxShadow: '0 8px 24px rgba(239, 68, 68, 0.4)'
          }}
          title="Expand FastAgent Sidebar"
        >
          <ChevronLeft size={24} color="#ef4444" />
        </button>
      ) : (
        /* Expanded Sidebar Widget */
        <div style={{
          background: 'var(--bg-widget)',
          border: '1px solid var(--border-color)',
          borderRadius: '16px',
          padding: '18px',
          boxShadow: '0 12px 40px rgba(0, 0, 0, 0.6)',
          backdropFilter: 'blur(16px)',
          display: 'flex',
          flexDirection: 'column',
          maxHeight: '580px'
        }}>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }} className="drag-handle">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{ width: '28px', height: '28px', background: '#ef4444', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Laptop size={16} color="white" />
              </div>
              <div>
                <div style={{ fontSize: '0.88rem', fontWeight: 800 }}>FastAgent Desktop</div>
                <div style={{ fontSize: '0.68rem', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  {isBackendOnline ? <Wifi size={10} color="#10b981" /> : <WifiOff size={10} color="#ef4444" />}
                  <span>{isBackendOnline ? 'Presence Online' : 'Presence Offline'}</span>
                </div>
              </div>
            </div>

            <button
              onClick={handleToggleSidebar}
              style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '4px' }}
              title="Collapse Sidebar"
            >
              <ChevronRight size={20} />
            </button>
          </div>

          {/* Kill Switch Indicator */}
          <KillSwitchIndicator
            isActive={isKillSwitchActive}
            onTrigger={() => {
              setIsKillSwitchActive(true);
              handleCancelAction();
              window.electronAPI?.triggerKillSwitch();
            }}
            onReset={() => {
              setIsKillSwitchActive(false);
              window.electronAPI?.resetKillSwitch();
            }}
          />

          {/* Status Overlay (Heard -> Doing with 2s cancel window) */}
          <StatusOverlay overlay={overlay} onCancel={handleCancelAction} />

          {/* Push-to-talk Mic Section */}
          <div style={{
            background: 'rgba(30, 41, 59, 0.4)',
            border: '1px solid rgba(255, 255, 255, 0.06)',
            borderRadius: '10px',
            padding: '14px',
            marginBottom: '14px',
            textAlign: 'center'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase' }}>
                Push-To-Talk Voice
              </span>
              <button
                onClick={() => setIsMicToggledOn(!isMicToggledOn)}
                style={{
                  background: isMicToggledOn ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                  color: isMicToggledOn ? '#10b981' : '#ef4444',
                  border: 'none',
                  borderRadius: '12px',
                  padding: '3px 8px',
                  fontSize: '0.7rem',
                  fontWeight: 700,
                  cursor: 'pointer'
                }}
              >
                {isMicToggledOn ? 'Mic Enabled' : 'Mic Muted'}
              </button>
            </div>

            <button
              onMouseDown={handlePushToTalkStart}
              onMouseUp={handlePushToTalkEnd}
              onTouchStart={handlePushToTalkStart}
              onTouchEnd={handlePushToTalkEnd}
              disabled={!isMicToggledOn || isKillSwitchActive}
              className={isPushToTalkHeld ? 'pulsing-mic' : ''}
              style={{
                width: '100%',
                padding: '14px',
                borderRadius: '8px',
                background: isPushToTalkHeld
                  ? 'linear-gradient(135deg, #ef4444, #dc2626)'
                  : isMicToggledOn
                  ? '#1e293b'
                  : '#0f172a',
                color: isPushToTalkHeld ? '#ffffff' : isMicToggledOn ? '#f8fafc' : '#64748b',
                border: `1px solid ${isPushToTalkHeld ? '#ef4444' : 'rgba(255, 255, 255, 0.1)'}`,
                fontWeight: 700,
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                cursor: isMicToggledOn && !isKillSwitchActive ? 'pointer' : 'not-allowed'
              }}
            >
              {isMicToggledOn ? <Mic size={18} /> : <MicOff size={18} />}
              <span>{isPushToTalkHeld ? 'Listening (Release to Execute)...' : 'Hold to Speak (Push-To-Talk)'}</span>
            </button>
            <div style={{ fontSize: '0.68rem', color: '#64748b', marginTop: '6px' }}>
              Mic opens strictly while toggled ON & held down
            </div>
          </div>

          {/* Context Store Viewer (Last 20 operations + sanitized summary) */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: '120px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', fontWeight: 700, color: '#94a3b8' }}>
                <History size={14} />
                <span>Sanitized Context Store</span>
              </div>
              <button
                onClick={handleClearHistory}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#94a3b8',
                  fontSize: '0.7rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  cursor: 'pointer'
                }}
                title="Clear Context History"
              >
                <Trash2 size={12} />
                <span>Clear</span>
              </button>
            </div>

            <div style={{ fontSize: '0.72rem', color: '#cbd5e1', marginBottom: '8px', background: 'rgba(0,0,0,0.2)', padding: '6px 8px', borderRadius: '4px' }}>
              {contextSummary}
            </div>

            <div style={{ flex: 1, overflowY: 'auto', maxHeight: '140px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {operations.map((op, idx) => (
                <div
                  key={idx}
                  style={{
                    fontSize: '0.72rem',
                    padding: '4px 8px',
                    borderRadius: '4px',
                    background: 'rgba(255, 255, 255, 0.03)',
                    display: 'flex',
                    justifyContent: 'space-between'
                  }}
                >
                  <span style={{ color: '#60a5fa', fontWeight: 600 }}>{op.intent}</span>
                  <span style={{ color: '#94a3b8' }}>{op.target}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
