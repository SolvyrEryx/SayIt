import { describe, expect, it } from "vitest";
import { detectPlatform } from "@/lib/platform";

describe("detectPlatform", () => {
  it("prefers userAgentData when present", () => {
    expect(detectPlatform({ userAgentDataPlatform: "Windows" })).toBe("windows");
    expect(detectPlatform({ userAgentDataPlatform: "macOS" })).toBe("macos");
    expect(detectPlatform({ userAgentDataPlatform: "Linux" })).toBe("linux");
  });

  it("falls back to navigator.platform", () => {
    expect(detectPlatform({ platform: "Win32" })).toBe("windows");
    expect(detectPlatform({ platform: "MacIntel" })).toBe("macos");
    expect(detectPlatform({ platform: "Linux x86_64" })).toBe("linux");
  });

  it("falls back to the user agent string", () => {
    expect(
      detectPlatform({ userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }),
    ).toBe("windows");
    expect(
      detectPlatform({ userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" }),
    ).toBe("macos");
    expect(detectPlatform({ userAgent: "Mozilla/5.0 (X11; Linux x86_64)" })).toBe("linux");
  });

  it("never mistakes mobile or ChromeOS for a supported desktop", () => {
    // Android devices often report navigator.platform = "Linux armv8l".
    expect(
      detectPlatform({
        platform: "Linux armv8l",
        userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 8)",
      }),
    ).toBe("unknown");
    expect(
      detectPlatform({ userAgentDataPlatform: "Android", platform: "Linux armv8l" }),
    ).toBe("unknown");
    expect(
      detectPlatform({ userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)" }),
    ).toBe("unknown");
    expect(
      detectPlatform({ userAgent: "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0)" }),
    ).toBe("unknown");
  });

  it("treats desktop-impersonating iPadOS as macOS (correct: unsupported either way)", () => {
    expect(
      detectPlatform({
        platform: "MacIntel",
        userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
      }),
    ).toBe("macos");
  });

  it("respects userAgentData over a conflicting user agent", () => {
    // Linux UA-CH wins over a stale Windows user agent.
    expect(
      detectPlatform({
        userAgentDataPlatform: "Linux",
        userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      }),
    ).toBe("linux");
  });

  it("returns unknown when nothing is usable", () => {
    expect(detectPlatform({})).toBe("unknown");
    expect(detectPlatform({ platform: "", userAgent: "" })).toBe("unknown");
  });
});
