"use client";

import { Background, Controls, ReactFlow, type Node } from "@xyflow/react";
import type { Paper } from "@/lib/types";

export function CitationCanvas({
  paper,
  onSelect,
}: {
  paper: Paper | null;
  onSelect: () => void;
}) {
  const nodes: Node[] = paper
    ? [
        {
          id: paper.id,
          position: { x: 80, y: 80 },
          data: { label: paper.title },
        },
      ]
    : [];
  return (
    <div className="graph-container" role="region" aria-label="Citation graph">
      <ReactFlow
        key={paper?.id ?? "empty"}
        nodes={nodes}
        edges={[]}
        onNodeClick={onSelect}
        nodesDraggable={false}
        nodesConnectable={false}
        fitView
        minZoom={0.25}
        maxZoom={2}
        colorMode="dark"
      >
        <Background color="#35384c" gap={24} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
      {!paper && (
        <div className="graph-empty">
          <div className="empty-symbol" aria-hidden="true">
            ⌘
          </div>
          <h2>Follow the connections.</h2>
          <p>
            Search for a paper to begin exploring.
            <br />
            Your research graph starts with one idea.
          </p>
        </div>
      )}
    </div>
  );
}
