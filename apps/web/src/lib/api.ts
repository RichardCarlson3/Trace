import type { Classification, Graph, Paper, SearchResponse } from "./types";

/** Fields consumed by the existing citation panel; predictions are per passage. */
export interface CitationContexts {
  citing_paper_id: string;
  cited_paper_id: string;
  origin: "live" | "memory_cache" | "verified_example" | "unavailable";
  // Existing response fields, read only to explain why no passage was shown.
  status?: string;
  reason?: string | null;
  fallback_reason?: string | null;
  contexts: {
    context_text: string;
    source: "semantic_scholar" | "openalex_tei";
    source_url: string;
    classification: Classification | null;
  }[];
}

const baseUrl = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiRequest<T>(
  path: string,
  signal?: AbortSignal,
  options?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}/api/v1${path}`, {
      ...options,
      signal: signal ?? AbortSignal.timeout(35000),
    });
  } catch (error) {
    // DOMException can come from a different realm than Error (e.g. a browser
    // frame); its name still identifies cancellation and deadline expiry.
    const name =
      typeof error === "object" && error !== null && "name" in error
        ? error.name
        : null;
    if (name === "AbortError") throw error;
    if (name === "TimeoutError")
      throw new ApiError("The API request timed out. Please try again.", 0);
    throw new ApiError(
      "Could not reach the API. Check that FastAPI is running on port 8000.",
      0,
    );
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      body?.error?.message || `API request failed (${response.status}).`,
      response.status,
    );
  }
  if (body === null)
    throw new ApiError("The API returned invalid JSON.", response.status);
  return body as T;
}

export const api = {
  classifyCitation: async (
    citingPaperId: string,
    citedPaperId: string,
    signal?: AbortSignal,
  ) => {
    const result = await apiRequest<CitationContexts>(
      "/citation-contexts/classify",
      AbortSignal.any([
        ...(signal ? [signal] : []),
        AbortSignal.timeout(120_000),
      ]),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          citing_paper_id: citingPaperId,
          cited_paper_id: citedPaperId,
          mode: "auto",
        }),
      },
    );
    if (
      result.citing_paper_id !== citingPaperId ||
      result.cited_paper_id !== citedPaperId ||
      !Array.isArray(result.contexts)
    ) {
      throw new ApiError(
        "The API returned evidence for a different relationship.",
        200,
      );
    }
    return result;
  },
  health: (signal?: AbortSignal) =>
    apiRequest<{ status: string; service: string }>("/health", signal),
  search: (query: string, signal?: AbortSignal) =>
    apiRequest<SearchResponse>(
      `/papers/search?${new URLSearchParams({ q: query })}`,
      signal,
    ),
  paper: (id: string, signal?: AbortSignal) =>
    apiRequest<Paper>(`/papers/${encodeURIComponent(id)}`, signal),
  neighbors: (id: string, signal?: AbortSignal) =>
    apiRequest<Graph>(`/papers/${encodeURIComponent(id)}/neighbors`, signal),
  references: (id: string, signal?: AbortSignal) =>
    apiRequest<Graph>(
      `/papers/${encodeURIComponent(id)}/references?limit=10&offset=0`,
      signal,
    ),
  citations: (id: string, signal?: AbortSignal) =>
    apiRequest<Graph>(
      `/papers/${encodeURIComponent(id)}/citations?limit=10`,
      signal,
    ),
};
