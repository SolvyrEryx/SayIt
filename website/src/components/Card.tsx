import type { HTMLAttributes, ReactNode } from "react";

type CardProps = HTMLAttributes<HTMLDivElement> & {
  /** Adds a subtle hover lift for clickable/interactive cards. */
  interactive?: boolean;
  children: ReactNode;
};

export function Card({ interactive = false, className = "", children, ...rest }: CardProps) {
  const classes = [
    "rounded-xl border border-line bg-surface shadow-card",
    interactive
      ? "transition-[transform,box-shadow] duration-[var(--motion-base)] ease-soft hover:-translate-y-0.5 hover:shadow-lift motion-reduce:hover:translate-y-0"
      : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes} {...rest}>
      {children}
    </div>
  );
}
