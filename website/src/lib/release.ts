import { BASE_PATH } from "./basePath";

/**
 * Release manifest — the single source of truth for download data (master
 * plan §11, §38, §64). The website never calls the GitHub API from the
 * client; it consumes a static, same-origin `/release-manifest.json` that
 * the release pipeline generates from actual release artifacts (Stage E).
 *
 * While no release exists, the manifest file is intentionally absent and
 * every consumer must degrade to the honest fallback states below.
 */

export type PlatformKey = "windows" | "linux";

export type PlatformAsset = {
  architecture: string;
  format: string;
  url: string;
  sha256?: string;
  size_bytes?: number;
};

export type ReleaseManifest = {
  version: string;
  release_date: string;
  stable: boolean;
  platforms: Partial<Record<PlatformKey, PlatformAsset>>;
  notes_url?: string;
  changelog_url?: string;
};

export type ReleaseLoadResult =
  | { status: "ok"; manifest: ReleaseManifest }
  | { status: "unavailable"; reason: "missing" | "invalid" | "network" };

/** Site-root relative; BASE_PATH keeps it correct on GitHub Pages sub-paths. */
export const MANIFEST_URL = `${BASE_PATH}/release-manifest.json`;

const KNOWN_FORMATS = new Set(["exe", "AppImage"]);
const SHA256_PATTERN = /^[a-fA-F0-9]{64}$/;
const VERSION_PATTERN = /^\d+\.\d+\.\d+(?:[-+][\w.-]+)?$/;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function isHttpsUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "https:";
  } catch {
    return false;
  }
}

function optionalString(value: unknown, pattern?: RegExp): value is string {
  if (typeof value !== "string") return false;
  return pattern ? pattern.test(value) : value.length > 0;
}

/**
 * Validates untrusted manifest data. Returns null when the manifest is not
 * usable — callers must fall back to the GitHub Releases link instead of
 * rendering anything fabricated. Unknown extra top-level keys are allowed
 * for forward compatibility (§98).
 */
export function validateReleaseManifest(data: unknown): ReleaseManifest | null {
  if (typeof data !== "object" || data === null) return null;
  const record = data as Record<string, unknown>;

  if (!optionalString(record.version, VERSION_PATTERN)) return null;
  if (!optionalString(record.release_date, DATE_PATTERN)) return null;
  if (typeof record.stable !== "boolean") return null;
  if (typeof record.platforms !== "object" || record.platforms === null) return null;

  const rawPlatforms = record.platforms as Record<string, unknown>;
  const platforms: ReleaseManifest["platforms"] = {};

  for (const key of ["windows", "linux"] as const) {
    const raw = rawPlatforms[key];
    if (raw === undefined) continue;
    if (typeof raw !== "object" || raw === null) return null;
    const asset = raw as Record<string, unknown>;

    if (!optionalString(asset.architecture)) return null;
    if (!optionalString(asset.format) || !KNOWN_FORMATS.has(asset.format)) return null;
    if (!isHttpsUrl(asset.url)) return null;
    if (asset.sha256 !== undefined && !optionalString(asset.sha256, SHA256_PATTERN)) return null;
    if (
      asset.size_bytes !== undefined &&
      (typeof asset.size_bytes !== "number" || !Number.isFinite(asset.size_bytes) || asset.size_bytes <= 0)
    ) {
      return null;
    }

    platforms[key] = {
      architecture: asset.architecture,
      format: asset.format,
      url: asset.url,
      ...(asset.sha256 !== undefined ? { sha256: asset.sha256 } : {}),
      ...(asset.size_bytes !== undefined ? { size_bytes: asset.size_bytes } : {}),
    };
  }

  if (record.notes_url !== undefined && !isHttpsUrl(record.notes_url)) return null;
  if (record.changelog_url !== undefined && !isHttpsUrl(record.changelog_url)) return null;

  return {
    version: record.version,
    release_date: record.release_date,
    stable: record.stable,
    platforms,
    ...(record.notes_url !== undefined ? { notes_url: record.notes_url } : {}),
    ...(record.changelog_url !== undefined ? { changelog_url: record.changelog_url } : {}),
  };
}

/** Loads the manifest. Never throws — every failure becomes a fallback reason. */
export async function fetchReleaseManifest(
  fetchImpl: typeof fetch = fetch,
): Promise<ReleaseLoadResult> {
  let response: Response;
  try {
    response = await fetchImpl(MANIFEST_URL);
  } catch {
    return { status: "unavailable", reason: "network" };
  }

  if (!response.ok) {
    return { status: "unavailable", reason: "missing" };
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    return { status: "unavailable", reason: "invalid" };
  }

  const manifest = validateReleaseManifest(data);
  return manifest
    ? { status: "ok", manifest }
    : { status: "unavailable", reason: "invalid" };
}

/** Human-readable size. Only ever called with a measured size from the manifest. */
export function formatBytes(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return `${mb >= 100 ? Math.round(mb) : Math.round(mb * 10) / 10} MB`;
}
