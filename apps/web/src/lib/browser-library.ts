import type { DirectionFilter } from "./graph";
import type { Citation, Graph, Paper } from "./types";

export const SAVED_GRAPHS_KEY = "trace.saved-graphs.v1";
export const RECENT_SEARCHES_KEY = "trace.recent-searches.v1";
export const LIBRARY_CHANGED = "trace-library-changed";

export interface GraphLayout {
  positions: Record<string, { x: number; y: number }>;
  viewport: { x: number; y: number; zoom: number } | null;
}

export interface GraphSnapshot {
  seed_paper_id: string;
  graph: Graph;
  expanded_nodes: string[];
  edge_groups: Record<string, string[]>;
  selected_paper_id: string | null;
  filters: { direction: DirectionFilter; year_from: string; year_to: string };
  layout: GraphLayout;
}

export interface LocalSavedGraph extends GraphSnapshot {
  id: string;
  name: string;
  saved_at: string;
}

export interface RecentSearch {
  query: string;
  searched_at: string;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function strings(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((item) => typeof item === "string")
  );
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function paper(value: unknown): value is Paper {
  return (
    record(value) &&
    typeof value.id === "string" &&
    /^W\d+$/.test(value.id) &&
    typeof value.title === "string" &&
    strings(value.authors) &&
    (value.year === null ||
      (finite(value.year) && Number.isInteger(value.year))) &&
    finite(value.cited_by_count) &&
    value.cited_by_count >= 0 &&
    nullableString(value.doi) &&
    nullableString(value.abstract) &&
    nullableString(value.landing_page_url)
  );
}

function citation(value: unknown): value is Citation {
  return (
    record(value) &&
    typeof value.id === "string" &&
    typeof value.source === "string" &&
    typeof value.target === "string" &&
    (value.intent === null ||
      (typeof value.intent === "string" &&
        ["background", "method", "result"].includes(value.intent))) &&
    (value.confidence === null ||
      (finite(value.confidence) &&
        value.confidence >= 0 &&
        value.confidence <= 1)) &&
    nullableString(value.context_text) &&
    nullableString(value.context_source_url)
  );
}

function timestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

export function isRecentSearch(value: unknown): value is RecentSearch {
  return (
    record(value) &&
    typeof value.query === "string" &&
    value.query.trim().length > 0 &&
    value.query.length <= 500 &&
    timestamp(value.searched_at)
  );
}

export function isSavedGraph(value: unknown): value is LocalSavedGraph {
  if (
    !record(value) ||
    typeof value.id !== "string" ||
    !value.id ||
    typeof value.name !== "string" ||
    !value.name.trim() ||
    value.name.length > 120 ||
    !timestamp(value.saved_at) ||
    typeof value.seed_paper_id !== "string" ||
    !record(value.graph) ||
    !Array.isArray(value.graph.papers) ||
    !value.graph.papers.every(paper) ||
    !Array.isArray(value.graph.citations) ||
    !value.graph.citations.every(citation) ||
    !strings(value.expanded_nodes) ||
    !record(value.edge_groups) ||
    !record(value.filters) ||
    !record(value.layout) ||
    !record(value.layout.positions)
  )
    return false;

  const ids = new Set(value.graph.papers.map((item) => item.id));
  const edgeIds = new Set(value.graph.citations.map((item) => item.id));
  const relationships = new Set(
    value.graph.citations.map((item) => `${item.source}:${item.target}`),
  );
  const validGroup = (key: string) => {
    const match = /^(W\d+):(references|citations)$/.exec(key);
    return match !== null && ids.has(match[1]);
  };
  const viewport = value.layout.viewport;
  return (
    ids.size === value.graph.papers.length &&
    ids.has(value.seed_paper_id) &&
    edgeIds.size === value.graph.citations.length &&
    relationships.size === value.graph.citations.length &&
    value.graph.citations.every(
      (item) => ids.has(item.source) && ids.has(item.target),
    ) &&
    (value.selected_paper_id === null ||
      (typeof value.selected_paper_id === "string" &&
        ids.has(value.selected_paper_id))) &&
    Object.entries(value.edge_groups).every(
      ([key, edges]) =>
        validGroup(key) &&
        strings(edges) &&
        edges.every((edge) => relationships.has(edge)),
    ) &&
    value.expanded_nodes.every(
      (key) =>
        validGroup(key) && Object.hasOwn(value.edge_groups as object, key),
    ) &&
    typeof value.filters.direction === "string" &&
    ["all", "references", "citations"].includes(value.filters.direction) &&
    typeof value.filters.year_from === "string" &&
    typeof value.filters.year_to === "string" &&
    Object.entries(value.layout.positions).every(
      ([id, position]) =>
        ids.has(id) &&
        record(position) &&
        finite(position.x) &&
        finite(position.y),
    ) &&
    (viewport === null ||
      (record(viewport) &&
        finite(viewport.x) &&
        finite(viewport.y) &&
        finite(viewport.zoom) &&
        viewport.zoom >= 0.15 &&
        viewport.zoom <= 2))
  );
}

export function parseCollection<T>(
  raw: string | null,
  validate: (value: unknown) => value is T,
): T[] {
  if (raw === null) return [];
  const value: unknown = JSON.parse(raw);
  if (
    !record(value) ||
    value.version !== 1 ||
    !Array.isArray(value.items) ||
    !value.items.every(validate)
  ) {
    throw new Error("Stored data has an unsupported or damaged format.");
  }
  return value.items;
}

export function writeCollection<T>(key: string, items: T[]) {
  // setItem is atomic: a quota failure leaves the previous saved value intact.
  window.localStorage.setItem(key, JSON.stringify({ version: 1, items }));
  window.dispatchEvent(new Event(LIBRARY_CHANGED));
}

export function addRecentSearch(
  items: RecentSearch[],
  query: string,
): RecentSearch[] {
  const trimmed = query.trim();
  if (!trimmed || trimmed.length > 500) return items;
  return [
    { query: trimmed, searched_at: new Date().toISOString() },
    ...items.filter(
      (item) => item.query.toLowerCase() !== trimmed.toLowerCase(),
    ),
  ].slice(0, 20);
}
