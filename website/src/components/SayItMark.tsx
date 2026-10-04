type SayItMarkProps = {
  size?: number;
  className?: string;
  /** Accessible name; pass "" only when the mark is purely decorative next to visible text. */
  title?: string;
};

/**
 * The SayIt symbol — six rounded bars ascending left to right in the brand
 * spectrum (violet → blue → teal), alternating solid and halftone-dot fills
 * (the "dots become sound" construction from the brand sheet). The dot
 * texture is a mask over the same gradient, so colored dots match each bar's
 * hue at every size.
 *
 * This is the SYMBOL alone; the full primary logo (symbol + "Say It"
 * wordmark) lives in SayItLogo.
 */
export function SayItMark({ size = 32, className, title = "SayIt" }: SayItMarkProps) {
  // The halftone texture reads from ~40px up; below that it dissolves, so
  // small sizes render solid bars — same as the brand sheet's shrink row.
  const textured = size >= 40;
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
        {textured ? (
          <>
            <pattern id="sayit-dotgrid" width="4.2" height="4.2" patternUnits="userSpaceOnUse">
              <circle cx="2.1" cy="2.1" r="1.6" fill="#ffffff" />
            </pattern>
            <mask id="sayit-dotmask">
              <rect width="64" height="64" fill="#000000" />
              <rect width="64" height="64" fill="url(#sayit-dotgrid)" />
            </mask>
          </>
        ) : null}
      </defs>
      {/* Ascending bars, baseline y = 58. Alternating solid / halftone. */}
      <rect x="7.25" y="50" width="5" height="8" rx="2.5" fill="url(#sayit-spectrum)" />
      <rect x="14.85" y="41" width="5.5" height="17" rx="2.75" fill="url(#sayit-spectrum)" />
      <rect
        x="22.95"
        y="32"
        width="6.5"
        height="26"
        rx="3.25"
        fill="url(#sayit-spectrum)"
        {...(textured ? { mask: "url(#sayit-dotmask)" } : {})}
      />
      <rect x="32.05" y="23" width="6.5" height="35" rx="3.25" fill="url(#sayit-spectrum)" />
      <rect
        x="41.15"
        y="14"
        width="6.5"
        height="44"
        rx="3.25"
        fill="url(#sayit-spectrum)"
        {...(textured ? { mask: "url(#sayit-dotmask)" } : {})}
      />
      <rect x="50.25" y="5" width="6.5" height="53" rx="3.25" fill="url(#sayit-spectrum)" />
    </svg>
  );
}
