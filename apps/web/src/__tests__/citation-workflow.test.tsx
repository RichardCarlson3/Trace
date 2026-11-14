import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { useCitationGraph } from "@/hooks/use-citation-graph";
import type { Citation, Graph, Paper } from "@/lib/types";
import { previewFullGraph, previewInitialGraph } from "@/lib/preview-graph";

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...original,
    api: {
      ...original.api,
      neighbors: vi.fn(),
      references: vi.fn(),
      citations: vi.fn(),
    },
  };
});

const seed: Paper = {
  id: "W1",
  doi: null,
  title: "Fixture seed",
  year: 2024,
  authors: [],
  abstract: null,
  cited_by_count: 0,
  landing_page_url: null,
};

function paper(id: string): Paper {
  return { ...seed, id, title: `Fixture ${id}` };
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

const initial: Graph = {
  papers: [seed, paper("W2")],
  citations: [citation("W1", "W2")],
};

beforeEach(() => vi.clearAllMocks());

describe("citation graph workflow", () => {
  it("lets developers preview expansion without calling the academic API", async () => {
    const { result } = renderHook(() => useCitationGraph());
    act(() =>
      result.current.openPreview(previewInitialGraph, previewFullGraph),
    );

    await act(async () => {
      await result.current.expand("W2", "references");
    });

    expect(result.current.isPreview).toBe(true);
    expect(result.current.graph.papers.some((entry) => entry.id === "W4")).toBe(
      true,
    );
    expect(api.neighbors).not.toHaveBeenCalled();
  });

  it("loads neighbors, selects a paper, and expands without losing earlier nodes", async () => {
    vi.mocked(api.neighbors)
      .mockResolvedValueOnce(initial)
      .mockResolvedValueOnce({
        papers: [paper("W2"), paper("W3")],
        citations: [citation("W2", "W3")],
      });
    const { result } = renderHook(() => useCitationGraph());

    await act(async () => {
      await result.current.openPaper(seed);
    });
    expect(result.current.graph.papers).toHaveLength(2);
    expect(result.current.graph.citations).toHaveLength(1);

    act(() => result.current.selectPaper("W2"));
    expect(result.current.selectedPaper?.id).toBe("W2");

    await act(async () => {
      await result.current.expand("W2", "references");
    });
    expect(result.current.graph.papers.map((entry) => entry.id)).toEqual([
      "W1",
      "W2",
      "W3",
    ]);
    expect(result.current.graph.citations).toHaveLength(2);
    expect(result.current.expanded.has("W2:references")).toBe(true);
  });

  it("hides and restores a loaded branch without fetching it again", async () => {
    vi.mocked(api.neighbors)
      .mockResolvedValueOnce(initial)
      .mockResolvedValueOnce({
        papers: [paper("W2"), paper("W3")],
        citations: [citation("W2", "W3")],
      });
    const { result } = renderHook(() => useCitationGraph());
    await act(async () => result.current.openPaper(seed));
    await act(async () => result.current.expand("W2", "references"));
    expect(result.current.visibleGraph.papers.map((entry) => entry.id)).toEqual(
      ["W1", "W2", "W3"],
    );
    await act(async () => result.current.expand("W2", "references"));
    expect(result.current.visibleGraph.papers.map((entry) => entry.id)).toEqual(
      ["W1", "W2"],
    );
    await act(async () => result.current.expand("W2", "references"));
    expect(result.current.visibleGraph.papers.map((entry) => entry.id)).toEqual(
      ["W1", "W2", "W3"],
    );
    expect(api.neighbors).toHaveBeenCalledTimes(2);
  });

  it("retains the graph after an expansion request fails", async () => {
    vi.mocked(api.neighbors)
      .mockResolvedValueOnce(initial)
      .mockRejectedValueOnce(new Error("Provider unavailable"));
    const { result } = renderHook(() => useCitationGraph());

    await act(async () => {
      await result.current.openPaper(seed);
    });
    await act(async () => {
      await result.current.expand("W2", "references");
    });

    expect(result.current.graph).toEqual(initial);
    expect(result.current.expansionError).toBe("Provider unavailable");
    expect(result.current.expanded.has("W2:references")).toBe(false);
  });

  it("combines the available citation directions when the neighbor endpoint is pending", async () => {
    vi.mocked(api.neighbors).mockRejectedValue(new ApiError("Pending", 501));
    vi.mocked(api.references).mockResolvedValue(initial);
    vi.mocked(api.citations).mockResolvedValue({
      papers: [seed, paper("W3")],
      citations: [citation("W3", "W1")],
    });
    const { result } = renderHook(() => useCitationGraph());
    await act(async () => {
      await result.current.openPaper(seed);
    });
    expect(result.current.graph.papers.map((entry) => entry.id)).toEqual([
      "W1",
      "W2",
      "W3",
    ]);
    expect(result.current.graph.citations).toHaveLength(2);
    expect(result.current.loadError).toBeNull();
  });

  it("clears selection on the canvas and resets to the home state", () => {
    const { result } = renderHook(() => useCitationGraph());
    act(() =>
      result.current.openPreview(previewInitialGraph, previewFullGraph),
    );
    expect(result.current.seed).not.toBeNull();
    act(() => result.current.clearSelection());
    expect(result.current.selectedPaper).toBeNull();
    expect(result.current.selectedCitation).toBeNull();
    act(() => result.current.reset());
    expect(result.current.seed).toBeNull();
    expect(result.current.graph.papers).toHaveLength(0);
  });
});
