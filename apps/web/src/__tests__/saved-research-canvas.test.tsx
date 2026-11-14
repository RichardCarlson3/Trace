import { render, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import {
  CitationCanvas,
  type CitationCanvasHandle,
} from "@/components/graph/citation-canvas";
import { previewInitialGraph } from "@/lib/preview-graph";
import { spaceCircles } from "@/lib/graph-focus";

vi.mock("@/lib/graph-focus", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/graph-focus")>();
  return { ...original, spaceCircles: vi.fn(original.spaceCircles) };
});

vi.mock("@/components/graph/ambient-links", () => ({
  AmbientLinks: () => null,
}));

vi.stubGlobal(
  "ResizeObserver",
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);

describe("actual React Flow canvas", () => {
  it("restores saved node positions and viewport instead of fitting a new layout", async () => {
    const canvas = createRef<CitationCanvasHandle>();
    const layout = {
      positions: {
        W1: { x: 120, y: -60 },
        W2: { x: 500, y: 200 },
        W3: { x: -300, y: 80 },
      },
      viewport: { x: 30, y: 45, zoom: 0.7 },
    };
    const { rerender } = render(
      <CitationCanvas
        ref={canvas}
        initialLayout={layout}
        seedId="W1"
        graph={previewInitialGraph}
        visibleGraph={previewInitialGraph}
        selectedPaperId="W1"
        selectedCitationId={null}
        expansionOrigin={null}
        loading={false}
        onSelectPaper={() => {}}
        onSelectCitation={() => {}}
        onClearSelection={() => {}}
      />,
    );
    await waitFor(() => expect(canvas.current?.getLayout()).toEqual(layout));
    expect(document.querySelector('[data-id="W1"]')).toHaveStyle({
      transform: "translate(120px,-60px)",
    });
    expect(spaceCircles).not.toHaveBeenCalled();
    rerender(
      <CitationCanvas
        ref={canvas}
        initialLayout={layout}
        seedId="W1"
        graph={previewInitialGraph}
        visibleGraph={previewInitialGraph}
        selectedPaperId="W2"
        selectedCitationId={null}
        expansionOrigin={null}
        loading={false}
        onSelectPaper={() => {}}
        onSelectCitation={() => {}}
        onClearSelection={() => {}}
      />,
    );
    await waitFor(() => expect(spaceCircles).toHaveBeenCalled());
    expect(canvas.current?.getLayout()).toEqual(layout);
  });
});
