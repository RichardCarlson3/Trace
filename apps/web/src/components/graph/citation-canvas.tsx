"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  useNodesState,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import { AmbientLinks } from "./ambient-links";
import type { Graph, Paper } from "@/lib/types";

type PaperNodeData = { paper: Paper };
type PaperNode = Node<PaperNodeData, "paperBubble">;

function PaperBubble({ data }: NodeProps<PaperNode>) {
  const paper = data.paper;
  return (
    <div className="paper-bubble" title={paper.title}>
      <Handle type="target" id="target-left" position={Position.Left} />
      <Handle type="source" id="source-left" position={Position.Left} />
      <Handle type="target" id="target-right" position={Position.Right} />
      <Handle type="source" id="source-right" position={Position.Right} />
      <span className="paper-bubble-year">{paper.year ?? "Year unknown"}</span>
      <span className="paper-bubble-title">{paper.title}</span>
    </div>
  );
}

const nodeTypes = { paperBubble: PaperBubble };
const intentColors = {
  background: "#ad98ff",
  method: "#6fafff",
  result: "#62d8aa",
  unknown: "#8e9bb7",
};

function positionNewNode(
  id: string,
  originId: string | null,
  graph: Graph,
  placed: PaperNode[],
) {
  const anchor = placed.find((node) => node.id === originId)?.position ?? {
    x: 0,
    y: 0,
  };
  const relation = graph.citations.find(
    (item) =>
      (item.source === originId && item.target === id) ||
      (item.target === originId && item.source === id),
  );
  const side = relation?.source === originId ? -1 : 1;
  let x = anchor.x + side * 330;
  let y = anchor.y + (((placed.length - 1) % 5) - 2) * 170;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (
      !placed.some(
        (node) =>
          Math.abs(node.position.x - x) < 185 &&
          Math.abs(node.position.y - y) < 155,
      )
    )
      break;
    y += 170;
    if (attempt === 19) {
      x += side * 300;
      y = anchor.y - 340;
    }
  }
  return { x, y };
}

type Hover = { paper: Paper; x: number; y: number };

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
  const [nodes, setNodes, onNodesChange] = useNodesState<PaperNode>([]);
  const [instance, setInstance] = useState<ReactFlowInstance<PaperNode> | null>(
    null,
  );
  const [hover, setHover] = useState<Hover | null>(null);
  const fitted = useRef(false);

  useEffect(() => {
    setNodes((current) => {
      const placed = [...current];
      const known = new Set(current.map((node) => node.id));
      for (const paper of graph.papers) {
        if (known.has(paper.id)) continue;
        placed.push({
          id: paper.id,
          type: "paperBubble",
          position:
            paper.id === seedId
              ? { x: 0, y: 0 }
              : positionNewNode(
                  paper.id,
                  expansionOrigin ?? seedId,
                  graph,
                  placed,
                ),
          data: { paper },
        });
        known.add(paper.id);
      }
      return placed;
    });
  }, [graph, seedId, expansionOrigin, setNodes]);

  useEffect(() => {
    if (!instance || fitted.current || graph.papers.length < 1) return;
    fitted.current = true;
    const frame = requestAnimationFrame(
      () =>
        void instance.fitView({ padding: 0.25, duration: 850, maxZoom: 1.2 }),
    );
    return () => cancelAnimationFrame(frame);
  }, [instance, graph.papers.length]);

  const visibleIds = useMemo(
    () => new Set(visibleGraph.papers.map((paper) => paper.id)),
    [visibleGraph.papers],
  );
  const highlightedIds = useMemo(() => {
    const ids = new Set<string>();
    if (hover) ids.add(hover.paper.id);
    const citation = visibleGraph.citations.find(
      (item) => item.id === selectedCitationId,
    );
    if (citation) {
      ids.add(citation.source);
      ids.add(citation.target);
    }
    return ids;
  }, [hover, selectedCitationId, visibleGraph.citations]);
  const shownNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        hidden: !visibleIds.has(node.id),
        className: `paper-node${node.id === selectedPaperId ? " is-selected" : ""}${highlightedIds.has(node.id) ? " is-highlighted" : ""}`,
      })),
    [nodes, visibleIds, selectedPaperId, highlightedIds],
  );
  const positions = useMemo(
    () => new Map(nodes.map((node) => [node.id, node.position])),
    [nodes],
  );
  const edges = useMemo(
    () =>
      visibleGraph.citations.map((citation) => {
        const sourceX = positions.get(citation.source)?.x ?? 0;
        const targetX = positions.get(citation.target)?.x ?? 0;
        const towardRight = targetX >= sourceX;
        const color = intentColors[citation.intent ?? "unknown"];
        return {
          id: citation.id,
          source: citation.source,
          target: citation.target,
          sourceHandle: towardRight ? "source-right" : "source-left",
          targetHandle: towardRight ? "target-left" : "target-right",
          type: "default",
          className: `citation-edge${citation.id === selectedCitationId ? " is-selected" : ""}`,
          style: { stroke: color, strokeWidth: 2.2 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color,
            width: 18,
            height: 18,
          },
          interactionWidth: 28,
        };
      }),
    [visibleGraph.citations, positions, selectedCitationId],
  );

  function showHover(paper: Paper | undefined, event: React.MouseEvent) {
    if (!paper) return;
    setHover({ paper, x: event.clientX, y: event.clientY });
  }

  return (
    <div className="graph-container" role="region" aria-label="Citation graph">
      <AmbientLinks />
      <ReactFlow
        nodes={shownNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onInit={setInstance}
        onNodeClick={(_, node) => onSelectPaper(node.id)}
        onEdgeClick={(_, edge) => onSelectCitation(edge.id)}
        onNodeMouseEnter={(event, node) =>
          showHover(
            graph.papers.find((paper) => paper.id === node.id),
            event,
          )
        }
        onNodeMouseMove={(event, node) =>
          showHover(
            graph.papers.find((paper) => paper.id === node.id),
            event,
          )
        }
        onNodeMouseLeave={() => setHover(null)}
        onEdgeMouseEnter={(event, edge) =>
          showHover(
            graph.papers.find((paper) => paper.id === edge.target),
            event,
          )
        }
        onEdgeMouseMove={(event, edge) =>
          showHover(
            graph.papers.find((paper) => paper.id === edge.target),
            event,
          )
        }
        onEdgeMouseLeave={() => setHover(null)}
        nodesConnectable={false}
        fitView
        minZoom={0.15}
        maxZoom={2}
        colorMode="dark"
      >
        <Background color="#35384c" gap={30} size={1} />
        {seedId && <Controls showInteractive={false} />}
      </ReactFlow>
      {hover && (
        <div
          className="paper-hover"
          role="tooltip"
          style={{
            left: Math.min(
              hover.x + 20,
              typeof window === "undefined" ? hover.x : window.innerWidth - 300,
            ),
            top: Math.min(
              hover.y + 18,
              typeof window === "undefined"
                ? hover.y
                : window.innerHeight - 190,
            ),
          }}
        >
          <span className="eyebrow">
            Paper preview · {hover.paper.year ?? "Year unknown"}
          </span>
          <strong>{hover.paper.title}</strong>
          <p>
            {hover.paper.abstract ?? "No abstract is available for this paper."}
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
