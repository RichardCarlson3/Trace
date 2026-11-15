"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import type { useBrowserLibrary } from "@/hooks/use-browser-library";
import styles from "./paper-search.module.css";

export function PaperSearch({
  query,
  onChange,
  onSubmit,
  onSearch,
  busy,
  library,
}: {
  query: string;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSearch: (value: string) => void;
  busy: boolean;
  library: ReturnType<typeof useBrowserLibrary>;
}) {
  const [open, setOpen] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const history = useRef<HTMLDivElement>(null);
  const focusHistory = useRef(false);
  const id = useId();
  const items = library.recentSearches
    .filter((item) =>
      item.query.toLowerCase().includes(query.trim().toLowerCase()),
    )
    .slice(0, 8);
  const visible =
    open && !busy && (items.length > 0 || Boolean(library.searchError));

  useEffect(() => {
    if (visible && focusHistory.current) {
      focusHistory.current = false;
      history.current
        ?.querySelector<HTMLButtonElement>("[data-recent]")
        ?.focus();
    }
  }, [visible]);

  function dismiss() {
    input.current?.focus();
    setOpen(false);
  }

  function navigate(event: KeyboardEvent, index: number) {
    const buttons =
      history.current?.querySelectorAll<HTMLButtonElement>("[data-recent]");
    if (event.key === "Escape") {
      event.preventDefault();
      dismiss();
    } else if (
      buttons?.length &&
      (event.key === "ArrowDown" || event.key === "ArrowUp")
    ) {
      event.preventDefault();
      const next = index + (event.key === "ArrowDown" ? 1 : -1);
      if (next < 0 || next >= buttons.length) input.current?.focus();
      else buttons[next].focus();
    }
  }

  return (
    <div
      className={styles.root}
      onKeyDown={(event) => {
        if (event.key === "Escape" && !event.defaultPrevented) {
          event.preventDefault();
          dismiss();
        }
      }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          setOpen(false);
      }}
    >
      <form
        className="search-form"
        role="search"
        onSubmit={(event) => {
          setOpen(false);
          onSubmit(event);
        }}
      >
        <input
          ref={input}
          type="search"
          aria-label="Search scientific papers or paste an article link"
          placeholder="Search a paper or paste an article link / DOI"
          autoComplete="off"
          value={query}
          onFocus={() => setOpen(true)}
          onClick={() => setOpen(true)}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              setOpen(false);
            } else if (event.key === "ArrowDown" && items.length && !busy) {
              event.preventDefault();
              if (visible) {
                history.current
                  ?.querySelector<HTMLButtonElement>("[data-recent]")
                  ?.focus();
              } else {
                focusHistory.current = true;
                setOpen(true);
              }
            }
          }}
          aria-controls={visible ? id : undefined}
          maxLength={500}
        />
        <button
          className="primary-button"
          type="submit"
          disabled={busy || !query.trim()}
        >
          {busy ? "Finding…" : "Explore"}
        </button>
      </form>
      {visible && (
        <div
          id={id}
          ref={history}
          className={styles.history}
          role="region"
          aria-label="Recent searches"
        >
          <div className={styles.heading}>
            <strong>Recent searches</strong>
            <button type="button" onClick={library.clearSearches}>
              Clear history
            </button>
          </div>
          {library.searchError && (
            <p className="feedback error" role="alert">
              {library.searchError}
            </p>
          )}
          <ul>
            {items.map((item, index) => (
              <li key={item.query.toLowerCase()}>
                <button
                  type="button"
                  data-recent
                  onKeyDown={(event) => navigate(event, index)}
                  aria-label={`Search again for ${item.query}`}
                  onClick={() => {
                    setOpen(false);
                    onSearch(item.query);
                  }}
                >
                  {item.query}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
