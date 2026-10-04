"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Container } from "./Container";
import { SayItLogo } from "./SayItLogo";
import { site } from "@/lib/site";

const NAV_LINKS = [
  { href: "/download", label: "Download", emphasize: true },
  { href: "/install", label: "Install", emphasize: false },
  { href: "/features", label: "Features", emphasize: false },
  { href: "/privacy", label: "Privacy", emphasize: false },
];

/**
 * Scroll-aware glass navbar: transparent while the page is at the top, then
 * the border and a soft shadow fade in once content scrolls underneath.
 * Scroll state is decoration only — the bar is fully usable without JS.
 */
export function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 8);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  return (
    <header
      className={`sticky top-0 z-40 border-b backdrop-blur transition-[background-color,border-color,box-shadow] duration-[var(--motion-base)] ease-soft ${
        scrolled
          ? "border-line bg-page/80 shadow-card"
          : "border-transparent bg-page/60"
      }`}
    >
      <Container>
        {/* min-h-14 keeps the desktop bar at its designed height; on small
            screens the links wrap to a second row instead of overflowing. */}
        <div className="flex min-h-14 flex-wrap items-center justify-between gap-y-1 py-1 sm:flex-nowrap sm:py-0">
          {/* PRIMARY LOGO (brand sheet) — colored bars + wordmark */}
          <SayItLogo size={28} href="/" ariaLabel="Say It home" />
          <nav aria-label="Main">
            <ul className="flex flex-wrap items-center gap-0.5 sm:gap-1">
              {NAV_LINKS.map((link) => {
                // Current route gets a quiet accent pill; transition keeps the
                // handoff between pages smooth during client navigation.
                const active = pathname === link.href || pathname === `${link.href}/`;
                return (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      aria-current={active ? "page" : undefined}
                      className={
                        link.emphasize
                          ? "inline-block rounded-lg border border-accent bg-accent px-2 py-1.5 text-sm font-medium text-on-accent shadow-sm transition-[background-color,border-color,color,transform,box-shadow] duration-[var(--motion-fast)] ease-soft hover:-translate-y-px hover:bg-accent-hover hover:shadow-[var(--shadow-glow)] sm:px-3"
                          : `inline-block rounded-md px-2 py-2 text-sm transition-[background-color,color,transform] duration-[var(--motion-fast)] ease-soft hover:-translate-y-px sm:px-3 ${
                              active
                                ? "bg-accent-soft font-medium text-accent-text"
                                : "text-body hover:bg-subtle hover:text-strong"
                            }`
                      }
                    >
                      {link.label}
                    </Link>
                  </li>
                );
              })}
              <li>
                <a
                  href={site.repositoryUrl}
                  className="inline-block rounded-md px-2 py-2 text-sm text-body transition-[background-color,color,transform] duration-[var(--motion-fast)] ease-soft hover:-translate-y-px hover:bg-subtle hover:text-strong sm:px-3"
                >
                  GitHub
                </a>
              </li>
            </ul>
          </nav>
        </div>
      </Container>
    </header>
  );
}
