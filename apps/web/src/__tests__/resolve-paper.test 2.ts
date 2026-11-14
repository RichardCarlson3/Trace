import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { resolvePaper } from "@/lib/resolve-paper";
import type { Paper } from "@/lib/types";

vi.mock("@/lib/api", () => ({ api: { paper: vi.fn(), search: vi.fn() } }));

const paper: Paper = {
  id: "W123",
  doi: "https://doi.org/10.1234/example",
  title: "Example",
  year: 2024,
  authors: [],
  abstract: null,
  cited_by_count: 0,
  landing_page_url: "https://publisher.example/article/10.1234/example",
};

beforeEach(() => vi.clearAllMocks());

describe("article link resolution", () => {
  it("uses the paper endpoint for OpenAlex links", async () => {
    vi.mocked(api.paper).mockResolvedValue(paper);
    expect(await resolvePaper("https://openalex.org/W123")).toEqual(paper);
    expect(api.paper).toHaveBeenCalledWith("W123");
  });

  it("requires an exact DOI match from search results", async () => {
    vi.mocked(api.search).mockResolvedValue({
      papers: [paper],
      total: 1,
      page: 1,
      per_page: 10,
    });
    expect(await resolvePaper("https://doi.org/10.1234/example")).toEqual(
      paper,
    );
    await expect(resolvePaper("https://doi.org/10.1234/other")).rejects.toThrow(
      /could not match/i,
    );
  });
});
