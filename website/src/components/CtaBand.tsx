import { Button } from "./Button";
import { SayItMark } from "./SayItMark";

/**
 * Closing call to action. The oversized brand mark is a decorative watermark;
 * the band stays on token surfaces (accent-soft) with text-strong copy, which
 * the contrast audit already covers.
 */
export function CtaBand() {
  return (
    <section
      aria-labelledby="cta-heading"
      className="relative overflow-hidden rounded-3xl border border-line bg-accent-soft px-6 py-14 text-center sm:px-10 sm:py-20"
    >
      <div
        aria-hidden="true"
        className="aurora-blob -left-16 top-1/2 size-72 -translate-y-1/2 bg-accent/15"
      />
      <SayItMark
        size={280}
        title=""
        className="bob pointer-events-none absolute -bottom-14 -right-10 hidden text-accent opacity-10 sm:block"
      />
      <div className="relative">
        <h2
          id="cta-heading"
          className="mx-auto max-w-2xl text-3xl font-semibold tracking-tight text-strong sm:text-4xl"
        >
          Hold a key. Say the thing.
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-body">
          SayIt for Windows and Linux — hold, speak, release, and the words are typed where your
          cursor is.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Button href="/download" size="lg">
            Download SayIt
          </Button>
          <Button href="/install" variant="secondary" size="lg">
            Install guide
          </Button>
        </div>
        <p className="mt-6 text-sm text-muted">
          Released under the MIT License — no account, no API key for core dictation.
        </p>
      </div>
    </section>
  );
}
