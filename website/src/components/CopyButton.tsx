"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Status = "idle" | "copied" | "failed";

async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the legacy path
  }
  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand("copy");
    textarea.remove();
    return ok;
  } catch {
    return false;
  }
}

type CopyButtonProps = {
  text: string;
  label?: string;
};

/**
 * Copies the given text and shows the honest outcome: "Copied" or
 * "Copy failed". No fabricated success states.
 */
export function CopyButton({ text, label = "Copy" }: CopyButtonProps) {
  const [status, setStatus] = useState<Status>("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const handleCopy = useCallback(async () => {
    const ok = await copyText(text);
    setStatus(ok ? "copied" : "failed");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setStatus("idle"), 1600);
  }, [text]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex h-8 shrink-0 items-center rounded-md border border-line-strong bg-surface px-3 text-xs font-medium text-body transition-colors duration-[var(--motion-fast)] ease-soft hover:border-accent hover:text-strong"
    >
      {status === "copied" ? "Copied" : status === "failed" ? "Copy failed" : label}
      <span aria-hidden="true" className="ml-1.5 w-3 text-accent">
        {status === "copied" ? "✓" : ""}
      </span>
    </button>
  );
}
