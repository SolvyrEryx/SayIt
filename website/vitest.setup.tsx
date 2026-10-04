import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";
import type { ReactNode } from "react";

// next/link requires the app-router runtime context, which plain component
// renders in vitest don't provide. Stand in a plain anchor that marks itself
// so tests can tell Link-rendered anchors from raw ones. Client-side routing
// and basePath prefixing are verified against production builds instead.
vi.mock("next/link", () => ({
  default: ({ children, ...rest }: { children?: ReactNode } & Record<string, unknown>) => (
    <a data-next-link="true" {...rest}>
      {children}
    </a>
  ),
}));
