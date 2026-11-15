"use client";

import { BrowserLibrary } from "./browser-library";
import styles from "./saved-research.module.css";
import type { useSavedResearch } from "@/hooks/use-saved-research";

export function SavedResearchControls({
  research,
}: {
  research: ReturnType<typeof useSavedResearch>;
}) {
  return (
    <div className={styles.tools}>
      <div className={styles.actions}>
        <button
          className="toolbar-button"
          aria-expanded={research.session.open}
          aria-controls="browser-library"
          onClick={research.toggle}
        >
          Saved
        </button>
      </div>
      {research.session.open && (
        <BrowserLibrary
          library={research.library}
          name={research.session.name}
          onNameChange={research.setName}
          canSave={Boolean(research.canSave)}
          isUpdate={research.isUpdate}
          savedMessage={research.session.message}
          onSave={research.save}
          onOpen={research.openSaved}
          onDelete={research.deleteGraph}
          onClose={research.close}
        />
      )}
    </div>
  );
}
