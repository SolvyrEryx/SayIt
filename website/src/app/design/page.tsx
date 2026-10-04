import type { Metadata } from "next";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { CommandBlock } from "@/components/CommandBlock";
import { Container } from "@/components/Container";
import { SectionHeading } from "@/components/SectionHeading";

export const metadata: Metadata = {
  title: "Design system",
  description:
    "Internal reference for the SayIt website design tokens and components. Not part of the public product pages.",
  robots: { index: false, follow: false },
};

const COLOR_TOKENS = [
  { name: "page", className: "bg-page", value: "#fbfcfb" },
  { name: "surface", className: "bg-surface", value: "#ffffff" },
  { name: "subtle", className: "bg-subtle", value: "#f1f4f3" },
  { name: "strong", className: "bg-strong", value: "#1f2422" },
  { name: "body", className: "bg-body", value: "#3d4441" },
  { name: "muted", className: "bg-muted", value: "#676f6c" },
  { name: "line", className: "bg-line", value: "#e4e8e6" },
  { name: "line-strong", className: "bg-line-strong", value: "#c9d1ce" },
  { name: "accent", className: "bg-accent", value: "#3b9c8c" },
  { name: "accent-hover", className: "bg-accent-hover", value: "#43a695" },
  { name: "accent-soft", className: "bg-accent-soft", value: "#e2f0ed" },
  { name: "accent-text", className: "bg-accent-text", value: "#2f7f72" },
  { name: "on-accent", className: "bg-on-accent", value: "#1f2422" },
  { name: "record", className: "bg-record", value: "#d9534f" },
  { name: "record-soft", className: "bg-record-soft", value: "#fbeceb" },
] as const;

const MOTION_TOKENS = [
  { name: "--motion-fast", value: "120ms", use: "Color/hover feedback on small controls" },
  { name: "--motion-base", value: "180ms", use: "Buttons, cards, panels" },
  { name: "--motion-slow", value: "280ms", use: "Section reveals, larger surfaces" },
  { name: "--motion-ease-soft", value: "cubic-bezier(0.22, 1, 0.36, 1)", use: "Default deceleration" },
  { name: "--motion-ease-spring", value: "cubic-bezier(0.34, 1.3, 0.64, 1)", use: "Gentle overshoot for press feedback" },
] as const;

const RADII = [
  { name: "rounded-sm", className: "rounded-sm", value: "6px" },
  { name: "rounded-md", className: "rounded-md", value: "8px — desktop control radius" },
  { name: "rounded-lg", className: "rounded-lg", value: "10px — desktop group radius" },
  { name: "rounded-xl", className: "rounded-xl", value: "14px — cards" },
] as const;

