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

export function PaperDetails({ paper }: { paper: Paper | null }) {
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
          <div className="paper-links">
            {externalUrl(paper.landing_page_url) && (
              <a
                href={externalUrl(paper.landing_page_url)}
                target="_blank"
                rel="noreferrer"
              >
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
          <div className="abstract">
            <h3>Abstract</h3>
            <p>
              {paper.abstract ?? "An abstract is unavailable for this paper."}
            </p>
          </div>
          <p className="muted sidebar-note">
            Citation expansion is planned. Citation intent requires a genuine
            passage from the citing paper.
          </p>
        </>
      ) : (
        <div className="details-empty">
          <div className="empty-symbol" aria-hidden="true">
            ▤
          </div>
          <h3>A closer look</h3>
          <p className="muted">
            Select a paper to see its authors,
            <br />
            abstract, and publication details.
          </p>
        </div>
      )}
    </aside>
  );
}
