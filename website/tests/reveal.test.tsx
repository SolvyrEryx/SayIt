import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { Reveal } from "@/components/Reveal";

type IntersectionCallback = (entries: { isIntersecting: boolean }[]) => void;

class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = [];
  callback: IntersectionCallback;
  observe = vi.fn();
  disconnect = vi.fn();
  unobserve = vi.fn();

  constructor(callback: IntersectionCallback) {
    this.callback = callback;
    MockIntersectionObserver.instances.push(this);
  }
}

afterEach(() => {
  MockIntersectionObserver.instances = [];
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Reveal", () => {
  it("reveals synchronously when already in the viewport (no flash)", () => {
    render(
      <Reveal>
        <p>hello</p>
      </Reveal>,
    );
    const el = document.querySelector(".scroll-reveal");
    expect(el).not.toBeNull();
    expect(el).toHaveAttribute("data-js", "true");
    expect(el).toHaveAttribute("data-visible", "true");
  });

  it("reveals via the observer when content scrolls into view", () => {
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      top: 5000,
      bottom: 5100,
      height: 100,
      left: 0,
      right: 100,
      width: 100,
      x: 0,
      y: 5000,
      toJSON: () => ({}),
    } as DOMRect);

    const { container } = render(
      <Reveal>
        <p>below the fold</p>
      </Reveal>,
    );
    const el = container.firstElementChild as HTMLElement;
    expect(el).toHaveAttribute("data-js", "true");
    expect(el).not.toHaveAttribute("data-visible");

    expect(MockIntersectionObserver.instances).toHaveLength(1);
    MockIntersectionObserver.instances[0].callback([{ isIntersecting: true }]);
    expect(el).toHaveAttribute("data-visible", "true");
    expect(MockIntersectionObserver.instances[0].disconnect).toHaveBeenCalled();
  });

  it("applies the stagger variant class for child sequencing", () => {
    render(
      <Reveal stagger className="grid gap-4">
        <p>one</p>
        <p>two</p>
      </Reveal>,
    );
    const el = document.querySelector(".scroll-reveal-stagger");
    expect(el).not.toBeNull();
    expect(el).toHaveClass("grid", "gap-4");
  });
});
