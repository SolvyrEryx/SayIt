"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { Button } from "./Button";
import { DownloadCard } from "./DownloadCard";
import { detectNavigatorPlatform, type Platform } from "@/lib/platform";
import {
  fetchReleaseManifest,
  type PlatformKey,
  type ReleaseManifest,
} from "@/lib/release";
import { site } from "@/lib/site";

type CenterState =
  | { kind: "loading" }
  | { kind: "unavailable"; reason: "missing" | "invalid" | "network" }
  | { kind: "ready"; manifest: ReleaseManifest };

const PLATFORM_META: Record<PlatformKey, { name: string; formatLabel: string }> = {
  windows: { name: "Windows", formatLabel: "Installer (.exe)" },
  linux: { name: "Linux", formatLabel: "AppImage" },
};

const subscribeNoop = () => () => {};
const getServerPlatform = (): Platform => "unknown";

function orderedKeys(detected: Platform): PlatformKey[] {
  if (detected === "linux") return ["linux", "windows"];
  return ["windows", "linux"];
}

/**
 * The download center (master plan §9, §63, §64). Consumes the static
 * release manifest; degrades to honest fallback states when no release
 * exists, the manifest is invalid, or the network check fails. Platform
 * detection only reorders/emphasizes cards — it is never stored or sent
 * anywhere.
 */
export function DownloadCenter({ platform: platformOverride }: { platform?: Platform }) {
  const [state, setState] = useState<CenterState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  // Platform is a client-only fact: unknown on the server, detected after
  // hydration, never re-detected, never persisted.
  const detected = useSyncExternalStore(
    subscribeNoop,
    () => platformOverride ?? detectNavigatorPlatform(),
    getServerPlatform,
  );

  useEffect(() => {
    let cancelled = false;
    fetchReleaseManifest().then((result) => {
      if (cancelled) return;
      setState(
        result.status === "ok"
          ? { kind: "ready", manifest: result.manifest }
          : { kind: "unavailable", reason: result.reason },
      );
    });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = () => {
    setState({ kind: "loading" });
    setAttempt((value) => value + 1);
  };

  const showMacNotice = detected === "macos";

  return (
    <div>
      {showMacNotice ? (
        <div className="mb-8 rounded-xl border border-line bg-subtle p-5 text-sm leading-relaxed text-body">
          <strong className="font-semibold text-strong">
            macOS support is not currently available.
          </strong>{" "}
          SayIt currently supports Windows and Linux.{" "}
          <Link
            href="/#platforms"
            className="font-medium text-strong underline decoration-line-strong underline-offset-4 hover:underline"
          >
            View supported platforms
          </Link>
          .
        </div>
      ) : null}

      {state.kind === "loading" ? (
        <div aria-live="polite" aria-busy="true">
          <p className="text-sm text-muted">Checking for the latest release…</p>
          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            {[0, 1].map((index) => (
              <div
                key={index}
                aria-hidden="true"
                className="h-48 animate-pulse rounded-xl border border-line bg-subtle"
              />
            ))}
          </div>
        </div>
      ) : null}

      {state.kind === "unavailable" ? (
        <div>
          {state.reason === "missing" ? (
            <div className="rounded-xl border border-line bg-subtle p-6 text-sm leading-relaxed text-body sm:p-8">
              <h2 className="text-base font-semibold text-strong">
                No published release manifest is available right now.
              </h2>
              <p className="mt-2">
                A published release normally appears here with version, release date, and
                SHA-256 checksums sourced from the official release. Until it is available,
                use{" "}
                <a
                  className="font-medium text-strong underline decoration-line-strong underline-offset-2 hover:text-accent-text"
                  href={site.releasesUrl}
                >
                  GitHub Releases
                </a>
                .
              </p>
            </div>
          ) : (
            <div className="rounded-xl border border-line bg-subtle p-6 text-sm leading-relaxed text-body sm:p-8">
              <h2 className="text-base font-semibold text-strong">
                {state.reason === "network"
                  ? "Couldn't check for releases right now."
                  : "The release information is temporarily unavailable."}
              </h2>
              <p className="mt-2">
                Download links always come from the official release. You can retry, or go straight
                to{" "}
                <a
                  className="font-medium text-strong underline decoration-line-strong underline-offset-2 hover:text-accent-text"
                  href={site.releasesUrl}
                >
                  GitHub Releases
                </a>
                .
              </p>
              <div className="mt-4">
                <Button variant="secondary" onClick={retry}>
                  Retry
                </Button>
              </div>
            </div>
          )}

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            {orderedKeys(detected).map((key) => (
              <DownloadCard
                key={key}
                platformName={PLATFORM_META[key].name}
                formatLabel={PLATFORM_META[key].formatLabel}
                status={state.reason === "missing" ? "planned" : "unavailable"}
                detected={detected === key}
                githubUrl={site.releasesUrl}
                installHref="/install"
              />
            ))}
          </div>
        </div>
      ) : null}

      {state.kind === "ready" ? (
        <div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h2 className="text-lg font-semibold text-strong">
              Latest {state.manifest.stable ? "stable" : ""} release
            </h2>
            <span className="font-mono text-sm text-body">v{state.manifest.version}</span>
            <span className="text-sm text-muted">Released {state.manifest.release_date}</span>
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            {orderedKeys(detected).map((key) => {
              const asset = state.manifest.platforms[key];
              return (
                <DownloadCard
                  key={key}
                  platformName={PLATFORM_META[key].name}
                  formatLabel={PLATFORM_META[key].formatLabel}
                  status={asset ? "available" : "unavailable"}
                  detected={detected === key}
                  architecture={asset?.architecture}
                  version={`v${state.manifest.version}`}
                  releaseDate={state.manifest.release_date}
                  sizeBytes={asset?.size_bytes}
                  sha256={asset?.sha256}
                  downloadUrl={asset?.url}
                  githubUrl={site.releasesUrl}
                  installHref="/install"
                />
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
