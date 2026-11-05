import { useEffect, useRef, useState, useCallback } from 'react';
import './DuitRoamer.css';
import DuitMascot from './DuitMascot';

const PHRASES = {
  idle: [
    "Just say it, ho gaya.",
    "Searching your desktop files...",
    "Kya karna hai boss?",
    "WhatsApp check kar raha hu...",
    "Chrome profile 4 ready hai!",
  ],
  wave: [
    "Hey! Main DUIT hu!",
    "Namaste! Aapka desktop sambhal liya!",
    "Remote control ready hai boss!",
  ],
  happy: [
    "Ho gaya! Action complete!",
    "Done boss! Next task?",
    "Calendar & Gmail updated!",
  ],
  sleep: [
    "Zzz... thoda background rest...",
    "Heartbeat active... standby mode...",
  ],
  scrollFeatures: [
    "Yeh dekho, multi-profile browser features!",
    "WhatsApp se desktop commands!",
  ],
  scrollConnect: [
    "Yahan se Google account link kar lo boss!",
  ]
};

export default function DuitRoamer() {
  const [pos, setPos] = useState({ x: 120, y: 260 });
  const [target, setTarget] = useState({ x: 300, y: 260 });
  const [mood, setMood] = useState('idle');
  const [bubble, setBubble] = useState('');
  const [facing, setFacing] = useState(1);
  const [isDragging, setIsDragging] = useState(false);

  const posRef = useRef(pos);
  const targetRef = useRef(target);
  const moodRef = useRef(mood);
  posRef.current = pos;
  targetRef.current = target;
  moodRef.current = mood;

  const pickNewTarget = useCallback(() => {
    const padding = 80;
    const newX = padding + Math.random() * (Math.max(window.innerWidth - padding * 2, 200));
    const newY = 120 + Math.random() * (Math.max(window.innerHeight - 280, 200));
    setTarget({ x: newX, y: newY });
    targetRef.current = { x: newX, y: newY };
    setFacing(newX > posRef.current.x ? 1 : -1);
  }, []);

  // Main roaming physics loop - 60fps
  useEffect(() => {
    let raf;
    let idleTimer = 0;

    const loop = () => {
      const cur = posRef.current;
      const tgt = targetRef.current;
      const dx = tgt.x - cur.x;
      const dy = tgt.y - cur.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (moodRef.current === 'sleeping' || moodRef.current === 'dancing') {
        // Paused
      } else if (dist > 6 && !isDragging) {
        if (moodRef.current !== 'walking') setMood('walking');
        const speed = 1.6;
        const nx = cur.x + (dx / dist) * speed;
        const ny = cur.y + (dy / dist) * speed;
        setPos({ x: nx, y: ny });
        idleTimer = 0;
      } else {
        idleTimer++;
        if (moodRef.current === 'walking') setMood('idle');
        if (idleTimer > 130) {
          const actions = ['walk', 'walk', 'wave', 'dance', 'talk', 'sleep'];
          const pick = actions[Math.floor(Math.random() * actions.length)];

          if (pick === 'walk') {
            pickNewTarget();
          } else if (pick === 'wave') {
            setMood('waving');
            setBubble(PHRASES.wave[Math.floor(Math.random() * PHRASES.wave.length)]);
            setTimeout(() => { setMood('idle'); setBubble(''); pickNewTarget(); }, 2500);
          } else if (pick === 'dance') {
            setMood('dancing');
            setTimeout(() => { setMood('idle'); pickNewTarget(); }, 3000);
          } else if (pick === 'talk') {
            setBubble(PHRASES.idle[Math.floor(Math.random() * PHRASES.idle.length)]);
            setTimeout(() => setBubble(''), 2800);
          } else if (pick === 'sleep') {
            setMood('sleeping');
            setBubble(PHRASES.sleep[0]);
            setTimeout(() => { setMood('idle'); setBubble(''); pickNewTarget(); }, 3800);
          }
          idleTimer = 0;
        }
      }
      raf = requestAnimationFrame(loop);
    };

    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [pickNewTarget, isDragging]);

  // Initial target
  useEffect(() => {
    const t = setTimeout(pickNewTarget, 800);
    return () => clearTimeout(t);
  }, [pickNewTarget]);

  // Scroll reaction
  useEffect(() => {
    const handleScroll = () => {
      const scrollPos = window.scrollY;
      if (scrollPos > 400 && scrollPos < 900 && !bubble) {
        setBubble(PHRASES.scrollFeatures[0]);
        setTimeout(() => setBubble(''), 2500);
      } else if (scrollPos > 1200 && !bubble) {
        setBubble(PHRASES.scrollConnect[0]);
        setTimeout(() => setBubble(''), 2500);
      }
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [bubble]);

  const handleClick = () => {
    setMood('jumping');
    setBubble(PHRASES.happy[Math.floor(Math.random() * PHRASES.happy.length)]);
    setTimeout(() => { setMood('idle'); setBubble(''); pickNewTarget(); }, 1400);
  };

  const onMouseDown = () => {
    setIsDragging(true);
    setMood('jumping');
  };

  const onMouseMove = (e) => {
    if (isDragging) {
      setPos({ x: e.clientX - 50, y: e.clientY - 60 });
    }
  };

  const onMouseUp = () => {
    if (isDragging) {
      setIsDragging(false);
      setMood('idle');
      pickNewTarget();
    }
  };

  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [isDragging]);

  return (
    <div
      className={`roamer ${mood} ${isDragging ? 'dragging' : ''}`}
      style={{ left: pos.x, top: pos.y, transform: `scaleX(${facing})` }}
      onClick={handleClick}
      onMouseDown={onMouseDown}
    >
      {bubble && (
        <div className="speech-bubble" style={{ transform: `scaleX(${facing})` }}>
          {bubble}
        </div>
      )}
      <div className="mascot-body">
        <DuitMascot mood={mood} size={110} />
      </div>
      <div className="shadow-ground" />
    </div>
  );
}

