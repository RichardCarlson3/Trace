import { fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AmbientLinks } from "@/components/graph/ambient-links";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("freeform background links", () => {
  it("connects newly clicked positions and waits until selection is cleared", () => {
    const context = {
      setTransform: vi.fn(),
      clearRect: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
    };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      context as unknown as CanvasRenderingContext2D,
    );
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: 400,
      bottom: 300,
      width: 400,
      height: 300,
      toJSON: () => ({}),
    });
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
    vi.stubGlobal("matchMedia", () => ({ matches: true }));

    const { container, rerender } = render(<AmbientLinks canDraw />);
    const host = container.firstElementChild?.parentElement;
    expect(host).not.toBeNull();
    fireEvent.click(host!, { clientX: 80, clientY: 90, button: 0, detail: 1 });
    fireEvent.click(host!, {
      clientX: 310,
      clientY: 220,
      button: 0,
      detail: 1,
    });
    expect(context.moveTo).toHaveBeenCalledWith(80, 90);
    expect(
      context.lineTo.mock.calls.some(
        ([x, y]) => Math.abs(x - 310) < 0.001 && Math.abs(y - 220) < 0.001,
      ),
    ).toBe(true);

    rerender(<AmbientLinks canDraw={false} />);
    context.lineTo.mockClear();
    fireEvent.click(host!, {
      clientX: 373,
      clientY: 219,
      button: 0,
      detail: 1,
    });
    expect(
      context.lineTo.mock.calls.some(
        ([x, y]) => Math.abs(x - 373) < 0.001 && Math.abs(y - 219) < 0.001,
      ),
    ).toBe(false);
  });
});
