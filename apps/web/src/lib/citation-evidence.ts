import type { CitationContexts } from "./api";

/**
 * Why a classification response does or does not carry a passage.
 * Mirrors `evidence_outcome` in apps/api/app/services/citation_contexts.py.
 */
export type EvidenceOutcome =
  | "classified"
  | "classification_failed"
  | "rate_limited"
  | "provider_failed"
  | "identifier_resolution_failed"
  | "not_attempted"
  | "context_unavailable";

// A source was checked and holds no usable passage for this edge.
const coverage = new Set([
  "semantic_scholar_references_unavailable",
  "openalex_tei_content_unavailable",
  "openalex_relationship_not_verified",
  "tei_no_safe_body_sentence",
  "tei_bibliography_not_verified",
  "tei_ambiguous_bibliography",
  "tei_ambiguous_reference_list",
  "tei_conflicting_bibliography_identifier",
]);
// Paper or document identity could not be verified.
const identity = new Set([
  "ambiguous_paper_pair",
  "ambiguous_reference_identity",
  "openalex_work_identity_mismatch",
  "tei_document_identity_mismatch",
  "tei_unrecognized_header_identifier",
]);
// A source was deliberately not consulted.
const notAttempted = new Set([
  "semantic_scholar_disabled",
  "openalex_tei_disabled",
  "openalex_key_missing",
  "no_verified_example",
]);

export function evidenceOutcome(result: CitationContexts): EvidenceOutcome {
  if (result.contexts.length)
    return result.contexts.some((context) => context.classification)
      ? "classified"
      : "classification_failed";
  const reasons = [result.reason, result.fallback_reason].filter(
    (reason): reason is string => Boolean(reason),
  );
  // Transient failures first: a throttled source may still hold a passage.
  if (
    reasons.some(
      (reason) =>
        reason.includes("rate_limited") ||
        reason.endsWith("_http_429") ||
        reason.endsWith("_cooldown"),
    )
  )
    return "rate_limited";
  if (
    result.status === "example_not_found" ||
    (result.status === "provider_unavailable" &&
      reasons.length > 0 &&
      reasons.every((reason) => notAttempted.has(reason)))
  )
    return "not_attempted";
  if (
    result.status === "incomplete" ||
    reasons.some(
      (reason) =>
        !coverage.has(reason) &&
        !identity.has(reason) &&
        !notAttempted.has(reason),
    )
  )
    return "provider_failed";
  if (
    result.status === "unresolved_identifiers" ||
    reasons.some((reason) => identity.has(reason))
  )
    return "identifier_resolution_failed";
  return "context_unavailable";
}

/** Explanation shown after "Citation evidence unavailable." — never a claim of absence. */
export const outcomeExplanation: Partial<Record<EvidenceOutcome, string>> = {
  rate_limited:
    "An evidence source is rate-limiting requests, so not every source could be checked. This does not mean no passage exists; try again shortly.",
  provider_failed:
    "An evidence source failed or did not finish responding, so not every source could be checked. Try again later.",
  identifier_resolution_failed:
    "The two papers could not be matched to verified records in the evidence sources, so no passage could be checked for this link.",
  not_attempted: "Live evidence retrieval is turned off on this server.",
  context_unavailable:
    "No verified passage was found in the sources checked (Semantic Scholar and OpenAlex full text). The paper may still discuss this citation elsewhere.",
};

export const retryableOutcomes = new Set<EvidenceOutcome>([
  "rate_limited",
  "provider_failed",
]);
