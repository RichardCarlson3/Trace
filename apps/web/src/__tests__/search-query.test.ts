import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { fuzzySearchQuery, normalizeSearchQuery } from "@/lib/search-query";
import { useResearch } from "@/hooks/use-research";
import type { SearchResponse } from "@/lib/types";

vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  api: { health: vi.fn().mockResolvedValue({ status: "ok" }), search: vi.fn() },
}));
const empty: SearchResponse = { papers: [], total: 0, page: 1, per_page: 10 };
// Synthetic provider response, never a claim about a real paper or search ranking.
const found: SearchResponse = {
  ...empty,
  total: 1,
  papers: [
    {
      id: "W1",
      title: "Synthetic neural networks fixture",
      doi: null,
      year: null,
      authors: [],
      abstract: null,
      cited_by_count: 0,
      landing_page_url: null,
    },
  ],
};
beforeEach(() => vi.resetAllMocks());

describe("paper search matching", () => {
  it("normalizes casing and whitespace while retaining words for provider stemming", () => {
    expect(normalizeSearchQuery("  NeUrAl   NETWORKS ")).toBe(
      "neural networks",
    );
    expect(normalizeSearchQuery("NEURAL NETWORK")).toBe("neural network");
    expect(fuzzySearchQuery("nerual netwroks")).toBe("nerual~2 netwroks~2");
    expect(fuzzySearchQuery("dna of 2024")).toBeNull();
    expect(fuzzySearchQuery("word ".repeat(25))).toBeNull();
    expect(fuzzySearchQuery("abcdefghij ".repeat(24))).toBeNull();
  });

  it.each([
    '"Exact Title"',
    "cat AND dog",
    "gene~1",
    "https://example.org/paper",
    "10.1234/abc",
    "W123",
  ])("preserves explicit syntax or identifiers: %s", (query) => {
    expect(normalizeSearchQuery(query)).toBe(query);
    expect(fuzzySearchQuery(query)).toBeNull();
  });

  it("makes one normalized search when the provider returns matches", async () => {
    vi.mocked(api.health).mockResolvedValue({
      status: "ok",
      service: "fixture",
    });
    vi.mocked(api.search).mockResolvedValue(found);
    const { result } = renderHook(() => useResearch());
    await act(() => result.current.search("NEURAL NETWORKS"));
    expect(api.search).toHaveBeenCalledExactlyOnceWith(
      "neural networks",
      expect.any(AbortSignal),
    );
    expect(result.current.result).toEqual(found);
    expect(result.current.searchNotice).toBeNull();
  });

  it("makes at most one fuzzy retry with the same deadline, retaining only returned metadata", async () => {
    vi.mocked(api.health).mockResolvedValue({
      status: "ok",
      service: "fixture",
    });
    vi.mocked(api.search)
      .mockResolvedValueOnce(empty)
      .mockResolvedValueOnce(found);
    const { result } = renderHook(() => useResearch());
    await act(() => result.current.search("NeRuAl netwroks"));
    const calls = vi.mocked(api.search).mock.calls;
    expect(calls.map(([query]) => query)).toEqual([
      "nerual netwroks",
      "nerual~2 netwroks~2",
    ]);
    expect(calls[0][1]).toBe(calls[1][1]);
    expect(result.current.result).toEqual(found);
    expect(result.current.searchNotice).toMatch(/Showing close matches/);
    expect(result.current.result?.papers[0].title).toBe(found.papers[0].title);
  });

  it("stops after an empty fuzzy retry and never retries a provider error", async () => {
    vi.mocked(api.health).mockResolvedValue({
      status: "ok",
      service: "fixture",
    });
    vi.mocked(api.search).mockResolvedValue(empty);
    const { result } = renderHook(() => useResearch());
    await act(() => result.current.search("netwroks"));
    expect(api.search).toHaveBeenCalledTimes(2);
    expect(result.current.result).toEqual(empty);
    expect(result.current.searchNotice).toBeNull();
    vi.mocked(api.search)
      .mockReset()
      .mockRejectedValue(new Error("Provider unavailable"));
    await act(() => result.current.search("another query"));
    expect(api.search).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBe("Provider unavailable");
  });

  it("does not let a stale fuzzy response replace a newer search", async () => {
    vi.mocked(api.health).mockResolvedValue({
      status: "ok",
      service: "fixture",
    });
    let finish!: (value: SearchResponse) => void;
    vi.mocked(api.search)
      .mockResolvedValueOnce(empty)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve;
          }),
      );
    const { result } = renderHook(() => useResearch());
    let pending!: Promise<void>;
    await act(async () => {
      pending = result.current.search("netwroks");
      await Promise.resolve();
    });
    const latest = {
      ...found,
      papers: [
        { ...found.papers[0], id: "W2", title: "Synthetic latest fixture" },
      ],
    };
    vi.mocked(api.search).mockResolvedValueOnce(latest);
    await act(() => result.current.search("latest"));
    await act(async () => {
      finish(found);
      await pending;
    });
    expect(result.current.result).toEqual(latest);
    expect(result.current.searchNotice).toBeNull();
  });
});
