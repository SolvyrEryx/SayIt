import { createHash } from "node:crypto";
import { mkdtemp, rm, writeFile, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { afterAll, describe, expect, it } from "vitest";
import { validateReleaseManifest } from "@/lib/release";

// The generator is a dependency-free Node script (it runs in CI); import it
// dynamically so the site's TypeScript toolchain doesn't need to type it.
const { generateReleaseManifest, stripTagPrefix, toReleaseDate } = (await import(
  "../scripts/generate-manifest.mjs"
)) as unknown as {
  generateReleaseManifest: (options: {
    tag: string;
    repo: string;
    releaseDate?: string;
    releaseFilesDir: string;
    outDir: string;
  }) => Promise<{
    manifest: {
      version: string;
      release_date: string;
      stable: boolean;
      platforms: Record<string, { url: string; sha256: string; size_bytes: number }>;
    };
    manifestPath: string;
    checksumsPath: string;
  }>;
  stripTagPrefix: (tag: string) => string;
  toReleaseDate: (iso?: string) => string;
};

const execFileAsync = promisify(execFile);
const tempDirs: string[] = [];

afterAll(async () => {
  await Promise.all(tempDirs.map((dir) => rm(dir, { recursive: true, force: true })));
});

async function makeFixtureDir(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), "sayit-manifest-"));
  tempDirs.push(dir);
  return dir;
}

async function writeArtifact(dir: string, name: string, content: string, sidecar = true) {
  await writeFile(join(dir, name), content);
  if (sidecar) {
    const hash = createHash("sha256").update(content).digest("hex");
    await writeFile(join(dir, `${name}.sha256`), `${hash.toUpperCase()}  ${name}\n`, "utf8");
  }
}

const FAKE_EXE = "fake installer bytes";
const FAKE_APPIMAGE = "fake appimage bytes";

async function writeValidFixtures(dir: string) {
  await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);
  await writeArtifact(dir, "SayIt-v0.1.2-Linux-x86_64.AppImage", FAKE_APPIMAGE);
}

describe("release manifest generator", () => {
  it("produces a manifest the website's own validator accepts", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeValidFixtures(dir);

    const { manifest, manifestPath, checksumsPath } = await generateReleaseManifest({
      tag: "v0.1.2",
      repo: "VptrCipher/SayIt",
      releaseDate: "2026-10-05T12:00:00Z",
      releaseFilesDir: dir,
      outDir: out,
    });

    // The lock between CI-side generation and site-side consumption:
    expect(validateReleaseManifest(manifest)).toEqual(manifest);

    expect(manifest.version).toBe("0.1.2");
    expect(manifest.release_date).toBe("2026-10-05");
    expect(manifest.stable).toBe(true);

    const windows = manifest.platforms.windows;
    expect(windows.url).toBe(
      "https://github.com/VptrCipher/SayIt/releases/download/v0.1.2/SayIt-Setup-x64.exe",
    );
    expect(windows.size_bytes).toBe(FAKE_EXE.length);
    expect(windows.sha256).toMatch(/^[a-f0-9]{64}$/);

    const linux = manifest.platforms.linux;
    expect(linux.url).toBe(
      "https://github.com/VptrCipher/SayIt/releases/download/v0.1.2/SayIt-v0.1.2-Linux-x86_64.AppImage",
    );
    expect(linux.size_bytes).toBe(FAKE_APPIMAGE.length);

    // The written file round-trips through the validator as well.
    const fromDisk = JSON.parse(await readFile(manifestPath, "utf8"));
    expect(validateReleaseManifest(fromDisk)).not.toBeNull();

    // checksums.txt is sha256sum-compatible and matches the artifacts.
    const checksums = await readFile(checksumsPath, "utf8");
    const lines = checksums.trim().split("\n");
    expect(lines).toHaveLength(2);
    const exeHash = createHash("sha256").update(FAKE_EXE).digest("hex");
    expect(lines[0]).toBe(`${exeHash}  SayIt-Setup-x64.exe`);
  });

  it("fails when a platform artifact is missing (no partial releases)", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);

    await expect(
      generateReleaseManifest({
        tag: "v0.1.2",
        repo: "VptrCipher/SayIt",
        releaseFilesDir: dir,
        outDir: out,
      }),
    ).rejects.toThrow(/AppImage artifact missing/i);
  });

  it("fails when an artifact does not match its own .sha256 sidecar", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE, false);
    await writeFile(
      join(dir, "SayIt-Setup-x64.exe.sha256"),
      `${"0".repeat(64)}  SayIt-Setup-x64.exe\n`,
      "utf8",
    );
    await writeArtifact(dir, "SayIt-v0.1.2-Linux-x86_64.AppImage", FAKE_APPIMAGE);

    await expect(
      generateReleaseManifest({
        tag: "v0.1.2",
        repo: "VptrCipher/SayIt",
        releaseFilesDir: dir,
        outDir: out,
      }),
    ).rejects.toThrow(/SHA-256 mismatch/i);
  });

  it("fails on a version mismatch between tag and artifact name", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);
    await writeArtifact(dir, "SayIt-v9.9.9-Linux-x86_64.AppImage", FAKE_APPIMAGE);

    await expect(
      generateReleaseManifest({
        tag: "v0.1.2",
        repo: "VptrCipher/SayIt",
        releaseFilesDir: dir,
        outDir: out,
      }),
    ).rejects.toThrow(/Version mismatch/i);
  });

  it("exits nonzero from the CLI on failure — CI gates on this", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE); // no AppImage

    const scriptPath = join(process.cwd(), "scripts", "generate-manifest.mjs");
    await expect(
      execFileAsync(process.execPath, [
        scriptPath,
        "--tag",
        "v0.1.2",
        "--repo",
        "VptrCipher/SayIt",
        "--release-files",
        dir,
        "--out",
        out,
      ]),
    ).rejects.toMatchObject({ code: 1 });
  });
});

