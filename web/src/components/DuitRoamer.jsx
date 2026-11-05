import React, { useEffect, useState, useRef } from 'react';
import './DuitRoamer.css';

const PHRASES = {
  scroll: [
    "Just say it, ho gaya.",
    "Browsing DUIT features...",
    "WhatsApp bridge active!",
    "Multi-profile Chrome ready!",
    "Calendar & Gmail connected!"
  ],
  click: [
    "Kya karna hai boss?",
    "Ho gaya! Next task?",
    "Namaste! Desktop sambhal liya!",
    "Boliye boss, command ready!"
  ]
};

export default function DuitRoamer() {
  const [isScrolling, setIsScrolling] = useState(false);
  const [isJumping, setIsJumping] = useState(false);
  const [bubble, setBubble] = useState('');
  const [transform, setTransform] = useState('translateY(0) rotate(0deg)');
  const scrollTimeout = useRef(null);
  const bubbleTimeout = useRef(null);
  const lastScrollY = useRef(0);
  const lastSection = useRef(-1);

  const showBubble = (text, duration = 2200) => {
    setBubble(text);
    if (bubbleTimeout.current) clearTimeout(bubbleTimeout.current);
    bubbleTimeout.current = setTimeout(() => setBubble(''), duration);
  };

  useEffect(() => {
    const handleScroll = () => {
      const currentY = window.scrollY;
      const delta = currentY - lastScrollY.current;
      lastScrollY.current = currentY;

      setIsScrolling(true);
      const tilt = Math.max(-6, Math.min(6, delta * 0.15));
      const microY = Math.max(-8, Math.min(0, -Math.abs(delta * 0.2)));
      setTransform(`translateY(${microY}px) rotate(${tilt}deg)`);

      const totalHeight = document.documentElement.scrollHeight - window.innerHeight;
      const progress = totalHeight > 0 ? currentY / totalHeight : 0;
      const sectionIdx = Math.floor(progress * 4);

      if (sectionIdx !== lastSection.current && Math.abs(delta) > 5) {
        lastSection.current = sectionIdx;
        showBubble(PHRASES.scroll[sectionIdx % PHRASES.scroll.length], 2000);
      }

      if (scrollTimeout.current) clearTimeout(scrollTimeout.current);
      scrollTimeout.current = setTimeout(() => {
        setIsScrolling(false);
        setTransform('translateY(0) rotate(0deg)');
      }, 160);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', handleScroll);
      if (scrollTimeout.current) clearTimeout(scrollTimeout.current);
      if (bubbleTimeout.current) clearTimeout(bubbleTimeout.current);
    };
  }, []);

  const handleClick = () => {
    setIsJumping(true);
    showBubble(PHRASES.click[Math.floor(Math.random() * PHRASES.click.length)], 2400);
    setTimeout(() => setIsJumping(false), 600);
  };

  return (
    <div
      className={`corner-mascot ${isScrolling ? 'scrolling' : ''} ${isJumping ? 'jump' : ''}`}
      style={{ transform }}
      onClick={handleClick}
      title="Click to interact with DUIT!"
    >
      {bubble && <div className="corner-speech-bubble">{bubble}</div>}
      <div className="mascot-seated">
        <img
          src="/duit-mascot.png"
          alt="DUIT Companion Mascot"
          style={{ width: '100%', height: '100%', objectFit: 'contain', pointerEvents: 'none' }}
        />
      </div>
      <div className="corner-shadow" />
    </div>
  );
}