export default function DesignSystemPage() {
  return (
    <Container className="pb-16">
      <section className="py-14">
        <div className="reveal max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-wider text-accent-text">
            Stage H polish
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-strong sm:text-4xl">
            SayIt design system
          </h1>
          <p className="mt-4 text-base leading-relaxed text-muted">
            The tokens and primitives every SayIt page is built from. They mirror the desktop
            application&rsquo;s visual language: a quiet teal accent, near-black ink, soft radii,
            and short, purposeful motion. The calm red is reserved exclusively for the
            active-recording state, exactly as in the desktop app.
          </p>
        </div>
      </section>

      {/* Colors */}
      <section aria-labelledby="colors" className="py-10">
        <SectionHeading
          eyebrow="Tokens"
          title="Colors"
          description="Semantic tokens, defined once in globals.css. The site ships a single light theme by product decision — no system-theme switching."
        />
        <div
          id="colors"
          className="reveal-stagger mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4"
        >
          {COLOR_TOKENS.map((token) => (
            <Card key={token.name} className="overflow-hidden p-0">
              <div className={`h-14 border-b border-line ${token.className}`} />
              <div className="p-3">
                <p className="font-mono text-xs font-medium text-strong">--color-{token.name}</p>
                <p className="mt-0.5 font-mono text-[11px] text-muted">{token.value}</p>
              </div>
            </Card>
          ))}
        </div>
        <p className="mt-4 text-sm text-muted">
          One theme, one set of values — if a dark theme returns, it comes back behind an explicit
          user toggle, not the OS setting.
        </p>
      </section>

      {/* Typography */}
      <section aria-labelledby="typography" className="py-10">
        <SectionHeading
          eyebrow="Tokens"
          title="Typography"
          description="The system font stack — no webfonts, no extra bytes, and the same neutral voice as the desktop app."
        />
        <div id="typography" className="mt-8 space-y-4">
          <p className="text-4xl font-semibold tracking-tight text-strong sm:text-5xl">
            Headline — semibold, tight tracking
          </p>
          <p className="text-2xl font-semibold tracking-tight text-strong">
            Section title — 2xl semibold
          </p>
          <p className="text-base leading-relaxed text-body">
            Body text — 16px, relaxed leading. SayIt is a local push-to-talk voice-typing utility.
          </p>
          <p className="text-sm text-muted">Secondary text — 14px muted.</p>
          <p className="font-mono text-sm text-strong">
            Mono — hotkeys like Ctrl + Space and commands
          </p>
        </div>
      </section>

      {/* Radii & elevation */}
      <section aria-labelledby="shape" className="py-10">
        <SectionHeading
          eyebrow="Tokens"
          title="Radii & elevation"
          description="Radii follow the desktop stylesheet (8px controls, 10px groups). Two restrained shadow levels only."
        />
        <div id="shape" className="mt-8 grid gap-4 sm:grid-cols-2">
          <Card className="p-6">
            <h3 className="text-base font-semibold text-strong">Radii</h3>
            <div className="mt-4 space-y-3">
              {RADII.map((radius) => (
                <div key={radius.name} className="flex items-center gap-3">
                  <div className={`h-8 w-14 shrink-0 border border-line-strong bg-subtle ${radius.className}`} />
                  <div className="text-sm">
                    <span className="font-mono text-xs text-strong">{radius.name}</span>
                    <span className="ml-2 text-muted">{radius.value}</span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
          <Card className="p-6">
            <h3 className="text-base font-semibold text-strong">Elevation</h3>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <div className="rounded-lg border border-line bg-page p-4 text-center text-xs text-muted shadow-card">
                shadow-card
              </div>
              <div className="rounded-lg border border-line bg-page p-4 text-center text-xs text-muted shadow-lift">
                shadow-lift
              </div>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-muted">
              Shadows are soft and low-spread — elevation whispers, it never shouts.
            </p>
          </Card>
        </div>
      </section>

      {/* Motion */}
      <section aria-labelledby="motion" className="py-10">
        <SectionHeading
          eyebrow="Tokens"
          title="Motion"
          description="Short, purposeful, GPU-friendly. Only transform, color, and shadow animate — never layout. Try the demos: hover the card, press the button, and reload to see the staggered entrance."
        />
        <div id="motion" className="mt-8 grid gap-4 lg:grid-cols-2">
          <Card className="p-6">
            <h3 className="text-base font-semibold text-strong">Durations & easing</h3>
            <div className="mt-4 space-y-3 text-sm">
              {MOTION_TOKENS.map((token) => (
                <div key={token.name} className="border-b border-line pb-3 last:border-0 last:pb-0">
                  <p className="font-mono text-xs text-strong">
                    {token.name} = {token.value}
                  </p>
                  <p className="mt-0.5 text-xs text-muted">{token.use}</p>
                </div>
              ))}
            </div>
          </Card>
          <div className="space-y-4">
            <Card interactive className="p-6">
              <h3 className="text-base font-semibold text-strong">Hover lift (interactive card)</h3>
              <p className="mt-2 text-sm text-muted">
                Hover this card: it rises 2px with shadow-lift over 180ms.
              </p>
            </Card>
            <Card className="p-6">
              <h3 className="text-base font-semibold text-strong">Press feedback</h3>
              <p className="mt-2 text-sm text-muted">Press and hold the button below.</p>
              <div className="mt-4">
                <Button>Press me</Button>
              </div>
            </Card>
          </div>
        </div>
        <div className="mt-4 rounded-lg border border-line bg-subtle p-4 text-sm leading-relaxed text-muted">
          <strong className="font-semibold text-strong">Reduced motion:</strong> when the OS asks
          for <code className="font-mono text-xs text-strong">prefers-reduced-motion: reduce</code>,
          entrances render instantly, lifts and presses stop moving, and smooth scrolling is
          disabled — mirroring the desktop app&rsquo;s reduced-motion behavior. State feedback
          (focus rings, color changes) is preserved.
        </div>
      </section>

      {/* Buttons */}
      <section aria-labelledby="buttons" className="py-10">
        <SectionHeading
          eyebrow="Components"
          title="Buttons"
          description="One primitive, three variants. Buttons say what they do — no “Get started” ambiguity. Hover/pressed states are demonstrated live on each control."
        />
        <div id="buttons" className="mt-8 space-y-6">
          <Card className="p-6">
            <h3 className="text-base font-semibold text-strong">Variants & sizes</h3>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button size="lg">Primary large</Button>
              <Button>Primary</Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="ghost">Ghost</Button>
            </div>
          </Card>
          <Card className="p-6">
            <h3 className="text-base font-semibold text-strong">States</h3>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button disabled>Disabled</Button>
              <Button loading>Loading</Button>
              <Button href="#buttons" variant="secondary">
                Link button
              </Button>
            </div>
            <p className="mt-3 text-sm text-muted">
              The loading state disables the control and sets <code className="font-mono text-xs text-strong">aria-busy</code> —
              the site never fakes progress it does not control.
            </p>
          </Card>
        </div>
      </section>

      {/* Command block */}
      <section aria-labelledby="command-blocks" className="py-10">
        <SectionHeading
          eyebrow="Components"
          title="Command blocks"
          description="Exact, copyable, labeled. Placeholders are never shipped on production pages — this demo uses a harmless example command."
        />
        <div id="command-blocks" className="mt-8 max-w-xl">
          <CommandBlock label="Example (Windows PowerShell)" command="Get-ChildItem $env:LOCALAPPDATA" />
        </div>
      </section>

      {/* Accessibility */}
      <section aria-labelledby="accessibility" className="py-10">
        <SectionHeading
          eyebrow="Foundations"
          title="Accessibility"
          description="Baked in, not bolted on. Press Tab from here to see the focus treatment move through this page."
        />
        <div id="accessibility" className="mt-8 grid gap-4 sm:grid-cols-3">
          {[
            {
              title: "Visible focus",
              body: "One consistent 2px focus ring on every interactive element, offset from the control.",
            },
            {
              title: "Keyboard first",
              body: "A skip link is the first tab stop; navigation, buttons, and copy actions are all reachable and operable by keyboard.",
            },
            {
              title: "Semantic structure",
              body: "Landmarks, real headings, labeled navigation, and text (not color alone) carries meaning.",
            },
          ].map((item) => (
            <Card key={item.title} className="p-6">
              <h3 className="text-base font-semibold text-strong">{item.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{item.body}</p>
            </Card>
          ))}
        </div>
      </section>
    </Container>
  );
}
