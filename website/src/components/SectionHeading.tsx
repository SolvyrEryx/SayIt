import type { ReactNode } from "react";

type SectionHeadingProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  center?: boolean;
  icon?: ReactNode;
};

export function SectionHeading({
  eyebrow,
  title,
  description,
  center = false,
  icon,
}: SectionHeadingProps) {
  return (
    <div className={center ? "text-center" : undefined}>
      {icon ? (
        <span
          className={`mb-3 inline-flex size-10 items-center justify-center rounded-lg bg-accent-soft text-accent ${center ? "mx-auto" : ""}`.trim()}
        >
          {icon}
        </span>
      ) : null}
      {eyebrow ? (
        <p className="text-sm font-semibold uppercase tracking-wider text-accent-text">{eyebrow}</p>
      ) : null}
      <h2 className="mt-2 text-2xl font-semibold tracking-tight text-strong sm:text-3xl">{title}</h2>
      {description ? (
        <p
          className={`mt-3 max-w-2xl text-base leading-relaxed text-muted ${center ? "mx-auto" : ""}`.trim()}
        >
          {description}
        </p>
      ) : null}
    </div>
  );
}
