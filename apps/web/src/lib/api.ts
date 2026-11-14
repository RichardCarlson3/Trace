import type { SearchResponse } from "./types";

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
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}/api/v1${path}`, {
      signal: signal ?? AbortSignal.timeout(35000),
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
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
  health: (signal?: AbortSignal) =>
    apiRequest<{ status: string; service: string }>("/health", signal),
  search: (query: string, signal?: AbortSignal) =>
    apiRequest<SearchResponse>(
      `/papers/search?${new URLSearchParams({ q: query })}`,
      signal,
    ),
};