describe("manifest helper functions", () => {
  it("strips the v prefix from tags", () => {
    expect(stripTagPrefix("v0.1.2")).toBe("0.1.2");
    expect(stripTagPrefix("0.2.0")).toBe("0.2.0");
  });

  it("normalizes release dates and defaults to today", () => {
    expect(toReleaseDate("2026-10-05T12:00:00Z")).toBe("2026-10-05");
    expect(toReleaseDate("2026-10-05")).toBe("2026-10-05");
    expect(toReleaseDate(undefined)).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(() => toReleaseDate("October 3rd")).toThrow(/Unrecognized release date/);
  });
});

const FAKE_OFFLINE = "fake offline installer bytes — much larger in reality";

async function writeDualFixtures(dir: string) {
  await writeArtifact(dir, "SayIt-Setup-x64-Offline.exe", FAKE_OFFLINE);
  await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);
  await writeArtifact(dir, "SayIt-v0.2.0-Linux-x86_64.AppImage", FAKE_APPIMAGE);
}

describe("dual Windows installers (v0.2.0)", () => {
  it("emits windows=offline (primary, models) + windows_ondemand=smaller + linux", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeDualFixtures(dir);

    const { manifest } = await generateReleaseManifest({
      tag: "v0.2.0",
      repo: "VptrCipher/SayIt",
      releaseDate: "2026-10-17",
      releaseFilesDir: dir,
      outDir: out,
    });

    expect(validateReleaseManifest(manifest)).toEqual(manifest);

    const win = manifest.platforms.windows as Record<string, unknown>;
    const ond = manifest.platforms.windows_ondemand as Record<string, unknown>;
    const linux = manifest.platforms.linux as Record<string, unknown>;

    expect(win.url).toContain("SayIt-Setup-x64-Offline.exe");
    expect(win.variant).toBe("offline");
    expect(win.bundles_models).toBe(true);
    expect(Array.isArray(win.models)).toBe(true);
    expect((win.models as unknown[]).length).toBe(4);

    expect(ond.url).toContain("SayIt-Setup-x64.exe");
    expect(ond.variant).toBe("ondemand");
    expect(ond.bundles_models).toBe(false);
    expect(ond.models).toBeUndefined();

    expect(linux.url).toContain("Linux-x86_64.AppImage");

    // The offline fixture is larger than the smaller fixture here.
    expect(win.size_bytes).toBeGreaterThan(ond.size_bytes as number);
  });

  it("offline-only release puts the offline installer in the windows slot", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-Setup-x64-Offline.exe", FAKE_OFFLINE);
    await writeArtifact(dir, "SayIt-v0.2.0-Linux-x86_64.AppImage", FAKE_APPIMAGE);

    const { manifest } = await generateReleaseManifest({
      tag: "v0.2.0",
      repo: "VptrCipher/SayIt",
      releaseFilesDir: dir,
      outDir: out,
    });
    const win = manifest.platforms.windows as Record<string, unknown>;
    expect(win.variant).toBe("offline");
    expect(manifest.platforms.windows_ondemand).toBeUndefined();
  });

  it("smaller-only release stays backward compatible (windows=ondemand)", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);
    await writeArtifact(dir, "SayIt-v0.2.0-Linux-x86_64.AppImage", FAKE_APPIMAGE);

    const { manifest } = await generateReleaseManifest({
      tag: "v0.2.0",
      repo: "VptrCipher/SayIt",
      releaseFilesDir: dir,
      outDir: out,
    });
    const win = manifest.platforms.windows as Record<string, unknown>;
    expect(win.url).toContain("SayIt-Setup-x64.exe");
    expect(win.variant).toBe("ondemand");
    expect(win.bundles_models).toBe(false);
    expect(manifest.platforms.windows_ondemand).toBeUndefined();
  });

  it("fails when no .exe is present", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-v0.2.0-Linux-x86_64.AppImage", FAKE_APPIMAGE);
    await expect(
      generateReleaseManifest({ tag: "v0.2.0", repo: "VptrCipher/SayIt", releaseFilesDir: dir, outDir: out }),
    ).rejects.toThrow(/\.exe artifact missing/i);
  });

  it("fails when the Linux AppImage is missing even if both exes exist", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-Setup-x64-Offline.exe", FAKE_OFFLINE);
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);
    await expect(
      generateReleaseManifest({ tag: "v0.2.0", repo: "VptrCipher/SayIt", releaseFilesDir: dir, outDir: out }),
    ).rejects.toThrow(/appimage artifact missing/i);
  });

  it("fails on ambiguous (duplicate) smaller installers", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);
    await writeArtifact(dir, "SayIt-Setup-x64-alt.exe", FAKE_EXE + "2");
    await writeArtifact(dir, "SayIt-v0.2.0-Linux-x86_64.AppImage", FAKE_APPIMAGE);
    await expect(
      generateReleaseManifest({ tag: "v0.2.0", repo: "VptrCipher/SayIt", releaseFilesDir: dir, outDir: out }),
    ).rejects.toThrow(/Ambiguous smaller installers/i);
  });

  it("fails on ambiguous (duplicate) offline installers", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-Setup-x64-Offline.exe", FAKE_OFFLINE);
    await writeArtifact(dir, "SayIt-Setup-arm64-Offline.exe", FAKE_OFFLINE + "2");
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);
    await writeArtifact(dir, "SayIt-v0.2.0-Linux-x86_64.AppImage", FAKE_APPIMAGE);
    await expect(
      generateReleaseManifest({ tag: "v0.2.0", repo: "VptrCipher/SayIt", releaseFilesDir: dir, outDir: out }),
    ).rejects.toThrow(/Ambiguous Full Offline installers/i);
  });

  it("fails when either installer mismatches its checksum sidecar", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-Setup-x64-Offline.exe", FAKE_OFFLINE, false);
    await writeFile(join(dir, "SayIt-Setup-x64-Offline.exe.sha256"), `${"a".repeat(64)}  SayIt-Setup-x64-Offline.exe\n`, "utf8");
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);
    await writeArtifact(dir, "SayIt-v0.2.0-Linux-x86_64.AppImage", FAKE_APPIMAGE);
    await expect(
      generateReleaseManifest({ tag: "v0.2.0", repo: "VptrCipher/SayIt", releaseFilesDir: dir, outDir: out }),
    ).rejects.toThrow(/SHA-256 mismatch/i);
  });

  it("writes checksum lines for all three artifacts", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeDualFixtures(dir);
    const { checksumsPath } = await generateReleaseManifest({
      tag: "v0.2.0",
      repo: "VptrCipher/SayIt",
      releaseFilesDir: dir,
      outDir: out,
    });
    const lines = (await readFile(checksumsPath, "utf8")).trim().split("\n");
    expect(lines).toHaveLength(3);
    expect(lines.some((l) => l.includes("SayIt-Setup-x64-Offline.exe"))).toBe(true);
    expect(lines.some((l) => /SayIt-Setup-x64\.exe$/.test(l))).toBe(true);
    expect(lines.some((l) => l.includes(".AppImage"))).toBe(true);
  });
});


