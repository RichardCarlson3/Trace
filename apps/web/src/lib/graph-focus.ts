import type { Citation, Graph } from "./types";

export function relationshipKey(citation: Citation): string {
  return `${citation.source}:${citation.target}`;
}

export function directionKeys(
  graph: Graph,
  id: string,
  direction: "references" | "citations",
) {
  return graph.citations
    .filter((citation) =>
      direction === "references"
        ? citation.source === id
        : citation.target === id,
    )
    .map(relationshipKey);
}

export function visibleExpansionGraph(
  graph: Graph,
  seedId: string | null,
  groups: Record<string, string[]>,
  active: Set<string>,
): Graph {
  if (!seedId) return { papers: [], citations: [] };
  const enabled = new Set([...active].flatMap((key) => groups[key] ?? []));
  const candidates = graph.citations.filter((citation) =>
    enabled.has(relationshipKey(citation)),
  );
  const connected = new Set([seedId]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const citation of candidates) {
      if (connected.has(citation.source) && !connected.has(citation.target)) {
        connected.add(citation.target);
        changed = true;
      } else if (
        connected.has(citation.target) &&
        !connected.has(citation.source)
      ) {
        connected.add(citation.source);
        changed = true;
      }
    }
  }
  return {
    papers: graph.papers.filter((paper) => connected.has(paper.id)),
    citations: candidates.filter(
      (citation) =>
        connected.has(citation.source) && connected.has(citation.target),
    ),
  };
}

export function graphDistances(
  graph: Graph,
  focusId: string | null,
): Map<string, number> {
  const distances = new Map<string, number>();
  if (!focusId) return distances;
  const neighbors = new Map<string, string[]>();
  for (const citation of graph.citations) {
    neighbors.set(citation.source, [
      ...(neighbors.get(citation.source) ?? []),
      citation.target,
    ]);
    neighbors.set(citation.target, [
      ...(neighbors.get(citation.target) ?? []),
      citation.source,
    ]);
  }
  const queue = [focusId];
  distances.set(focusId, 0);
  for (let index = 0; index < queue.length; index += 1) {
    const id = queue[index];
    for (const neighbor of neighbors.get(id) ?? []) {
      if (distances.has(neighbor)) continue;
      distances.set(neighbor, (distances.get(id) ?? 0) + 1);
      queue.push(neighbor);
    }
  }
  return distances;
}

export function paperSize(distance: number | undefined): number {
  if (distance === 0) return 204;
  if (distance === 1) return 154;
  if (distance === 2) return 126;
  if (distance === 3) return 108;
  return 92;
}
