import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SayItMark } from "@/components/SayItMark";

describe("SayItMark", () => {
  it("renders as an accessible image named after the product", () => {
    render(<SayItMark />);
    expect(screen.getByRole("img", { name: "SayIt" })).toBeInTheDocument();
  });

  it("draws in currentColor so it adapts to light/dark like the desktop icon", () => {
    const { container } = render(<SayItMark />);
    expect(container.querySelector("svg")).toHaveAttribute("fill", "currentColor");
  });

  it("can be marked decorative when adjacent visible text carries the name", () => {
    const { container } = render(<SayItMark title="" />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).not.toHaveAttribute("aria-label");
  });
});
