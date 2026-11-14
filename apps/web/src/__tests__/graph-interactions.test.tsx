import { StrictMode } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Node, ReactFlowProps } from "@xyflow/react";
import { CitationCanvas } from "@/components/graph/citation-canvas";
import { previewInitialGraph, previewFullGraph } from "@/lib/preview-graph";
import type { Graph, Paper } from "@/lib/types";
import { circle, DIRECTION_GAP } from "@/lib/graph-physics";

type TestNode = Node<{ paper: Paper }, "paperBubble">;
const capture = vi.hoisted(() => ({
  props: null as ReactFlowProps<TestNode> | null,
}));
vi.mock("@/components/graph/ambient-links", () => ({
  AmbientLinks: () => null,
}));
vi.mock("@xyflow/react", async (original) => ({
  ...(await original<typeof import("@xyflow/react")>()),
  ReactFlow: (props: ReactFlowProps<TestNode>) => {
    capture.props = props;
    return (
      <div>
        {props.nodes
          ?.filter((node) => !node.hidden)
          .map((node) => (
            <button
              key={node.id}
              data-testid={`node-${node.id}`}
              onMouseEnter={(event) => props.onNodeMouseEnter?.(event, node)}
              onMouseMove={(event) => props.onNodeMouseMove?.(event, node)}
              onMouseLeave={(event) => props.onNodeMouseLeave?.(event, node)}
              onClick={(event) => props.onNodeClick?.(event, node)}
            >
              {node.data.paper.title}
            </button>
          ))}
        {props.edges?.map((edge) => (
          <button
            key={edge.id}
            data-testid={`edge-${edge.id}`}
            onMouseEnter={(event) => props.onEdgeMouseEnter?.(event, edge)}
            onMouseMove={(event) => props.onEdgeMouseMove?.(event, edge)}
            onMouseLeave={(event) => props.onEdgeMouseLeave?.(event, edge)}
            onClick={(event) => props.onEdgeClick?.(event, edge)}
          >
            Citation
          </button>
        ))}
      </div>
    );
  },
}));

let frames = new Map<number, FrameRequestCallback>(),
  nextId = 0,
  time = 0;
beforeEach(() => {
  frames = new Map();
  nextId = time = 0;
  vi.stubGlobal(
    "requestAnimationFrame",
    vi.fn((callback: FrameRequestCallback) => {
      frames.set(++nextId, callback);
      return nextId;
    }),
  );
  vi.stubGlobal(
    "cancelAnimationFrame",
    vi.fn((id: number) => frames.delete(id)),
  );
});
afterEach(() => vi.unstubAllGlobals());
/** Advance frames until the simulation loop stops by itself (bounded). */
function settleFrames() {
  for (let i = 0; i < 1000 && frames.size; i += 1) tick();
  expect(frames.size).toBe(0);
}
function tick(count = 1) {
  act(() => {
    for (let i = 0; i < count; i += 1) {
      time += 16;
      const pending = [...frames.values()];
      frames.clear();
      for (const frame of pending) frame(time);
    }
  });
}
const defaultProps = {
  seedId: "W1",
  graph: previewInitialGraph,
  visibleGraph: previewInitialGraph,
  selectedPaperId: null,
  selectedCitationId: null,
  expansionOrigin: null,
  loading: false,
  onSelectPaper: vi.fn(),
  onSelectCitation: vi.fn(),
  onClearSelection: vi.fn(),
};
function positions() {
  return new Map(
    capture.props!.nodes!.map((node) => [node.id, { ...node.position }]),
  );
}
function center(id: string) {
  const node = capture.props!.nodes!.find((item) => item.id === id)!;
  const size = Math.max(node.measured?.width ?? 0, Number(node.style!.width));
  return circle({ id, ...node.position, width: size, height: size });
}
function drag(id: string, to: { x: number; y: number }, moves = 1) {
  const node = capture.props!.nodes!.find((item) => item.id === id)!;
  const from = { ...node.position };
  for (let k = 1; k <= moves; k += 1) {
    const position = {
      x: from.x + ((to.x - from.x) * k) / moves,
      y: from.y + ((to.y - from.y) * k) / moves,
    };
    act(() => {
      capture.props!.onNodesChange?.([
        { type: "position", id, position, dragging: true },
      ]);
      capture.props!.onNodeDrag?.(
        new MouseEvent("mousemove"),
        { ...node, position },
        [{ ...node, position }],
      );
    });
    tick();
  }
}
function startDrag(id: string) {
  const node = capture.props!.nodes!.find((item) => item.id === id)!;
  act(() =>
    capture.props!.onNodeDragStart?.(new MouseEvent("mousedown"), node, [node]),
  );
}
function stopDrag(id: string) {
  const node = capture.props!.nodes!.find((item) => item.id === id)!;
  act(() =>
    capture.props!.onNodeDragStop?.(new MouseEvent("mouseup"), node, [node]),
  );
}

