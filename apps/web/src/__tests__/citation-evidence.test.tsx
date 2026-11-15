import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CitationDetails } from "@/components/papers/citation-details";
import { api, type CitationContexts } from "@/lib/api";
import { evidenceOutcome } from "@/lib/citation-evidence";
import type { Citation } from "@/lib/types";

// Synthetic responses: only status/reason codes matter; no scholarly evidence.
function response(
  status: string,
  reason: string | null = null,
  fallback: string | null = null,
): CitationContexts {
  return {
    citing_paper_id: "W1",
    cited_paper_id: "W2",
    origin: "unavailable",
    status,
    reason,
    fallback_reason: fallback,
    contexts: [],
  };
}

const edge: Citation = {
  id: "W1-W2",
  source: "W1",
  target: "W2",
  intent: null,
  confidence: null,
  context_text: null,
  context_source_url: null,
};

afterEach(() => vi.restoreAllMocks());

describe("evidence outcome categories (mirror of the backend)", () => {
  it.each([
    [
      response(
        "provider_unavailable",
        "semantic_scholar_rate_limited",
        "tei_invalid_xml_or_identifiers",
      ),
      "rate_limited",
    ],
    [response("no_context", null, "openalex_tei_http_429"), "rate_limited"],
    [
      response(
        "provider_unavailable",
        "semantic_scholar_unavailable",
        "tei_no_safe_body_sentence",
      ),
      "provider_failed",
    ],
    [
      response("unresolved_identifiers", null, "tei_no_safe_body_sentence"),
      "identifier_resolution_failed",
    ],
    [
      response(
        "provider_unavailable",
        "semantic_scholar_disabled",
        "openalex_tei_disabled",
      ),
      "not_attempted",
    ],
    [
      response(
        "provider_unavailable",
        "semantic_scholar_references_unavailable",
        "openalex_tei_content_unavailable",
      ),
      "context_unavailable",
    ],
  ] as const)("%#: %s", (result, expected) => {
    expect(evidenceOutcome(result)).toBe(expected);
  });
});

describe("citation popup explains missing evidence", () => {
  it("says a rate limit is temporary and retries only when asked", async () => {
    const classify = vi
      .spyOn(api, "classifyCitation")
      .mockResolvedValue(
        response("provider_unavailable", "semantic_scholar_rate_limited"),
      );
    render(<CitationDetails citation={edge} papers={[]} onClose={() => {}} />);
    expect(
      await screen.findByText(/rate-limiting requests/),
    ).toBeInTheDocument();
    expect(screen.getByText(/does not mean no passage exists/)).toBeVisible();
    expect(classify).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(classify).toHaveBeenCalledTimes(2));
    expect(classify).toHaveBeenLastCalledWith("W1", "W2", expect.anything());
  });

  it("reports sources checked without claiming absence, and offers no retry", async () => {
    vi.spyOn(api, "classifyCitation").mockResolvedValue(
      response("no_context", null, "tei_no_safe_body_sentence"),
    );
    render(<CitationDetails citation={edge} papers={[]} onClose={() => {}} />);
    expect(
      await screen.findByText(
        /No verified passage was found in the sources checked/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/may still discuss this citation/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });
});
