import type { Citation, Paper } from "@/lib/types";

const intentNames = {
  background: "Background",
  method: "Method",
  result: "Result",
};

export function CitationDetails({
  citation,
  papers,
}: {
  citation: Citation;
  papers: Paper[];
}) {
  const citing = papers.find((paper) => paper.id === citation.source);
  const cited = papers.find((paper) => paper.id === citation.target);
  let sourceUrl: string | null = null;
  try {
    const url = new URL(citation.context_source_url ?? "");
    if (["http:", "https:"].includes(url.protocol)) sourceUrl = url.href;
  } catch {
    // Context provenance is optional; an invalid URL is not rendered as a link.
  }
  return (
    <aside className="details citation-details" aria-label="Citation details">
      <p className="eyebrow">Citation evidence</p>
      <h2 className="paper-title">Why these papers connect</h2>
      <p className="paper-meta">
        <strong>{citing?.title ?? citation.source}</strong> cites{" "}
        <strong>{cited?.title ?? citation.target}</strong>
      </p>
      <div className="intent-card">
        <span className={`intent-dot ${citation.intent ?? "unknown"}`} />
        <div>
          <span className="eyebrow">Predicted intent</span>
          <strong>
            {citation.intent ? intentNames[citation.intent] : "Unclassified"}
          </strong>
        </div>
      </div>
      {citation.context_text ? (
        <>
          <h3>Passage from the citing paper</h3>
          <blockquote className="context-quote">
            {citation.context_text}
          </blockquote>
          {sourceUrl && (
            <a href={sourceUrl} target="_blank" rel="noreferrer">
              View passage source ↗
            </a>
          )}
          {citation.confidence !== null && (
            <p className="muted model-note">
              Model score: {citation.confidence.toFixed(2)}. This score is not a
              calibrated probability of correctness.
            </p>
          )}
        </>
      ) : (
        <p className="muted evidence-empty">
          No citation passage is available for this relationship. TRACE leaves
          its purpose unclassified.
        </p>
      )}
    </aside>
  );
}
