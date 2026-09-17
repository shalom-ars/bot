interface BrandLogoProps {
  size?: number;
  className?: string;
  glow?: boolean;
}

export default function BrandLogo({ size = 32, className = '', glow = true }: BrandLogoProps) {
  return (
    <div 
      className={`relative inline-flex items-center justify-center shrink-0 ${className}`}
      style={{ width: size, height: size }}
    >
      <svg
        viewBox="0 0 48 48"
        width={size}
        height={size}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full transform transition-transform hover:scale-105"
      >
        <defs>
          {/* Hexagon Outer Gradient */}
          <linearGradient id="jonandaHexGrad" x1="4" y1="4" x2="44" y2="44" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#38bdf8" />     {/* Sky Blue */}
            <stop offset="50%" stopColor="#3b82f6" />    {/* Electric Blue */}
            <stop offset="100%" stopColor="#10b981" />   {/* Emerald */}
          </linearGradient>

          {/* Hexagon Surface Dark Gradient */}
          <linearGradient id="jonandaBgGrad" x1="12" y1="8" x2="36" y2="40" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#0f172a" />     {/* Slate 900 */}
            <stop offset="100%" stopColor="#020617" />   {/* Slate 950 */}
          </linearGradient>

          {/* Pulse Wave Stroke Gradient */}
          <linearGradient id="jonandaPulseGrad" x1="11" y1="24" x2="37" y2="24" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#38bdf8" />
            <stop offset="45%" stopColor="#60a5fa" />
            <stop offset="70%" stopColor="#34d399" />
            <stop offset="100%" stopColor="#10b981" />
          </linearGradient>

          {/* Neon Glow Filter */}
          {glow && (
            <filter id="jonandaGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="1.5" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          )}
        </defs>

        {/* Outer Precision Hexagon Frame */}
        <path
          d="M24 4.5L41.5 14.6V33.4L24 43.5L6.5 33.4V14.6L24 4.5Z"
          fill="url(#jonandaBgGrad)"
          stroke="url(#jonandaHexGrad)"
          strokeWidth="2.4"
          strokeLinejoin="round"
        />

        {/* Subtle Cyber Grid / Candle Background Bars */}
        <line x1="20" y1="18" x2="20" y2="30" stroke="#1e293b" strokeWidth="1" strokeDasharray="1.5 1.5" opacity="0.6" />
        <line x1="28" y1="18" x2="28" y2="30" stroke="#1e293b" strokeWidth="1" strokeDasharray="1.5 1.5" opacity="0.6" />
        <line x1="15" y1="24" x2="33" y2="24" stroke="#1e293b" strokeWidth="1" strokeDasharray="1.5 1.5" opacity="0.6" />

        {/* Core Electric Pulse & Candlestick Wave */}
        <path
          d="M12 24.5H16.5L19.5 19L23.5 29.5L28 15.5L32 25.5H36"
          stroke="url(#jonandaPulseGrad)"
          strokeWidth="2.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          filter={glow ? "url(#jonandaGlow)" : undefined}
        />

        {/* Apex Signal Vertex Node */}
        <circle 
          cx="28" 
          cy="15.5" 
          r="2" 
          fill="#34d399" 
          stroke="#ffffff" 
          strokeWidth="0.8" 
        />
        
        {/* Trailing Micro-Particle */}
        <circle 
          cx="19.5" 
          cy="19" 
          r="1.2" 
          fill="#38bdf8" 
        />
      </svg>
    </div>
  );
}
