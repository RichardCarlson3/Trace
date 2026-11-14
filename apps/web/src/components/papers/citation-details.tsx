import { useEffect, useState } from "react";
import { api, type CitationContexts } from "@/lib/api";
import type { Citation, Paper } from "@/lib/types";

const intentNames = {
  background: "Background",
  method: "Method",
  result: "Result",
};

export function CitationDetails({
  citation,
  papers,
  isPreview = false,
  onClose,
}: {
  citation: Citation;
  papers: Paper[];
  isPreview?: boolean;
  onClose: () => void;
}) {
  const citing = papers.find((paper) => paper.id === citation.source);
  const cited = papers.find((paper) => paper.id === citation.target);
  const { source, target } = citation;
  const pair = `${source}->${target}`;
  const [response, setResponse] = useState<{
    pair: string;
    result?: CitationContexts;
    error?: string;
  } | null>(null);

  useEffect(() => {
    if (isPreview) return;
    const controller = new AbortController();
    let active = true;
    // Defer transport so Strict Mode's immediate cleanup does not issue a POST.
    void Promise.resolve().then(async () => {
      if (!active) return;
      try {
        const result = await api.classifyCitation(
          source,
          target,
          controller.signal,
        );
        if (active) setResponse({ pair, result });
      } catch (error) {
        if (active)
          setResponse({
            pair,
            error:
              error instanceof Error
                ? error.message
                : "Citation request failed.",
          });
      }
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [source, target, pair, isPreview]);

  const current = response?.pair === pair ? response : null;
  const result = current?.result;
  // Display one passage and its own prediction, never an aggregate across texts.
  const passage =
    result?.contexts.find((context) => context.classification) ??
    result?.contexts[0];
  const prediction = passage?.classification;
  let sourceUrl: string | null = null;
  try {
    const url = new URL(passage?.source_url ?? "");
    if (["http:", "https:"].includes(url.protocol)) sourceUrl = url.href;
  } catch {
    // Context provenance is optional; an invalid URL is not rendered as a link.
  }
  return (
    <aside
      className="citation-popover floating-panel"
      aria-label="Citation details"
    >
      <div className="citation-popover-header">
        <p className="eyebrow">Citation connection</p>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close citation popup"
        >
          ×
        </button>
      </div>
      <p className="citation-connection">
        <strong>{citing?.title ?? citation.source}</strong> cites{" "}
        <strong>{cited?.title ?? citation.target}</strong>.
      </p>
      {isPreview ? (
        <p className="muted">
          Sample preview — live classification is disabled.
        </p>
      ) : !current ? (
        <p role="status">
          Retrieving citation evidence and classifying… This can take up to two
          minutes.
        </p>
      ) : current.error ? (
        <p className="feedback error" role="alert">
          Could not classify citation: {current.error} Close and select the edge
          to retry.
        </p>
      ) : (
        <>
          <p className="citation-excerpt">
            {passage?.context_text ||
              "Citation evidence unavailable. No verified passage was returned; intent and confidence are unknown."}
          </p>
          <div className="intent-card">
            <span className={`intent-dot ${prediction?.intent ?? "unknown"}`} />
            <div>
              <span className="eyebrow">Predicted intent</span>
              <strong>
                {prediction ? intentNames[prediction.intent] : "Unclassified"}
              </strong>
            </div>
          </div>
          {passage && (
            <p className="muted model-note">
              Source:{" "}
              {passage.source === "openalex_tei"
                ? "OpenAlex TEI"
                : "Semantic Scholar"}
              {result?.origin === "memory_cache"
                ? " · Backend cache"
                : result?.origin === "verified_example"
                  ? " · Recorded verified example"
                  : " · Live retrieval"}
              {result &&
                result.contexts.length > 1 &&
                ` · Passage ${result.contexts.indexOf(passage) + 1} of ${result.contexts.length}`}
              {!prediction &&
                " · Passage available; classification unavailable."}
            </p>
          )}
          {sourceUrl && passage && (
            <a href={sourceUrl} target="_blank" rel="noreferrer">
              View passage source ↗
            </a>
          )}
          {prediction && (
            <p className="muted model-note">
              Model confidence: {(prediction.confidence * 100).toFixed(2)}%;
              this is not a calibrated probability.
              <br />
              Model: {prediction.model_version}
            </p>
          )}
        </>
      )}
    </aside>
  );
}
