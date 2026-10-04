import Link from "next/link";
import { Container } from "./Container";
import { SayItLogo } from "./SayItLogo";
import { site } from "@/lib/site";

export function Footer() {
  return (
    <footer className="mt-16 border-t border-line">
      <Container>
        <div className="flex flex-col gap-8 py-10 sm:flex-row sm:justify-between">
          <div className="max-w-sm">
            {/* PRIMARY LOGO (brand sheet), small size */}
            <SayItLogo size={20} />
            <p className="mt-3 text-sm leading-relaxed text-muted">
              Local push-to-talk voice typing for Windows and Linux. Hold a hotkey, speak, release —
              the text appears at your cursor.
            </p>
            <p className="mt-3 text-xs leading-relaxed text-muted">
              No account. No tracking. No API key needed for core dictation.
            </p>
          </div>
          <nav aria-label="Footer" className="grid grid-cols-2 gap-8 text-sm sm:gap-16">
            <ul className="space-y-2.5">
              <li>
                <Link href="/download" className="text-body hover:text-strong">
                  Download
                </Link>
              </li>
              <li>
                <Link href="/install" className="text-body hover:text-strong">
                  Install
                </Link>
              </li>
              <li>
                <Link href="/features" className="text-body hover:text-strong">
                  Features
                </Link>
              </li>
              <li>
                <Link href="/privacy" className="text-body hover:text-strong">
                  Privacy
                </Link>
              </li>
            </ul>
            <ul className="space-y-2.5">
              <li>
                <a href={site.repositoryUrl} className="text-body hover:text-strong">
                  GitHub repository
                </a>
              </li>
              <li>
                <a href={site.releasesUrl} className="text-body hover:text-strong">
                  Releases
                </a>
              </li>
              <li>
                <a href={site.issuesUrl} className="text-body hover:text-strong">
                  Issues
                </a>
              </li>
            </ul>
          </nav>
        </div>
        <div className="border-t border-line py-6 text-xs leading-relaxed text-muted">
          <p>
            SayIt is released under the MIT License. Optional LLM enhancement is a separate,
            off-by-default feature; core dictation runs locally on your device.
          </p>
          <p className="mt-1">
            SayIt is the product name, package, and application identity.
          </p>
        </div>
      </Container>
    </footer>
  );
}
