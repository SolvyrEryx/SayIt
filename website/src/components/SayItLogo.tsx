import Link from "next/link";
import { SayItMark } from "./SayItMark";

type SayItLogoProps = {
  /** Symbol size in px; the wordmark scales proportionally. */
  size?: number;
  className?: string;
  href?: string;
  /** Accessible name for the link; omit when the lockup is not a link. */
  ariaLabel?: string;
};

/**
 * The PRIMARY LOGO from the brand sheet: the ascending-bars symbol followed
 * by the "Say It" wordmark (Inter bold, tight tracking), black on light —
 * the exact lockup specified for light surfaces. Used in the navbar and
 * footer; on dark surfaces the system's white-on-black primary applies.
 */
export function SayItLogo({ size = 24, className = "", href, ariaLabel }: SayItLogoProps) {
  const lockup = (
    <span
      className={`inline-flex items-center gap-2 text-strong ${className}`.trim()}
      style={{ lineHeight: 1 }}
    >
      <SayItMark size={size} title="" />
      <span
        className="font-bold"
        style={{
          fontSize: `${Math.round(size * 0.72)}px`,
          letterSpacing: "-0.03em",
        }}
      >
        Say It
      </span>
    </span>
  );

  if (!href) {
    return lockup;
  }
  return (
    <Link href={href} aria-label={ariaLabel} className="inline-flex rounded-md">
      {lockup}
    </Link>
  );
}
