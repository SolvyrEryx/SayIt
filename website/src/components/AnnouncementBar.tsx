import Link from "next/link";
import { ArrowRightIcon } from "./icons";

/**
 * Slim release notice shown above the navbar on every page.
 * The release page remains the authoritative source for published artifacts.
 */
export function AnnouncementBar() {
  return (
    <div className="border-b border-line bg-subtle">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-center gap-x-3 gap-y-0.5 px-4 py-2 text-center text-xs sm:px-6 sm:text-sm lg:px-8">
        <p className="text-muted">The latest SayIt release is live for Windows and Linux.</p>
        <Link
          href="/download"
          className="inline-flex items-center gap-1 whitespace-nowrap font-medium text-accent-text hover:underline"
        >
          Download SayIt
          <ArrowRightIcon size={12} />
        </Link>
      </div>
    </div>
  );
}
