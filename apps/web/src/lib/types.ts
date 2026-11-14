export type CitationIntent = "background" | "method" | "result";

export interface Paper {
  id: string;
  doi: string | null;
  title: string;
  year: number | null;
  authors: string[];
  abstract: string | null;
  cited_by_count: number;
  landing_page_url: string | null;
}

export interface Citation {
  id: string;
  source: string;
  target: string;
  intent: CitationIntent | null;
  confidence: number | null;
  context_text: string | null;
  context_source_url: string | null;
}

export interface Graph {
  papers: Paper[];
  citations: Citation[];
}

export interface SearchResponse {
  papers: Paper[];
  total: number;
  page: number;
  per_page: number;
}

export interface Classification {
  intent: CitationIntent;
  confidence: number;
}

export interface SaveGraphRequest {
  name: string;
  seed_paper_id: string;
  graph: Graph;
  positions: Record<string, { x: number; y: number }>;
  expanded_nodes: string[];
  settings: Record<string, unknown>;
  filters: Record<string, unknown>;
}
