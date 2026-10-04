import type { Metadata } from "next";
import { Container } from "@/components/Container";
import { DownloadCenter } from "@/components/DownloadCenter";
import { PageHero } from "@/components/PageHero";
import { Reveal } from "@/components/Reveal";

export const metadata: Metadata = {
  title: "Download",
  description:
    "Download SayIt for Windows and Linux — official installers with SHA-256 checksums, straight from the release. No account, no API key, no telemetry.",
  alternates: { canonical: "/download" },
};

export default function DownloadPage() {
  return (
    <Container className="pb-16">
      <PageHero
        eyebrow="Download"
        title="Download SayIt"
        description="Free and open source. No account, no signup, and no API key — downloads come straight from the official release. Pick your platform below; we highlight the one your browser is running on."
      />

      <Reveal>
        <DownloadCenter />
      </Reveal>

      <section aria-labelledby="download-faq" className="py-12">
        <Reveal>
          <div className="rounded-xl border border-line bg-subtle p-6 text-sm leading-relaxed text-muted sm:p-8">
            <h2 id="download-faq" className="text-base font-semibold text-strong">
              What the installer includes — and what it doesn&rsquo;t
            </h2>
            <p className="mt-2">
              The SayIt installer is self-contained: it bundles the application and its runtime, so
              you don&rsquo;t need Python, a terminal, or a development environment.{" "}
              <strong className="font-semibold text-body">
                Speech models are not bundled
              </strong>{" "}
              — the app downloads the model you choose on first use (roughly 100 MB to 1 GB
              depending on the model). Uninstalling never silently deletes your settings or
              downloaded models; you are asked first.
            </p>
          </div>
        </Reveal>
      </section>
    </Container>
  );
}
