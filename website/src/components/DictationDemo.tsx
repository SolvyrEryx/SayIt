import { CheckIcon } from "./icons";
import { HotkeyChip } from "./HotkeyChip";
import { MiniWindow } from "./MiniWindow";

/**
 * The hero's signature demo: one push-to-talk utterance looping through
 * record → transcribe → inserted text. The phases are a pure-CSS loop (see
 * the demo-* keyframes in globals.css); with animation collapsed — reduced
 * motion, tests — only the finished transcript shows, which is also the only
 * phase exposed to assistive tech: the transient phases are decorative.
 *
 * Every correction shown is a documented SayIt capability (src/lib/features.ts):
 * "git hub" → GitHub (technical correction), "next js" → Next.js (custom
 * vocabulary), "get user by id camel case" → getUserById (developer mode).
 * Nothing in the loop implies filler-word removal or AI rewriting.
 */

const CORRECTIONS = [
  { rule: "Technical correction", from: "git hub", to: "GitHub" },
  { rule: "Custom vocabulary", from: "next js", to: "Next.js" },
  { rule: "Developer mode", from: "get user by id camel case", to: "getUserById" },
];

export function DictationDemo() {
  return (
    <figure className="relative m-0">
      {/* Soft accent glow behind the window */}
      <div
        aria-hidden="true"
        className="absolute -inset-x-8 top-8 -bottom-10 rounded-full bg-accent-soft/70 blur-3xl"
      />

      <MiniWindow title="Active window: code editor" chip="Profile: Developer" className="card-glow">
        <div className="demo-stage">
          {/* Phase 1 — recording */}
          <div className="demo-phase demo-phase-record" aria-hidden="true">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-record bg-record-soft px-3 py-1 text-xs font-semibold text-record">
                <span className="rec-dot size-2 rounded-full bg-record" />
                Recording
              </span>
              <span className="inline-flex items-center gap-2 text-xs text-muted">
                <HotkeyChip keys={["Hotkey"]} /> held — configurable
              </span>
              <span className="wave-bars ml-auto hidden text-record sm:flex">
                {[10, 20, 13, 24, 15, 21, 9, 17, 12].map((height, index) => (
                  <span
                    key={index}
                    className="wave-bar"
                    style={{ "--wave-h": `${height}px`, "--i": index } as React.CSSProperties}
                  />
                ))}
              </span>
            </div>
            <p className="mt-5 text-lg leading-relaxed text-body sm:text-xl">
              “open the git hub actions log for the next js build and run get user by id camel
              case on it”
              <span
                aria-hidden="true"
                className="caret-blink ml-1 inline-block h-5 w-0.5 translate-y-1 bg-accent"
              />
            </p>
          </div>

          {/* Phase 2 — local transcription */}
          <div className="demo-phase demo-phase-transcribe" aria-hidden="true">
            <div className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className="size-4 animate-spin rounded-full border-2 border-accent border-t-transparent"
              />
              <span className="text-base font-medium text-strong">Transcribing locally</span>
            </div>
            <p className="mt-2 text-sm text-muted">
              Sherpa-ONNX — recognition runs on your device, once you release the key.
            </p>
            <div className="mt-6 h-1.5 overflow-hidden rounded-full bg-subtle">
              <div className="demo-progress-bar h-full w-1/3 rounded-full bg-accent" />
            </div>
          </div>

          {/* Phase 3 — the result (the only phase assistive tech sees) */}
          <div className="demo-phase demo-phase-result">
            <p className="text-lg leading-relaxed text-strong sm:text-xl">
              Open the{" "}
              <mark className="rounded bg-accent-soft px-1 font-semibold text-strong no-underline">
                GitHub
              </mark>{" "}
              Actions log for the{" "}
              <mark className="rounded bg-accent-soft px-1 font-semibold text-strong no-underline">
                Next.js
              </mark>{" "}
              build and run{" "}
              <code className="rounded bg-subtle px-1.5 py-0.5 font-mono text-[0.9em] text-strong">
                getUserById
              </code>{" "}
              on it.
              <span
                aria-hidden="true"
                className="caret-blink ml-1 inline-block h-5 w-0.5 translate-y-1 bg-accent"
              />
            </p>
            <ul className="mt-5 flex flex-wrap gap-2">
              {CORRECTIONS.map((correction) => (
                <li
                  key={correction.rule}
                  className="inline-flex items-center gap-1.5 rounded-full border border-line bg-subtle px-2.5 py-1 text-xs text-muted"
                >
                  <span className="font-medium text-strong">{correction.rule}</span>
                  <span className="font-mono">
                    {correction.from} → {correction.to}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-5 flex items-center gap-2 text-sm text-muted">
              <span className="inline-flex size-5 items-center justify-center rounded-full bg-accent-soft text-accent">
                <CheckIcon size={12} strokeWidth={2.5} />
              </span>
              Inserted at your cursor — Esc cancels at any point.
            </p>
          </div>
        </div>
      </MiniWindow>

      <figcaption className="relative mt-4 text-center text-sm text-muted">
        One utterance, start to finish. Every fix shown is a real, toggleable rule — not an
        artist’s impression.
      </figcaption>
    </figure>
  );
}
