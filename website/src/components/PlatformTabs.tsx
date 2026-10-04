"use client";

import { useId, useRef, useState, useSyncExternalStore, type KeyboardEvent, type ReactNode } from "react";
import Link from "next/link";
import { detectNavigatorPlatform, type Platform } from "@/lib/platform";

export type InstallTabKey = "windows" | "linux" | "source";

export type InstallTab = {
  key: InstallTabKey;
  label: string;
  content: ReactNode;
};

/** Pure mapping from detected platform to the tab shown first (plan §29). */
export function preferredInstallTab(platform: Platform): InstallTabKey {
  return platform === "linux" ? "linux" : "windows";
}

const subscribePlatform = () => () => {};
const getServerPlatform = (): Platform => "unknown";

function subscribeHash(callback: () => void) {
  window.addEventListener("hashchange", callback);
  window.addEventListener("popstate", callback);
  return () => {
    window.removeEventListener("hashchange", callback);
    window.removeEventListener("popstate", callback);
  };
}

/**
 * Accessible platform tabs for the install page. Defaults to the detected
 * platform (Windows when unknown), shows an honest macOS notice, and
 * deep-links tab selection to the URL hash (/install#windows, /install#linux,
 * /install#source).
 */
export function PlatformTabs({
  tabs,
  platform: platformOverride,
}: {
  tabs: InstallTab[];
  platform?: Platform;
}) {
  const detected = useSyncExternalStore(
    subscribePlatform,
    () => platformOverride ?? detectNavigatorPlatform(),
    getServerPlatform,
  );

  const [active, setActive] = useState<InstallTabKey>(() => preferredInstallTab(detected));
  const baseId = useId();
  const tablistRef = useRef<HTMLDivElement>(null);

  // The URL hash is an external store: /install#linux selects the Linux guide.
  const hashTab = useSyncExternalStore(
    subscribeHash,
    () => {
      const hash = window.location.hash.slice(1) as InstallTabKey;
      return tabs.some((tab) => tab.key === hash) ? hash : ("" as InstallTabKey | "");
    },
    () => "" as InstallTabKey | "",
  );
  const effective = hashTab || active;

  const selectTab = (key: InstallTabKey) => {
    setActive(key);
    history.replaceState(null, "", `#${key}`);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const currentIndex = tabs.findIndex((tab) => tab.key === effective);
    let next = currentIndex;
    if (event.key === "ArrowRight") next = (currentIndex + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (currentIndex - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    selectTab(tabs[next].key);
    const buttons = tablistRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    buttons?.[next]?.focus();
  };

  return (
    <div>
      {detected === "macos" ? (
        <div className="mb-8 rounded-xl border border-line bg-subtle p-5 text-sm leading-relaxed text-body">
          <strong className="font-semibold text-strong">
            SayIt currently supports Windows and Linux.
          </strong>{" "}
          There is no macOS version. The guides below cover the supported platforms, plus a{" "}
          <Link
            href="#source"
            className="font-medium text-strong underline decoration-line-strong underline-offset-4 hover:underline"
          >
            developer / source install
          </Link>{" "}
          for building from source.
        </div>
      ) : null}

      <div
        ref={tablistRef}
        role="tablist"
        aria-label="Installation platform"
        onKeyDown={handleKeyDown}
        className="flex flex-wrap gap-2"
      >
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            id={`${baseId}-tab-${tab.key}`}
            aria-selected={effective === tab.key}
            aria-controls={`${baseId}-panel-${tab.key}`}
            tabIndex={effective === tab.key ? 0 : -1}
            onClick={() => selectTab(tab.key)}
            className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors duration-[var(--motion-fast)] ease-soft ${
              effective === tab.key
                ? "border-accent bg-accent text-on-accent shadow-sm"
                : "border-line-strong bg-surface text-body hover:border-accent hover:text-strong"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {tabs.map((tab) => (
        <div
          key={tab.key}
          role="tabpanel"
          id={`${baseId}-panel-${tab.key}`}
          aria-labelledby={`${baseId}-tab-${tab.key}`}
          hidden={effective !== tab.key}
          className="pt-8"
        >
          {tab.content}
        </div>
      ))}
    </div>
  );
}
