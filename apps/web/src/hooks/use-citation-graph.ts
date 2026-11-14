"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { mergeGraphs } from "@/lib/graph";
import type { Citation, Graph, Paper } from "@/lib/types";

export type ExpansionDirection = "references" | "citations";

function expansionKey(id: string, direction: ExpansionDirection) {
  return `${id}:${direction}`;
}

function matchingNeighbors(
  graph: Graph,
  id: string,
  direction: ExpansionDirection,
): Graph {
  const citations = graph.citations.filter((citation) =>
    direction === "references"
      ? citation.source === id
      : citation.target === id,
  );
  const paperIds = new Set([id]);
  for (const citation of citations) {
    paperIds.add(citation.source);
    paperIds.add(citation.target);
  }
  return {
    papers: graph.papers.filter((paper) => paperIds.has(paper.id)),
    citations,
  };
}

async function fetchNeighbors(id: string, signal: AbortSignal): Promise<Graph> {
  try {
    return await api.neighbors(id, signal);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 501) throw error;
    const [references, citations] = await Promise.allSettled([
      api.references(id, signal),
      api.citations(id, signal),
    ]);
    if (references.status === "rejected" && citations.status === "rejected") {
      throw error;
    }
    return mergeGraphs(
      references.status === "fulfilled"
        ? references.value
        : { papers: [], citations: [] },
      citations.status === "fulfilled"
        ? citations.value
        : { papers: [], citations: [] },
    );
  }
}

export function useCitationGraph() {
  const [seed, setSeed] = useState<Paper | null>(null);
  const [isPreview, setIsPreview] = useState(false);
  const [graph, setGraph] = useState<Graph>({ papers: [], citations: [] });
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(
    null,
  );
  const [loadingSeed, setLoadingSeed] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [expanding, setExpanding] = useState<string | null>(null);
  const [expansionError, setExpansionError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [expansionOrigin, setExpansionOrigin] = useState<string | null>(null);
  const version = useRef(0);
  const seedRequest = useRef<AbortController | null>(null);
  const expansionRequest = useRef<AbortController | null>(null);
  const previewNeighbors = useRef<Graph | null>(null);

  useEffect(
    () => () => {
      seedRequest.current?.abort();
      expansionRequest.current?.abort();
    },
    [],
  );

  const openPaper = useCallback(async (paper: Paper) => {
    const requestVersion = ++version.current;
    seedRequest.current?.abort();
    expansionRequest.current?.abort();
    previewNeighbors.current = null;
    setIsPreview(false);
    const controller = new AbortController();
    seedRequest.current = controller;
    setSeed(paper);
    setGraph({ papers: [paper], citations: [] });
    setSelectedPaperId(paper.id);
    setSelectedCitationId(null);
    setExpanded(new Set());
    setExpansionOrigin(null);
    setExpanding(null);
    setExpansionError(null);
    setLoadError(null);
    setLoadingSeed(true);

    try {
      const neighbors = await fetchNeighbors(paper.id, controller.signal);
      if (version.current === requestVersion && !controller.signal.aborted) {
        setGraph((current) => mergeGraphs(current, neighbors));
      }
    } catch (error) {
      if (version.current === requestVersion && !controller.signal.aborted) {
        setLoadError(
          error instanceof ApiError && error.status === 501
            ? "Citation data is not available from the API yet. You can still inspect this paper."
            : error instanceof Error
              ? error.message
              : "Could not load this paper's citations.",
        );
      }
    } finally {
      if (version.current === requestVersion && !controller.signal.aborted) {
        setLoadingSeed(false);
      }
    }
  }, []);

  const openPreview = useCallback((initial: Graph, full: Graph) => {
    ++version.current;
    seedRequest.current?.abort();
    expansionRequest.current?.abort();
    previewNeighbors.current = full;
    setIsPreview(true);
    setSeed(initial.papers[0] ?? null);
    setGraph(initial);
    setSelectedPaperId(initial.papers[0]?.id ?? null);
    setSelectedCitationId(null);
    setExpanded(new Set());
    setExpansionOrigin(null);
    setExpanding(null);
    setExpansionError(null);
    setLoadError(null);
    setLoadingSeed(false);
  }, []);

  const expand = useCallback(
    async (id: string, direction: ExpansionDirection) => {
      const key = expansionKey(id, direction);
      if (!seed || expanding || expanded.has(key)) return;
      const requestVersion = version.current;
      const controller = new AbortController();
      expansionRequest.current = controller;
      setExpanding(key);
      setExpansionError(null);
      try {
        const neighbors =
          previewNeighbors.current ??
          (await fetchNeighbors(id, controller.signal));
        if (version.current !== requestVersion || controller.signal.aborted)
          return;
        setExpansionOrigin(id);
        setGraph((current) =>
          mergeGraphs(current, matchingNeighbors(neighbors, id, direction)),
        );
        setExpanded((current) => new Set(current).add(key));
      } catch (error) {
        if (version.current === requestVersion && !controller.signal.aborted) {
          setExpansionError(
            error instanceof Error
              ? error.message
              : "Could not expand this paper.",
          );
        }
      } finally {
        if (version.current === requestVersion && !controller.signal.aborted) {
          setExpanding(null);
        }
      }
    },
    [seed, expanding, expanded],
  );

  const selectPaper = useCallback((id: string) => {
    setSelectedPaperId(id);
    setSelectedCitationId(null);
    setExpansionError(null);
  }, []);

  const selectCitation = useCallback((id: string) => {
    setSelectedCitationId(id);
    setSelectedPaperId(null);
  }, []);

  const selectedPaper =
    graph.papers.find((paper) => paper.id === selectedPaperId) ?? null;
  const selectedCitation: Citation | null =
    graph.citations.find((citation) => citation.id === selectedCitationId) ??
    null;

  return {
    seed,
    isPreview,
    graph,
    selectedPaper,
    selectedPaperId,
    selectedCitation,
    selectedCitationId,
    loadingSeed,
    loadError,
    expanding,
    expansionError,
    expanded,
    expansionOrigin,
    openPaper,
    openPreview,
    expand,
    selectPaper,
    selectCitation,
  };
}
