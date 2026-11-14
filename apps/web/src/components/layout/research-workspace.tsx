"use client";

import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { CitationCanvas } from "@/components/graph/citation-canvas";
import { CitationDetails } from "@/components/papers/citation-details";
import { PaperDetails } from "@/components/papers/paper-details";
import { useCitationGraph } from "@/hooks/use-citation-graph";
import { useResearch } from "@/hooks/use-research";
import { filteredGraph, type DirectionFilter } from "@/lib/graph";
import { previewFullGraph, previewInitialGraph } from "@/lib/preview-graph";
import type { Paper } from "@/lib/types";

export function ResearchWorkspace() {
  const [query, setQuery] = useState("");
  const [resultsOpen, setResultsOpen] = useState(true);
  const [direction, setDirection] = useState<DirectionFilter>("all");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const { connection, result, loading, error, search } = useResearch();
  const citationGraph = useCitationGraph();
  const visibleGraph = useMemo(
    () =>
      filteredGraph(
        citationGraph.graph,
        citationGraph.seed?.id ?? null,
        direction,
        yearFrom,
        yearTo,
      ),
    [citationGraph.graph, citationGraph.seed?.id, direction, yearFrom, yearTo],
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (query.trim()) {
      setResultsOpen(true);
      void search(query.trim());
    }
  }

  function choose(paper: Paper) {
    setResultsOpen(false);
    setDirection("all");
    setYearFrom("");
    setYearTo("");
    void citationGraph.openPaper(paper);
  }

  return (
    <>
      <header className="topbar">
        <Link className="brand" href="/" aria-label="TRACE home">
          <span className="brand-mark" aria-hidden="true">
            ◎
          </span>
          TRACE
        </Link>
        <nav aria-label="Main navigation">
          <a href="#workspace">Explore</a>
          <button
            className="text-button"
            disabled
            title="Saved graphs are planned after the graph API is complete"
          >
            Saved graphs
          </button>
        </nav>
        <form className="search-form" onSubmit={submit} role="search">
          <input
            type="search"
            aria-label="Search scientific papers"
            placeholder="Search papers by title, keyword, or DOI…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            maxLength={300}
          />
          <button
            className="primary-button"
            type="submit"
            disabled={loading || !query.trim()}
          >
            {loading ? "Searching…" : "Search"}
          </button>
        </form>
      </header>
      <main className="workspace" id="workspace">
        <aside className="sidebar" aria-label="Graph settings">
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
              disabled={citationGraph.graph.citations.length === 0}
            >
              <option value="all">All relationships</option>
              <option value="references">References from seed</option>
              <option value="citations">Papers citing seed</option>
            </select>
            <p className="muted sidebar-note">
              Direction filters are relative to the starting paper.
            </p>
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
                disabled={citationGraph.graph.papers.length < 2}
              />
              <span className="muted">–</span>
              <input
                type="number"
                placeholder="To"
                aria-label="Publication year to"
                value={yearTo}
                onChange={(event) => setYearTo(event.target.value)}
                disabled={citationGraph.graph.papers.length < 2}
              />
            </div>
          </div>
          <div className="filter-group">
            <h3>Citation intent</h3>
            <ul className="legend">
              <li>
                <span className="dot background-dot" />
                Background
              </li>
              <li>
                <span className="dot method-dot" />
                Method
              </li>
              <li>
                <span className="dot result-dot" />
                Result
              </li>
              <li>
                <span className="dot unknown-dot" />
                Unclassified
              </li>
            </ul>
          </div>
          <p className="muted sidebar-note">
            Arrows run from a citing paper to the paper it cites.
          </p>
        </aside>
        <section className="center" aria-label="Research workspace">
          <div className="workspace-heading">
            <div>
              <p className="eyebrow">
                Tracing Relationships Across Citation Evidence
              </p>
              <h1>Research explorer</h1>
              <p className="muted">
                Discover papers. Watch their connections grow.
              </p>
            </div>
            <span className="connection" role="status">
              <span
                className={`dot ${connection === "API connected" ? "result-dot" : "unknown-dot"}`}
              />
              {connection}
            </span>
          </div>
          {process.env.NODE_ENV === "development" &&
            (!citationGraph.seed || citationGraph.loadError) && (
              <div className="preview-entry">
                <span>Waiting for the citation API?</span>
                <button
                  className="secondary-button"
                  onClick={() =>
                    citationGraph.openPreview(
                      previewInitialGraph,
                      previewFullGraph,
                    )
                  }
                >
                  Preview graph interactions with sample data
                </button>
              </div>
            )}
          {citationGraph.isPreview && (
            <p className="preview-notice" role="status">
              UI preview: these sample papers are not real academic records.
            </p>
          )}
          {loading && (
            <p className="feedback" role="status">
              Searching OpenAlex…
            </p>
          )}
          {error && (
            <p className="feedback error" role="alert">
              {error}
            </p>
          )}
          {result && resultsOpen && (
            <div className="results" aria-label="Search results">
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
          {citationGraph.loadError && (
            <p className="feedback error" role="alert">
              {citationGraph.loadError}
            </p>
          )}
          <CitationCanvas
            key={citationGraph.seed?.id ?? "empty"}
            seedId={citationGraph.seed?.id ?? null}
            graph={citationGraph.graph}
            visibleGraph={visibleGraph}
            selectedPaperId={citationGraph.selectedPaperId}
            selectedCitationId={citationGraph.selectedCitationId}
            expansionOrigin={citationGraph.expansionOrigin}
            loading={citationGraph.loadingSeed}
            onSelectPaper={citationGraph.selectPaper}
            onSelectCitation={citationGraph.selectCitation}
          />
          <footer className="graph-footer">
            <span>
              {visibleGraph.papers.length} papers ·{" "}
              {visibleGraph.citations.length} relationships
              {visibleGraph.papers.length < citationGraph.graph.papers.length &&
                ` · ${citationGraph.graph.papers.length - visibleGraph.papers.length} filtered`}
            </span>
            <span>
              Tap or click open space to draw temporary links ·{" "}
              {citationGraph.isPreview
                ? "UI sample data"
                : "Metadata from OpenAlex"}
            </span>
          </footer>
        </section>
        {citationGraph.selectedCitation ? (
          <CitationDetails
            citation={citationGraph.selectedCitation}
            papers={citationGraph.graph.papers}
          />
        ) : (
          <PaperDetails
            paper={citationGraph.selectedPaper}
            isPreview={citationGraph.isPreview}
            onExpand={citationGraph.expand}
            expanding={citationGraph.expanding}
            expanded={citationGraph.expanded}
            expansionError={citationGraph.expansionError}
          />
        )}
      </main>
    </>
  );
}
