import { render, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import {
  CitationCanvas,
  type CitationCanvasHandle,
} from "@/components/graph/citation-canvas";
import { previewFullGraph, previewInitialGraph } from "@/lib/preview-graph";
import { createPhysics } from "@/lib/graph-physics";

// The elastic simulation is the canvas's only layout engine; spying on it shows
// whether anything could move the restored papers.
vi.mock("@/lib/graph-physics", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/graph-physics")>();
  return { ...original, createPhysics: vi.fn(original.createPhysics) };
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
    // Let measurements and any animation frames run: the restored layout must
    // still be untouched and no simulation may have started.
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(createPhysics).not.toHaveBeenCalled();
    expect(canvas.current?.getLayout()).toEqual(layout);
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
    // Selecting another paper is a real change: the elastic layout resumes and
    // reorganizes direct relationships around the new focus (by design).
    await waitFor(() => expect(createPhysics).toHaveBeenCalled());
    expect(canvas.current?.getLayout().viewport).toEqual(layout.viewport);
  });

  it("starts physics from restored positions and activates only newly added papers", async () => {
    vi.mocked(createPhysics).mockClear();
    const layout = {
      positions: {
        W1: { x: 120, y: -60 },
        W2: { x: 500, y: 200 },
        W3: { x: -300, y: 80 },
      },
      viewport: { x: 30, y: 45, zoom: 0.7 },
    };
    const props = {
      initialLayout: layout,
      seedId: "W1",
      selectedPaperId: "W1",
      selectedCitationId: null,
      loading: false,
      onSelectPaper: () => {},
      onSelectCitation: () => {},
      onClearSelection: () => {},
    };
    const { rerender } = render(
      <CitationCanvas
        {...props}
        graph={previewInitialGraph}
        visibleGraph={previewInitialGraph}
        expansionOrigin={null}
      />,
    );
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(createPhysics).not.toHaveBeenCalled();
    // Expand the reopened graph with one new paper (W6, cited by W1).
    const expanded = {
      papers: [...previewInitialGraph.papers, previewFullGraph.papers[5]],
      citations: [
        ...previewInitialGraph.citations,
        previewFullGraph.citations.find((c) => c.id === "W1-W6")!,
      ],
    };
    rerender(
      <CitationCanvas
        {...props}
        graph={expanded}
        visibleGraph={expanded}
        expansionOrigin="W1"
      />,
    );
    // The simulation that runs is the one created once W6 is placed; it
    // activates only the new paper.
    await waitFor(() =>
      expect(vi.mocked(createPhysics).mock.lastCall?.[3]?.active).toEqual(
        new Set(["W6"]),
      ),
    );
    const [bodies] = vi.mocked(createPhysics).mock.lastCall!;
    // It starts from the saved positions; nothing replaced them beforehand.
    for (const [id, saved] of Object.entries(layout.positions))
      expect(bodies.find((body) => body.id === id)).toMatchObject(saved);
  });
});
