import Link from "next/link";
import type { CSSProperties } from "react";
import { Button } from "@/components/Button";
import { Container } from "@/components/Container";
import { CtaBand } from "@/components/CtaBand";
import { DictationDemo } from "@/components/DictationDemo";
import { FaqSection } from "@/components/FaqSection";
import { HeroWave } from "@/components/HeroWave";
import { HotkeyChip } from "@/components/HotkeyChip";
import { Marquee } from "@/components/Marquee";
import { PersonalizationBento } from "@/components/PersonalizationBento";
import { PlatformStatus } from "@/components/PlatformStatus";
import { ProfileTabs } from "@/components/ProfileTabs";
import { Reveal } from "@/components/Reveal";
import { SectionHeading } from "@/components/SectionHeading";
import { SpeakCompare } from "@/components/SpeakCompare";
import { Spotlight } from "@/components/Spotlight";
import { TiltCard } from "@/components/TiltCard";
import { CheckIcon, MicIcon, ShieldIcon, StackIcon, WaveIcon, WindowIcon } from "@/components/icons";
import { site } from "@/lib/site";

const STEPS = [
  {
    title: "Hold the hotkey",
    body: "Hold your configurable push-to-talk hotkey and speak naturally.",
    kbd: ["Hotkey"],
    icon: MicIcon,
  },
  {
    title: "Say what you mean",
    body: "Dictate prose, code identifiers, URLs — or spoken edits like \"scratch that\".",
    icon: WaveIcon,
  },
  {
    title: "Release to transcribe",
    body: "Recognition runs locally on your device, then deterministic formatting rules tidy the text.",
    icon: StackIcon,
  },
  {
    title: "Text at your cursor",
    body: "The result is inserted into the app you were typing in. Changed your mind? Esc cancels.",
    kbd: ["Esc"],
    icon: WindowIcon,
  },
];

const PRIVACY_POINTS = [
  "Transcription via Sherpa-ONNX, on your device",
  "No account and no API key for core dictation",
  "Safe zones block recording before audio capture",
  "Every local rule is deterministic and can be switched off",
];

