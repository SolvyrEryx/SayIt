type PageHeroProps = {
  eyebrow: string;
  title: string;
  description: string;
};

/** Consistent header block for interior pages. Pure-CSS entrance. */
export function PageHero({ eyebrow, title, description }: PageHeroProps) {
  return (
    <section className="py-14">
      <div className="reveal max-w-2xl">
        <p className="text-sm font-semibold uppercase tracking-wider text-accent-text">{eyebrow}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-strong sm:text-4xl">
          {title}
        </h1>
        <p className="mt-4 text-base leading-relaxed text-muted">{description}</p>
      </div>
    </section>
  );
}
