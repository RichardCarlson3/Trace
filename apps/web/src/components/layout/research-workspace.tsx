"use client";

import { useMemo, useRef, useState, type FormEvent } from "react";
import Image from "next/image";
import Link from "next/link";
import { SavedResearchControls } from "@/components/layout/saved-research-controls";
import { PaperSearch } from "@/components/layout/paper-search";
import {
  CitationCanvas,
  type CitationCanvasHandle,
} from "@/components/graph/citation-canvas";
import { CitationDetails } from "@/components/papers/citation-details";
import { PaperDetails } from "@/components/papers/paper-details";
import { useCitationGraph } from "@/hooks/use-citation-graph";
import { useResearch } from "@/hooks/use-research";
import { useSavedResearch } from "@/hooks/use-saved-research";
import { filteredGraph, type DirectionFilter } from "@/lib/graph";
import { isPaperLink, resolvePaper } from "@/lib/resolve-paper";
import type { Paper } from "@/lib/types";

export function ResearchWorkspace({ onHome }: { onHome?: () => void } = {}) {
  const [query, setQuery] = useState("");
  const [resultsOpen, setResultsOpen] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(true);
  const [citationPopup, setCitationPopup] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const [direction, setDirection] = useState<DirectionFilter>("all");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const linkVersion = useRef(0);
  const { result, loading, error, searchNotice, search, clearSearch } =
    useResearch();
  const citationGraph = useCitationGraph();
  const canvasRef = useRef<CitationCanvasHandle>(null);
  const savedResearch = useSavedResearch({
    citationGraph,
    canvasRef,
    filters: { direction, year_from: yearFrom, year_to: yearTo },
    onOpen: () => {
      setFiltersOpen(false);
      setCitationPopup(null);
    },
    onRestore: (saved) => {
      ++linkVersion.current;
      clearSearch();
      setResolving(false);
      setLinkError(null);
      setResultsOpen(false);
      setQuery("");
      setDirection(saved.filters.direction);
      setYearFrom(saved.filters.year_from);
      setYearTo(saved.filters.year_to);
      setDetailsOpen(true);
      setCitationPopup(null);
      setFiltersOpen(false);
    },
  });
  const hasGraph = Boolean(citationGraph.seed);
  const visibleGraph = useMemo(
    () =>
      filteredGraph(
        citationGraph.visibleGraph,
        citationGraph.seed?.id ?? null,
        direction,
        yearFrom,
        yearTo,
      ),
    [
      citationGraph.visibleGraph,
      citationGraph.seed?.id,
      direction,
      yearFrom,
      yearTo,
    ],
  );

  function choose(paper: Paper) {
    savedResearch.startGraph(paper.title);
    setResultsOpen(false);
    setLinkError(null);
    setDetailsOpen(true);
    setCitationPopup(null);
    setDirection("all");
    setYearFrom("");
    setYearTo("");
    void citationGraph.openPaper(paper);
  }

  function goHome() {
    savedResearch.startGraph();
    ++linkVersion.current;
    clearSearch();
    citationGraph.reset();
    setQuery("");
    setResultsOpen(false);
    setResolving(false);
    setLinkError(null);
    setFiltersOpen(false);
    setDetailsOpen(true);
    setCitationPopup(null);
    setDirection("all");
    setYearFrom("");
    setYearTo("");
    onHome?.();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runSearch(query.trim());
  }

  async function runSearch(value: string) {
    if (!value) return;
    savedResearch.recordSearch(value);
    const requestVersion = ++linkVersion.current;
    setLinkError(null);
    if (isPaperLink(value)) {
      setResultsOpen(false);
      setResolving(true);
      try {
        const paper = await resolvePaper(value);
        if (requestVersion === linkVersion.current) choose(paper);
      } catch (caught) {
        if (requestVersion === linkVersion.current) {
          setLinkError(
            caught instanceof Error
              ? caught.message
              : "Could not open that article link.",
          );
        }
      } finally {
        if (requestVersion === linkVersion.current) setResolving(false);
      }
    } else {
      setResultsOpen(true);
      await search(value);
    }
  }

  const searchForm = (
    <PaperSearch
      query={query}
      onChange={setQuery}
      onSubmit={submit}
      onSearch={(value) => {
        setQuery(value);
        void runSearch(value);
      }}
      busy={loading || resolving}
      library={savedResearch.library}
    />
  );

  const searchFeedback = (
    <>
      {(loading || resolving) && (
        <p className="feedback" role="status">
          Finding papers…
        </p>
      )}
      {(error || linkError) && (
        <p className="feedback error" role="alert">
          {linkError ?? error}
        </p>
      )}
      {result && resultsOpen && (
        <div className="results" aria-label="Search results">
          {searchNotice && (
            <p className="feedback" role="status">
              {searchNotice}
            </p>
          )}
          <h2>
            {result.total.toLocaleString()} results · showing{" "}
            {result.papers.length}
          </h2>
          {result.papers.length === 0 ? (
            <p className="muted">
              No papers found. Try another title or keyword.
            </p>
          ) : (
            result.papers.map((paper) => (
              <button
                className="paper-result"
                key={paper.id}
                onClick={() => choose(paper)}
              >
                <strong>{paper.title}</strong>
                <span>
                  {paper.year ?? "Year unavailable"} ·{" "}
                  {paper.authors.slice(0, 2).join(", ") ||
                    "Authors unavailable"}{" "}
                  · {paper.cited_by_count.toLocaleString()} citations
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </>
  );

  return (
    <main
      className={`workspace ${hasGraph ? "has-graph" : "is-empty"}`}
      id="workspace"
    >
      <CitationCanvas
        key={`${citationGraph.seed?.id ?? "empty"}:${savedResearch.session.version}`}
        ref={canvasRef}
        initialLayout={savedResearch.session.initialLayout}
        seedId={citationGraph.seed?.id ?? null}
        graph={citationGraph.graph}
        visibleGraph={visibleGraph}
        selectedPaperId={citationGraph.selectedPaperId}
        selectedCitationId={citationGraph.selectedCitationId}
        expansionOrigin={citationGraph.expansionOrigin}
        loading={citationGraph.loadingSeed}
        onSelectPaper={(id) => {
          citationGraph.selectPaper(id);
          setCitationPopup(null);
          setDetailsOpen(true);
        }}
        onSelectCitation={(id, x, y) => {
          citationGraph.selectCitation(id);
          setCitationPopup({
            x: Math.max(12, Math.min(x + 16, window.innerWidth - 352)),
            y: Math.max(12, Math.min(y + 16, window.innerHeight - 300)),
          });
          setDetailsOpen(false);
        }}
        onClearSelection={() => {
          citationGraph.clearSelection();
          setCitationPopup(null);
          setDetailsOpen(false);
        }}
      />
      <header className="topbar">
        <Link
          className="brand"
          href="/"
          aria-label="TRACE home"
          onClick={(event) => {
            event.preventDefault();
            goHome();
          }}
        >
          <Image
            className="brand-mark"
            src="/utrace-logo.png"
            width={1385}
            height={1136}
            alt=""
            aria-hidden="true"
          />
        </Link>
        <div className="topbar-actions">
          {hasGraph && (
            <>
              <button
                className="toolbar-button"
                onClick={() => setFiltersOpen((open) => !open)}
                aria-expanded={filtersOpen}
              >
                Filters
              </button>
              <button
                className="toolbar-button"
                onClick={() => {
                  setCitationPopup(null);
                  setDetailsOpen((open) => !open);
                }}
                aria-expanded={detailsOpen}
              >
                Details
              </button>
            </>
          )}
          <SavedResearchControls research={savedResearch} />
        </div>
      </header>
      {!hasGraph ? (
        <section className="hero" aria-label="Start exploring">
          <h1>Follow the connections.</h1>
          {searchForm}
          {searchFeedback}
        </section>
      ) : (
        <>
          <section className="floating-search" aria-label="Find another paper">
            {searchForm}
            {searchFeedback}
            {citationGraph.loadError && (
              <p className="feedback error" role="alert">
                {citationGraph.loadError}
              </p>
            )}
            {citationGraph.isPreview && (
              <p className="preview-notice" role="status">
                UI preview · sample papers, not academic records
              </p>
            )}
          </section>
          {filtersOpen && (
            <aside
              className="sidebar floating-panel"
              aria-label="Graph settings"
            >
              <p className="eyebrow">Exploration</p>
              <h2>Graph settings</h2>
              <div className="filter-group">
                <label htmlFor="direction">Citation direction</label>
                <select
                  id="direction"
                  value={direction}
                  onChange={(event) =>
                    setDirection(event.target.value as DirectionFilter)
                  }
                >
                  <option value="all">All relationships</option>
                  <option value="references">References from seed</option>
                  <option value="citations">Papers citing seed</option>
                </select>
              </div>
              <div className="filter-group">
                <label htmlFor="year-from">Publication year</label>
                <div className="year-range">
                  <input
                    id="year-from"
                    type="number"
                    placeholder="From"
                    value={yearFrom}
                    onChange={(event) => setYearFrom(event.target.value)}
                  />
                  <span className="muted">–</span>
                  <input
                    type="number"
                    placeholder="To"
                    aria-label="Publication year to"
                    value={yearTo}
                    onChange={(event) => setYearTo(event.target.value)}
                  />
                </div>
              </div>
              <p className="muted sidebar-note">
                Arrows run from a citing paper to the paper it cites.
              </p>
            </aside>
          )}
          {citationPopup && citationGraph.selectedCitation && (
            <div
              className="citation-popover-anchor"
              style={{ left: citationPopup.x, top: citationPopup.y }}
            >
              <CitationDetails
                citation={citationGraph.selectedCitation}
                papers={citationGraph.graph.papers}
                isPreview={citationGraph.isPreview}
                onClose={() => {
                  setCitationPopup(null);
                  citationGraph.clearSelection();
                }}
              />
            </div>
          )}
          {detailsOpen && (
            <div className="details-panel floating-panel">
              <PaperDetails
                paper={citationGraph.selectedPaper}
                isPreview={citationGraph.isPreview}
                onExpand={citationGraph.expand}
                expanding={citationGraph.expanding}
                expanded={citationGraph.expanded}
                expansionError={citationGraph.expansionError}
              />
            </div>
          )}
        </>
      )}
    </main>
  );
}
