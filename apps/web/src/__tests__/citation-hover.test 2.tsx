import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CitationCanvas } from "@/components/graph/citation-canvas";
import { previewInitialGraph } from "@/lib/preview-graph";

vi.mock("@/components/graph/ambient-links", () => ({
  AmbientLinks: () => null,
}));
vi.mock("@xyflow/react", async (importOriginal) => {
  const original = await importOriginal<typeof import("@xyflow/react")>();
  type TestNode = { id: string; className?: string };
  type TestEdge = { id: string; className?: string };
  return {
    ...original,
    ReactFlow: ({
      nodes,
      edges,
      onEdgeMouseEnter,
    }: {
      nodes: TestNode[];
      edges: TestEdge[];
      onEdgeMouseEnter: (
        event: React.MouseEvent<HTMLButtonElement>,
        edge: TestEdge,
      ) => void;
    }) => (
      <div>
        {nodes.map((node) => (
          <div
            key={node.id}
            data-testid={`node-${node.id}`}
            className={node.className}
          />
        ))}
        {edges.map((edge) => (
          <button
            key={edge.id}
            data-testid={`edge-${edge.id}`}
            className={edge.className}
            onMouseEnter={(event) => onEdgeMouseEnter(event, edge)}
          />
        ))}
      </div>
    ),
  };
});

describe("citation hover", () => {
  it("highlights both papers and their connecting edge", async () => {
    render(
      <CitationCanvas
        seedId="W1"
        graph={previewInitialGraph}
        visibleGraph={previewInitialGraph}
        selectedPaperId={null}
        selectedCitationId={null}
        expansionOrigin={null}
        loading={false}
        onSelectPaper={() => {}}
        onSelectCitation={() => {}}
        onClearSelection={() => {}}
      />,
    );
    const edge = await screen.findByTestId("edge-W1-W2");
    fireEvent.mouseEnter(edge);
    expect(edge).toHaveClass("is-highlighted");
    expect(screen.getByTestId("node-W1")).toHaveClass("is-highlighted");
    expect(screen.getByTestId("node-W2")).toHaveClass("is-highlighted");
  });
});
