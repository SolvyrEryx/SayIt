import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import PrivacyPage from "@/app/privacy/page";
import { site } from "@/lib/site";

describe("Privacy page", () => {
  it("renders the core privacy facts", () => {
    render(<PrivacyPage />);
    for (const title of [
      "Recognition runs locally",
      "No account. No API key.",
      "Enhancement is optional and off by default",
      "Context detection reads metadata only",
      "Learning is explicit",
      "Safe zones",
      "History is off by default",
      "Network access, honestly",
    ]) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
  });

  it("states exactly what context detection does not do", () => {
    render(<PrivacyPage />);
    expect(screen.getByText(/never takes screenshots/i)).toBeInTheDocument();
    expect(screen.getByText(/logs keystrokes/i)).toBeInTheDocument();
  });

  it("describes the optional enhancement honestly, including the network case", () => {
    render(<PrivacyPage />);
    expect(screen.getByText(/transcript text \(never audio\) is sent/i)).toBeInTheDocument();
  });

  it("mentions Clear Data and what it removes", () => {
    render(<PrivacyPage />);
    expect(screen.getByText(/clear data removes settings, history, logs, and downloaded models/i)).toBeInTheDocument();
  });

  it("declines absolute privacy/offline promises", () => {
    render(<PrivacyPage />);
    expect(screen.getByText(/doesn.t promise a completely private/i)).toBeInTheDocument();
  });

  it("links onward to features and the repository", () => {
    render(<PrivacyPage />);
    expect(screen.getByRole("link", { name: /see what sayit does/i })).toHaveAttribute(
      "href",
      "/features",
    );
    expect(screen.getByRole("link", { name: /view source on github/i })).toHaveAttribute(
      "href",
      site.repositoryUrl,
    );
  });
});
