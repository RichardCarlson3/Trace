import type { Citation, Paper } from "@/lib/types";

const intentNames = {
  background: "Background",
  method: "Method",
  result: "Result",
};

export function CitationDetails({
  citation,
  papers,
  onClose,
}: {
  citation: Citation;
  papers: Paper[];
  onClose: () => void;
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
  const excerpt = citation.context_text
    ?.trim()
    .split(/(?<=[.!?])\s+/)
    .slice(0, 2)
    .join(" ");
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
      <p className="citation-excerpt">
        {excerpt ||
          "No verified passage is available, so the reason for this citation is unknown."}
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
      {sourceUrl && excerpt && (
        <a href={sourceUrl} target="_blank" rel="noreferrer">
          View passage source ↗
        </a>
      )}
      {citation.confidence !== null && (
        <p className="muted model-note">
          Model score: {citation.confidence.toFixed(2)}; this is not a
          calibrated probability.
        </p>
      )}
    </aside>
  );
}
