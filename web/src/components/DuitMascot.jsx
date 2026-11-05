import React from 'react';
import './DuitMascot.css';

export default function DuitMascot({ mood = 'idle', size = 120 }) {
  return (
    <div className={`duit-wrap mood-${mood}`} style={{ width: size, height: size }}>
      <svg viewBox="0 0 300 320" fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Shadow */}
        <ellipse className="shadow" cx="150" cy="300" rx="65" ry="12" fill="#000" opacity="0.15" />

        {/* Antenna */}
        <line x1="150" y1="42" x2="150" y2="18" stroke="#10b981" strokeWidth="4" strokeLinecap="round" />
        <circle className="antenna-ball" cx="150" cy="14" r="10" fill="#10b981" />
        <circle cx="150" cy="14" r="4" fill="#ffffff" />

        {/* Tilak / Badge on forehead */}
        <path d="M144 56 C144 48 156 48 156 56 C156 72 150 78 150 78 C150 78 144 72 144 56 Z" fill="#f97316" stroke="#ea580c" strokeWidth="1.5" />

        {/* Backpack - left */}
        <rect x="28" y="150" width="28" height="80" rx="12" fill="#1e293b" stroke="#334155" strokeWidth="3" />
        <rect x="28" y="168" width="28" height="12" fill="#10b981" />

        {/* Body - Cream Ladoo */}
        <circle cx="150" cy="175" r="105" fill="#fef3c7" stroke="#1c1917" strokeWidth="4" />
        {/* Ladoo texture dots */}
        <circle cx="95" cy="145" r="5" fill="#fde68a" />
        <circle cx="205" cy="145" r="5" fill="#fde68a" />
        <circle cx="110" cy="220" r="4" fill="#fde68a" />
        <circle cx="190" cy="220" r="4" fill="#fde68a" />
        <circle cx="150" cy="250" r="4" fill="#fde68a" />

        {/* Glowing Visor / Center Eye */}
        <circle cx="150" cy="155" r="44" fill="#18181b" stroke="#27272a" strokeWidth="3" />
        <circle cx="150" cy="155" r="36" fill="url(#visorGlow)" />
        <circle cx="150" cy="155" r="22" fill="#ea580c" />
        <circle cx="144" cy="148" r="7" fill="#fed7aa" opacity="0.8" />

        {/* Smile */}
        <path className="mouth" d="M136 215 Q150 225 164 215" stroke="#78716c" strokeWidth="4" strokeLinecap="round" fill="none" />

        {/* Arms */}
        <g className="arm-left">
          <rect x="38" y="210" width="42" height="22" rx="11" fill="#fef3c7" stroke="#1c1917" strokeWidth="3" />
          <circle cx="42" cy="221" r="10" fill="#fff" stroke="#1c1917" strokeWidth="3" />
        </g>
        <g className="arm-right">
          <rect x="220" y="210" width="42" height="22" rx="11" fill="#fef3c7" stroke="#1c1917" strokeWidth="3" />
          <circle cx="258" cy="221" r="10" fill="#fff" stroke="#1c1917" strokeWidth="3" />
        </g>

        {/* Legs */}
        <rect x="110" y="268" width="28" height="28" rx="10" fill="#e2e8f0" stroke="#1c1917" strokeWidth="3" />
        <rect x="162" y="268" width="28" height="28" rx="10" fill="#e2e8f0" stroke="#1c1917" strokeWidth="3" />

        {/* Chest Badge - DUIT */}
        <rect x="125" y="235" width="50" height="22" rx="11" fill="#10b981" />
        <text x="150" y="250" textAnchor="middle" fill="#000000" fontSize="12" fontFamily="Arial, sans-serif" fontWeight="800" letterSpacing="0.5">DUIT</text>

        <defs>
          <radialGradient id="visorGlow" cx="0.5" cy="0.5" r="0.5" fx="0.35" fy="0.35">
            <stop offset="0%" stopColor="#fb923c" />
            <stop offset="60%" stopColor="#f97316" />
            <stop offset="100%" stopColor="#c2410c" />
          </radialGradient>
        </defs>
      </svg>
    </div>
  );
}