describe("Windows/Linux-only v0.2.0 (macOS deferred)", () => {
  it("produces a valid manifest with NO macOS platform keys when no DMGs are present", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    // Exactly what the tag-triggered release job uploads when build-macos is
    // skipped for v0.2.0: both Windows installers + the Linux AppImage, no DMG.
    await writeArtifact(dir, "SayIt-Setup-x64-Offline.exe", FAKE_OFFLINE);
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);
    await writeArtifact(dir, "SayIt-v0.2.0-Linux-x86_64.AppImage", FAKE_APPIMAGE);

    const { manifest } = await generateReleaseManifest({
      tag: "v0.2.0",
      repo: "VptrCipher/SayIt",
      releaseFilesDir: dir,
      outDir: out,
    });

    expect(validateReleaseManifest(manifest)).toEqual(manifest);
    // Windows + Linux present...
    expect(manifest.platforms.windows).toBeDefined();
    expect(manifest.platforms.linux).toBeDefined();
    // ...and absolutely no macOS keys (no unavailable/fabricated mac downloads).
    const macKeys = Object.keys(manifest.platforms).filter((k) =>
      k.startsWith("macos"),
    );
    expect(macKeys).toEqual([]);
  });

  it("still fails fast if the Linux AppImage is missing (no partial release)", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-Setup-x64-Offline.exe", FAKE_OFFLINE);
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);
    await expect(
      generateReleaseManifest({
        tag: "v0.2.0",
        repo: "VptrCipher/SayIt",
        releaseFilesDir: dir,
        outDir: out,
      }),
    ).rejects.toThrow(/appimage artifact missing/i);
  });
});


