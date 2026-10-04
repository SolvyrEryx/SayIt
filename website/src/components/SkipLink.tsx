/**
 * Hidden until keyboard-focused; the first tab stop on every page.
 */
export function SkipLink() {
  return (
    <a
      href="#main"
      className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-accent focus:px-4 focus:py-2 focus:text-on-accent focus:shadow-lift"
    >
      Skip to content
    </a>
  );
}
