"use client";

import type { FormEvent } from "react";
import type { useBrowserLibrary } from "@/hooks/use-browser-library";
import type { LocalSavedGraph } from "@/lib/browser-library";
import styles from "./saved-research.module.css";

export function BrowserLibrary({
  library,
  name,
  onNameChange,
  canSave,
  isUpdate,
  savedMessage,
  onSave,
  onOpen,
  onDelete,
  onSearch,
  onClose,
}: {
  library: ReturnType<typeof useBrowserLibrary>;
  name: string;
  onNameChange: (name: string) => void;
  canSave: boolean;
  isUpdate: boolean;
  savedMessage: string | null;
  onSave: (event: FormEvent<HTMLFormElement>) => void;
  onOpen: (graph: LocalSavedGraph) => void;
  onDelete: (id: string) => void;
  onSearch: (query: string) => void;
  onClose: () => void;
}) {
  return (
    <aside
      className={styles.panel}
      aria-label="Saved graphs and recent searches"
      id="browser-library"
    >
      <div className={styles.heading}>
        <h2>Saved & recent</h2>
        <button
          className="toolbar-button"
          onClick={onClose}
          aria-label="Close saved graphs and recent searches"
        >
          Close
        </button>
      </div>
      <p className="muted">
        Saved in this browser on this computer. Clearing site data removes these
        items.
      </p>
      {canSave && (
        <form className={styles.save} onSubmit={onSave}>
          <label htmlFor="saved-graph-name">Graph name</label>
          <input
            id="saved-graph-name"
            value={name}
            onChange={(event) => onNameChange(event.target.value)}
            maxLength={120}
            required
          />
          <button
            className="primary-button"
            type="submit"
            disabled={!name.trim()}
          >
            {isUpdate ? "Update saved graph" : "Save graph"}
          </button>
        </form>
      )}
      {savedMessage && (
        <p className="feedback" role="status">
          {savedMessage}
        </p>
      )}
      <h3>Saved graphs</h3>
      {library.graphError && (
        <p className="feedback error" role="alert">
          {library.graphError}
        </p>
      )}
      {library.savedGraphs.length === 0 && (
        <p className="muted">
          No saved graphs yet. Open a paper, then save its graph here.
        </p>
      )}
      <ul className={styles.list}>
        {library.savedGraphs.map((graph) => (
          <li key={graph.id}>
            <button
              className={styles.open}
              onClick={() => onOpen(graph)}
              aria-label={`Open saved graph ${graph.name}`}
            >
              <strong>{graph.name}</strong>
              <span>
                {graph.graph.papers.length} papers ·{" "}
                {new Date(graph.saved_at).toLocaleDateString()}
              </span>
            </button>
            <button
              className={styles.remove}
              onClick={() => onDelete(graph.id)}
              aria-label={`Delete saved graph ${graph.name}`}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
      {library.graphError && library.savedGraphs.length === 0 && (
        <button className="toolbar-button" onClick={library.clearGraphs}>
          Clear saved graphs
        </button>
      )}
      <div className={styles.heading}>
        <h3>Recent searches</h3>
        <button
          className={styles.remove}
          onClick={library.clearSearches}
          disabled={!library.recentSearches.length && !library.searchError}
        >
          Clear history
        </button>
      </div>
      {library.searchError && (
        <p className="feedback error" role="alert">
          {library.searchError}
        </p>
      )}
      {library.recentSearches.length === 0 && (
        <p className="muted">Your latest searches will appear here.</p>
      )}
      <ul className={styles.list}>
        {library.recentSearches.map((item) => (
          <li key={item.query.toLowerCase()}>
            <button
              className={styles.open}
              onClick={() => onSearch(item.query)}
              aria-label={`Search again for ${item.query}`}
            >
              {item.query}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