const FAKE_DMG_ARM = "fake arm64 offline dmg bytes larger than smaller";
const FAKE_DMG_ARM_ON = "fake arm64 ondemand dmg";
const FAKE_DMG_INTEL = "fake x86_64 offline dmg bytes larger";

describe("macOS DMG manifest (cross-arch, v0.2.0)", () => {
  async function writeFullMatrix(dir: string) {
    await writeArtifact(dir, "SayIt-Setup-x64-Offline.exe", FAKE_OFFLINE);
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);
    await writeArtifact(dir, "SayIt-v0.2.0-Linux-x86_64.AppImage", FAKE_APPIMAGE);
    await writeArtifact(dir, "SayIt-macOS-arm64-Offline.dmg", FAKE_DMG_ARM);
    await writeArtifact(dir, "SayIt-macOS-arm64-OnDemand.dmg", FAKE_DMG_ARM_ON);
    await writeArtifact(dir, "SayIt-macOS-x86_64-Offline.dmg", FAKE_DMG_INTEL);
  }

  it("emits macos_arm64/_ondemand and macos_intel with arch + model metadata", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeFullMatrix(dir);
    const { manifest } = await generateReleaseManifest({
      tag: "v0.2.0", repo: "VptrCipher/SayIt", releaseDate: "2026-10-17",
      releaseFilesDir: dir, outDir: out,
    });
    expect(validateReleaseManifest(manifest)).toEqual(manifest);
    const p = manifest.platforms as Record<string, Record<string, unknown>>;

    expect(p.macos_arm64.format).toBe("dmg");
    expect(p.macos_arm64.architecture).toBe("arm64");
    expect(p.macos_arm64.variant).toBe("offline");
    expect(p.macos_arm64.bundles_models).toBe(true);
    expect((p.macos_arm64.models as unknown[]).length).toBe(4);
    expect(p.macos_arm64.min_os_version).toBe("12.0");
    expect(p.macos_arm64.url).toContain("SayIt-macOS-arm64-Offline.dmg");

    expect(p.macos_arm64_ondemand.variant).toBe("ondemand");
    expect(p.macos_arm64_ondemand.bundles_models).toBe(false);
    expect(p.macos_arm64_ondemand.models).toBeUndefined();

    expect(p.macos_intel.architecture).toBe("x86_64");
    expect(p.macos_intel.variant).toBe("offline");
    // Intel on-demand was not provided -> absent.
    expect(p.macos_intel_ondemand).toBeUndefined();
  });

  it("macOS is optional: a Windows+Linux-only release has no macos keys", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);
    await writeArtifact(dir, "SayIt-v0.2.0-Linux-x86_64.AppImage", FAKE_APPIMAGE);
    const { manifest } = await generateReleaseManifest({
      tag: "v0.2.0", repo: "VptrCipher/SayIt", releaseFilesDir: dir, outDir: out,
    });
    const keys = Object.keys(manifest.platforms);
    expect(keys.some((k) => k.startsWith("macos"))).toBe(false);
    expect(keys).toContain("windows");
    expect(keys).toContain("linux");
  });

  it("fails on ambiguous macOS arm64 offline DMGs", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeArtifact(dir, "SayIt-Setup-x64.exe", FAKE_EXE);
    await writeArtifact(dir, "SayIt-v0.2.0-Linux-x86_64.AppImage", FAKE_APPIMAGE);
    await writeArtifact(dir, "SayIt-macOS-arm64-Offline.dmg", FAKE_DMG_ARM);
    await writeArtifact(dir, "SayIt-macOS-arm64.dmg", FAKE_DMG_ARM + "2"); // also offline (default)
    await expect(
      generateReleaseManifest({ tag: "v0.2.0", repo: "VptrCipher/SayIt", releaseFilesDir: dir, outDir: out }),
    ).rejects.toThrow(/Ambiguous macOS arm64 offline/i);
  });

  it("writes a checksum line for each DMG", async () => {
    const dir = await makeFixtureDir();
    const out = await makeFixtureDir();
    await writeFullMatrix(dir);
    const { checksumsPath } = await generateReleaseManifest({
      tag: "v0.2.0", repo: "VptrCipher/SayIt", releaseFilesDir: dir, outDir: out,
    });
    const lines = (await readFile(checksumsPath, "utf8")).trim().split("\n");
    expect(lines.some((l) => l.includes("SayIt-macOS-arm64-Offline.dmg"))).toBe(true);
    expect(lines.some((l) => l.includes("SayIt-macOS-x86_64-Offline.dmg"))).toBe(true);
  });
});
