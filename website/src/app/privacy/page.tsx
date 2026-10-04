import type { Metadata } from "next";
import { Button } from "@/components/Button";
import { PageHero } from "@/components/PageHero";
import { PrivacyCard } from "@/components/PrivacyCard";
import { Reveal } from "@/components/Reveal";
import { MicIcon, ShieldIcon, SlidersIcon, WaveIcon, WindowIcon } from "@/components/icons";
import { site } from "@/lib/site";

export const metadata: Metadata = {
  title: "Privacy",
  description:
    "How SayIt handles speech, text, and data: local recognition, no required API key, optional off-by-default enhancement, metadata-only context detection, and explicit learning.",
  alternates: { canonical: "/privacy" },
};

const CARDS = [
  {
    icon: <MicIcon size={18} />,
    title: "Recognition runs locally",
    body: "Speech recognition runs on your device with a locally stored Sherpa-ONNX model. Your audio is processed on your machine, not sent to a speech service.",
  },
  {
    icon: <ShieldIcon size={18} />,
    title: "No account. No API key.",
    body: "Core dictation works without signing up, without an API key, and without a cloud speech service. The application never asks for one to type by voice.",
  },
  {
    icon: <WaveIcon size={18} />,
    title: "Enhancement is optional and off by default",
    body: "Transcript enhancement — via a local Ollama instance or a cloud provider — is opt-in. If you enable a remote provider, transcript text (never audio) is sent to that provider.",
  },
  {
    icon: <WindowIcon size={18} />,
    title: "Context detection reads metadata only",
    body: "SayIt detects the active application using process and window metadata. It never takes screenshots, reads your clipboard, logs keystrokes, or scans page and editor contents.",
  },
  {
    icon: <SlidersIcon size={18} />,
    title: "Learning is explicit",
    body: "Vocabulary rules are created only by you, or when you deliberately choose \"Remember\" after correcting a transcript. There is no silent learning, and vocabulary never leaves your device.",
  },
  {
    icon: <ShieldIcon size={18} />,
    title: "Safe zones",
    body: "Applications you mark as protected — password managers, banking — block recording before any audio is captured.",
  },
  {
    icon: <MicIcon size={18} />,
    title: "History is off by default",
    body: "Persistent transcript history is opt-in. The most recent transcript is kept in memory so it survives a failed insertion, and Clear Data removes settings, history, logs, and downloaded models.",
  },
  {
    icon: <WindowIcon size={18} />,
    title: "Network access, honestly",
    body: "SayIt touches the network to download speech models and — only if you switch it on — for optional transcript enhancement. The application contains no telemetry or analytics.",
  },
];

export default function PrivacyPage() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-6 lg:px-8">
      <PageHero
        eyebrow="Privacy"
        title="Your voice stays yours"
        description="How SayIt handles speech, text, and data — in plain language, matching the application's actual behavior."
      />

      <Reveal stagger className="grid gap-4 sm:grid-cols-2">
        {CARDS.map((card) => (
          <PrivacyCard key={card.title} icon={card.icon} title={card.title} body={card.body} />
        ))}
      </Reveal>

      <section aria-label="Honest boundaries" className="py-10">
        <Reveal>
          <div className="rounded-xl border border-line bg-subtle p-6 text-sm leading-relaxed text-muted sm:p-8">
            <h2 className="text-base font-semibold text-strong">No absolute promises</h2>
            <p className="mt-2">
              Because model downloads and optional cloud enhancement involve the network, SayIt
              doesn&rsquo;t promise a completely private or completely offline setup — it keeps
              those parts optional, local-first, and off by default, and says so plainly in its own
              privacy screen.
            </p>
          </div>
        </Reveal>
      </section>

      <section aria-label="Continue" className="pb-4">
        <Reveal>
          <div className="flex flex-wrap gap-3">
            <Button href="/features" variant="secondary">
              See what SayIt does
            </Button>
            <Button href={site.repositoryUrl} variant="ghost">
              View source on GitHub
            </Button>
          </div>
        </Reveal>
      </section>
    </div>
  );
}
