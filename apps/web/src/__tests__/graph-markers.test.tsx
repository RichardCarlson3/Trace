import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CitationCanvas } from "@/components/graph/citation-canvas";
import { previewInitialGraph } from "@/lib/preview-graph";

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

describe("actual React Flow SVG markers", () => {
  it("generates scoped closed arrowheads with fixed units in multiple canvases", () => {
    const props = {
      seedId: "W1",
      graph: previewInitialGraph,
      visibleGraph: previewInitialGraph,
      selectedPaperId: null,
      selectedCitationId: null,
      expansionOrigin: null,
      loading: false,
      onSelectPaper: () => {},
      onSelectCitation: () => {},
      onClearSelection: () => {},
    };
    const { container } = render(
      <>
        <CitationCanvas {...props} />
        <CitationCanvas {...props} />
      </>,
    );
    const markers = [...container.querySelectorAll("marker")];
    expect(markers).toHaveLength(2);
    expect(new Set(markers.map((marker) => marker.id)).size).toBe(2);
    for (const marker of markers) {
      expect(marker).toHaveAttribute("markerUnits", "userSpaceOnUse");
      expect(marker).toHaveAttribute("markerWidth", "20");
      expect(marker).toHaveAttribute("orient", "auto-start-reverse");
      expect(marker.querySelector("polyline")).toBeInTheDocument();
    }
  });
});
