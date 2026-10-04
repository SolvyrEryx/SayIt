import type { Metadata } from "next";
import { Container } from "@/components/Container";
import { HotkeyChip } from "@/components/HotkeyChip";
import { PageHero } from "@/components/PageHero";
import { PlatformTabs, type InstallTab } from "@/components/PlatformTabs";
import { Reveal } from "@/components/Reveal";
import { Callout, Steps } from "@/components/install-bits";
import { LinuxGuide, SourceGuide, WindowsGuide } from "@/components/install-guides";

export const metadata: Metadata = {
  title: "Install",
  description:
    "How to install SayIt on Windows or Linux — download, run, verify, and complete first-run setup. Source-install instructions for developers.",
  alternates: { canonical: "/install" },
};

const TABS: InstallTab[] = [
  { key: "windows", label: "Windows", content: <WindowsGuide /> },
  { key: "linux", label: "Linux", content: <LinuxGuide /> },
  { key: "source", label: "Source", content: <SourceGuide /> },
];

export default function InstallPage() {
  return (
    <Container className="pb-16">
      <PageHero
        eyebrow="Installation"
        title="Install SayIt"
        description="Pick your platform below — the guide for your system opens first. In short: download the installer, run it, follow the setup wizard, dictate. There is no account and no API key."
      />

      <Reveal>
        <PlatformTabs tabs={TABS} />
      </Reveal>

      {/* Shared first-run walkthrough (identical on Windows and Linux) */}
      <section id="first-run" aria-labelledby="first-run-heading" className="scroll-mt-20 pt-14">
        <h2 id="first-run-heading" className="text-2xl font-semibold tracking-tight text-strong">
          First-run setup
        </h2>
        <p className="mt-3 max-w-2xl text-base leading-relaxed text-muted">
          On first launch, the setup wizard walks you through everything. It states honestly what
          is and isn&rsquo;t ready — for example, it never fakes a transcription while no model is
          installed.
        </p>
        <Reveal className="mt-8">
          <Steps
            items={[
              <>
                <strong className="text-body">Welcome &amp; privacy</strong> — what SayIt does and a
                plain-language privacy summary.
              </>,
              <>
                <strong className="text-body">Microphone</strong> — select your input device and run
                the built-in signal test.
              </>,
              <>
                <strong className="text-body">Speech model</strong> — install a model now or finish
                setup and do it later. Model downloads are separate from the application and are
                roughly 100 MB to 1 GB depending on the model.
              </>,
              <>
                <strong className="text-body">Hotkey</strong> — choose the push-to-talk combination.
                The default is <HotkeyChip keys={["Ctrl", "Space"]} />.
              </>,
              <>
                <strong className="text-body">Try your first dictation</strong> — hold the hotkey,
                speak, release; the text appears at your cursor.{" "}
                <HotkeyChip keys={["Esc"]} /> cancels mid-dictation.
              </>,
              <>
                <strong className="text-body">Setup complete</strong> — a summary of what is ready
                and what remains (dictation stays unavailable until a model is installed).
              </>,
            ]}
          />
        </Reveal>
        <Callout title="One honest note">
          <p className="mt-1">
            You can complete the wizard without a model, but you can&rsquo;t dictate until one is
            installed — the app tells you so instead of pretending.
          </p>
        </Callout>
      </section>

      {/* Uninstall & data */}
      <section aria-labelledby="uninstall-heading" className="pt-14">
        <h2 id="uninstall-heading" className="text-2xl font-semibold tracking-tight text-strong">
          Uninstalling — and what happens to your data
        </h2>
        <Reveal className="mt-8 grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-line bg-surface p-6 shadow-card">
            <h3 className="text-base font-semibold text-strong">Windows</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              Uninstall from Settings → Apps → Installed apps → SayIt (a running instance is closed
              automatically). Your user data — settings, vocabulary, history, logs, and downloaded
              models in <code className="font-mono text-xs">%LOCALAPPDATA%\SayIt</code> — is{" "}
              <strong className="text-body">kept by default</strong>; the uninstaller asks before
              deleting it. For a full wipe at any time, use Clear Data in Settings → Privacy &amp;
              Data.
            </p>
          </div>
          <div className="rounded-xl border border-line bg-surface p-6 shadow-card">
            <h3 className="text-base font-semibold text-strong">Linux</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              Delete the AppImage file — that removes the application. Your settings and downloaded
              models are stored separately in your user directories and are not removed
              automatically; run Clear Data in the app first if you want them gone.
            </p>
          </div>
        </Reveal>
      </section>
    </Container>
  );
}
