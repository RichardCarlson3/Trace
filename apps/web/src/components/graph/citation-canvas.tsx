"use client";

import {
  useCallback,
  useEffect,
  useId,
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
  useInternalNode,
  type EdgeProps,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import { AmbientLinks } from "./ambient-links";
import { graphDistances, paperSize } from "@/lib/graph-focus";
import {
  citationGeometry,
  circle,
  createPhysics,
  placeNear,
  uniqueCitations,
} from "@/lib/graph-physics";
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
  const source = useInternalNode<PaperNode>(props.source);
  const target = useInternalNode<PaperNode>(props.target);
  if (!source || !target) return null;
  const bounds = (node: typeof source) => ({
    id: node.id,
    ...node.internals.positionAbsolute,
    width: node.measured.width ?? 154,
    height: node.measured.height ?? 154,
  });
  const geometry = citationGeometry(
    bounds(source),
    bounds(target),
    props.data?.reciprocal === true,
  );
  const sides = {
    left: Position.Left,
    right: Position.Right,
    top: Position.Top,
    bottom: Position.Bottom,
  };
  const [path] = getBezierPath({
    ...geometry,
    sourcePosition: sides[geometry.sourceSide],
    targetPosition: sides[geometry.targetSide],
  });
  const a = circle(bounds(source));
  const loop =
    source.id === target.id
      ? `M ${a.x + a.radius + 12},${a.y} C ${a.x + a.radius + 110},${a.y - a.radius - 110} ${a.x},${a.y - a.radius - 110} ${a.x},${a.y - a.radius - 12}`
      : path;
  return (
    <BaseEdge
      path={loop}
      pathLength={1}
      markerEnd={props.markerEnd}
      style={props.style}
      interactionWidth={props.interactionWidth}
    />
  );
}
const edgeTypes = { citation: CitationEdge };
const intentColors = {
  background: "#d66b74",
  method: "#bc4b55",
  result: "#aa3e49",
  unknown: "#ac9da0",
};

function positionNewNode(
  id: string,
  originId: string | null,
  graph: Graph,
  placed: PaperNode[],
) {
  return placeNear(
    { id, x: 0, y: 0, width: 164, height: 164 },
    originId,
    placed.map((node) => ({
      id: node.id,
      ...node.position,
      width: node.measured?.width ?? 208,
      height: node.measured?.height ?? 208,
    })),
    graph.citations,
  );
}

type Hover = { paper: Paper; x: number; y: number };

