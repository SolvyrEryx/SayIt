import { CopyButton } from "./CopyButton";

type ChecksumBlockProps = {
  sha256: string;
};

/**
 * SHA-256 verification block (master plan §39). The full checksum is
 * copyable and expandable — verification is only useful with the complete
 * value, so it is never truncated-only.
 */
export function ChecksumBlock({ sha256 }: ChecksumBlockProps) {
  return (
    <div className="rounded-lg border border-line bg-subtle p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wider text-muted">SHA-256</span>
        <CopyButton text={sha256} label="Copy checksum" />
      </div>
      <details className="mt-1">
        <summary className="cursor-pointer select-none font-mono text-xs text-body transition-colors duration-[var(--motion-fast)] hover:text-strong">
          {sha256.slice(0, 16)}…{sha256.slice(-8)}{" "}
          <span className="text-muted">(show full)</span>
        </summary>
        <p className="mt-2 break-all font-mono text-xs leading-relaxed text-strong">{sha256}</p>
      </details>
      <p className="mt-2 text-xs leading-relaxed text-muted">
        Compare this against the checksum of your downloaded file before running it.
      </p>
    </div>
  );
}
