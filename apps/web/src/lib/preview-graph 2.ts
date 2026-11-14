import type { Citation, Graph, Paper } from "./types";

// Development-only UI fixture. These are deliberately labeled sample papers.
// They are not academic records and must never appear in a judged research demo.
function samplePaper(id: string, title: string, year: number): Paper {
  return {
    id,
    doi: null,
    title,
    year,
    authors: ["UI sample"],
    abstract:
      "Sample data for checking the graph interface while the API is built.",
    cited_by_count: 0,
    landing_page_url: null,
  };
}

function sampleCitation(source: string, target: string): Citation {
  return {
    id: `${source}-${target}`,
    source,
    target,
    intent: null,
    confidence: null,
    context_text: null,
    context_source_url: null,
  };
}

const papers = [
  samplePaper("W1", "UI sample: Starting paper", 2024),
  samplePaper("W2", "UI sample: Earlier method", 2021),
  samplePaper("W3", "UI sample: Later study", 2025),
  samplePaper("W4", "UI sample: Foundational work", 2018),
  samplePaper("W5", "UI sample: Follow-up research", 2026),
  samplePaper("W6", "UI sample: Shared reference", 2020),
];

export const previewInitialGraph: Graph = {
  papers: papers.slice(0, 3),
  citations: [sampleCitation("W1", "W2"), sampleCitation("W3", "W1")],
};

export const previewFullGraph: Graph = {
  papers,
  citations: [
    ...previewInitialGraph.citations,
    sampleCitation("W2", "W4"),
    sampleCitation("W3", "W5"),
    sampleCitation("W1", "W6"),
    sampleCitation("W5", "W2"),
    sampleCitation("W6", "W4"),
  ],
};
