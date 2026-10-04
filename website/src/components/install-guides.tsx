import Link from "next/link";
import { Callout, Steps, Troubleshooting, type TroubleshootingItem } from "./install-bits";
import { CommandBlock } from "./CommandBlock";
import { site } from "@/lib/site";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-10 first:mt-0">
      <h3 className="text-lg font-semibold text-strong">{title}</h3>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Requirements({ items }: { items: string[] }) {
  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <li key={item} className="flex gap-2.5 text-sm leading-relaxed text-body">
          <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-accent" />
          {item}
        </li>
      ))}
    </ul>
  );
}

const WINDOWS_TROUBLESHOOTING: TroubleshootingItem[] = [
  {
    question: "Windows SmartScreen shows “Windows protected your PC”",
    answer: (
      <>
        The installer is not code-signed yet, so Windows shows this warning for new downloads.
        Choose <strong className="text-body">More info</strong> →{" "}
        <strong className="text-body">Run anyway</strong> — but only because you downloaded the
        installer from the official releases page. The site does not claim any signing
        verification, and you can check the SHA-256 checksum against the value shown on the
        download page.
      </>
    ),
  },
  {
    question: "The microphone is not detected",
    answer: (
      <>
        Check the input device selection in the setup wizard or in Settings → Configuration, and
        verify Windows microphone permissions for SayIt. Use the built-in microphone test to
        confirm a signal.
      </>
    ),
  },
  {
    question: "The model download fails or is slow",
    answer: (
      <>
        The first model download needs network access and can be roughly 100 MB to 1 GB depending
        on the model. It is stored under <code className="font-mono text-xs">%LOCALAPPDATA%
        \SayIt\models</code> and is only downloaded once per model.
      </>
    ),
  },
  {
    question: "The hotkey does nothing in some apps",
    answer: (
      <>
        Some applications intercept or block global shortcuts. Try a different combination in
        Settings → Configuration — no single hotkey works in every application on Windows.
      </>
    ),
  },
  {
    question: "Text is not inserted after dictation",
    answer: (
      <>
        Insertion requires a focused editable text field in the active app. If a paste fails, the
        transcript stays recoverable — the app shows an error state instead of silently losing the
        text, and the last transcript remains on the clipboard.
      </>
    ),
  },
  {
    question: "SayIt seems stuck on recording or processing",
    answer: (
      <>
        Press <strong className="text-body">Esc</strong> to cancel the active dictation. If the
        tray icon stays unresponsive, quit from the tray menu and relaunch.
      </>
    ),
  },
];

const LINUX_TROUBLESHOOTING: TroubleshootingItem[] = [
  {
    question: "Running the AppImage says “Permission denied”",
    answer: (
      <>
        The executable bit is not set (or was lost when the file was moved by an unzipping tool).
        Run <code className="font-mono text-xs">chmod +x SayIt-*.AppImage</code> again, then start
        it with <code className="font-mono text-xs">./SayIt-*.AppImage</code>.
      </>
    ),
  },
  {
    question: "Text is not inserted (clipboard issues)",
    answer: (
      <>
        Clipboard operations require <code className="font-mono text-xs">xclip</code>. Install it
        with your distribution&rsquo;s package manager (for example{" "}
        <code className="font-mono text-xs">sudo apt install xclip</code> on Debian/Ubuntu).
      </>
    ),
  },
  {
    question: "The global hotkey does not respond",
    answer: (
      <>
        Global hotkey capture may require X11 and may not work under Wayland. This is a known
        limitation of the current Linux support, not a misconfiguration on your side.
      </>
    ),
  },
  {
    question: "The model download fails",
    answer: (
      <>
        Model downloads need network access; weights are fetched from the upstream Sherpa-ONNX
        releases and stored locally. Retry from the setup wizard or Settings once connectivity is
        restored.
      </>
    ),
  },
];

