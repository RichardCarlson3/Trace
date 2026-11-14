import { describe, expect, it } from "vitest";
import { filteredGraph, mergeGraphs } from "@/lib/graph";
import type { Citation, Paper } from "@/lib/types";

function paper(id: string): Paper {
  return {
    id,
    doi: null,
    title: `Fixture ${id}`,
    year: 2024,
    authors: [],
    abstract: null,
    cited_by_count: 0,
    landing_page_url: null,
  };
}

function citation(source: string, target: string): Citation {
  return {
    id: `${source}-${target}`,
    source,
    target,
    intent: null,
    confidence: null,
    context_text: null,
    context_source_url: null,
  };
}

describe("graph expansion merge", () => {
  it("keeps existing relationships and deduplicates a paper reached twice", () => {
    const original = {
      papers: [paper("W1"), paper("W2")],
      citations: [citation("W1", "W2")],
    };
    const expansion = {
      papers: [paper("W2"), paper("W3")],
      citations: [citation("W1", "W2"), citation("W3", "W1")],
    };

    const merged = mergeGraphs(original, expansion);

    expect(merged.papers.map(({ id }) => id)).toEqual(["W1", "W2", "W3"]);
    expect(merged.citations).toHaveLength(2);
    expect(
      merged.citations.map(({ source, target }) => [source, target]),
    ).toEqual([
      ["W1", "W2"],
      ["W3", "W1"],
    ]);
  });

  it("uses genuine evidence when an existing edge is enriched", () => {
    const originalEdge = citation("W1", "W2");
    const enrichedEdge: Citation = {
      ...originalEdge,
      context_text: "Fixture citation passage",
      context_source_url: "https://example.org/fixture",
      intent: "method",
      confidence: 0.7,
    };

    const merged = mergeGraphs(
      { papers: [paper("W1"), paper("W2")], citations: [originalEdge] },
      { papers: [paper("W1"), paper("W2")], citations: [enrichedEdge] },
    );

    expect(merged.citations).toEqual([enrichedEdge]);
  });
});

describe("graph filters", () => {
  const graph = {
    papers: [paper("W1"), paper("W2"), { ...paper("W3"), year: null }],
    citations: [citation("W1", "W2"), citation("W3", "W1")],
  };

  it("keeps unknown-year papers visible until a year filter is applied", () => {
    expect(filteredGraph(graph, "W1", "all", "", "").papers).toHaveLength(3);
    expect(
      filteredGraph(graph, "W1", "all", "2020", "2025").papers.map(
        ({ id }) => id,
      ),
    ).toEqual(["W1", "W2"]);
  });

  it("filters citation direction relative to the starting paper", () => {
    const result = filteredGraph(graph, "W1", "citations", "", "");
    expect(result.papers.map(({ id }) => id)).toEqual(["W1", "W3"]);
    expect(
      result.citations.map(({ source, target }) => [source, target]),
    ).toEqual([["W3", "W1"]]);
  });
});
