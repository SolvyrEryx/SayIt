type SayItMarkProps = {
  size?: number;
  className?: string;
  /** Accessible name; pass "" only when the mark is purely decorative next to visible text. */
  title?: string;
  /** Bars rise from the baseline in sequence on mount (hero entrance). */
  entrance?: boolean;
};

/**
 * The SayIt symbol — six rounded bars ascending left to right in the brand
 * spectrum (violet → blue → teal), every bar carrying the warm-ink outline
 * from the brand sheet, alternating solid and halftone-dot fills. The dot
 * texture is a mask over the gradient so colored dots match each bar's hue;
 * the outline is a separate stroke-only pass on dotted bars so it stays solid.
 *
 * This is the SYMBOL alone; the full primary logo (symbol + "Say It"
 * wordmark) lives in SayItLogo. A standalone asset copy is saved at
 * public/logo.svg.
 */

const OUTLINE = "#292420";
const OUTLINE_WIDTH = 2;

function Bar({
  x,
  y,
  width,
  height,
  dotted,
  riseClass,
  style,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  dotted: boolean;
  riseClass?: string;
  style?: React.CSSProperties;
}) {
  const rx = width / 2;
  if (!dotted) {
    return (
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={rx}
        fill="url(#sayit-spectrum)"
        stroke={OUTLINE}
        strokeWidth={OUTLINE_WIDTH}
        className={riseClass}
        style={style}
      />
    );
  }
  return (
    <>
      {/* Halftone fill, masked so the gradient shows only through the dots */}
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={rx}
        fill="url(#sayit-spectrum)"
        mask="url(#sayit-dotmask)"
        className={riseClass}
        style={style}
      />
      {/* Outline pass stays solid above the dotted fill */}
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={rx}
        fill="none"
        stroke={OUTLINE}
        strokeWidth={OUTLINE_WIDTH}
        className={riseClass}
        style={style}
      />
    </>
  );
}

export function SayItMark({ size = 32, className, title = "SayIt", entrance = false }: SayItMarkProps) {
  const riseClass = entrance ? "mark-rise" : undefined;
  const riseStyle = (i: number) =>
    entrance ? ({ "--i": i } as React.CSSProperties) : undefined;

  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      fill="currentColor"
      role="img"
      aria-label={title || undefined}
      aria-hidden={title ? undefined : true}
      focusable="false"
      className={className}
    >
      <defs>
        <linearGradient
          id="sayit-spectrum"
          x1="7"
          y1="0"
          x2="57"
          y2="0"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#8A63F6" />
          <stop offset="0.5" stopColor="#4E7DF9" />
          <stop offset="1" stopColor="#2FB39A" />
        </linearGradient>
        <pattern id="sayit-dotgrid" width="3.4" height="3.4" patternUnits="userSpaceOnUse">
          <circle cx="1.7" cy="1.7" r="1.35" fill="#ffffff" />
        </pattern>
        <mask id="sayit-dotmask">
          <rect width="64" height="64" fill="#000000" />
          <rect width="64" height="64" fill="url(#sayit-dotgrid)" />
        </mask>
      </defs>
      {/* Ascending bars, baseline y = 57. Alternating solid / halftone. */}
      <Bar x={7.25} y={49} width={5} height={8} dotted={false} riseClass={riseClass} style={riseStyle(0)} />
      <Bar x={14.85} y={40} width={5.5} height={17} dotted={false} riseClass={riseClass} style={riseStyle(1)} />
      <Bar x={22.95} y={31} width={6.5} height={26} dotted riseClass={riseClass} style={riseStyle(2)} />
      <Bar x={32.05} y={22} width={6.5} height={35} dotted={false} riseClass={riseClass} style={riseStyle(3)} />
      <Bar x={41.15} y={13} width={6.5} height={44} dotted riseClass={riseClass} style={riseStyle(4)} />
      <Bar x={50.25} y={4} width={6.5} height={53} dotted={false} riseClass={riseClass} style={riseStyle(5)} />
    </svg>
  );
}
