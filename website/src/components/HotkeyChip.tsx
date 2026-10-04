type HotkeyChipProps = {
  /** Key names in display order, e.g. ["Ctrl", "Space"]. */
  keys: string[];
  className?: string;
};

/** Renders a keyboard combination as <kbd> chips with an accessible label. */
export function HotkeyChip({ keys, className = "" }: HotkeyChipProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 ${className}`.trim()}
      aria-label={keys.join(" plus ")}
    >
      {keys.map((key, index) => (
        <span key={key} className="inline-flex items-center gap-1.5">
          {index > 0 ? (
            <span aria-hidden="true" className="text-xs text-muted">
              +
            </span>
          ) : null}
          <kbd className="rounded-md border border-line-strong bg-subtle px-1.5 py-0.5 font-mono text-xs text-strong">
            {key}
          </kbd>
        </span>
      ))}
    </span>
  );
}
