import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Button } from "@/components/Button";

describe("Button", () => {
  it("renders as a link when href is provided", () => {
    render(<Button href="/design">Design system</Button>);
    const link = screen.getByRole("link", { name: "Design system" });
    expect(link).toHaveAttribute("href", "/design");
  });

  it("routes internal paths through next/link for client navigation and basePath", () => {
    render(<Button href="/download">Download</Button>);
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute(
      "data-next-link",
      "true",
    );
  });

  it("keeps external URLs and hash anchors as plain anchors", () => {
    render(
      <>
        <Button href="https://github.com/VptrCipher/SayIt">GitHub</Button>
        <Button href="#how-it-works">How it works</Button>
      </>,
    );
    for (const name of ["GitHub", "How it works"]) {
      expect(screen.getByRole("link", { name })).not.toHaveAttribute("data-next-link");
    }
  });

  it("defaults to type=button so it never submits a form implicitly", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("type", "button");
  });

  it("exposes a disabled state", () => {
    render(<Button disabled>Download</Button>);
    expect(screen.getByRole("button", { name: "Download" })).toBeDisabled();
  });

  it("disables the control and marks it busy while loading", () => {
    render(<Button loading>Download</Button>);
    const button = screen.getByRole("button", { name: "Download" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });
});
