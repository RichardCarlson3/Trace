import { StrictMode, type ComponentProps } from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResearchWorkspace } from "@/components/layout/research-workspace";
import { CitationDetails } from "@/components/papers/citation-details";
import { CitationCanvas } from "@/components/graph/citation-canvas";
import { api, type CitationContexts } from "@/lib/api";
import type { Citation, Paper } from "@/lib/types";
import recorded from "../../../../docs/reports/openalex_fallback_live.json";
import examples from "../../../../apps/api/app/examples/citation_contexts.json";

// Offline regression fixture: the real recorded BART TEI response, no live calls.
const bart = recorded.response as CitationContexts;
const edge: Citation = {
  id: "bart-word2vec",
  source: bart.citing_paper_id,
  target: bart.cited_paper_id,
  intent: null,
  confidence: null,
  context_text: null,
  context_source_url: null,
};
// Synthetic reverse edge is only a selection-race fixture, never scholarly evidence.
const other = {
  ...edge,
  id: "offline-unavailable",
  source: edge.target,
  target: edge.source,
};
const unavailable = {
  ...bart,
  citing_paper_id: other.source,
  cited_paper_id: other.target,
  contexts: [],
  available: false,
  status: "no_context",
  origin: "unavailable",
  source: "semantic_scholar",
  reason: "no_citation_contexts",
};
const papers: Paper[] = [
  recorded.response.citing_mapping,
  recorded.response.cited_mapping,
].map((mapping) => ({
  id: mapping.openalex_id,
  title: mapping.title,
  doi: mapping.doi,
  year: null,
  authors: [],
  abstract: null,
  cited_by_count: 0,
  landing_page_url: null,
}));

