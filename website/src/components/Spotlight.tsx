"use client";

import { useEffect, useRef } from "react";

/**
 * Pointer-tracked spotlight for the hero: a soft accent radial that follows
 * the cursor (fine pointers only, motion-safe only, never without JS). The
 * layer renders hidden and is switched on by data attribute, so the no-JS
 * page is unaffected.
 */
export function Spotlight({ className = "" }: { className?: string }) {
  const layerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    if (typeof window.matchMedia !== "function") return;
    if (!window.matchMedia("(pointer: fine)").matches) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let frame = 0;
    const onMove = (event: PointerEvent) => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        const host = layer.parentElement;
        if (!host) return;
        const rect = host.getBoundingClientRect();
        layer.style.setProperty("--sx", `${event.clientX - rect.left}px`);
        layer.style.setProperty("--sy", `${event.clientY - rect.top}px`);
        layer.setAttribute("data-on", "true");
      });
    };
    const onLeave = () => layer.removeAttribute("data-on");

    const host = layer.parentElement;
    host?.addEventListener("pointermove", onMove, { passive: true });
    host?.addEventListener("pointerleave", onLeave);
    return () => {
      host?.removeEventListener("pointermove", onMove);
      host?.removeEventListener("pointerleave", onLeave);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div
      ref={layerRef}
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-700 ease-soft data-[on=true]:opacity-100 ${className}`.trim()}
      style={{
        background:
          "radial-gradient(560px circle at var(--sx, 50%) var(--sy, 30%), color-mix(in oklab, var(--accent) 9%, transparent), transparent 70%)",
      }}
    />
  );
}
