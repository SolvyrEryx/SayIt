/**
 * Viewport-anchored ambient glow: a soft accent wash pinned to the top of the
 * viewport with a fainter counter-glow at the bottom, so every scroll depth —
 * especially on phones, where the page is long — keeps ambient depth instead
 * of flattening out. Pure CSS, behind all content and behind the
 * AmbientField particle canvas.
 */
export function PageGlow() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-20">
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(130vh 60vh at 50% -18vh, color-mix(in oklab, var(--accent) 13%, transparent), transparent 72%), radial-gradient(110vh 60vh at 50% 118vh, color-mix(in oklab, var(--accent) 9%, transparent), transparent 74%)",
        }}
      />
    </div>
  );
}
