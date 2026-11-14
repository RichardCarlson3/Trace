"use client";

import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type Ref,
} from "react";
import {
  BaseEdge,
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  getBezierPath,
  useNodesState,
  type EdgeProps,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import { AmbientLinks } from "./ambient-links";
import { graphDistances, paperSize, spaceCircles } from "@/lib/graph-focus";
import type { Graph, Paper } from "@/lib/types";
import type { GraphLayout } from "@/lib/browser-library";

export interface CitationCanvasHandle {
  getLayout: () => GraphLayout;
}

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
      <Handle type="target" id="target-top" position={Position.Top} />
      <Handle type="source" id="source-top" position={Position.Top} />
      <Handle type="target" id="target-bottom" position={Position.Bottom} />
      <Handle type="source" id="source-bottom" position={Position.Bottom} />
      <span className="paper-bubble-year">{paper.year ?? "Year unknown"}</span>
      <span className="paper-bubble-title">{paper.title}</span>
    </div>
  );
}

const nodeTypes = { paperBubble: PaperBubble };
function CitationEdge(props: EdgeProps) {
  const [path] = getBezierPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
  });
  return (
    <BaseEdge
      path={path}
      pathLength={1}
      markerEnd={props.markerEnd}
      style={props.style}
      interactionWidth={props.interactionWidth}
    />
  );
}
const edgeTypes = { citation: CitationEdge };
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
  ref,
  initialLayout,
  seedId,
  graph,
  visibleGraph,
  selectedPaperId,
  selectedCitationId,
  expansionOrigin,
  loading,
  onSelectPaper,
  onSelectCitation,
  onClearSelection,
}: {
  ref?: Ref<CitationCanvasHandle>;
  initialLayout?: GraphLayout;
  seedId: string | null;
  graph: Graph;
  visibleGraph: Graph;
  selectedPaperId: string | null;
  selectedCitationId: string | null;
  expansionOrigin: string | null;
  loading: boolean;
  onSelectPaper: (id: string) => void;
  onSelectCitation: (id: string, x: number, y: number) => void;
  onClearSelection: () => void;
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState<PaperNode>([]);
  const [instance, setInstance] = useState<ReactFlowInstance<PaperNode> | null>(
    null,
  );
  const [hover, setHover] = useState<Hover | null>(null);
  const [hoveredCitationId, setHoveredCitationId] = useState<string | null>(
    null,
  );
  const fitted = useRef(false);
  const animation = useRef<number | null>(null);
  const nodesRef = useRef(nodes);

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useImperativeHandle(
    ref,
    () => ({
      getLayout: () => ({
        positions: Object.fromEntries(
          nodes.map((node) => [node.id, node.position]),
        ),
        viewport: instance?.getViewport() ?? null,
      }),
    }),
    [nodes, instance],
  );

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
            initialLayout?.positions[paper.id] ??
            (paper.id === seedId
              ? { x: 0, y: 0 }
              : positionNewNode(
                  paper.id,
                  expansionOrigin ?? seedId,
                  graph,
                  placed,
                )),
          data: { paper },
        });
        known.add(paper.id);
      }
      return placed;
    });
  }, [graph, seedId, expansionOrigin, setNodes, initialLayout]);

  useEffect(() => {
    if (
      !instance ||
      fitted.current ||
      graph.papers.length < 1 ||
      initialLayout?.viewport
    )
      return;
    fitted.current = true;
    const frame = requestAnimationFrame(
      () =>
        void instance.fitView({ padding: 0.25, duration: 850, maxZoom: 1.2 }),
    );
    return () => cancelAnimationFrame(frame);
  }, [instance, graph.papers.length, initialLayout]);

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
    const hoveredCitation = visibleGraph.citations.find(
      (item) => item.id === hoveredCitationId,
    );
    if (hoveredCitation) {
      ids.add(hoveredCitation.source);
      ids.add(hoveredCitation.target);
    }
    return ids;
  }, [hover, selectedCitationId, hoveredCitationId, visibleGraph.citations]);
  const focusId = visibleIds.has(selectedPaperId ?? "")
    ? selectedPaperId
    : seedId;
  const distances = useMemo(
    () => graphDistances(visibleGraph, focusId),
    [visibleGraph, focusId],
  );
  const restoredView = useRef(
    initialLayout && Object.keys(initialLayout.positions).length > 0
      ? { graph: visibleGraph, focusId }
      : null,
  );
  const settleOverlaps = useCallback(
    (source: PaperNode[], pinnedId: string | null = focusId) => {
      if (animation.current !== null) cancelAnimationFrame(animation.current);
      const circles = source
        .filter((node) => visibleIds.has(node.id))
        .map((node) => ({
          id: node.id,
          x: node.position.x,
          y: node.position.y,
          size: paperSize(distances.get(node.id)),
        }));
      if (circles.length < 2) return;
      const targets = spaceCircles(circles, pinnedId);
      const start = new Map(source.map((node) => [node.id, node.position]));
      if (
        circles.every((circle) => {
          const target = targets.get(circle.id);
          return (
            target &&
            Math.abs(target.x - circle.x) < 0.1 &&
            Math.abs(target.y - circle.y) < 0.1
          );
        })
      )
        return;
      const reducedMotion = window.matchMedia?.(
        "(prefers-reduced-motion: reduce)",
      ).matches;
      const duration = reducedMotion ? 0 : 620;
      let startedAt: number | null = null;
      const frame = (time: number) => {
        startedAt ??= time;
        const progress =
          duration === 0 ? 1 : Math.min(1, (time - startedAt) / duration);
        const eased = 1 - Math.pow(1 - progress, 3);
        const moving = circles.map((circle) => {
          const from = start.get(circle.id) ?? { x: circle.x, y: circle.y };
          const to = targets.get(circle.id) ?? from;
          return {
            ...circle,
            x: from.x + (to.x - from.x) * eased,
            y: from.y + (to.y - from.y) * eased,
          };
        });
        const spaced = spaceCircles(moving, pinnedId);
        setNodes((current) =>
          current.map((node) => {
            const position = spaced.get(node.id);
            return position ? { ...node, position } : node;
          }),
        );
        animation.current = progress < 1 ? requestAnimationFrame(frame) : null;
      };
      animation.current = requestAnimationFrame(frame);
    },
    [distances, focusId, setNodes, visibleIds],
  );

  useEffect(() => {
    if (restoredView.current) {
      if (
        restoredView.current.graph === visibleGraph &&
        restoredView.current.focusId === focusId
      )
        return;
      restoredView.current = null;
    }
    if (nodes.length > 1) settleOverlaps(nodesRef.current);
  }, [settleOverlaps, nodes.length, visibleGraph, focusId]);

  useEffect(
    () => () => {
      if (animation.current !== null) cancelAnimationFrame(animation.current);
    },
    [],
  );
  const shownNodes = useMemo(
    () =>
      nodes.map((node) => {
        const size = paperSize(distances.get(node.id));
        const depth = distances.get(node.id) ?? 5;
        const faded = selectedPaperId && node.id !== selectedPaperId;
        return {
          ...node,
          hidden: !visibleIds.has(node.id),
          style: { ...node.style, width: size, height: size },
          className: `paper-node${node.id === focusId ? " is-selected" : ""}${faded ? ` focus-distance-${Math.min(depth, 4)}` : ""}${highlightedIds.has(node.id) ? " is-highlighted" : ""}`,
        };
      }),
    [nodes, visibleIds, focusId, selectedPaperId, highlightedIds, distances],
  );
  const positions = useMemo(
    () => new Map(nodes.map((node) => [node.id, node.position])),
    [nodes],
  );
  const edges = useMemo(
    () =>
      visibleGraph.citations.map((citation) => {
        const source = positions.get(citation.source) ?? { x: 0, y: 0 };
        const target = positions.get(citation.target) ?? { x: 0, y: 0 };
        const dx = target.x - source.x;
        const dy = target.y - source.y;
        const horizontal = Math.abs(dx) >= Math.abs(dy);
        const sourceSide = horizontal
          ? dx >= 0
            ? "right"
            : "left"
          : dy >= 0
            ? "bottom"
            : "top";
        const targetSide = horizontal
          ? dx >= 0
            ? "left"
            : "right"
          : dy >= 0
            ? "top"
            : "bottom";
        const color = intentColors[citation.intent ?? "unknown"];
        return {
          id: citation.id,
          source: citation.source,
          target: citation.target,
          sourceHandle: `source-${sourceSide}`,
          targetHandle: `target-${targetSide}`,
          type: "citation",
          className: `citation-edge${selectedPaperId ? (citation.source === selectedPaperId || citation.target === selectedPaperId ? " is-focus-near" : " is-focus-far") : ""}${citation.id === selectedCitationId ? " is-selected" : ""}${citation.id === hoveredCitationId ? " is-highlighted" : ""}`,
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
    [
      visibleGraph.citations,
      positions,
      selectedPaperId,
      selectedCitationId,
      hoveredCitationId,
    ],
  );

  function showHover(paper: Paper | undefined, event: React.MouseEvent) {
    if (!paper) return;
    setHover({ paper, x: event.clientX, y: event.clientY });
  }

  return (
    <div className="graph-container" role="region" aria-label="Citation graph">
      <AmbientLinks canDraw={!selectedPaperId && !selectedCitationId} />
      <ReactFlow
        nodes={shownNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onNodeDragStart={() => {
          if (animation.current !== null)
            cancelAnimationFrame(animation.current);
          animation.current = null;
        }}
        onNodeDragStop={(_, node) => {
          const settled = nodesRef.current.map((item) =>
            item.id === node.id ? { ...item, position: node.position } : item,
          );
          settleOverlaps(settled, node.id);
        }}
        onInit={setInstance}
        onNodeClick={(_, node) => onSelectPaper(node.id)}
        onEdgeClick={(event, edge) => {
          setHover(null);
          onSelectCitation(edge.id, event.clientX, event.clientY);
        }}
        onPaneClick={(event) => {
          if (selectedPaperId || selectedCitationId) event.stopPropagation();
          setHover(null);
          setHoveredCitationId(null);
          onClearSelection();
        }}
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
        onEdgeMouseEnter={(event, edge) => {
          setHoveredCitationId(edge.id);
          showHover(
            graph.papers.find((paper) => paper.id === edge.target),
            event,
          );
        }}
        onEdgeMouseMove={(event, edge) =>
          showHover(
            graph.papers.find((paper) => paper.id === edge.target),
            event,
          )
        }
        onEdgeMouseLeave={() => {
          setHover(null);
          setHoveredCitationId(null);
        }}
        nodesConnectable={false}
        fitView={!initialLayout?.viewport}
        defaultViewport={initialLayout?.viewport ?? undefined}
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
