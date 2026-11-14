import type { ExpansionDirection } from "@/hooks/use-citation-graph";
import type { Paper } from "@/lib/types";

function externalUrl(value: string | null) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

export function PaperDetails({
  paper,
  isPreview,
  onExpand,
  expanding,
  expanded,
  expansionError,
}: {
  paper: Paper | null;
  isPreview: boolean;
  onExpand: (id: string, direction: ExpansionDirection) => void;
  expanding: string | null;
  expanded: Set<string>;
  expansionError: string | null;
}) {
  const publicationUrl = externalUrl(paper?.landing_page_url ?? null);
  return (
    <aside className="details" aria-label="Paper details">
      <p className="eyebrow">Paper details</p>
      {paper ? (
        <>
          <h2 className="paper-title">{paper.title}</h2>
          <p className="paper-meta">
            {paper.authors.join(", ") || "Authors unavailable"}
          </p>
          <p className="paper-meta">
            {paper.year ?? "Year unavailable"} ·{" "}
            {paper.cited_by_count.toLocaleString()} citations
          </p>
          {!isPreview && (
            <div className="paper-links">
              {publicationUrl && (
                <a href={publicationUrl} target="_blank" rel="noreferrer">
                  View publication ↗
                </a>
              )}
              <a
                href={`https://openalex.org/${paper.id}`}
                target="_blank"
                rel="noreferrer"
              >
                OpenAlex ↗
              </a>
            </div>
          )}
          <div className="abstract">
            <h3>Abstract</h3>
            <p>
              {paper.abstract ?? "An abstract is unavailable for this paper."}
            </p>
          </div>
          <div className="expansion-actions">
            <h3>Explore from this paper</h3>
            {(["references", "citations"] as const).map((direction) => {
              const key = `${paper.id}:${direction}`;
              const shown = expanded.has(key);
              return (
                <button
                  key={direction}
                  className="secondary-button"
                  onClick={() => onExpand(paper.id, direction)}
                  disabled={Boolean(expanding)}
                  aria-pressed={shown}
                >
                  {expanding === key
                    ? "Growing connections…"
                    : shown
                      ? direction === "references"
                        ? "Hide references"
                        : "Hide citing papers"
                      : direction === "references"
                        ? "Show references"
                        : "Show citing papers"}
                </button>
              );
            })}
            {expansionError && (
              <p className="feedback error expansion-error" role="alert">
                {expansionError} You can try again.
              </p>
            )}
          </div>
        </>
      ) : (
        <div className="details-empty">
          <div className="empty-symbol" aria-hidden="true">
            ▤
          </div>
          <h3>A closer look</h3>
          <p className="muted">
            Select a paper to see its authors, abstract, and publication
            details.
          </p>
        </div>
      )}
    </aside>
  );
}
