import type { ReactNode } from "react";

type CalloutProps = {
  tone?: "info" | "warn";
  title?: string;
  children: ReactNode;
};

const TONE_CLASSES = {
  info: "border-line bg-subtle text-body",
  warn: "border-line-strong bg-surface text-body",
} as const;

/** A short, honest note. Warn tones underline risk without being alarming. */
export function Callout({ tone = "info", title, children }: CalloutProps) {
  return (
    <div className={`rounded-lg border p-4 text-sm leading-relaxed ${TONE_CLASSES[tone]}`}>
      {title ? <p className="font-semibold text-strong">{title}</p> : null}
      <div className={title ? "mt-1" : undefined}>{children}</div>
    </div>
  );
}

type StepsProps = {
  items: ReactNode[];
};

/** A numbered step list for installation flows. */
export function Steps({ items }: StepsProps) {
  return (
    <ol className="space-y-4">
      {items.map((item, index) => (
        <li key={index} className="flex gap-3">
          <span
            aria-hidden="true"
            className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-accent-soft font-mono text-sm font-semibold text-accent"
          >
            {index + 1}
          </span>
          <div className="min-w-0 flex-1 pt-0.5 text-sm leading-relaxed text-body">{item}</div>
        </li>
      ))}
    </ol>
  );
}

export type TroubleshootingItem = {
  question: string;
  answer: ReactNode;
};

/** No-JS-friendly accordion of real, observed issues — never invented fixes. */
export function Troubleshooting({ items }: { items: TroubleshootingItem[] }) {
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <details
          key={item.question}
          className="group rounded-lg border border-line bg-surface px-4 py-3 open:shadow-card"
        >
          <summary className="cursor-pointer select-none text-sm font-medium text-strong marker:content-none">
            <span
              aria-hidden="true"
              className="mr-2 inline-block text-accent transition-transform duration-[var(--motion-fast)] group-open:rotate-90 motion-reduce:transition-none"
            >
              ▸
            </span>
            {item.question}
          </summary>
          <div className="mt-2 pl-6 text-sm leading-relaxed text-muted">{item.answer}</div>
        </details>
      ))}
    </div>
  );
}
