import { site } from "@/lib/site";
import { ArrowRightIcon } from "./icons";

/**
 * Slim pre-release notice shown above the navbar on every page. It states a
 * verifiable fact (no public release exists yet) and links to the real
 * releases page — no launch-date promises, no counters.
 */
export function AnnouncementBar() {
  return (
    <div className="border-b border-line bg-subtle">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-center gap-x-3 gap-y-0.5 px-4 py-2 text-center text-xs sm:px-6 sm:text-sm lg:px-8">
        <p className="text-muted">Pre-release — installers appear with the first public release.</p>
        <a
          href={site.releasesUrl}
          className="inline-flex items-center gap-1 whitespace-nowrap font-medium text-accent-text hover:underline"
        >
          Watch releases
          <ArrowRightIcon size={12} />
        </a>
      </div>
    </div>
  );
}
