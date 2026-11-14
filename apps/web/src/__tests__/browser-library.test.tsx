import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useBrowserLibrary } from "@/hooks/use-browser-library";
import { useCitationGraph } from "@/hooks/use-citation-graph";
import { api } from "@/lib/api";
import {
  addRecentSearch,
  isSavedGraph,
  parseCollection,
  SAVED_GRAPHS_KEY,
  type GraphSnapshot,
} from "@/lib/browser-library";
import type { Graph, Paper } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return { ...original, api: { ...original.api, neighbors: vi.fn() } };
});

// Synthetic offline fixture; these records do not represent research metadata.
const seed: Paper = {
  id: "W1",
  title: "Synthetic saved seed",
  doi: null,
  year: 2024,
  authors: [],
  abstract: null,
  cited_by_count: 0,
  landing_page_url: null,
};
const snapshot: GraphSnapshot = {
  seed_paper_id: seed.id,
  graph: {
    papers: [seed, { ...seed, id: "W2", title: "Synthetic reference" }],
    citations: [
      {
        id: "W1-W2",
        source: "W1",
        target: "W2",
        intent: null,
        confidence: null,
        context_text: null,
        context_source_url: null,
      },
    ],
  },
  edge_groups: { "W1:references": ["W1:W2"] },
  expanded_nodes: [], // This branch was hidden when saved.
  selected_paper_id: "W1",
  filters: { direction: "references", year_from: "2020", year_to: "2025" },
  layout: {
    positions: { W1: { x: 123, y: -40 }, W2: { x: 400, y: 90 } },
    viewport: { x: 11, y: 20, zoom: 0.7 },
  },
};

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
});

describe("browser research library", () => {
  it("persists, updates, and deletes graph snapshots across mounts", () => {
    const first = renderHook(() => useBrowserLibrary());
    let id: string;
    act(() => {
      id = first.result.current.saveGraph("My research", snapshot, null)!.id;
    });
    first.unmount();
    const second = renderHook(() => useBrowserLibrary());
    expect(second.result.current.savedGraphs[0]).toMatchObject({
      ...snapshot,
      id: id!,
      name: "My research",
    });
    act(() => {
      second.result.current.saveGraph("Renamed", snapshot, id!);
    });
    expect(second.result.current.savedGraphs).toHaveLength(1);
    expect(second.result.current.savedGraphs[0].name).toBe("Renamed");
    act(() => {
      second.result.current.deleteGraph(id!);
    });
    second.unmount();
    const third = renderHook(() => useBrowserLibrary());
    expect(third.result.current.savedGraphs).toEqual([]);
  });

  it("keeps the latest 20 searches, deduplicates, and persists cleared history", () => {
    let items = addRecentSearch([], "  Synthetic query  ");
    items = addRecentSearch(items, "synthetic QUERY");
    expect(items).toHaveLength(1);
    for (let index = 0; index < 25; index++)
      items = addRecentSearch(items, `Synthetic ${index}`);
    expect(items).toHaveLength(20);
    expect(items[0].query).toBe("Synthetic 24");
    const first = renderHook(() => useBrowserLibrary());
    act(() => {
      first.result.current.recordSearch("Synthetic query");
    });
    first.unmount();
    const second = renderHook(() => useBrowserLibrary());
    expect(second.result.current.recentSearches[0].query).toBe(
      "Synthetic query",
    );
    act(() => {
      second.result.current.clearSearches();
    });
    second.unmount();
    expect(
      renderHook(() => useBrowserLibrary()).result.current.recentSearches,
    ).toEqual([]);
  });

  it("retains previous snapshots and reports quota failures", () => {
    const { result } = renderHook(() => useBrowserLibrary());
    act(() => {
      result.current.saveGraph("Original", snapshot, null);
    });
    const previous = window.localStorage.getItem(SAVED_GRAPHS_KEY);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Full", "QuotaExceededError");
    });
    act(() => {
      expect(result.current.saveGraph("New", snapshot, null)).toBeNull();
    });
    expect(result.current.graphError).toMatch(/Existing saves have been kept/);
    expect(window.localStorage.getItem(SAVED_GRAPHS_KEY)).toBe(previous);
    expect(result.current.savedGraphs[0].name).toBe("Original");
  });

  it("does not overwrite damaged or future-version data", () => {
    const previous = JSON.stringify({ version: 9, items: [] });
    window.localStorage.setItem(SAVED_GRAPHS_KEY, previous);
    const { result } = renderHook(() => useBrowserLibrary());
    expect(result.current.graphError).toMatch(/Could not read/);
    act(() => {
      expect(result.current.saveGraph("New", snapshot, null)).toBeNull();
    });
    expect(window.localStorage.getItem(SAVED_GRAPHS_KEY)).toBe(previous);
    act(() => {
      result.current.clearGraphs();
    });
    expect(result.current.graphError).toBeNull();
  });

  it("rejects malformed graph data before it can reach the canvas", () => {
    const saved = {
      ...snapshot,
      id: "fixture",
      name: "Fixture",
      saved_at: new Date().toISOString(),
    };
    expect(isSavedGraph(saved)).toBe(true);
    expect(
      isSavedGraph({ ...saved, graph: { ...saved.graph, papers: [] } }),
    ).toBe(false);
    expect(
      isSavedGraph({
        ...saved,
        graph: {
          ...saved.graph,
          citations: [{ ...saved.graph.citations[0], target: "W999" }],
        },
      }),
    ).toBe(false);
    expect(
      isSavedGraph({
        ...saved,
        layout: { positions: {}, viewport: { x: 0, y: 0, zoom: -1 } },
      }),
    ).toBe(false);
    expect(() => parseCollection("not json", isSavedGraph)).toThrow();
  });

  it("restores hidden branches offline and ignores an earlier in-flight request", async () => {
    let finish: (graph: Graph) => void = () => {};
    vi.mocked(api.neighbors).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const { result } = renderHook(() => useCitationGraph());
    let pending: Promise<void>;
    act(() => {
      pending = result.current.openPaper({ ...seed, id: "W999" });
    });
    act(() => {
      result.current.restore(snapshot);
    });
    expect(result.current.graph).toEqual(snapshot.graph);
    expect(result.current.visibleGraph.papers.map((paper) => paper.id)).toEqual(
      ["W1"],
    );
    await act(async () => {
      await result.current.expand("W1", "references");
    });
    expect(result.current.visibleGraph.papers).toHaveLength(2);
    expect(api.neighbors).toHaveBeenCalledTimes(1);
    await act(async () => {
      finish({ papers: [{ ...seed, id: "W999" }], citations: [] });
      await pending;
    });
    expect(result.current.seed?.id).toBe("W1");
    expect(result.current.graph).toEqual(snapshot.graph);
  });
});
