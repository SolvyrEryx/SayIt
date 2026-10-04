/**
 * Decorative marquee ribbon of the *kinds of places* SayIt types into —
 * generic categories, not product-integration claims. Two identical copies
 * scroll seamlessly (the track translates exactly one copy width); it pauses
 * on hover and collapses to a static row under reduced motion. Entirely
 * decorative: aria-hidden, with the caption carrying the meaning.
 */

const ITEMS = [
  "Code editors",
  "Terminals",
  "Email",
  "Chat",
  "Issue trackers",
  "Notes",
  "Docs",
  "CRMs",
  "Search boxes",
  "Forms",
];

export function Marquee() {
  return (
    <div className="py-2">
      <p className="text-center text-sm text-muted">
        Wherever words happen
      </p>
      <div aria-hidden="true" className="marquee mt-4">
        <div className="marquee-track">
          {[0, 1].map((copy) => (
            <div key={copy} className="flex shrink-0 items-center">
              {ITEMS.map((item) => (
                <span key={item} className="flex items-center">
                  <span className="whitespace-nowrap text-sm font-medium text-body">
                    {item}
                  </span>
                  <span className="mx-8 size-1 rounded-full bg-accent/50" />
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
