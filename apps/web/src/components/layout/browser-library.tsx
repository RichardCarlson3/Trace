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
  onClose: () => void;
}) {
  return (
    <aside
      className={styles.panel}
      aria-label="Saved graphs"
      id="browser-library"
    >
      <div className={styles.heading}>
        <h2>Saved</h2>
        <button
          className="toolbar-button"
          onClick={onClose}
          aria-label="Close saved graphs"
        >
          Close
        </button>
      </div>
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
    </aside>
  );
}
