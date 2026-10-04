"use client";

import { useId, useRef, useState, useSyncExternalStore } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { MiniWindow } from "./MiniWindow";

/**
 * Interactive demo for context awareness: pick the app SayIt is "typing" into
 * and see a documented local behavior applied. Panels render stacked and fully
 * visible without JavaScript; after hydration the component switches to real
 * ARIA tabs (keyboard arrows included) and hides inactive panels.
 *
 * Copy rules: every shown behavior maps to a documented feature
 * (src/lib/features.ts) — technical correction, voice edit, structure
 * commands — and profile names come from the actual profile list.
 */

type ProfileDemo = {
  id: string;
  tab: string;
  window: string;
  profile: string;
  said: string;
  inserted: ReactNode;
  features: string[];
  note: string;
};

const markClass =
  "rounded bg-accent-soft px-1 font-semibold text-strong no-underline";

const subscribeNoop = () => () => {};

const PROFILES: ProfileDemo[] = [
  {
    id: "developer",
    tab: "Code editor",
    window: "Active window: code editor",
    profile: "Profile: Developer",
    said: "open the ci slash cd logs and check the git hub runner",
    inserted: (
      <>
        Open the <mark className={markClass}>CI/CD</mark> logs and check the{" "}
        <mark className={markClass}>GitHub</mark> runner.
      </>
    ),
    features: ["Technical correction", "Formatting profiles"],
    note: "The Developer profile runs the local technical-correction rules: spoken tech terms come out formatted, while ordinary prose is left alone.",
  },
  {
    id: "email",
    tab: "Email client",
    window: "Active window: email client",
    profile: "Profile: Email",
    said: "i'll arrive at five actually six new paragraph kind regards",
    inserted: (
      <>
        <span className="block">I&apos;ll arrive at six.</span>
        <span className="mt-3 block">Kind regards</span>
      </>
    ),
    features: ["Voice edit", "Structure commands"],
    note: "“Actually six” supersedes “five”, and “new paragraph” becomes a real break — deterministic local rules, no LLM in the loop.",
  },
  {
    id: "chat",
    tab: "Chat app",
    window: "Active window: chat app",
    profile: "Profile: Chat",
    said: "let's sync tomorrow scratch that let's sync on thursday",
    inserted: <>Let&apos;s sync on Thursday.</>,
    features: ["Voice edit — “scratch that”"],
    note: "“Scratch that” drops what came before it in the utterance, so the message lands as if the false start never happened.",
  },
];

export function ProfileTabs() {
  const baseId = useId();
  const [active, setActive] = useState(PROFILES[0].id);
  // False during SSR and without JavaScript: all panels stay visible, stacked.
  // The canonical hydration probe — no setState-in-effect cascade.
  const interactive = useSyncExternalStore(
    subscribeNoop,
    () => true,
    () => false,
  );
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const activeIndex = Math.max(
    0,
    PROFILES.findIndex((profile) => profile.id === active),
  );

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const last = PROFILES.length - 1;
    let next = activeIndex;
    if (event.key === "ArrowRight") next = activeIndex === last ? 0 : activeIndex + 1;
    else if (event.key === "ArrowLeft") next = activeIndex === 0 ? last : activeIndex - 1;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = last;
    else return;
    event.preventDefault();
    setActive(PROFILES[next].id);
    tabRefs.current[next]?.focus();
  }

  return (
    <div>
      <div
        role="tablist"
        aria-label="Formatting profile examples"
        onKeyDown={onKeyDown}
        className="flex flex-wrap gap-2"
      >
        {PROFILES.map((profile, index) => {
          const selected = profile.id === active;
          return (
            <button
              key={profile.id}
              ref={(node) => {
                tabRefs.current[index] = node;
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${profile.id}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${profile.id}`}
              tabIndex={interactive && !selected ? -1 : 0}
              onClick={() => setActive(profile.id)}
              className={`rounded-lg border px-3.5 py-1.5 text-sm font-medium transition-colors duration-[var(--motion-fast)] ease-soft ${
                selected
                  ? "border-accent bg-accent text-on-accent shadow-sm"
                  : "border-line-strong bg-surface text-body hover:border-accent hover:text-strong"
              }`}
            >
              {profile.tab}
            </button>
          );
        })}
      </div>

      <div className="mt-5">
        {PROFILES.map((profile) => {
          const selected = profile.id === active;
          return (
            <div
              key={profile.id}
              role="tabpanel"
              id={`${baseId}-panel-${profile.id}`}
              aria-labelledby={`${baseId}-tab-${profile.id}`}
              hidden={interactive && !selected}
              className={selected ? "panel-in" : "mt-4"}
            >
              <MiniWindow title={profile.window} chip={profile.profile}>
                <p className="text-xs font-semibold uppercase tracking-wider text-muted">
                  You say
                </p>
                <p className="mt-2 text-base leading-relaxed text-body">“{profile.said}”</p>
                <p className="mt-5 text-xs font-semibold uppercase tracking-wider text-accent-text">
                  Inserted
                </p>
                <p className="mt-2 text-lg font-medium leading-relaxed text-strong">
                  {profile.inserted}
                </p>
                <ul className="mt-5 flex flex-wrap gap-2">
                  {profile.features.map((feature) => (
                    <li
                      key={feature}
                      className="inline-flex items-center rounded-full border border-line bg-subtle px-2.5 py-1 text-xs text-muted"
                    >
                      {feature}
                    </li>
                  ))}
                </ul>
                <p className="mt-4 border-t border-line pt-3 text-sm leading-relaxed text-muted">
                  {profile.note}
                </p>
              </MiniWindow>
            </div>
          );
        })}
      </div>
    </div>
  );
}
