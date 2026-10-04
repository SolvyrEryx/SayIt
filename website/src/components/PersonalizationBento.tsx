import type { ReactNode } from "react";
import { Card } from "./Card";
import {
  CheckIcon,
  PlusIcon,
  ShieldIcon,
  SlidersIcon,
  StackIcon,
  WaveIcon,
  WindowIcon,
} from "./icons";

/**
 * Personalization bento for the landing page. Every mock inside the cards is
 * decorative (aria-hidden) and illustrates a documented feature from
 * src/lib/features.ts; the card body carries the actual claim.
 */

const VOCAB_ROWS = [
  { spoken: "next js", written: "Next.js" },
  { spoken: "open ai", written: "OpenAI" },
  { spoken: "kubernetes", written: "Kubernetes" },
];

function BentoCard({
  title,
  body,
  icon,
  mock,
  className = "",
}: {
  title: string;
  body: string;
  icon: ReactNode;
  mock: ReactNode;
  className?: string;
}) {
  return (
    <Card className={`card-glow flex h-full flex-col p-6 ${className}`.trim()}>
      <span className="inline-flex size-9 items-center justify-center rounded-md bg-accent-soft text-accent">
        {icon}
      </span>
      <h3 className="mt-3 text-base font-semibold text-strong">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-muted">{body}</p>
      <div aria-hidden="true" className="mt-auto pt-5">
        {mock}
      </div>
    </Card>
  );
}

const chip = "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs";

export function PersonalizationBento() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <BentoCard
        className="lg:col-span-2"
        title="Custom vocabulary"
        body="Spoken-form → written-form mappings you create yourself — case-insensitive, multi-word, longest-match first. Entries exist only because you added them; each one can be edited or switched off."
        icon={<SlidersIcon size={18} />}
        mock={
          <div className="rounded-lg border border-line bg-subtle p-3 font-mono text-sm">
            {VOCAB_ROWS.map((row) => (
              <div
                key={row.spoken}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line py-2 last:border-b-0"
              >
                <span className="text-body">“{row.spoken}”</span>
                <span className="text-muted">→</span>
                <span className="font-semibold text-strong">{row.written}</span>
                <span
                  className={`${chip} ml-auto border-accent bg-accent-soft text-accent-text`}
                >
                  On
                </span>
              </div>
            ))}
            <span className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-dashed border-line-strong px-3 py-1.5 text-xs text-muted">
              <PlusIcon size={12} /> Add entry
            </span>
          </div>
        }
      />

      <BentoCard
        title="Snippets"
        body="Say a trigger to insert a saved block of text. Snippets are text only — content like git pull is inserted as literal text and never executed."
        icon={<StackIcon size={18} />}
        mock={
          <div className="rounded-lg border border-line bg-subtle p-3 text-sm">
            <span className={`${chip} border-line-strong bg-surface font-mono text-strong`}>
              “my email”
            </span>
            <span className="mx-2 text-muted">→</span>
            <span className="font-mono text-body">you@example.com</span>
          </div>
        }
      />

      <BentoCard
        title="Voice edit"
        body="Spoken corrections — “scratch that”, “replace five with six”, “delete the last sentence” — are applied by deterministic local rules. Ambiguous phrases stay ordinary text."
        icon={<WaveIcon size={18} />}
        mock={
          <p className="rounded-lg border border-line bg-subtle p-3 text-sm text-strong">
            I&apos;ll arrive at <s className="text-muted">five. Actually</s> six.
          </p>
        }
      />

      <BentoCard
        title="Developer mode"
        body="Casing commands on demand — camel, snake, kebab, pascal — plus a spoken code-block wrapper, for talking to your editor in its own dialect."
        icon={<WindowIcon size={18} />}
        mock={
          <p className="rounded-lg border border-line bg-subtle p-3 font-mono text-sm text-body">
            get user by id, camel case{" "}
            <span className="text-muted">→</span>{" "}
            <span className="font-semibold text-strong">getUserById</span>
          </p>
        }
      />

      <BentoCard
        title="Safe zones"
        body="Designate protected applications — password managers, banking — where recording is blocked before any audio is captured."
        icon={<ShieldIcon size={18} />}
        mock={
          <div className="flex items-center gap-2 rounded-lg border border-line bg-subtle p-3 text-sm">
            <span className="text-accent">
              <ShieldIcon size={16} />
            </span>
            <span className="font-medium text-strong">Password manager</span>
            <span className={`${chip} ml-auto border-accent bg-accent-soft text-accent-text`}>
              Recording blocked
            </span>
          </div>
        }
      />

      <BentoCard
        className="lg:col-span-2"
        title="Remember corrections"
        body="Fix a transcript and SayIt can offer to remember it. Only an explicit “Remember” creates a rule — there is no silent learning, ever."
        icon={<CheckIcon size={18} />}
        mock={
          <div className="rounded-lg border border-line bg-subtle p-3 text-sm">
            <span className="text-body">
              You corrected <span className="font-mono text-body">“gethub”</span> to{" "}
              <span className="font-mono font-semibold text-strong">“GitHub”</span>
            </span>
            <span className="mt-3 flex flex-wrap gap-2">
              <span className="rounded-lg border border-accent bg-accent px-3 py-1 text-xs font-medium text-on-accent">
                Remember
              </span>
              <span className="rounded-lg border border-line-strong bg-surface px-3 py-1 text-xs font-medium text-body">
                Not now
              </span>
            </span>
          </div>
        }
      />

      <BentoCard
        title="Switch off anything"
        body="Every local rule can be disabled, and identical input, context, and settings always produce identical output. The behavior is a choice, not a black box."
        icon={<SlidersIcon size={18} />}
        mock={
          <div className="flex flex-wrap gap-2 rounded-lg border border-line bg-subtle p-3 text-xs">
            <span className={`${chip} border-accent bg-accent-soft text-accent-text`}>
              Technical correction — On
            </span>
            <span className={`${chip} border-line-strong bg-surface text-muted`}>
              Developer mode — Off
            </span>
          </div>
        }
      />
    </div>
  );
}
