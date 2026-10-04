import type { ReactNode } from "react";
import { Card } from "./Card";

type PrivacyCardProps = {
  icon: ReactNode;
  title: string;
  body: string;
};

export function PrivacyCard({ icon, title, body }: PrivacyCardProps) {
  return (
    <Card className="card-glow h-full p-6">
      <span className="inline-flex size-9 items-center justify-center rounded-md bg-accent-soft text-accent">
        {icon}
      </span>
      <h3 className="mt-3 text-base font-semibold text-strong">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-muted">{body}</p>
    </Card>
  );
}
