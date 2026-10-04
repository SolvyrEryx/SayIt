import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import DesignSystemPage from "@/app/design/page";

describe("Design system page", () => {
  it("renders the core token sections", () => {
    render(<DesignSystemPage />);
    expect(screen.getByRole("heading", { name: "Colors" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Typography" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Motion" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Buttons" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Accessibility" })).toBeInTheDocument();
  });

  it("documents the reduced-motion contract", () => {
    render(<DesignSystemPage />);
    expect(screen.getAllByText(/prefers-reduced-motion/i).length).toBeGreaterThan(0);
  });

  it("does not display a version number — none has been released", () => {
    const { container } = render(<DesignSystemPage />);
    expect(container.textContent).not.toMatch(/v?\d+\.\d+\.\d+/);
  });
});