function physicsPositions(
  nodes: PaperNode[],
  simulation: ReturnType<typeof createPhysics>,
) {
  let moved = false;
  const next = nodes.map((node) => {
    const point = simulation.positions.get(node.id);
    if (
      !point ||
      Math.hypot(point.x - node.position.x, point.y - node.position.y) < 0.001
    )
      return node;
    moved = true;
    return { ...node, position: { ...point } };
  });
  return moved ? next : nodes;
}

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
  const flowId = useId();
  const animation = useRef<number | null>(null);
  const nodesRef = useRef(nodes);
  const physics = useRef<ReturnType<typeof createPhysics> | null>(null);
  // The node under the pointer, plus any other selected nodes React Flow
  // drags with it. The simulation holds all of them at their dragged positions.
  const draggingId = useRef<string | null>(null);
  const draggingIds = useRef<string[]>([]);
  const previousVisible = useRef(new Set<string>());

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
    // A restored saved viewport is kept as-is; only new graphs are fitted.
    if (
      !instance ||
      fitted.current ||
      graph.papers.length < 1 ||
      initialLayout?.viewport
    )
      return;
    // Mark as fitted inside the frame: if Strict Mode's cleanup cancels this
    // frame, the re-run effect must still be allowed to fit.
    const frame = requestAnimationFrame(() => {
      fitted.current = true;
      void instance.fitView({ padding: 0.25, duration: 850, maxZoom: 1.2 });
    });
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
  // Identifies what is on screen by content, not object identity: a re-created
  // but identical visible graph must not count as a change to a restored layout.
  const visibleKey = useMemo(
    () => [...visibleIds].sort().join("|"),
    [visibleIds],
  );
  // A reopened saved graph keeps its stored positions: the simulation stays idle
  // until the visible papers or the focus actually change.
  const restoredView = useRef(
    initialLayout && Object.keys(initialLayout.positions).length > 0
      ? { visibleKey, focusId }
      : null,
  );
  const layoutDimensions = nodes
    .filter((node) => visibleIds.has(node.id))
    .map((node) => {
      const size = paperSize(distances.get(node.id));
      return `${node.id}:${Math.max(node.measured?.width ?? 0, size)}:${Math.max(node.measured?.height ?? 0, size)}`;
    })
    .join("|");
  const publish = useCallback(() => {
    const simulation = physics.current;
    if (simulation)
      setNodes((current) => physicsPositions(current, simulation));
  }, [setNodes]);
  // Drives the current simulation with fixed 16 ms steps. The loop stops by
  // itself once the network is at rest; dragging keeps it awake.
  const run = useCallback(() => {
    const simulation = physics.current;
    if (!simulation) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      // No settling animation: resolve the layout in one bounded batch
      // (or a few steps per pointer event while a drag is in progress).
      if (simulation.dragging) for (let i = 0; i < 6; i += 1) simulation.step();
      else while (simulation.step()) {}
      publish();
      return;
    }
    if (animation.current !== null) return;
    let lastTime: number | null = null;
    let elapsed = 0;
    const frame: FrameRequestCallback = (time) => {
      animation.current = null;
      if (physics.current !== simulation) return;
      elapsed += lastTime === null ? 16 : Math.min(48, time - lastTime);
      lastTime = time;
      let running = true;
      while (elapsed >= 16 && running) {
        running = simulation.step();
        elapsed -= 16;
      }
      publish();
      if (running) animation.current = requestAnimationFrame(frame);
    };
    animation.current = requestAnimationFrame(frame);
  }, [publish]);
  // Starts a new settling episode from the current React Flow positions,
  // carrying over velocities and any drag in progress so restarts are seamless.
  const settle = useCallback(
    (source: PaperNode[], active: Set<string>) => {
      if (animation.current !== null) cancelAnimationFrame(animation.current);
      animation.current = null;
      const previous = physics.current;
      const simulation = createPhysics(
        source
          .filter((node) => visibleIds.has(node.id))
          .map((node) => ({
            id: node.id,
            ...node.position,
            width: Math.max(
              node.measured?.width ?? 0,
              paperSize(distances.get(node.id)),
            ),
            height: Math.max(
              node.measured?.height ?? 0,
              paperSize(distances.get(node.id)),
            ),
          })),
        visibleGraph.citations,
        focusId,
        { active, velocities: previous?.velocities() },
      );
      physics.current = simulation;
      for (const id of draggingIds.current) {
        const node = source.find((item) => item.id === id);
        if (node) simulation.drag(id, node.position, id === draggingId.current);
      }
      run();
    },
    [distances, focusId, run, visibleIds, visibleGraph.citations],
  );
  useEffect(() => {
    const placedIds = new Set(
      nodesRef.current
        .filter((node) => visibleIds.has(node.id))
        .map((node) => node.id),
    );
    const added = new Set(
      [...placedIds].filter((id) => !previousVisible.current.has(id)),
    );
    // Restored papers count as already placed, so a later expansion activates
    // only the newly added papers in the simulation.
    previousVisible.current = placedIds;
    if (restoredView.current) {
      if (
        restoredView.current.visibleKey === visibleKey &&
        restoredView.current.focusId === focusId
      )
        return;
      restoredView.current = null;
    }
    if (nodes.length > 1)
      settle(
        nodesRef.current,
        added.size ? added : new Set(focusId ? [focusId] : []),
      );
  }, [settle, nodes.length, visibleIds, visibleKey, focusId, layoutDimensions]);

  useEffect(
    () => () => {
      if (animation.current !== null) cancelAnimationFrame(animation.current);
      animation.current = null;
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
  const directedPairs = useMemo(
    () =>
      new Set(
        visibleGraph.citations.map((edge) => `${edge.source}:${edge.target}`),
      ),
    [visibleGraph.citations],
  );
  const edges = useMemo(
    () =>
      uniqueCitations(visibleGraph.citations)
        .filter(
          (edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target),
        )
        .map((citation) => {
          const color = intentColors[citation.intent ?? "unknown"];
          return {
            id: citation.id,
            source: citation.source,
            target: citation.target,
            sourceHandle: "source-left",
            targetHandle: "target-left",
            type: "citation",
            data: {
              reciprocal: directedPairs.has(
                `${citation.target}:${citation.source}`,
              ),
            },
            className: `citation-edge${selectedPaperId ? (citation.source === selectedPaperId || citation.target === selectedPaperId ? " is-focus-near" : " is-focus-far") : ""}${citation.id === selectedCitationId ? " is-selected" : ""}${citation.id === hoveredCitationId ? " is-highlighted" : ""}`,
            style: { stroke: color, strokeWidth: 2.2 },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              color,
              width: 20,
              height: 20,
              markerUnits: "userSpaceOnUse",
            },
            interactionWidth: 28,
          };
        }),
    [
      visibleGraph.citations,
      visibleIds,
      selectedPaperId,
      selectedCitationId,
      hoveredCitationId,
      directedPairs,
    ],
  );

  function showHover(paper: Paper | undefined, event: React.MouseEvent) {
    if (!paper || draggingId.current) return;
    setHoveredCitationId(null);
    setHover({ paper, x: event.clientX, y: event.clientY });
  }

  return (
    <div className="graph-container" role="region" aria-label="Citation graph">
      <AmbientLinks canDraw={!selectedPaperId && !selectedCitationId} />
      <ReactFlow
        id={`citations-${flowId.replace(/[^a-zA-Z0-9_-]/g, "")}`}
        nodes={shownNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={(changes) => {
          const simulation = physics.current;
          let dragged = false;
          // React Flow reports the pointer-driven position; the simulation
          // adopts it verbatim, so physics never fights the pointer.
          for (const change of changes)
            if (
              change.type === "position" &&
              change.position &&
              simulation &&
              draggingIds.current.includes(change.id)
            ) {
              simulation.drag(
                change.id,
                change.position,
                change.id === draggingId.current,
              );
              dragged = true;
            }
          onNodesChange(changes);
          if (dragged) {
            publish();
            run();
          }
        }}
        onNodeDragStart={(_, node, dragged) => {
          draggingId.current = node.id;
          draggingIds.current = dragged.map((item) => item.id);
          if (!draggingIds.current.includes(node.id))
            draggingIds.current.push(node.id);
          setHover(null);
          setHoveredCitationId(null);
          const start = new Map(
            dragged.map((item) => [item.id, item.position]),
          );
          start.set(node.id, node.position);
          settle(
            nodesRef.current.map((item) =>
              start.has(item.id)
                ? { ...item, position: start.get(item.id)! }
                : item,
            ),
            new Set(draggingIds.current),
          );
        }}
        onNodeDragStop={(_, node, dragged) => {
          const simulation = physics.current;
          for (const item of dragged.length ? dragged : [node])
            simulation?.drag(item.id, item.position, false);
          draggingId.current = null;
          draggingIds.current = [];
          // Released papers stay where they were dropped; the rest of the
          // network keeps settling around them.
          simulation?.release();
          publish();
          run();
        }}
        onInit={setInstance}
        onNodeClick={(_, node) => onSelectPaper(node.id)}
        onEdgeClick={(event, edge) => {
          event.stopPropagation();
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
        onEdgeMouseEnter={(_, edge) => {
          setHover(null);
          setHoveredCitationId(edge.id);
        }}
        onEdgeMouseMove={() => setHover(null)}
        onEdgeMouseLeave={() => {
          setHoveredCitationId(null);
        }}
        nodesConnectable={false}
        fitView={!initialLayout?.viewport}
        defaultViewport={initialLayout?.viewport ?? undefined}
        minZoom={0.15}
        maxZoom={2}
        colorMode="dark"
      >
        <Background color="#321a1e" gap={30} size={1} />
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
