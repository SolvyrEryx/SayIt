import type { CSSProperties } from "react";
import { Card } from "./Card";
import { MicIcon, WaveIcon } from "./icons";

/**
 * The typing-vs-speaking comparison, staged honestly: both sides render the
 * same sentence, and the caption states up front that this is an illustration
 * rather than a benchmark (master-plan rule: no fabricated performance
 * numbers). The animation is pure CSS — with motion reduced, both lines
 * simply appear complete.
 */

// steps() in the type-line animation needs the exact character count.
const SENTENCE = "Ship the release notes before Friday.";

export function SpeakCompare() {
  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Card className="card-glow p-6 sm:p-7">
          <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted">
            <WaveIcon size={14} />
            On the keyboard
          </p>
          <p
            className="type-line mt-5 font-mono text-sm text-strong sm:text-base"
            style={{ "--type-chars": SENTENCE.length } as CSSProperties}
          >
            {SENTENCE}
          </p>
        </Card>
        <Card className="card-glow p-6 sm:p-7">
          <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-accent-text">
            <MicIcon size={14} />
            Said with SayIt
          </p>
          <span aria-hidden="true" className="wave-bars mt-6 text-accent">
            {[8, 16, 11, 20, 12, 17, 9].map((height, index) => (
              <span
                key={index}
                className="wave-bar"
                style={{ "--wave-h": `${height}px`, "--i": index } as CSSProperties}
              />
            ))}
          </span>
          <p className="voice-line mt-3 text-lg font-medium leading-relaxed text-strong sm:text-xl">
            {SENTENCE}
          </p>
        </Card>
      </div>
      <p className="mt-4 text-center text-sm text-muted">
        An illustration, not a benchmark — transcription time depends on your hardware, utterance
        length, and model choice.
      </p>
    </div>
  );
}
