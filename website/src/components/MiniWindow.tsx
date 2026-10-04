import type { ReactNode } from "react";

type MiniWindowProps = {
  /** Text for the mock title bar, e.g. "Active window: code editor". */
  title: string;
  /** Optional right-aligned chip, e.g. "Profile: Developer". */
  chip?: string;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
};

/**
 * Neutral mock application window used by the landing-page demos. Deliberately
 * platform-agnostic chrome — no traffic-light dots, no dock — because the site
 * must not imply support for platforms SayIt doesn't target.
 */
export function MiniWindow({
  title,
  chip,
  className = "",
  bodyClassName = "",
  children,
}: MiniWindowProps) {
  return (
    <div
      className={`overflow-hidden rounded-xl border border-line bg-surface shadow-card ${className}`.trim()}
    >
      <div className="flex items-center justify-between gap-3 border-b border-line bg-subtle px-4 py-2.5 sm:px-5">
        <span className="truncate text-xs font-medium text-muted">{title}</span>
        {chip ? (
          <span className="inline-flex shrink-0 items-center rounded-full border border-line bg-surface px-2.5 py-0.5 text-xs font-medium text-accent-text">
            {chip}
          </span>
        ) : null}
      </div>
      <div className={`p-5 sm:p-6 ${bodyClassName}`.trim()}>{children}</div>
    </div>
  );
}