describe("graph canvas interaction wiring (deterministic React Flow adapter)", () => {
  it("keeps node preview, edge highlighting and directed edge selection separate", () => {
    const onSelectPaper = vi.fn(),
      onSelectCitation = vi.fn();
    render(
      <CitationCanvas
        {...defaultProps}
        onSelectPaper={onSelectPaper}
        onSelectCitation={onSelectCitation}
      />,
    );
    fireEvent.mouseEnter(screen.getByTestId("node-W1"));
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "UI sample: Starting paper",
    );
    fireEvent.mouseLeave(screen.getByTestId("node-W1"));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.mouseEnter(screen.getByTestId("edge-W1-W2"));
    fireEvent.mouseMove(screen.getByTestId("edge-W1-W2"));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    expect(capture.props!.edges![0].className).toContain("is-highlighted");
    expect(onSelectPaper).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("edge-W1-W2"), {
      clientX: 180,
      clientY: 240,
    });
    expect(onSelectCitation).toHaveBeenCalledExactlyOnceWith("W1-W2", 180, 240);
    expect(onSelectPaper).not.toHaveBeenCalled();
    fireEvent.mouseEnter(screen.getByTestId("node-W2"));
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "UI sample: Earlier method",
    );
  });

  it("bounds Strict Mode animation, preserves pointer position, then settles and cleans up", () => {
    const { unmount } = render(
      <StrictMode>
        <CitationCanvas {...defaultProps} />
      </StrictMode>,
    );
    settleFrames();
    const node = capture.props!.nodes!.find((item) => item.id === "W2")!;
    act(() =>
      capture.props!.onNodeDragStart?.(new MouseEvent("mousedown"), node, [
        node,
      ]),
    );
    const moved = {
      ...node,
      position: { x: node.position.x - 100, y: node.position.y + 120 },
    };
    act(() => {
      capture.props!.onNodesChange?.([
        {
          type: "position",
          id: moved.id,
          position: moved.position,
          dragging: true,
        },
      ]);
      capture.props!.onNodeDrag?.(new MouseEvent("mousemove"), moved, [moved]);
    });
    tick(8);
    expect(positions().get("W2")).toEqual(moved.position);
    act(() =>
      capture.props!.onNodeDragStop?.(new MouseEvent("mouseup"), moved, [
        moved,
      ]),
    );
    settleFrames();
    expect(positions().get("W2")).toEqual(moved.position);
    act(() =>
      capture.props!.onNodeDragStart?.(new MouseEvent("mousedown"), moved, [
        moved,
      ]),
    );
    expect(frames.size).toBe(1);
    unmount();
    expect(frames.size).toBe(0);
  });

  it("preserves existing positions on expansion and state updates and never duplicates nodes", () => {
    const { rerender } = render(<CitationCanvas {...defaultProps} />);
    settleFrames();
    const before = positions();
    rerender(
      <CitationCanvas
        {...defaultProps}
        graph={previewFullGraph}
        visibleGraph={previewFullGraph}
        expansionOrigin="W2"
      />,
    );
    for (const [id, point] of before)
      expect(positions().get(id)).toEqual(point);
    expect(capture.props!.nodes).toHaveLength(6);
    settleFrames();
    const after = positions();
    rerender(
      <CitationCanvas
        {...defaultProps}
        graph={previewFullGraph}
        visibleGraph={previewFullGraph}
        expansionOrigin="W2"
        loading
      />,
    );
    tick(30);
    expect(positions()).toEqual(after);
    expect(capture.props!.nodes).toHaveLength(6);
  });

  it("keeps BART -> Word2Vec and fixed-size arrowheads as nodes move, deduplicating only identical directions", () => {
    const papers = previewInitialGraph.papers
      .slice(0, 2)
      .map((paper, index) => ({
        ...paper,
        id: index ? "W1614298861" : "W2982399380",
      }));
    const citation = {
      ...previewInitialGraph.citations[0],
      id: "bart-word2vec",
      source: papers[0].id,
      target: papers[1].id,
    };
    const graph: Graph = {
      papers,
      citations: [
        citation,
        { ...citation, id: "duplicate" },
        {
          ...citation,
          id: "reverse",
          source: citation.target,
          target: citation.source,
        },
      ],
    };
    render(
      <CitationCanvas
        {...defaultProps}
        seedId={papers[0].id}
        graph={graph}
        visibleGraph={graph}
      />,
    );
    expect(capture.props!.edges).toHaveLength(2);
    const edge = capture.props!.edges![0];
    expect(edge).toMatchObject({
      source: "W2982399380",
      target: "W1614298861",
      markerEnd: {
        type: "arrowclosed",
        markerUnits: "userSpaceOnUse",
        width: 20,
        height: 20,
      },
    });
    const source = capture.props!.nodes![0];
    act(() =>
      capture.props!.onNodesChange?.([
        { type: "position", id: source.id, position: { x: -900, y: 800 } },
      ]),
    );
    expect(capture.props!.edges![0]).toBe(edge);
    expect(capture.props!.edges![0].source).toBe("W2982399380");
  });

  it("resolves reduced-motion layout without scheduling a settling animation", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: true })),
    );
    render(<CitationCanvas {...defaultProps} />);
    expect(frames.size).toBe(0);
    expect(capture.props!.nodes).toHaveLength(3);
  });

  it("lets the selected paper be dragged anywhere, pulling its neighbors elastically on each pointer event, including under reduced motion", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: true })),
    );
    render(
      <CitationCanvas
        {...defaultProps}
        graph={previewFullGraph}
        visibleGraph={previewFullGraph}
        selectedPaperId="W1"
      />,
    );
    startDrag("W1");
    for (const delta of [
      { x: -500, y: 0 },
      { x: 1000, y: 0 },
      { x: 0, y: -500 },
      { x: 300, y: 1000 },
    ]) {
      const before = positions();
      const target = {
        x: before.get("W1")!.x + delta.x,
        y: before.get("W1")!.y + delta.y,
      };
      drag("W1", target);
      // The dragged focus is exactly at the pointer, never constrained.
      expect(positions().get("W1")).toEqual(target);
      // Direct neighbors respond in the same event but do not move as a
      // rigid copy of the pointer delta.
      for (const id of ["W2", "W3", "W6"]) {
        const moved = Math.hypot(
          positions().get(id)!.x - before.get(id)!.x,
          positions().get(id)!.y - before.get(id)!.y,
        );
        expect(moved).toBeGreaterThan(0);
        expect(moved).toBeLessThan(Math.hypot(delta.x, delta.y) - 1);
      }
      expect(frames.size).toBe(0);
    }
    const drop = { ...positions().get("W1")! };
    stopDrag("W1");
    expect(positions().get("W1")).toEqual(drop);
    expect(frames.size).toBe(0);
  });

  it("lets an ordinary node cross the focus and the origin, keeps it where dropped, then settles directions around it", () => {
    render(<CitationCanvas {...defaultProps} selectedPaperId="W1" />);
    settleFrames();
    // Reference W2 starts left of its citing focus W1.
    expect(center("W2").x).toBeLessThan(center("W1").x);
    const focus = { ...positions().get("W1")! };
    startDrag("W2");
    const target = { x: focus.x + 700, y: focus.y + 200 };
    drag("W2", target, 20);
    // No invisible wall: the node is exactly at the pointer on the far side.
    expect(positions().get("W2")).toEqual(target);
    expect(center("W2").x).toBeGreaterThan(center("W1").x);
    stopDrag("W2");
    settleFrames();
    expect(positions().get("W2")).toEqual(target);
    // At rest the citing focus has moved to the right of its reference.
    expect(center("W1").x - center("W2").x).toBeGreaterThan(
      center("W1").radius + center("W2").radius + DIRECTION_GAP / 2,
    );
  });

  it("reserves measured dimensions so differently sized nodes do not overlap at rest", () => {
    render(<CitationCanvas {...defaultProps} selectedPaperId="W1" />);
    settleFrames();
    act(() =>
      capture.props!.onNodesChange?.([
        {
          type: "dimensions",
          id: "W2",
          dimensions: { width: 380, height: 380 },
        },
      ]),
    );
    settleFrames();
    for (const [a, b] of [
      ["W1", "W2"],
      ["W2", "W3"],
      ["W1", "W3"],
    ]) {
      const first = center(a),
        second = center(b);
      expect(
        Math.hypot(first.x - second.x, first.y - second.y),
      ).toBeGreaterThan(first.radius + second.radius);
    }
    expect(center("W2").x).toBeLessThan(center("W1").x);
  });

  it("reorganizes shared expansions around a new selection while preserving directed edge callbacks", () => {
    const onSelectCitation = vi.fn();
    const { rerender } = render(<CitationCanvas {...defaultProps} />);
    settleFrames();
    const anchor = { ...positions().get("W2")! };
    rerender(
      <CitationCanvas
        {...defaultProps}
        graph={previewFullGraph}
        visibleGraph={previewFullGraph}
        selectedPaperId="W2"
        expansionOrigin="W2"
        onSelectCitation={onSelectCitation}
      />,
    );
    // Nothing jumps on the render that introduces the new papers.
    expect(positions().get("W2")).toEqual(anchor);
    settleFrames();
    for (const edge of capture.props!.edges!) {
      if (edge.source !== "W2" && edge.target !== "W2") continue;
      const citing = center(edge.source),
        cited = center(edge.target);
      expect(citing.x - cited.x, edge.id).toBeGreaterThan(
        citing.radius + cited.radius,
      );
    }
    // The heavier new focus stays near where it was.
    expect(
      Math.hypot(
        positions().get("W2")!.x - anchor.x,
        positions().get("W2")!.y - anchor.y,
      ),
    ).toBeLessThan(150);
    const edge = capture.props!.edges!.find((edge) => edge.source === "W2")!;
    fireEvent.click(screen.getByTestId(`edge-${edge.id}`), {
      clientX: 50,
      clientY: 80,
    });
    expect(onSelectCitation).toHaveBeenCalledExactlyOnceWith(edge.id, 50, 80);
    expect(frames.size).toBe(0);
  });
});
