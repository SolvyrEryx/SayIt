import type { Metadata, Viewport } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { AmbientField } from "@/components/AmbientField";
import { AnnouncementBar } from "@/components/AnnouncementBar";
import { CardGlowCursor } from "@/components/CardGlowCursor";
import { Footer } from "@/components/Footer";
import { Navbar } from "@/components/Navbar";
import { PageGlow } from "@/components/PageGlow";
import { ScrollProgress } from "@/components/ScrollProgress";
import { SkipLink } from "@/components/SkipLink";
import { baseMetadata } from "@/lib/base-metadata";

// Self-hosted at build time (no third-party runtime requests): Inter carries
// body text and UI; Space Grotesk gives headings a distinct technical voice.
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const grotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-grotesk",
  display: "swap",
});

export const metadata: Metadata = baseMetadata;

export const viewport: Viewport = {
  themeColor: "#f5f1e8",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${grotesk.variable}`}>
      <body className="flex min-h-dvh flex-col bg-page text-body">
        <PageGlow />
        <AmbientField />
        <ScrollProgress />
        <CardGlowCursor />
        <SkipLink />
        <AnnouncementBar />
        <Navbar />
        <main id="main" className="flex-1">
          {children}
        </main>
        <Footer />
      </body>
    </html>
  );
}
