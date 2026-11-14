import { describe, expect, it } from "vitest";
import {
  graphDistances,
  paperSize,
  spaceCircles,
  visibleExpansionGraph,
} from "@/lib/graph-focus";
import type { Graph, Paper } from "@/lib/types";

const paper = (id: string): Paper => ({
  id,
  doi: null,
  title: id,
  year: null,
  authors: [],
  abstract: null,
  cited_by_count: 0,
  landing_page_url: null,
});
const graph: Graph = {
  papers: ["W1", "W2", "W3", "W4"].map(paper),
  citations: [
    {
      id: "1",
      source: "W1",
      target: "W2",
      intent: null,
      confidence: null,
      context_text: null,
      context_source_url: null,
    },
    {
      id: "2",
      source: "W2",
      target: "W3",
      intent: null,
      confidence: null,
      context_text: null,
      context_source_url: null,
    },
    {
      id: "3",
      source: "W3",
      target: "W4",
      intent: null,
      confidence: null,
      context_text: null,
      context_source_url: null,
    },
  ],
};

describe("graph focus and branch visibility", () => {
  it("makes the selected node largest and shrinks each step away", () => {
    const first = graphDistances(graph, "W1");
    const next = graphDistances(graph, "W3");
    expect(
      ["W1", "W2", "W3", "W4"].map((id) => paperSize(first.get(id))),
    ).toEqual([208, 164, 146, 128]);
    expect(
      ["W1", "W2", "W3", "W4"].map((id) => paperSize(next.get(id))),
    ).toEqual([146, 164, 208, 164]);
  });

  it("keeps spaced papers in place when the focused paper changes", () => {
    const circles = [
      { id: "W1", x: 0, y: 0, size: 208 },
      { id: "W2", x: 460, y: 0, size: 164 },
      { id: "W3", x: 900, y: 0, size: 146 },
    ];
    const positions = spaceCircles(circles, "W1");
    expect(positions.get("W1")).toEqual({ x: 0, y: 0 });
    expect(positions.get("W2")).toEqual({ x: 460, y: 0 });
    expect(positions.get("W3")).toEqual({ x: 900, y: 0 });
  });

  it("separates colliding circles and preserves the dragged node", () => {
    const circles = [
      { id: "W1", x: 0, y: 0, size: 208 },
      { id: "W2", x: 0, y: 0, size: 164 },
      { id: "W3", x: 0, y: 0, size: 146 },
      { id: "W4", x: 0, y: 0, size: 128 },
    ];
    const positions = spaceCircles(circles, "W1");
    expect(positions.get("W1")).toEqual({ x: 0, y: 0 });
    for (let i = 0; i < circles.length; i += 1) {
      for (let j = i + 1; j < circles.length; j += 1) {
        const a = circles[i];
        const b = circles[j];
        const ap = positions.get(a.id)!;
        const bp = positions.get(b.id)!;
        const separation = Math.hypot(
          ap.x + a.size / 2 - bp.x - b.size / 2,
          ap.y + a.size / 2 - bp.y - b.size / 2,
        );
        expect(separation).toBeGreaterThanOrEqual((a.size + b.size) / 2 + 25.8);
      }
    }
  });

  it("hides orphaned descendants but preserves papers connected by another active branch", () => {
    const groups = {
      "W1:references": ["W1:W2"],
      "W2:references": ["W2:W3"],
      "W3:references": ["W3:W4"],
    };
    const all = new Set(Object.keys(groups));
    expect(visibleExpansionGraph(graph, "W1", groups, all).papers).toHaveLength(
      4,
    );
    all.delete("W2:references");
    expect(
      visibleExpansionGraph(graph, "W1", groups, all).papers.map(
        (entry) => entry.id,
      ),
    ).toEqual(["W1", "W2"]);

    const shared: Graph = {
      ...graph,
      citations: [
        ...graph.citations,
        {
          id: "4",
          source: "W1",
          target: "W3",
          intent: null,
          confidence: null,
          context_text: null,
          context_source_url: null,
        },
      ],
    };
    const sharedGroups = { ...groups, "W1:references": ["W1:W2", "W1:W3"] };
    expect(
      visibleExpansionGraph(shared, "W1", sharedGroups, all).papers.map(
        (entry) => entry.id,
      ),
    ).toEqual(["W1", "W2", "W3", "W4"]);
  });
});
