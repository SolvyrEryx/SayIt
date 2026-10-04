import type { ReactNode } from "react";
import { Card } from "./Card";
import { HotkeyChip } from "./HotkeyChip";

type FeatureCardProps = {
  title: string;
  body: string;
  /** Optional keyboard combination shown with the feature. */
  kbd?: string[];
  /** Optional small icon badge. */
  icon?: ReactNode;
  className?: string;
};

export function FeatureCard({ title, body, kbd, icon, className = "" }: FeatureCardProps) {
  return (
    <Card className={`card-glow flex h-full flex-col p-6 ${className}`.trim()}>
      {icon ? (
        <span className="mb-3 inline-flex size-9 items-center justify-center rounded-md bg-accent-soft text-accent">
          {icon}
        </span>
      ) : null}
      <h3 className="text-base font-semibold text-strong">{title}</h3>
      <p className="mt-2 flex-1 text-sm leading-relaxed text-muted">{body}</p>
      {kbd ? <HotkeyChip keys={kbd} className="mt-4" /> : null}
    </Card>
  );
}
