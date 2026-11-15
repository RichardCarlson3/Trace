"use client";

import { useState, type FormEvent, type RefObject } from "react";
import type { CitationCanvasHandle } from "@/components/graph/citation-canvas";
import type { useCitationGraph } from "@/hooks/use-citation-graph";
import { useBrowserLibrary } from "@/hooks/use-browser-library";
import type {
  GraphLayout,
  GraphSnapshot,
  LocalSavedGraph,
} from "@/lib/browser-library";

interface SavedResearchSession {
  version: number;
  initialLayout: GraphLayout | undefined;
  name: string;
  savedId: string | null;
  message: string | null;
  open: boolean;
}

// Keeps persistence-specific state out of the workspace's search/graph logic.
export function useSavedResearch({
  citationGraph,
  filters,
  onRestore,
  onOpen,
  canvasRef,
}: {
  citationGraph: ReturnType<typeof useCitationGraph>;
  filters: GraphSnapshot["filters"];
  onRestore: (saved: LocalSavedGraph) => void;
  onOpen: () => void;
  canvasRef: RefObject<CitationCanvasHandle | null>;
}) {
  const library = useBrowserLibrary();
  const [session, setSession] = useState<SavedResearchSession>({
    version: 0,
    initialLayout: undefined,
    name: "",
    savedId: null,
    message: null,
    open: false,
  });
  const canSave =
    Boolean(citationGraph.seed) &&
    !citationGraph.isPreview &&
    !citationGraph.loadingSeed &&
    !citationGraph.expanding;

  function close() {
    setSession((current) => ({ ...current, open: false }));
  }

  function startGraph(name = "") {
    setSession((current) => ({
      version: current.version + 1,
      initialLayout: undefined,
      name: name.slice(0, 120),
      savedId: null,
      message: null,
      open: false,
    }));
  }

  function openSaved(saved: LocalSavedGraph) {
    citationGraph.restore(saved);
    onRestore(saved);
    setSession((current) => ({
      version: current.version + 1,
      initialLayout: saved.layout,
      name: saved.name,
      savedId: saved.id,
      message: null,
      open: false,
    }));
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSave || !citationGraph.seed) return;
    const saved = library.saveGraph(
      session.name,
      {
        seed_paper_id: citationGraph.seed.id,
        graph: citationGraph.graph,
        selected_paper_id: citationGraph.selectedPaperId,
        expanded_nodes: [...citationGraph.expanded],
        edge_groups: citationGraph.edgeGroups,
        filters,
        layout: canvasRef.current?.getLayout() ?? {
          positions: {},
          viewport: null,
        },
      },
      session.savedId,
    );
    setSession((current) => ({
      ...current,
      savedId: saved?.id ?? current.savedId,
      message: saved ? `Saved “${saved.name}” in this browser.` : null,
    }));
  }

  return {
    library,
    session,
    canSave,
    isUpdate:
      session.savedId !== null &&
      library.savedGraphs.some((saved) => saved.id === session.savedId),
    hasGraph: Boolean(citationGraph.seed),
    close,
    startGraph,
    save,
    openSaved,
    setName: (name: string) =>
      setSession((current) => ({ ...current, name, message: null })),
    show: () => {
      onOpen();
      setSession((current) => ({ ...current, open: true, message: null }));
    },
    toggle: () => {
      if (!session.open) onOpen();
      setSession((current) => ({ ...current, open: !current.open }));
    },
    recordSearch: (query: string) => {
      library.recordSearch(query);
      close();
    },
    deleteGraph: (id: string) => {
      if (library.deleteGraph(id))
        setSession((current) => ({
          ...current,
          savedId: current.savedId === id ? null : current.savedId,
          message: null,
        }));
    },
  };
}
