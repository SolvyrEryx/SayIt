/**
 * Client-side platform detection for the download experience (master plan §8).
 *
 * Rules of the road: detection informs only the *order* and emphasis of
 * download cards. It is never stored, never transmitted, and never sent to
 * analytics — there is no analytics.
 */

export type Platform = "windows" | "linux" | "macos" | "unknown";

export type PlatformInput = {
  /** navigator.userAgentData?.platform — e.g. "Windows", "macOS", "Linux". */
  userAgentDataPlatform?: string | null;
  /** navigator.platform — e.g. "Win32", "MacIntel", "Linux x86_64". */
  platform?: string | null;
  /** navigator.userAgent. */
  userAgent?: string | null;
};

export function detectPlatform(input: PlatformInput): Platform {
  const userAgent = input.userAgent?.toLowerCase() ?? "";

  // Mobile/ChromeOS environments cannot run SayIt — resolve them first so a
  // "Linux armv8l" navigator.platform on an Android device is not mistaken
  // for desktop Linux.
  if (
    userAgent.includes("android") ||
    userAgent.includes("iphone") ||
    userAgent.includes("ipad") ||
    userAgent.includes("cros")
  ) {
    return "unknown";
  }

  const uaData = input.userAgentDataPlatform?.toLowerCase() ?? "";
  if (uaData) {
    if (uaData.includes("windows")) return "windows";
    if (uaData.includes("mac")) return "macos";
    if (uaData.includes("linux")) return "linux";
    if (uaData.includes("android") || uaData.includes("cros") || uaData.includes("ios")) {
      return "unknown";
    }
  }

  const platform = input.platform?.toLowerCase() ?? "";
  if (platform) {
    if (platform.includes("win")) return "windows";
    if (platform.includes("mac") || platform.includes("ipad") || platform.includes("iphone")) {
      return "macos";
    }
    if (platform.includes("linux")) return "linux";
  }

  if (userAgent) {
    if (userAgent.includes("windows nt")) return "windows";
    if (userAgent.includes("macintosh") || userAgent.includes("mac os")) return "macos";
    if (userAgent.includes("linux")) return "linux";
  }

  return "unknown";
}

/** Detection from the real browser environment. Client-side only. */
export function detectNavigatorPlatform(nav: Navigator = navigator): Platform {
  const userAgentData = (
    nav as Navigator & { userAgentData?: { platform?: string } }
  ).userAgentData;
  return detectPlatform({
    userAgentDataPlatform: userAgentData?.platform ?? null,
    platform: nav.platform ?? null,
    userAgent: nav.userAgent ?? null,
  });
}