vi.mock("@/components/graph/citation-canvas", () => ({
  CitationCanvas: ({
    visibleGraph,
    onSelectCitation,
  }: ComponentProps<typeof CitationCanvas>) => (
    <div aria-label="Citation graph">
      {visibleGraph.citations.map((citation) => (
        <button
          key={citation.id}
          onClick={() => onSelectCitation(citation.id, 100, 100)}
        >
          Select {citation.id}
        </button>
      ))}
    </div>
  ),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function backend(classify: () => Promise<Response>) {
  const fetchMock = vi.fn((url: string, options?: RequestInit) => {
    if (url.endsWith("/citation-contexts/classify")) return classify();
    if (url.endsWith("/health"))
      return Promise.resolve(Response.json({ status: "ok" }));
    if (url.includes("/papers/search?"))
      return Promise.resolve(
        Response.json({ papers: [papers[0]], total: 1, page: 1, per_page: 10 }),
      );
    if (url.endsWith("/neighbors"))
      return Promise.resolve(
        Response.json({ papers, citations: [edge, other] }),
      );
    throw new Error(`Unexpected offline request: ${url} ${options?.method}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function openBart() {
  render(<ResearchWorkspace />);
  fireEvent.change(screen.getByRole("searchbox"), {
    target: { value: "BART" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Explore" }));
  fireEvent.click(
    await screen.findByRole("button", { name: /BART: Denoising/ }),
  );
  await screen.findByRole("button", { name: "Select bart-word2vec" });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("selected citation classification (offline)", () => {
  it("POSTs only the selected direction, waits, displays BART and preserves backend cache provenance on reselection", async () => {
    const pending = deferred<Response>();
    const classify = vi
      .fn()
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValue(Response.json({ ...bart, origin: "memory_cache" }));
    const fetchMock = backend(classify);
    await openBart();
    expect(classify).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Select bart-word2vec" }),
    );
    expect(
      screen.getByText(/Retrieving citation evidence/),
    ).toBeInTheDocument();
    expect(screen.queryByText("Unclassified")).not.toBeInTheDocument();
    await waitFor(() => expect(classify).toHaveBeenCalledTimes(1));
    const request = fetchMock.mock.calls.find(([url]) =>
      url.endsWith("/citation-contexts/classify"),
    )!;
    expect(request[0]).toBe(
      "http://localhost:8000/api/v1/citation-contexts/classify",
    );
    expect(request[1]).toMatchObject({
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    expect(JSON.parse(request[1]!.body as string)).toEqual({
      citing_paper_id: edge.source,
      cited_paper_id: edge.target,
      mode: "auto",
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Select bart-word2vec" }),
    );
    expect(classify).toHaveBeenCalledTimes(1);
    await act(async () => pending.resolve(Response.json(bart)));
    expect(await screen.findByText("Background")).toBeInTheDocument();
    expect(screen.getByText(/Model confidence: 88.44%/)).toBeInTheDocument();
    expect(screen.getByText(bart.contexts[0].context_text)).toBeInTheDocument();
    expect(screen.getByText(/Source: OpenAlex TEI/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /View passage source/ }),
    ).toHaveAttribute("href", bart.contexts[0].source_url);
    fireEvent.click(
      screen.getByRole("button", { name: "Close citation popup" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Select bart-word2vec" }),
    );
    expect(await screen.findByText(/Backend cache/)).toBeInTheDocument();
    expect(classify).toHaveBeenCalledTimes(2);
  });

  it("aborts previous selection and ignores a late successful response after unavailable evidence", async () => {
    const old = deferred<Response>();
    const classify = vi
      .fn()
      .mockReturnValueOnce(old.promise)
      .mockResolvedValueOnce(Response.json(unavailable));
    const fetchMock = backend(classify);
    await openBart();
    fireEvent.click(
      screen.getByRole("button", { name: "Select bart-word2vec" }),
    );
    await waitFor(() => expect(classify).toHaveBeenCalledTimes(1));
    fireEvent.click(
      screen.getByRole("button", { name: "Select offline-unavailable" }),
    );
    expect(
      await screen.findByText(/Citation evidence unavailable\./),
    ).toBeInTheDocument();
    const signal = fetchMock.mock.calls.find(([url]) =>
      url.endsWith("/citation-contexts/classify"),
    )![1]!.signal;
    expect(signal!.aborted).toBe(true);
    await act(async () => old.resolve(Response.json(bart)));
    expect(screen.queryByText("Background")).not.toBeInTheDocument();
    expect(screen.queryByText(/88.44/)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders Semantic Scholar evidence with its recorded-example label", async () => {
    // Genuine saved S2 passage, intentionally unclassified in that capture.
    const s2: CitationContexts = {
      ...examples.examples[0],
      available: true,
      fallback_reason: null,
    } as CitationContexts;
    backend(async () => Response.json(s2));
    render(
      <CitationDetails
        citation={{
          ...edge,
          source: s2.citing_paper_id,
          target: s2.cited_paper_id,
        }}
        papers={[]}
        onClose={() => {}}
      />,
    );
    expect(
      await screen.findByText(/Recorded verified example/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Source: Semantic Scholar/)).toBeInTheDocument();
    expect(screen.getByText(s2.contexts[0].context_text)).toBeInTheDocument();
    expect(
      screen.getByText(/Passage available; classification unavailable/),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Citation evidence unavailable\./),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/Model confidence/)).not.toBeInTheDocument();
  });

  it("keeps API failures distinct from unavailable evidence and never retries automatically", async () => {
    const classify = vi.fn(async () =>
      Response.json(
        { error: { message: "Provider unavailable" } },
        { status: 503 },
      ),
    );
    backend(classify);
    await openBart();
    fireEvent.click(
      screen.getByRole("button", { name: "Select bart-word2vec" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not classify citation: Provider unavailable",
    );
    expect(
      screen.queryByText(/Citation evidence unavailable\./),
    ).not.toBeInTheDocument();
    expect(classify).toHaveBeenCalledTimes(1);
  });

  it("does not duplicate requests during Strict Mode's effect probe and cancels on close", async () => {
    const pending = deferred<Response>();
    const classify = vi.fn(() => pending.promise);
    const fetchMock = backend(classify);
    const { unmount } = render(
      <CitationDetails citation={edge} papers={papers} onClose={() => {}} />,
      { wrapper: StrictMode },
    );
    await waitFor(() => expect(classify).toHaveBeenCalledTimes(1));
    expect(
      screen.getByText(/Retrieving citation evidence/),
    ).toBeInTheDocument();
    unmount();
    expect(fetchMock.mock.calls[0][1]!.signal!.aborted).toBe(true);
    await act(async () => pending.resolve(Response.json(bart)));
    expect(screen.queryByText("Background")).not.toBeInTheDocument();
    expect(classify).toHaveBeenCalledTimes(1);
  });

  it("stays loading through a ten-second retrieval", async () => {
    vi.useFakeTimers();
    backend(
      () =>
        new Promise((resolve) =>
          setTimeout(() => resolve(Response.json(bart)), 10_000),
        ),
    );
    render(
      <CitationDetails citation={edge} papers={papers} onClose={() => {}} />,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9999);
    });
    expect(
      screen.getByText(/Retrieving citation evidence/),
    ).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(screen.getByText("Background")).toBeInTheDocument();
  });

  it("reports the two-minute deadline separately from network failure", async () => {
    const timeout = vi.spyOn(AbortSignal, "timeout");
    backend(async () => {
      throw new DOMException("deadline", "TimeoutError");
    });
    await expect(
      api.classifyCitation(edge.source, edge.target),
    ).rejects.toThrow("timed out");
    expect(timeout).toHaveBeenCalledWith(120_000);
  });

  it("rejects mismatched relationship evidence instead of displaying a prediction", async () => {
    backend(async () => Response.json({ ...bart, cited_paper_id: "W999" }));
    render(
      <CitationDetails citation={edge} papers={papers} onClose={() => {}} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "different relationship",
    );
    expect(screen.queryByText("Background")).not.toBeInTheDocument();
  });

  it("never requests classification for sample preview edges", async () => {
    const classify = vi.fn();
    backend(classify);
    render(
      <CitationDetails
        citation={edge}
        papers={papers}
        isPreview
        onClose={() => {}}
      />,
    );
    await act(async () => {});
    expect(screen.getByText(/Sample preview/)).toBeInTheDocument();
    expect(classify).not.toHaveBeenCalled();
  });
});
