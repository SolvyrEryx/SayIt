import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost";
type Size = "md" | "lg";

/**
 * Internal path links render through next/link (client navigation + automatic
 * basePath handling on GitHub Pages); external URLs and hash-only anchors
 * stay plain anchors.
 */
export function isInternalHref(href: string): boolean {
  return href.startsWith("/") && !href.startsWith("//");
}

const BASE_CLASSES = [
  "inline-flex select-none items-center justify-center gap-2 rounded-lg border font-medium",
  "transition-[background-color,border-color,color,transform,box-shadow]",
  "duration-[var(--motion-base)] ease-soft",
  "active:translate-y-px",
  "disabled:pointer-events-none disabled:opacity-50",
].join(" ");

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "border-accent bg-accent text-on-accent shadow-sm hover:-translate-y-0.5 hover:border-accent-hover hover:bg-accent-hover hover:shadow-[var(--shadow-glow)] active:translate-y-0 active:shadow-sm",
  secondary:
    "border-line-strong bg-surface text-body hover:-translate-y-0.5 hover:border-accent hover:text-strong active:translate-y-0 active:shadow-sm",
  ghost: "border-transparent bg-transparent text-body hover:bg-subtle hover:text-strong",
};

const SIZE_CLASSES: Record<Size, string> = {
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-base",
};

type CommonProps = {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  className?: string;
  children: ReactNode;
};

type ButtonAsButton = CommonProps & ButtonHTMLAttributes<HTMLButtonElement> & { href?: undefined };
type ButtonAsLink = CommonProps & AnchorHTMLAttributes<HTMLAnchorElement> & { href: string };

export type ButtonProps = ButtonAsButton | ButtonAsLink;

/**
 * The site's single button primitive. Renders an <a> when `href` is given,
 * otherwise a <button>. Every state (hover, pressed, focus, disabled,
 * loading) is part of the design system — never fake a state in markup.
 */
export function Button(props: ButtonProps) {
  const {
    variant = "primary",
    size = "md",
    loading = false,
    className = "",
    href,
    children,
    ...rest
  } = props;

  const classes = [BASE_CLASSES, VARIANT_CLASSES[variant], SIZE_CLASSES[size], className]
    .filter(Boolean)
    .join(" ");

  if (href !== undefined) {
    if (isInternalHref(href)) {
      return (
        <Link
          {...(rest as Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">)}
          href={href}
          className={classes}
        >
          {children}
        </Link>
      );
    }
    return (
      <a
        {...(rest as AnchorHTMLAttributes<HTMLAnchorElement>)}
        href={href}
        className={classes}
      >
        {children}
      </a>
    );
  }

  const buttonRest = rest as ButtonHTMLAttributes<HTMLButtonElement>;

  return (
    <button
      {...buttonRest}
      type={buttonRest.type ?? "button"}
      disabled={loading || buttonRest.disabled}
      aria-busy={loading || undefined}
      className={classes}
    >
      {loading ? (
        <span
          aria-hidden="true"
          className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      ) : null}
      {children}
    </button>
  );
}
