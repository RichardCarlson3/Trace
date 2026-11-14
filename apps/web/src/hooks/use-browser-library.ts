"use client";

import { useMemo, useState, useSyncExternalStore } from "react";
import {
  addRecentSearch,
  isRecentSearch,
  isSavedGraph,
  LIBRARY_CHANGED,
  parseCollection,
  RECENT_SEARCHES_KEY,
  SAVED_GRAPHS_KEY,
  writeCollection,
  type GraphSnapshot,
  type LocalSavedGraph,
} from "@/lib/browser-library";

function subscribe(notify: () => void) {
  window.addEventListener("storage", notify);
  window.addEventListener(LIBRARY_CHANGED, notify);
  return () => {
    window.removeEventListener("storage", notify);
    window.removeEventListener(LIBRARY_CHANGED, notify);
  };
}

function snapshot(key: string) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return "storage unavailable";
  }
}

function useCollection<T>(
  key: string,
  validate: (value: unknown) => value is T,
) {
  const raw = useSyncExternalStore(
    subscribe,
    () => snapshot(key),
    () => null,
  );
  const [actionError, setActionError] = useState<string | null>(null);
  const data = useMemo(() => {
    try {
      return { items: parseCollection(raw, validate), error: null };
    } catch {
      return {
        items: [] as T[],
        error:
          "Could not read this browser's saved data. Storage may be blocked, or the data may be damaged.",
      };
    }
  }, [raw, validate]);

  function update(change: (items: T[]) => T[]) {
    try {
      // Read again so another tab's changes are included in this write.
      const current = parseCollection(
        window.localStorage.getItem(key),
        validate,
      );
      writeCollection(key, change(current));
      setActionError(null);
      return true;
    } catch {
      setActionError(
        "Could not save changes in this browser. Storage may be full, blocked, or damaged. Existing saves have been kept.",
      );
      return false;
    }
  }

  function clear() {
    try {
      window.localStorage.removeItem(key);
      window.dispatchEvent(new Event(LIBRARY_CHANGED));
      setActionError(null);
    } catch {
      setActionError("Could not clear this browser's saved data.");
    }
  }

  return { items: data.items, error: actionError ?? data.error, update, clear };
}

export function useBrowserLibrary() {
  const graphs = useCollection(SAVED_GRAPHS_KEY, isSavedGraph);
  const searches = useCollection(RECENT_SEARCHES_KEY, isRecentSearch);

  function saveGraph(
    name: string,
    graph: GraphSnapshot,
    existingId: string | null,
  ): LocalSavedGraph | null {
    let saved: LocalSavedGraph | null = null;
    const success = graphs.update((items) => {
      const next: LocalSavedGraph = {
        ...graph,
        id: existingId ?? crypto.randomUUID(),
        name: name.trim(),
        saved_at: new Date().toISOString(),
      };
      if (!isSavedGraph(next))
        throw new Error("The graph snapshot is invalid.");
      saved = next;
      return [next, ...items.filter((item) => item.id !== next.id)];
    });
    return success ? saved : null;
  }

  return {
    savedGraphs: graphs.items,
    recentSearches: searches.items,
    graphError: graphs.error,
    searchError: searches.error,
    saveGraph,
    deleteGraph: (id: string) =>
      graphs.update((items) => items.filter((item) => item.id !== id)),
    recordSearch: (query: string) =>
      searches.update((items) => addRecentSearch(items, query)),
    clearSearches: searches.clear,
    clearGraphs: graphs.clear,
  };
}
