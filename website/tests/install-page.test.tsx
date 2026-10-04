import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import InstallPage from "@/app/install/page";
import { PlatformTabs, preferredInstallTab, type InstallTab } from "@/components/PlatformTabs";
import { site } from "@/lib/site";

const TABS: InstallTab[] = [
  { key: "windows", label: "Windows", content: <p>Windows guide content</p> },
  { key: "linux", label: "Linux", content: <p>Linux guide content</p> },
  { key: "source", label: "Source", content: <p>Source guide content</p> },
];

describe("preferredInstallTab", () => {
  it("maps detected platforms to the guide shown first", () => {
    expect(preferredInstallTab("windows")).toBe("windows");
    expect(preferredInstallTab("linux")).toBe("linux");
    expect(preferredInstallTab("macos")).toBe("windows");
    expect(preferredInstallTab("unknown")).toBe("windows");
  });
});

describe("PlatformTabs", () => {
  it("selects the detected platform and hides the others", () => {
    render(<PlatformTabs tabs={TABS} platform="linux" />);
    expect(screen.getByRole("tab", { name: "Linux" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: /Linux/ })).not.toHaveAttribute("hidden");
    // happy-dom cannot resolve aria-labelledby names on hidden elements, so
    // assert the inactive panel via its content.
    const windowsPanel = screen.getByText("Windows guide content").closest('[role="tabpanel"]');
    expect(windowsPanel).toHaveAttribute("hidden");
  });

  it("shows the honest macOS notice and never a macOS guide", () => {
    render(<PlatformTabs tabs={TABS} platform="macos" />);
    expect(screen.getByText(/SayIt currently supports Windows and Linux/i)).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "macOS" })).not.toBeInTheDocument();
  });

  it("supports keyboard arrow navigation between tabs", () => {
    const { container } = render(<PlatformTabs tabs={TABS} platform="windows" />);
    const tablist = container.querySelector('[role="tablist"]') as HTMLElement;
    fireEvent.keyDown(tablist, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Linux" })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tablist, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "Windows" })).toHaveAttribute("aria-selected", "true");
  });

  it("renders exactly one visible panel at a time", () => {
    const { container } = render(<PlatformTabs tabs={TABS} platform="windows" />);
    const panels = [...container.querySelectorAll('[role="tabpanel"]')];
    const visible = panels.filter((panel) => !panel.hasAttribute("hidden"));
    expect(visible).toHaveLength(1);
    expect(visible[0].textContent).toContain("Windows guide content");
  });
});

describe("Install page", () => {
  it("renders all three platform tabs and real guide content", () => {
    render(<InstallPage />);
    expect(screen.getByRole("tab", { name: "Windows" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Linux" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Source" })).toBeInTheDocument();
    expect(screen.getByText(/SayIt-Setup-x64\.exe/i)).toBeInTheDocument();
    expect(screen.getAllByText(/SayIt-\*\.AppImage/i).length).toBeGreaterThan(0);
  });

  it("answers 'what do I do' before any history", () => {
    render(<InstallPage />);
    expect(
      screen.getByText(/download the installer, run it, follow the setup wizard/i),
    ).toBeInTheDocument();
  });

  it("uses the real repository URL and module entry point in the source guide", () => {
    render(<InstallPage />);
    expect(
      screen.getByText(`git clone ${site.repositoryUrl}.git`, { exact: false }),
    ).toBeInTheDocument();
    expect(screen.getByText("cd SayIt && uv sync", { exact: false })).toBeInTheDocument();
    expect(
      screen.getAllByText("uv run python -m sayit", { exact: false }).length,
    ).toBeGreaterThan(0);
  });

  it("does not invent a CLI version command", () => {
    const { container } = render(<InstallPage />);
    expect(container.textContent ?? "").not.toMatch(/sayit\s+--version/i);
  });

  it("documents the honest SmartScreen situation", () => {
    render(<InstallPage />);
    expect(screen.getAllByText(/not code-signed yet/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/More info/i).length).toBeGreaterThan(0);
  });

  it("documents the Linux requirements that come from the build config", () => {
    render(<InstallPage />);
    expect(screen.getByText(/manylinux_2_28/i)).toBeInTheDocument();
    expect(screen.getAllByText(/xclip/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Wayland/i).length).toBeGreaterThan(0);
  });

  it("walks through the actual six-step setup wizard", () => {
    render(<InstallPage />);
    expect(screen.getByText(/Welcome & privacy/i)).toBeInTheDocument();
    expect(screen.getByText(/Speech model/i)).toBeInTheDocument();
    expect(screen.getByText(/Try your first dictation/i)).toBeInTheDocument();
    expect(screen.getByText(/Setup complete/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Ctrl plus Space")).toBeInTheDocument();
  });

  it("states that the wizard does not fake transcription", () => {
    render(<InstallPage />);
    expect(screen.getByText(/never fakes a transcription/i)).toBeInTheDocument();
  });

  it("documents uninstall behavior precisely — data kept by default", () => {
    render(<InstallPage />);
    expect(screen.getByText(/kept by default/i)).toBeInTheDocument();
    expect(screen.getByText(/%LOCALAPPDATA%\\SayIt/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Clear Data/i).length).toBeGreaterThan(0);
  });
});
