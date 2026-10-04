"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "./Button";
import { Card } from "./Card";
import { ChecksumBlock } from "./ChecksumBlock";
import { formatBytes } from "@/lib/release";

export type DownloadCardStatus = "available" | "unavailable" | "planned";

export type DownloadCardProps = {
  platformName: string;
  formatLabel: string;
  status: DownloadCardStatus;
  detected?: boolean;
  architecture?: string;
  version?: string;
  releaseDate?: string;
  sizeBytes?: number;
  sha256?: string;
  downloadUrl?: string;
  /** Real fallback destination (GitHub Releases) used when no artifact exists. */
  githubUrl: string;
  /** Link to the platform's installation guide. */
  installHref?: string;
};

const STATUS_BADGES: Record<DownloadCardStatus, { label: string; className: string }> = {
  available: {
    label: "Available",
    className: "border-accent bg-accent text-on-accent",
  },
  unavailable: {
    label: "Temporarily unavailable",
    className: "border-line-strong bg-surface text-muted",
  },
  planned: {
    label: "Not yet available",
    className: "border-line bg-subtle text-muted",
  },
};

/**
 * A platform download card generated from release metadata (master plan §37).
 * Never fabricates sizes, versions, or URLs: whatever is not in the manifest
 * renders as an honest fallback state pointing at GitHub Releases.
 */
export function DownloadCard({
  platformName,
  formatLabel,
  status,
  detected = false,
  architecture,
  version,
  releaseDate,
  sizeBytes,
  sha256,
  downloadUrl,
  githubUrl,
  installHref,
}: DownloadCardProps) {
  const [started, setStarted] = useState(false);
  const badge = STATUS_BADGES[status];

  return (
    <Card className="flex h-full flex-col p-6">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-semibold text-strong">{platformName}</h3>
        {detected ? (
          <span className="inline-flex items-center rounded-full border border-accent bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-strong">
            For your system
          </span>
        ) : null}
        <span
          className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${badge.className}`}
        >
          {badge.label}
        </span>
      </div>

      <p className="mt-2 text-sm text-muted">
        {[architecture, formatLabel].filter(Boolean).join(" · ")}
      </p>

      {version || releaseDate ? (
        <p className="mt-1 font-mono text-xs text-muted">
          {[version, releaseDate ? `Released ${releaseDate}` : null].filter(Boolean).join(" · ")}
        </p>
      ) : null}

      <div className="mt-4 flex-1">
        {status === "planned" ? (
          <p className="text-sm leading-relaxed text-muted">
            This installer is published with the first public release. Nothing is available for
            download yet — the link below always points at the official source.
          </p>
        ) : null}
        {status === "unavailable" ? (
          <p className="text-sm leading-relaxed text-muted">
            The installer is temporarily unavailable. You can find all published artifacts on the
            official releases page.
          </p>
        ) : null}
      </div>

      <div className="mt-4">
        {status === "available" && downloadUrl ? (
          <>
            <Button href={downloadUrl} onClick={() => setStarted(true)}>
              Download for {platformName}
            </Button>
            <p aria-live="polite" className="mt-2 min-h-5 text-sm text-accent-text">
              {started ? "Download started — check your browser's downloads." : ""}
            </p>
          </>
        ) : (
          <Button href={githubUrl} variant="secondary">
            View GitHub releases
          </Button>
        )}
      </div>

      {sizeBytes !== undefined ? (
        <p className="mt-2 text-xs text-muted">Download size: {formatBytes(sizeBytes)}</p>
      ) : null}

      {installHref ? (
        <p className="mt-2 text-xs">
          <Link
            href={installHref}
            className="font-medium text-accent-text underline-offset-4 hover:underline"
          >
            Installation guide →
          </Link>
        </p>
      ) : null}

      {sha256 ? <ChecksumBlock sha256={sha256} /> : null}
    </Card>
  );
}
