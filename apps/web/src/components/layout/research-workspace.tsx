"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { CitationCanvas } from "@/components/graph/citation-canvas";
import { PaperDetails } from "@/components/papers/paper-details";
import { useResearch } from "@/hooks/use-research";
import type { Paper } from "@/lib/types";

export function ResearchWorkspace() {
  const [query, setQuery] = useState("");
  const [seed, setSeed] = useState<Paper | null>(null);
  const [selected, setSelected] = useState<Paper | null>(null);
  const { connection, result, loading, error, search } = useResearch();

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (query.trim()) void search(query.trim());
  }

  function choose(paper: Paper) {
    setSeed(paper);
    setSelected(paper);
  }

  return (
    <>
      <header className="topbar">
        <Link className="brand" href="/" aria-label="ResearchGraph home">
          <span className="brand-mark" aria-hidden="true">
            ⌘
          </span>
          ResearchGraph
        </Link>
        <nav aria-label="Main navigation">
          <a href="#workspace">Explore</a>
          <button
            className="text-button"
            disabled
            title="Graph persistence is planned"
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
            <select id="direction" disabled>
              <option>References & citations</option>
            </select>
            <p className="muted sidebar-note">
              Available with graph expansion.
            </p>
          </div>
          <div className="filter-group">
            <label htmlFor="year-from">Publication year</label>
            <div className="year-range">
              <input
                id="year-from"
                placeholder="From"
                disabled
                aria-label="Publication year from"
              />
              <span className="muted">–</span>
              <input
                placeholder="To"
                disabled
                aria-label="Publication year to"
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
            Arrows follow citations from the citing paper to the cited paper.
          </p>
        </aside>
        <section className="center" aria-label="Research workspace">
          <div className="workspace-heading">
            <div>
              <h1>Research explorer</h1>
              <p className="muted">
                Discover papers. Explore how ideas connect.
              </p>
            </div>
            <span className="connection" role="status">
              <span
                className={`dot ${connection === "API connected" ? "result-dot" : "unknown-dot"}`}
              />
              {connection}
            </span>
          </div>
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
          {result && (
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
          <CitationCanvas paper={seed} onSelect={() => setSelected(seed)} />
          <footer className="graph-footer">
            <span>
              {seed
                ? "1 paper · 0 relationships"
                : "0 papers · 0 relationships"}
            </span>
            <span>Scholarly metadata from OpenAlex</span>
          </footer>
        </section>
        <PaperDetails paper={selected} />
      </main>
    </>
  );
}
