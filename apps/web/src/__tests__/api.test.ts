import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";

afterEach(() => vi.unstubAllGlobals());

describe("API client", () => {
  it("surfaces structured server errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ error: { message: "OpenAlex is busy" } }),
            { status: 503 },
          ),
        ),
    );
    await expect(api.search("science")).rejects.toThrow("OpenAlex is busy");
  });
  it("handles non-JSON errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("Bad gateway", { status: 502 })),
    );
    await expect(api.search("science")).rejects.toBeInstanceOf(ApiError);
  });
  it("handles network failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Network failed")),
    );
    await expect(api.health()).rejects.toThrow("Could not reach the API");
  });
  it("encodes search terms", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ papers: [], total: 0, page: 1, per_page: 10 }),
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    await api.search("graph & NLP");
    expect(fetchMock.mock.calls[0][0]).toContain("q=graph+%26+NLP");
  });
});
