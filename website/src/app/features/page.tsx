import type { Metadata } from "next";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { FeatureCard } from "@/components/FeatureCard";
import { PageHero } from "@/components/PageHero";
import { Reveal } from "@/components/Reveal";
import { SectionHeading } from "@/components/SectionHeading";
import { MicIcon, SlidersIcon, StackIcon, WindowIcon } from "@/components/icons";
import { site } from "@/lib/site";
import { FEATURE_SECTIONS, HONEST_LIMITATIONS } from "@/lib/features";

export const metadata: Metadata = {
  title: "Features",
  description:
    "Push-to-talk dictation, context-aware formatting, and a deterministic local intelligence layer — every feature listed here ships in the current SayIt application.",
  alternates: { canonical: "/features" },
};

const SECTION_ICONS = {
  dictation: <MicIcon size={20} />,
  context: <WindowIcon size={20} />,
  intelligence: <StackIcon size={20} />,
  personalization: <SlidersIcon size={20} />,
} as const;

const VOCABULARY_EXAMPLES = [
  { spoken: "next js", written: "Next.js" },
  { spoken: "open ai", written: "OpenAI" },
  { spoken: "my github", written: "→ your saved snippet" },
];

export default function FeaturesPage() {
  return (
    <>
      <div className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-6 lg:px-8">
        <PageHero
          eyebrow="Features"
          title="What SayIt does today"
          description="Every item below corresponds to functionality in the current application. Anything not implemented yet simply isn't listed."
        />

        {FEATURE_SECTIONS.map((section) => (
          <section
            key={section.id}
            id={section.id}
            aria-labelledby={`${section.id}-heading`}
            className="scroll-mt-24 py-10"
          >
            <SectionHeading
              eyebrow={section.eyebrow}
              title={section.title}
              description={section.description}
              icon={SECTION_ICONS[section.id as keyof typeof SECTION_ICONS]}
            />
            <Reveal stagger className="mt-8">
              <div
                className={
                  section.items.length > 1
                    ? "grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
                    : "grid gap-4"
                }
              >
                {section.items.map((item) => (
                  <FeatureCard
                    key={item.title}
                    title={item.title}
                    body={item.body}
                    kbd={item.kbd}
                  />
                ))}
              </div>
            </Reveal>

            {section.id === "intelligence" ? (
              <Reveal className="mt-6">
                <div className="rounded-xl border border-accent bg-accent-soft p-5 text-sm leading-relaxed text-strong">
                  The local intelligence layer uses no LLM, no network, no screenshots, no clipboard
                  reading, and no keylogging. Identical input, context, and settings always produce
                  the same output — and every feature can be turned off.
                </div>
              </Reveal>
            ) : null}

            {section.id === "personalization" ? (
              <Reveal className="mt-6">
                <Card className="p-6">
                  <h3 className="text-base font-semibold text-strong">Examples</h3>
                  <ul className="mt-4 space-y-3">
                    {VOCABULARY_EXAMPLES.map((example) => (
                      <li
                        key={example.spoken}
                        className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm"
                      >
                        <span className="font-mono text-muted">“{example.spoken}”</span>
                        <span aria-hidden="true" className="text-accent">
                          →
                        </span>
                        <span className="font-mono text-strong">{example.written}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-4 text-sm leading-relaxed text-muted">
                    Entries are user-created only, stored locally, and never transmitted.
                  </p>
                </Card>
              </Reveal>
            ) : null}
          </section>
        ))}

        {/* Honest limitations */}
        <section aria-labelledby="limits-heading" className="scroll-mt-24 py-10">
          <SectionHeading
            eyebrow="Honesty"
            title="Where the limits are"
            description="Knowing what a tool doesn't do is as useful as knowing what it does."
          />
          <Reveal className="mt-8">
            <Card className="p-6">
              <ul className="space-y-4">
                {HONEST_LIMITATIONS.map((limitation) => (
                  <li key={limitation} className="flex gap-3 text-sm leading-relaxed text-body">
                    <span
                      aria-hidden="true"
                      className="mt-2 size-1.5 shrink-0 rounded-full bg-line-strong"
                    />
                    {limitation}
                  </li>
                ))}
              </ul>
            </Card>
          </Reveal>
        </section>

        <section aria-label="Continue" className="py-10">
          <Reveal>
            <div className="flex flex-wrap gap-3">
              <Button href="/privacy" variant="secondary">
                Read the privacy notes
              </Button>
              <Button href={site.repositoryUrl} variant="ghost">
                View source on GitHub
              </Button>
            </div>
          </Reveal>
        </section>
      </div>
    </>
  );
}
