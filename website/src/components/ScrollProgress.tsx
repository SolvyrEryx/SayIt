/**
 * Scroll progress hairline: a thin spectrum gradient across the top edge that
 * fills with scroll depth. CSS scroll-driven where supported
 * (animation-timeline: scroll()); without support the animation collapses to
 * its final keyframe — a static brand hairline, which is a fine fallback.
 * Decorative: aria-hidden.
 */
export function ScrollProgress() {
  return (
    <div
      aria-hidden="true"
      className="scroll-progress pointer-events-none fixed inset-x-0 top-0 z-50 h-[3px] origin-left bg-gradient-to-r from-[#8A63F6] via-[#4E7DF9] to-[#2FB39A]"
    />
  );
}
