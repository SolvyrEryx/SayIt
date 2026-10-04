"use client";

import { useEffect, useRef } from "react";

type Particle = {
  x: number;
  y: number;
  radius: number;
  depth: number;
  vx: number;
  vy: number;
  glow: boolean;
};

/**
 * Full-page ambient particle field: sparse, depth-layered accent motes that
 * drift slowly and parallax against scroll (near particles move more),
 * painted on one fixed canvas behind all content. Zero dependencies, one
 * rAF loop, pauses when the tab is hidden, renders a single static frame
 * under prefers-reduced-motion, and scales particle count down on small
 * viewports. Decorative only — aria-hidden, pointer-events none.
 */
export function AmbientField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let width = 0;
    let height = 0;
    let particles: Particle[] = [];
    let raf = 0;
    let running = true;
    let scrollY = window.scrollY;

    const seed = () => {
      const count = width < 640 ? 18 : width < 1280 ? 30 : 42;
      particles = Array.from({ length: count }, () => {
        const depth = 0.25 + Math.random() * 0.75;
        return {
          x: Math.random() * width,
          y: Math.random() * (height + 240),
          radius: 0.8 + depth * 2.1,
          depth,
          vx: (Math.random() - 0.5) * 0.08,
          vy: -0.04 - Math.random() * 0.06,
          glow: depth > 0.8,
        };
      });
    };

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
      if (reduced) draw();
    };

    const accent =
      getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() ||
      "#3b9c8c";

    const draw = () => {
      ctx.clearRect(0, 0, width, height);
      for (const p of particles) {
        const parallax = scrollY * 0.08 * p.depth;
        const y = ((p.y - parallax) % (height + 240) + height + 240) % (height + 240) - 120;
        ctx.beginPath();
        ctx.arc(p.x, y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = accent;
        ctx.globalAlpha = 0.05 + p.depth * 0.13;
        if (p.glow) {
          ctx.shadowBlur = 12;
          ctx.shadowColor = accent;
        }
        ctx.fill();
        ctx.shadowBlur = 0;
      }
      ctx.globalAlpha = 1;
    };

    const tick = () => {
      if (!running) return;
      scrollY = window.scrollY;
      for (const p of particles) {
        p.x += p.vx * p.depth;
        p.y += p.vy * p.depth;
        if (p.x < -8) p.x = width + 8;
        if (p.x > width + 8) p.x = -8;
        if (p.y < -120) p.y = height + 240;
      }
      draw();
      raf = window.requestAnimationFrame(tick);
    }

    const onVisibility = () => {
      running = !document.hidden && !reduced;
      if (running) {
        window.cancelAnimationFrame(raf);
        raf = window.requestAnimationFrame(tick);
      }
    };

    resize();
    window.addEventListener("resize", resize, { passive: true });
    document.addEventListener("visibilitychange", onVisibility);
    if (!reduced) raf = window.requestAnimationFrame(tick);
    return () => {
      running = false;
      window.cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 -z-10 opacity-80"
    />
  );
}
