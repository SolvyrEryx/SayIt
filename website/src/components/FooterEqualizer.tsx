/**
 * Animated equalizer strip for the footer: 96 spectrum-gradient bars pulsing
 * like a live waveform — the brand symbol, set in motion. Heights are
 * deterministic (SSR and client must agree), the animation is pure CSS, and
 * the global reduced-motion collapse leaves a clean static strip.
 * Decorative: aria-hidden.
 */

const BARS = 96;
const SLOT = 8;

export function FooterEqualizer() {
  const bars = Array.from({ length: BARS }, (_, i) => {
    const envelope = Math.abs(Math.sin(i * 0.55) * 0.6 + Math.sin(i * 0.21) * 0.4);
    return Math.round(8 + envelope * 28);
  });

  return (
    <svg
      aria-hidden="true"
      className="footer-eq block w-full opacity-70"
      viewBox={`0 0 ${BARS * SLOT} 40`}
      preserveAspectRatio="none"
      style={{ height: 40 }}
    >
      <defs>
        <linearGradient
          id="footer-eq-spectrum"
          x1="0"
          y1="0"
          x2={BARS * SLOT}
          y2="0"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#8A63F6" />
          <stop offset="0.5" stopColor="#4E7DF9" />
          <stop offset="1" stopColor="#2FB39A" />
        </linearGradient>
      </defs>
      {bars.map((height, i) => (
        <rect
          key={i}
          className="footer-eq-bar"
          x={i * SLOT + (SLOT - 4.5) / 2}
          y={40 - height}
          width={4.5}
          height={height}
          rx={2.25}
          fill="url(#footer-eq-spectrum)"
          style={{ "--i": i } as React.CSSProperties}
        />
      ))}
    </svg>
  );
}
