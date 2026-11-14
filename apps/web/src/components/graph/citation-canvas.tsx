"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  useNodesState,
  type Node,
  type ReactFlowInstance,
} from "@xyflow/react";
import { AmbientLinks } from "./ambient-links";
import type { Graph, Paper } from "@/lib/types";

function nodeLabel(paper: Paper) {
  const title =
    paper.title.length > 66 ? `${paper.title.slice(0, 63)}…` : paper.title;
  return `${title}\n${paper.year ?? "Year unknown"}`;
}

function positionNewNode(
  id: string,
  originId: string | null,
  graph: Graph,
  placed: Node[],
) {
  const anchor = placed.find((node) => node.id === originId)?.position ?? {
    x: 0,
    y: 0,
  };
  const relationship = graph.citations.find(
    (citation) =>
      (citation.source === originId && citation.target === id) ||
      (citation.target === originId && citation.source === id),
  );
  const side = relationship?.source === originId ? -1 : 1;
  let x = anchor.x + side * 350;
  let y = anchor.y + (((placed.length - 1) % 5) - 2) * 150;

  // Expansion adds positions for new papers only; dragged papers keep theirs.
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const collision = placed.some(
      (node) =>
        Math.abs(node.position.x - x) < 250 &&
        Math.abs(node.position.y - y) < 125,
    );
    if (!collision) break;
    y += 150;
    if (attempt === 15) {
      x += side * 300;
      y = anchor.y - 300;
    }
  }
  return { x, y };
}

const intentColors = {
  background: "#ad98ff",
  method: "#6fafff",
  result: "#62d8aa",
  unknown: "#78849c",
};

export function CitationCanvas({
  seedId,
  graph,
  visibleGraph,
  selectedPaperId,
  selectedCitationId,
  expansionOrigin,
  loading,
  onSelectPaper,
  onSelectCitation,
}: {
  seedId: string | null;
  graph: Graph;
  visibleGraph: Graph;
  selectedPaperId: string | null;
  selectedCitationId: string | null;
  expansionOrigin: string | null;
  loading: boolean;
  onSelectPaper: (id: string) => void;
  onSelectCitation: (id: string) => void;
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [instance, setInstance] = useState<ReactFlowInstance | null>(null);
  const fitted = useRef(false);

  useEffect(() => {
    setNodes((current) => {
      const placed = [...current];
      const known = new Set(current.map((node) => node.id));
      for (const paper of graph.papers) {
        if (known.has(paper.id)) continue;
        placed.push({
          id: paper.id,
          position:
            paper.id === seedId
              ? { x: 0, y: 0 }
              : positionNewNode(
                  paper.id,
                  expansionOrigin ?? seedId,
                  graph,
                  placed,
                ),
          data: { label: nodeLabel(paper) },
        });
        known.add(paper.id);
      }
      return placed;
    });
  }, [graph, seedId, expansionOrigin, setNodes]);

  useEffect(() => {
    if (!instance || fitted.current || graph.papers.length < 2) return;
    fitted.current = true;
    const frame = requestAnimationFrame(() => {
      void instance.fitView({ padding: 0.2, duration: 750 });
    });
    return () => cancelAnimationFrame(frame);
  }, [instance, graph.papers.length]);

  const visibleIds = useMemo(
    () => new Set(visibleGraph.papers.map((paper) => paper.id)),
    [visibleGraph.papers],
  );
  const shownNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        hidden: !visibleIds.has(node.id),
        className:
          node.id === selectedPaperId ? "paper-node is-selected" : "paper-node",
      })),
    [nodes, visibleIds, selectedPaperId],
  );
  const edges = useMemo(
    () =>
      visibleGraph.citations.map((citation) => {
        const color = intentColors[citation.intent ?? "unknown"];
        return {
          id: citation.id,
          source: citation.source,
          target: citation.target,
          animated: citation.id === selectedCitationId,
          className:
            citation.id === selectedCitationId
              ? "citation-edge is-selected"
              : "citation-edge",
          style: { stroke: color, strokeWidth: 2 },
          markerEnd: { type: MarkerType.ArrowClosed, color },
        };
      }),
    [visibleGraph.citations, selectedCitationId],
  );

  return (
    <div className="graph-container" role="region" aria-label="Citation graph">
      <AmbientLinks />
      <ReactFlow
        nodes={shownNodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onInit={setInstance}
        onNodeClick={(_, node) => onSelectPaper(node.id)}
        onEdgeClick={(_, edge) => onSelectCitation(edge.id)}
        nodesConnectable={false}
        fitView
        minZoom={0.2}
        maxZoom={2}
        colorMode="dark"
      >
        <Background color="#35384c" gap={30} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
      {!seedId && (
        <div className="graph-empty">
          <div className="empty-symbol" aria-hidden="true">
            ◎
          </div>
          <h2>Follow the connections.</h2>
          <p>Search for a paper to grow its citation network.</p>
          <p className="ambient-hint">
            Tap or click open space to connect dots.
          </p>
        </div>
      )}
      {loading && (
        <div className="graph-loading" role="status">
          Mapping nearby research…
        </div>
      )}
    </div>
  );
}