export default function HomePage() {
  return (
    <Container className="pb-20">
      {/* Hero + signature dictation demo. overflow-hidden keeps the wide
          decorative layers from creating horizontal scroll on small screens. */}
      <section className="relative isolate overflow-hidden pb-16 pt-14 sm:pb-24 sm:pt-20">
        {/* Layered backdrop: parallax auroras, pointer spotlight, waveform. */}
        <div aria-hidden="true" className="parallax-lift absolute inset-x-0 top-0">
          <div className="aurora-blob -top-20 left-[8%] size-56 bg-accent-soft sm:size-72" />
        </div>
        <div aria-hidden="true" className="parallax-drop absolute inset-x-0 top-0">
          <div className="aurora-blob right-[6%] top-32 size-64 bg-accent/10 sm:size-80 [animation-delay:-8s]" />
        </div>
        <Spotlight />

        <HeroWave className="absolute inset-x-0 bottom-0 z-0 [mask-image:linear-gradient(to_top,#000_15%,transparent_80%)]" />

        <div className="relative mx-auto max-w-3xl text-center">
          <span
            className="reveal-lux inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3.5 py-1.5 text-xs font-medium text-body shadow-card"
            style={{ "--reveal-delay": "0ms" } as CSSProperties}
          >
            <MicIcon size={14} className="text-accent" />
            Local push-to-talk dictation · Windows &amp; Linux
          </span>
          <h1
            className="reveal-lux mt-6 text-5xl font-semibold tracking-tight text-strong sm:text-6xl lg:text-7xl"
            style={{ "--reveal-delay": "90ms" } as CSSProperties}
          >
            {site.tagline}
          </h1>
          <p
            className="reveal-lux mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-muted"
            style={{ "--reveal-delay": "180ms" } as CSSProperties}
          >
            SayIt is a local push-to-talk voice-typing utility for Windows and Linux. Hold a
            hotkey, speak, release — the transcribed text is inserted at your cursor.
          </p>
          <div
            className="reveal-lux mt-8 flex flex-wrap items-center justify-center gap-3"
            style={{ "--reveal-delay": "270ms" } as CSSProperties}
          >
            <Button href="/download" size="lg" className="w-full sm:w-auto">
              Download SayIt
            </Button>
            <Button href="#how-it-works" variant="secondary" size="lg" className="w-full sm:w-auto">
              See how it works
            </Button>
          </div>
          <p
            className="reveal-lux mx-auto mt-6 max-w-xl text-sm text-muted"
            style={{ "--reveal-delay": "360ms" } as CSSProperties}
          >
            Installers for Windows and Linux appear in the{" "}
            <Link
              className="font-medium text-strong underline decoration-line-strong underline-offset-2 hover:text-accent-text"
              href="/download"
            >
              download center
            </Link>{" "}
            with the first public release. Until then, the{" "}
            <a
              className="font-medium text-strong underline decoration-line-strong underline-offset-2 hover:text-accent-text"
              href={site.repositoryUrl}
            >
              source
            </a>{" "}
            and any{" "}
            <a
              className="font-medium text-strong underline decoration-line-strong underline-offset-2 hover:text-accent-text"
              href={site.releasesUrl}
            >
              release artifacts
            </a>{" "}
            live on GitHub.
          </p>
        </div>
        <div className="reveal relative mx-auto mt-14 max-w-3xl sm:mt-16">
          <TiltCard>
            <DictationDemo />
          </TiltCard>
        </div>
      </section>

      {/* Ambient ribbon of the surfaces SayIt types into */}
      <section aria-hidden="true" className="pb-4 pt-2 sm:pb-8">
        <Marquee />
      </section>

      {/* Why say it — typing vs speaking */}
      <section aria-labelledby="speed-heading" className="py-14 sm:py-20">
        <SectionHeading
          eyebrow="Why say it"
          title="Speak at the speed of thought"
          description="Typing tops out at your fingers. Speaking doesn't — and SayIt keeps the loop tight: hold, speak, release, done."
        />
        <Reveal className="mt-8">
          <SpeakCompare />
        </Reveal>
      </section>

      {/* How it works */}
      <section id="how-it-works" aria-labelledby="how-heading" className="scroll-mt-20 py-14 sm:py-20">
        <SectionHeading
          eyebrow="How it works"
          title="Four steps to your words on the page"
          description="No accounts, no setup wizard beyond a microphone and a model — just a key and your voice."
        />
        <Reveal stagger className="mt-8">
          <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((step, index) => {
              const StepIcon = step.icon;
              return (
                <li
                  key={step.title}
                  className="card-glow flex h-full flex-col rounded-xl border border-line bg-surface p-5 shadow-card"
                >
                  <div className="flex items-center justify-between">
                    <span
                      aria-hidden="true"
                      className="flex size-8 items-center justify-center rounded-full bg-accent-soft font-mono text-sm font-semibold text-accent"
                    >
                      {index + 1}
                    </span>
                    <StepIcon size={18} className="text-muted" />
                  </div>
                  <h3 className="mt-3 text-base font-semibold text-strong">{step.title}</h3>
                  <p className="mt-2 flex-1 text-sm leading-relaxed text-muted">{step.body}</p>
                  {step.kbd ? <HotkeyChip keys={step.kbd} className="mt-4" /> : null}
                </li>
              );
            })}
          </ol>
        </Reveal>
      </section>

      {/* Context awareness */}
      <section aria-labelledby="context-heading" className="relative isolate py-14 sm:py-20">
        <div
          aria-hidden="true"
          className="aurora-blob -right-10 top-6 size-48 bg-accent/5 sm:size-64"
        />
        <div className="relative">
          <SectionHeading
            eyebrow="Context awareness"
            title="Adapts to where you’re typing"
            description="SayIt reads the active application’s metadata — never its contents — and picks a matching formatting profile. A manual override always wins."
          />
          <Reveal className="mt-8">
            <ProfileTabs />
          </Reveal>
        </div>
      </section>

      {/* Personalization bento */}
      <section aria-labelledby="personalization-heading" className="py-14 sm:py-20">
        <SectionHeading
          eyebrow="Personalization"
          title="A vocabulary that’s actually yours"
          description="Rules, snippets, and corrections are visible, editable, and yours to switch off — nothing learns without you."
        />
        <Reveal stagger className="mt-8">
          <PersonalizationBento />
        </Reveal>
        <Reveal className="mt-6 text-center">
          <Link
            href="/features"
            className="text-sm font-medium text-accent-text underline-offset-4 hover:underline"
          >
            Explore all features →
          </Link>
        </Reveal>
      </section>

      {/* Privacy band */}
      <section aria-labelledby="privacy-band-heading" className="py-14 sm:py-20">
        <Reveal>
          <div className="grid items-center gap-8 rounded-3xl border border-line bg-subtle px-6 py-10 sm:px-10 sm:py-14 lg:grid-cols-2">
            <div>
              <span className="inline-flex size-10 items-center justify-center rounded-lg bg-accent-soft text-accent">
                <ShieldIcon size={20} />
              </span>
              <h2
                id="privacy-band-heading"
                className="mt-4 text-2xl font-semibold tracking-tight text-strong sm:text-3xl"
              >
                Your words stay on your machine
              </h2>
              <p className="mt-3 max-w-xl text-base leading-relaxed text-muted">
                Recognition runs on your device. Context detection reads application metadata
                only — no screenshots, no clipboard scraping, no keylogging. Optional cloud
                enhancement is off by default and clearly separated from core dictation.
              </p>
              <Button href="/privacy" variant="secondary" className="mt-6">
                Read the privacy notes
              </Button>
            </div>
            <ul className="space-y-3">
              {PRIVACY_POINTS.map((point) => (
                <li key={point} className="flex items-start gap-3">
                  <span
                    aria-hidden="true"
                    className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
                  >
                    <CheckIcon size={11} strokeWidth={2.5} />
                  </span>
                  <span className="text-sm leading-relaxed text-body">{point}</span>
                </li>
              ))}
            </ul>
          </div>
        </Reveal>
      </section>

      {/* Platform status */}
      <section id="platforms" aria-labelledby="platforms-heading" className="scroll-mt-20 py-14 sm:py-20">
        <SectionHeading
          eyebrow="Platforms"
          title="Where it runs today"
          description="Support reflects what has actually been validated — not marketing."
        />
        <Reveal className="mt-8">
          <PlatformStatus />
        </Reveal>
      </section>

      {/* FAQ */}
      <section className="relative isolate py-14 sm:py-20">
        <div
          aria-hidden="true"
          className="aurora-blob -left-12 bottom-0 size-48 bg-accent/5 sm:size-64"
        />
        <div className="relative">
          <Reveal>
            <FaqSection />
          </Reveal>
        </div>
      </section>

      {/* Closing CTA */}
      <section className="pt-6 sm:pt-10">
        <Reveal>
          <CtaBand />
        </Reveal>
      </section>
    </Container>
  );
}
