import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import FeaturesPage from "@/app/features/page";
import { site } from "@/lib/site";

describe("Features page", () => {
  it("renders all feature sections from the content data", () => {
    render(<FeaturesPage />);
    for (const heading of [
      "Voice dictation",
      "Context awareness",
      "Local intelligence",
      "Personalization",
      "Where the limits are",
    ]) {
      expect(screen.getByRole("heading", { level: 2, name: heading })).toBeInTheDocument();
    }
  });

  it("lists only implemented functionality with the default hotkey", () => {
    render(<FeaturesPage />);
    expect(screen.getByText("Push-to-talk recording")).toBeInTheDocument();
    expect(screen.getByLabelText("Ctrl plus Space")).toBeInTheDocument();
    expect(screen.getByText("Safe zones")).toBeInTheDocument();
    expect(screen.getByText("Remember corrections")).toBeInTheDocument();
    expect(screen.getByText("Custom vocabulary")).toBeInTheDocument();
  });

  it("documents the determinism boundaries of the intelligence layer", () => {
    render(<FeaturesPage />);
    expect(screen.getByText(/no LLM, no network/i)).toBeInTheDocument();
    expect(screen.getByText(/never executed/i)).toBeInTheDocument();
  });

  it("shows the honest limitations section with real caveats", () => {
    render(<FeaturesPage />);
    expect(screen.getByText(/not a streaming dictation system/i)).toBeInTheDocument();
    expect(screen.getByText(/may not work under Wayland/i)).toBeInTheDocument();
    expect(screen.getByText(/no fixed numbers are claimed/i)).toBeInTheDocument();
  });

  it("links onward to privacy and the repository", () => {
    render(<FeaturesPage />);
    expect(screen.getByRole("link", { name: /read the privacy notes/i })).toHaveAttribute(
      "href",
      "/privacy",
    );
    expect(screen.getByRole("link", { name: /view source on github/i })).toHaveAttribute(
      "href",
      site.repositoryUrl,
    );
  });
});