export function WindowsGuide() {
  return (
    <div>
      <Section title="Requirements">
        <Requirements
          items={[
            "Windows 10 or later, 64-bit",
            "A working microphone",
            "Network access for the first model download (roughly 100 MB to 1 GB depending on the model)",
          ]}
        />
      </Section>

      <Section title="Download">
        <p className="text-sm leading-relaxed text-body">
          Get <code className="font-mono text-xs">SayIt-Setup-x64.exe</code> from the{" "}
          <Link
            className="font-medium text-strong underline decoration-line-strong underline-offset-2 hover:text-accent-text"
            href="/download"
          >
            download center
          </Link>{" "}
          or the{" "}
          <a
            className="font-medium text-strong underline decoration-line-strong underline-offset-2 hover:text-accent-text"
            href={site.releasesUrl}
          >
            GitHub Releases
          </a>{" "}
          page. Verify the SHA-256 checksum shown with the release before running it.
        </p>
      </Section>

      <Section title="Install">
        <Steps
          items={[
            <>
              Run the installer. It installs <strong className="text-body">only for your user</strong>{" "}
              (no administrator prompt needed), into{" "}
              <code className="font-mono text-xs">%LOCALAPPDATA%\Programs\SayIt</code>.
            </>,
            <>
              Optional tasks: a desktop shortcut and &ldquo;Start SayIt when Windows starts&rdquo;
              — both are off by default. A Start Menu entry is always created.
            </>,
            <>
              Leave <strong className="text-body">Launch SayIt</strong> checked on the final screen
              (or start it from the Start Menu later).
            </>,
          ]}
        />
        <Callout tone="warn" title="About the SmartScreen warning">
          <p>
            The installer is not code-signed yet. If Windows shows &ldquo;Windows protected your
            PC&rdquo;, choose More info → Run anyway — after confirming you downloaded it from the
            official release and checked the checksum.
          </p>
        </Callout>
        <Callout title="Automated installs">
          <p>
            The installer is a standard Inno Setup package and accepts the usual silent flags
            (<code className="font-mono text-xs">/SILENT</code>,{" "}
            <code className="font-mono text-xs">/VERYSILENT</code>) for unattended deployment.
          </p>
        </Callout>
      </Section>

      <Section title="First launch & verification">
        <p className="text-sm leading-relaxed text-body">
          SayIt runs in the <strong className="text-body">system tray</strong>. On first start, the
          setup wizard opens — that window <em>is</em> the verification that the install worked.
          SayIt has no command-line version flag; success looks like: tray icon visible, wizard
          open, and a first dictation inserting text (after the model is installed). Continue with
          the{" "}
          <a
            className="font-medium text-strong underline decoration-line-strong underline-offset-2 hover:text-accent-text"
            href="#first-run"
          >
            first-run setup
          </a>{" "}
          below.
        </p>
      </Section>

      <Section title="Troubleshooting">
        <Troubleshooting items={WINDOWS_TROUBLESHOOTING} />
      </Section>
    </div>
  );
}

