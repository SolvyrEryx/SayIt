"use client";

import { useEffect, useRef, type ReactNode } from "react";

type RevealProps = {
  children: ReactNode;
  className?: string;
  /** Animate direct children in sequence instead of the container itself. */
  stagger?: boolean;
};

/**
 * Fades content in when it enters the viewport (once). The hidden state lives
 * in CSS behind a data-js attribute this component sets at mount, so content
 * is fully visible without JavaScript. prefers-reduced-motion disables the
 * effect entirely at the stylesheet level.
 *
 * Above-the-fold content should use the pure-CSS .reveal classes instead —
 * this component is for below-the-fold sections.
 */
export function Reveal({ children, className = "", stagger = false }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    el.setAttribute("data-js", "true");

    // Already on screen (e.g. short viewport or deep anchor link): reveal
    // synchronously — both attributes land in one style pass, no flash.
    const rect = el.getBoundingClientRect();
    if (rect.top < window.innerHeight * 0.9) {
      el.setAttribute("data-visible", "true");
      return;
    }

    if (typeof IntersectionObserver === "undefined") {
      el.setAttribute("data-visible", "true");
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            el.setAttribute("data-visible", "true");
            observer.disconnect();
          }
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -10% 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const base = stagger ? "scroll-reveal-stagger" : "scroll-reveal";
  return (
    <div ref={ref} className={`${base} ${className}`.trim()}>
      {children}
    </div>
  );
}
