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
  if (distance === 0) return 208;
  return Math.max(96, 182 - Math.min(distance ?? 5, 5) * 18);
}

export interface PositionedCircle {
  id: string;
  x: number;
  y: number;
  size: number;
}

export function spaceCircles(
  circles: PositionedCircle[],
  pinnedId: string | null,
  gap = 26,
): Map<string, { x: number; y: number }> {
  const placed = circles.map((circle) => ({
    ...circle,
    cx: circle.x + circle.size / 2,
    cy: circle.y + circle.size / 2,
  }));
  for (let pass = 0; pass < 64; pass += 1) {
    let collided = false;
    for (let i = 0; i < placed.length; i += 1) {
      for (let j = i + 1; j < placed.length; j += 1) {
        const a = placed[i];
        const b = placed[j];
        let dx = b.cx - a.cx;
        let dy = b.cy - a.cy;
        let distance = Math.hypot(dx, dy);
        const minimum = (a.size + b.size) / 2 + gap;
        if (distance >= minimum - 0.1) continue;
        collided = true;
        if (distance < 0.001) {
          const angle = (i * 17 + j * 31) * 2.39996;
          dx = Math.cos(angle);
          dy = Math.sin(angle);
          distance = 1;
        }
        const push = minimum - distance;
        const aWeight = a.id === pinnedId ? 0 : b.id === pinnedId ? 1 : 0.5;
        const bWeight = b.id === pinnedId ? 0 : a.id === pinnedId ? 1 : 0.5;
        a.cx -= (dx / distance) * push * aWeight;
        a.cy -= (dy / distance) * push * aWeight;
        b.cx += (dx / distance) * push * bWeight;
        b.cy += (dy / distance) * push * bWeight;
      }
    }
    if (!collided) break;
  }
  return new Map(
    placed.map((circle) => [
      circle.id,
      { x: circle.cx - circle.size / 2, y: circle.cy - circle.size / 2 },
    ]),
  );
}
