import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HorizontalScroller } from "@/components/shell/horizontal-scroller";

function metrics(element: HTMLElement, scrollWidth: number, clientWidth: number, scrollLeft: number) {
  Object.defineProperty(element, "scrollWidth", { configurable: true, value: scrollWidth });
  Object.defineProperty(element, "clientWidth", { configurable: true, value: clientWidth });
  Object.defineProperty(element, "scrollLeft", { configurable: true, writable: true, value: scrollLeft });
}

describe("HorizontalScroller", () => {
  it("disables the left arrow at the start and the right arrow at the end", () => {
    render(
      <HorizontalScroller>
        <div style={{ width: 800 }}>Rapports</div>
      </HorizontalScroller>,
    );
    const region = screen.getByText("Rapports").parentElement as HTMLElement;
    const scrollBy = vi.fn();
    region.scrollBy = scrollBy;
    metrics(region, 800, 300, 0);
    fireEvent.scroll(region);

    const left = screen.getByRole("button", { name: "Défiler vers la gauche" });
    const right = screen.getByRole("button", { name: "Défiler vers la droite" });
    expect(left).toBeDisabled();
    expect(right).not.toBeDisabled();

    fireEvent.click(right);
    expect(scrollBy).toHaveBeenCalledWith({ left: expect.any(Number), behavior: "smooth" });
    expect(scrollBy.mock.calls[0][0].left).toBeGreaterThan(0);

    metrics(region, 800, 300, 500);
    fireEvent.scroll(region);
    expect(left).not.toBeDisabled();
    expect(right).toBeDisabled();

    fireEvent.click(left);
    expect(scrollBy.mock.calls.at(-1)?.[0].left).toBeLessThan(0);
  });

  it("scrolls with the keyboard in both directions", () => {
    render(
      <HorizontalScroller>
        <div>Contenu</div>
      </HorizontalScroller>,
    );
    const region = screen.getByText("Contenu").parentElement as HTMLElement;
    const scrollBy = vi.fn();
    region.scrollBy = scrollBy;
    metrics(region, 800, 200, 100);
    fireEvent.scroll(region);
    region.focus();
    fireEvent.keyDown(region, { key: "ArrowLeft" });
    fireEvent.keyDown(region, { key: "ArrowRight" });
    expect(scrollBy.mock.calls.map((call) => call[0].left)).toEqual([
      expect.any(Number),
      expect.any(Number),
    ]);
    expect(scrollBy.mock.calls[0][0].left).toBeLessThan(0);
    expect(scrollBy.mock.calls[1][0].left).toBeGreaterThan(0);
  });
});
