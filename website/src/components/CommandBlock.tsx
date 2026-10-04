import { CopyButton } from "./CopyButton";

type CommandBlockProps = {
  /** Short, human label — e.g. "PowerShell" or "Make executable". */
  label: string;
  /** The exact command. Never a placeholder on a production page. */
  command: string;
  className?: string;
};

export function CommandBlock({ label, command, className = "" }: CommandBlockProps) {
  return (
    <figure className={`overflow-hidden rounded-lg border border-line bg-subtle ${className}`.trim()}>
      <figcaption className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
        <span className="text-xs font-medium uppercase tracking-wider text-muted">{label}</span>
        <CopyButton text={command} />
      </figcaption>
      <pre className="overflow-x-auto px-3 py-3 text-sm leading-relaxed">
        <code className="font-mono text-strong">{command}</code>
      </pre>
    </figure>
  );
}
