import { fireEvent, render, screen } from "@testing-library/react";
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

describe("actual React Flow canvas", () => {
  it("initializes a full-page empty viewport without graph controls", () => {
    const { container } = render(
      <CitationCanvas
        seedId={null}
        graph={{ papers: [], citations: [] }}
        visibleGraph={{ papers: [], citations: [] }}
        selectedPaperId={null}
        selectedCitationId={null}
        expansionOrigin={null}
        loading={false}
        onSelectPaper={() => {}}
        onSelectCitation={() => {}}
      />,
    );
    expect(
      container.querySelector(".react-flow__viewport"),
    ).toBeInTheDocument();
    expect(
      container.querySelector(".react-flow__background"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /zoom in/i })).toBeNull();
  });

  it("renders multiple papers from the graph response", async () => {
    render(
      <CitationCanvas
        seedId="W1"
        graph={previewInitialGraph}
        visibleGraph={previewInitialGraph}
        selectedPaperId="W1"
        selectedCitationId={null}
        expansionOrigin={null}
        loading={false}
        onSelectPaper={() => {}}
        onSelectCitation={() => {}}
      />,
    );

    expect(
      await screen.findByText(/UI sample: Starting paper/),
    ).toBeInTheDocument();
    expect(screen.getByText(/UI sample: Earlier method/)).toBeInTheDocument();
    expect(screen.getByText(/UI sample: Later study/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /zoom in/i }),
    ).toBeInTheDocument();
    const bubbles = document.querySelectorAll(".paper-bubble");
    expect(bubbles).toHaveLength(3);
    fireEvent.mouseEnter(bubbles[0]);
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "Sample data for checking the graph interface",
    );
  });
});
