type PageHeroProps = {
  eyebrow: string;
  title: string;
  description: string;
};

/**
 * Consistent header block for interior pages. Carries the landing page's
 * depth language into every tab: a soft aurora blob, a blur-in entrance, and
 * a gradient underline that grows under the title (scroll-driven where the
 * browser supports it). Pure CSS — no JavaScript.
 */
export function PageHero({ eyebrow, title, description }: PageHeroProps) {
  return (
    <section className="relative isolate overflow-hidden py-14">
      <div
        aria-hidden="true"
        className="aurora-blob -right-16 -top-16 size-56 bg-accent/10 sm:size-72"
      />
      <div className="reveal-lux relative max-w-2xl">
        <p className="text-sm font-semibold uppercase tracking-wider text-accent-text">
          {eyebrow}
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-strong sm:text-4xl">
          {title}
        </h1>
        <span
          aria-hidden="true"
          className="section-underline mt-4 block h-[3px] w-24 origin-left rounded-full"
        />
        <p className="mt-4 text-base leading-relaxed text-muted">{description}</p>
      </div>
    </section>
  );
}
