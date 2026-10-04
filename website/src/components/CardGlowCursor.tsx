"use client";

import { useEffect } from "react";

/**
 * Cursor-tracked card glow: one delegated pointermove listener feeds
 * --mx/--my into whichever .card-glow element is under the cursor, so every
 * glowing card on the site (home, features, privacy, download) gets a border
 * highlight that follows the mouse — no per-card listeners. Fine pointers
 * only; touch devices keep the static fallback glow.
 */
export function CardGlowCursor() {
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    if (!window.matchMedia("(pointer: fine)").matches) return;

    let frame = 0;
    let last: PointerEvent | null = null;

    const apply = () => {
      frame = 0;
      if (!last) return;
      const card = (last.target as Element | null)?.closest?.(".card-glow");
      if (!(card instanceof HTMLElement)) return;
      const rect = card.getBoundingClientRect();
      card.style.setProperty("--mx", `${last.clientX - rect.left}px`);
      card.style.setProperty("--my", `${last.clientY - rect.top}px`);
    };

    const onMove = (event: PointerEvent) => {
      last = event;
      if (!frame) frame = window.requestAnimationFrame(apply);
    };

    document.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      document.removeEventListener("pointermove", onMove);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  return null;
}