export function LinuxGuide() {
  return (
    <div>
      <Section title="Requirements">
        <Requirements
          items={[
            "A 64-bit Linux distribution with glibc 2.28 or newer (e.g. Ubuntu 20.04+) — the AppImage is built against manylinux_2_28",
            "xclip for clipboard-based text insertion",
            "A working microphone; network access for the first model download",
            "X11 session for global hotkeys (Wayland capture is a known limitation)",
          ]}
        />
      </Section>

      <Section title="Download">
        <p className="text-sm leading-relaxed text-body">
          Get the <code className="font-mono text-xs">SayIt-*.AppImage</code> from the{" "}
          <Link
            className="font-medium text-strong underline decoration-line-strong underline-offset-2 hover:text-accent-text"
            href="/download"
          >
            download center
          </Link>{" "}
          or the{" "}
          <a
            className="font-medium text-strong underline decoration-line-strong underline-offset-2 hover:text-accent-text"
            href={site.releasesUrl}
          >
            GitHub Releases
          </a>{" "}
          page, and verify its SHA-256 checksum.
        </p>
      </Section>

      <Section title="Make it executable and run">
        <Steps
          items={[
            <>
              Make the AppImage executable:
              <CommandBlock className="mt-2" label="Linux shell" command="chmod +x SayIt-*.AppImage" />
            </>,
            <>
              Start SayIt:
              <CommandBlock className="mt-2" label="Linux shell" command="./SayIt-*.AppImage" />
            </>,
            <>
              Optional: keep the AppImage somewhere stable such as{" "}
              <code className="font-mono text-xs">~/Applications</code>. SayIt does not install
              desktop integration automatically; it lives where you put it.
            </>,
          ]}
        />
      </Section>

      <Section title="First launch & verification">
        <p className="text-sm leading-relaxed text-body">
          SayIt runs in the <strong className="text-body">system tray</strong>, and the setup wizard
          opens on first start — seeing that wizard verifies the AppImage works. Note the honest
          limits: global hotkeys may require X11, and clipboard insertion needs{" "}
          <code className="font-mono text-xs">xclip</code>. Continue with the{" "}
          <a
            className="font-medium text-strong underline decoration-line-strong underline-offset-2 hover:text-accent-text"
            href="#first-run"
          >
            first-run setup
          </a>{" "}
          below.
        </p>
      </Section>

      <Section title="Troubleshooting">
        <Troubleshooting items={LINUX_TROUBLESHOOTING} />
      </Section>
    </div>
  );
}

export function SourceGuide() {
  return (
    <div>
      <Callout tone="warn" title="Developer / source install">
        <p>
          This route is for development and contribution. Regular users don&rsquo;t need any of it
          — use the Windows installer or the Linux AppImage.
        </p>
      </Callout>

      <Section title="Requirements">
        <Requirements
          items={[
            "Python 3.12 or newer",
            "The uv package manager",
            "Git",
            "Network access for the first model download",
          ]}
        />
      </Section>

      <Section title="Clone and sync">
        <Steps
          items={[
            <>
              Clone the repository:
              <CommandBlock
                className="mt-2"
                label="Shell"
                command={`git clone ${site.repositoryUrl}.git`}
              />
            </>,
            <>
              Create the virtual environment and install dependencies:
              <CommandBlock className="mt-2" label="Shell" command="cd SayIt && uv sync" />
            </>,
          ]}
        />
      </Section>

      <Section title="Run">
        <CommandBlock label="Shell" command="uv run python -m sayit" />
        <Callout title="Why python -m?">
          <p className="mt-1">
            The <code className="font-mono text-xs">sayit</code> entry points declared in{" "}
            <code className="font-mono text-xs">pyproject.toml</code> are not installed into the
            environment by <code className="font-mono text-xs">uv sync</code> — run the app as a
            module.
          </p>
        </Callout>
      </Section>

      <Section title="Run the tests">
        <CommandBlock
          label="Windows PowerShell"
          command={`$env:QT_QPA_PLATFORM = "offscreen"\n$env:PYNPUT_BACKEND = "dummy"\nuv run pytest -m "not slow"`}
        />
        <p className="mt-3 text-sm text-muted">The same suite on Linux/macOS:</p>
        <CommandBlock
          className="mt-2"
          label="bash"
          command={`QT_QPA_PLATFORM=offscreen PYNPUT_BACKEND=dummy uv run pytest -m "not slow"`}
        />
      </Section>

      <Section title="Verification">
        <p className="text-sm leading-relaxed text-body">
          <code className="font-mono text-xs">uv run python -m sayit</code> starts the tray
          app and opens the setup wizard on first run — that is the check. A passing fast test
          suite verifies the code, not the packaged app.
        </p>
      </Section>
    </div>
  );
}
