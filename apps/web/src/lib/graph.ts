import type { Citation, Graph, Paper } from "./types";

function citationKey(citation: Citation): string {
  return `${citation.source}:${citation.target}`;
}

export function mergeGraphs(current: Graph, incoming: Graph): Graph {
  const papers = new Map<string, Paper>(
    current.papers.map((paper) => [paper.id, paper]),
  );
  for (const paper of incoming.papers) {
    if (!papers.has(paper.id)) papers.set(paper.id, paper);
  }

  const citations = new Map<string, Citation>(
    current.citations.map((citation) => [citationKey(citation), citation]),
  );
  for (const citation of incoming.citations) {
    const key = citationKey(citation);
    const existing = citations.get(key);
    if (
      !existing ||
      (citation.context_text &&
        (!existing.context_text ||
          (citation.intent !== null && existing.intent === null)))
    ) {
      citations.set(key, citation);
    }
  }

  return { papers: [...papers.values()], citations: [...citations.values()] };
}

export type DirectionFilter = "all" | "references" | "citations";

export function filteredGraph(
  graph: Graph,
  seedId: string | null,
  direction: DirectionFilter,
  yearFrom: string,
  yearTo: string,
): Graph {
  const from = yearFrom ? Number(yearFrom) : null;
  const to = yearTo ? Number(yearTo) : null;
  const yearIds = new Set(
    graph.papers
      .filter(
        (paper) =>
          paper.id === seedId ||
          (from === null && to === null) ||
          (paper.year !== null &&
            (from === null || paper.year >= from) &&
            (to === null || paper.year <= to)),
      )
      .map((paper) => paper.id),
  );
  const citations = graph.citations.filter(
    (citation) =>
      yearIds.has(citation.source) &&
      yearIds.has(citation.target) &&
      (direction === "all" ||
        (direction === "references" && citation.source === seedId) ||
        (direction === "citations" && citation.target === seedId)),
  );
  const visibleIds =
    direction === "all"
      ? yearIds
      : new Set([
          seedId,
          ...citations.flatMap((citation) => [
            citation.source,
            citation.target,
          ]),
        ]);
  return {
    papers: graph.papers.filter((paper) => visibleIds.has(paper.id)),
    citations,
  };
}
