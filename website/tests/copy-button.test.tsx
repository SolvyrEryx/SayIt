import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CopyButton } from "@/components/CopyButton";

describe("CopyButton", () => {
  it("copies via the async clipboard and confirms honestly", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    render(<CopyButton text="SayIt-Setup-x64.exe" />);

    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Copied/ })).toBeInTheDocument();
    });
    expect(writeText).toHaveBeenCalledWith("SayIt-Setup-x64.exe");
  });

  it("reports failure instead of faking success when copying is unavailable", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
    });
    const execCommand = vi.fn().mockReturnValue(false);
    (document as unknown as { execCommand: unknown }).execCommand = execCommand;

    render(<CopyButton text="hello" />);

    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Copy failed/ })).toBeInTheDocument();
    });
    expect(execCommand).toHaveBeenCalledWith("copy");
  });
});
