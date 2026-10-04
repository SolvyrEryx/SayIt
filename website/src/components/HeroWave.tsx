import type { CSSProperties } from "react";

/**
 * Large, faint waveform visualizer anchoring the hero — the page's voice
 * signature. Bars are deterministic (no Math.random: SSR and client must
 * agree), purely decorative, and collapse to a static silhouette under
 * prefers-reduced-motion.
 */
export function HeroWave({ className = "" }: { className?: string }) {
  const BAR_COUNT = 56;
  const bars = Array.from({ length: BAR_COUNT }, (_, i) => {
    const envelope = Math.sin((i / (BAR_COUNT - 1)) * Math.PI);
    const jitter = Math.abs(Math.sin(i * 1.7) * 0.55 + Math.sin(i * 0.6) * 0.45);
    return Math.round(14 + envelope * jitter * 96);
  });

  return (
    <div
      aria-hidden="true"
      className={`hero-wave pointer-events-none text-accent ${className}`.trim()}
    >
      {bars.map((height, index) => (
        <span
          key={index}
          style={{ "--h": `${height}px`, "--i": index } as CSSProperties}
        />
      ))}
    </div>
  );
}
