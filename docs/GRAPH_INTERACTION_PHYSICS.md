# Citation graph interaction and physics changes

Work is uncommitted on `dev-ml`. The branch and working tree were inspected before
editing; the starting tree was clean. No backend, classifier, provider, database,
API-client, dependency, stylesheet, sidebar, or workspace-layout files changed.

## Findings and arrow repair

The citing -> cited relationship was already correct. Outgoing references were
placed left of their expanded paper; incoming citing papers were placed right.
That convention and the actual source/target IDs are preserved independently of
where users drag nodes.

The old renderer chose handle sides using top-left positions rather than centers
and depended on handle measurements inside the bubble's scale/bloom animations.
Arrow marker units defaulted to stroke width, while hover increased stroke width
from 2.2 to 4. This could enlarge arrowheads during hover. These are identified
code-level rendering risks; the reported visual glitches were not independently
reproduced in a browser because automation was unavailable.

The existing custom edge now computes circular boundary endpoints from React
Flow's current measured dimensions and absolute positions. A 12-unit buffer clears
the unchanged hover scale (up to about 7.3 units at the largest node). It still
renders through `BaseEdge`, retains its interaction path and normalized path
length for the existing edge animation, and passes through React Flow's marker.
Stable hidden handles remain present for React Flow's connectivity bookkeeping;
the visible floating path updates directly from node internals rather than moving
handle IDs. Edge configuration objects stay stable during dragging.

Closed arrowheads use `markerUnits: "userSpaceOnUse"` with 20x20 dimensions,
independent of hover stroke thickness. Each canvas has a unique React Flow ID,
preventing marker-definition collisions between canvas instances. Identical
directed relationships are deduplicated while the first relationship ID remains
the selection ID. Reciprocal relationships remain separate, with offset entry
angles; self-loops have a finite loop path.

This uses the existing library's supported
[node internals](https://reactflow.dev/api-reference/hooks/use-internal-node),
[BaseEdge](https://reactflow.dev/api-reference/components/base-edge), and
[marker configuration](https://reactflow.dev/api-reference/types/edge-marker).
No custom SVG marker definitions or new graph dependency were introduced.

## Hover ownership

The popup bug was explicit: `onEdgeMouseEnter` and `onEdgeMouseMove` called
`showHover()` for the edge's target paper. Those calls are removed. Edge hover
clears the paper preview and retains the existing edge/endpoint highlighting.
Only node hover calls the paper-preview function; node leave dismisses it.
Hover does not select a paper. Edge click stops propagation and invokes the same
existing citation-selection callback with the same ID and pointer coordinates.
Node hover is suppressed during dragging. Classification remains outside this
component and its API/loading/unavailable/error/timeout logic is unchanged.

## Elastic movement model (revision 2)

The first physics pass (below, "revision 1") felt rigid and could still produce
messy layouts. Causes found in that implementation:

- A hard `constrain()` projection ran at construction and after every step. It
  turned every citation into `citing.x >= cited.x + spacing`, propagated
  transitively through a DAG of the whole component, so nodes were teleported
  across "walls" and long chains spread the graph horizontally.
- `collide()` resolved overlaps only along y, as a hard projection that also
  rewrote each node's anchor, so collisions produced permanent vertical jumps.
- Dragging the focus added the identical pointer delta to every node in its
  component (rigid-body translation); springs never stretched.
- Position tethers pulled nodes back toward their start, non-adjacent nodes had
  zero mobility, velocity kept only 55% per step with a 5 px cap, and every
  episode stopped after 120 steps.
- Layout was published before animating, so selection changes snapped nodes.

Revision 2 (`apps/web/src/lib/graph-physics.ts`) keeps placement, geometry and
dedupe, and replaces the force model. No dependency was added: d3-force would
still need custom directional forces and its own timer disabled, for a smaller
saving than the code it would replace.

- Every interaction is a force or a bounded per-step correction; no coordinate
  is ever clamped. Springs (rest = radii + 110), soft repulsion, and collision
  contact (center circles from measured size, 30-unit gap, inelastic) are all
  equal and opposite, so the network never drifts on its own. Hubs and the
  focus respond less because their mass grows with degree (focus x3).
- Direction: a citing paper prefers the right of the paper it cites. Around the
  focus this is strong (clearance radii + 60); elsewhere weak; reciprocal pairs
  have none. Violations also get a small vertical component so a node can slide
  around blockers. These are relative to node positions, never the canvas.
- Dragging: React Flow's pointer position is adopted verbatim for the dragged
  node (and co-selected nodes). Nodes up to three hops away receive a decaying
  share of each pointer movement immediately (45%, 20%, 8%, divided by mass),
  and springs pull them the rest of the way, so the network trails and stretches
  rather than translating rigidly. While an ordinary node is dragged, its own
  side preference is suspended; the focus's preferences stay active when the
  focus is dragged, so neighbors re-sort around it as it moves.
- Release: dropped nodes stay exactly where released for the rest of the
  episode; if a neighbor was dropped on the wrong side, the rest of the layout
  (including the focus) moves to restore the relationship.
- Locality: the changed node's two-hop neighborhood is fully mobile; other nodes
  respond at 25% until a collision wakes them. Expansion places new papers next
  to their parent (references left, citing papers right) and settles locally.
- Settling: damping 0.78, speed cap 36 px/step, rest after 12 quiet steps below
  0.15 px/step, extra friction after 180 steps, hard cap 480 steps (~8 s). The
  loop sleeps at rest and wakes on drag, expansion, refocus or resize. Restarts
  carry velocities over, so they are seamless. Reduced motion settles in one
  bounded batch (a few steps per pointer event during a drag).

The canvas publishes simulation positions once per animation frame and keeps
React Flow as the owner of pointer tracking, pan and zoom.

### Revision 1 notes (superseded movement model)

Previously, new nodes were placed in fixed 330x170 offsets with a rectangular
overlap heuristic. Revision 1 introduced `placeNear` (kept), incremental
detection of newly placed nodes, retained positions across filtering, and frame
cleanup on restart/unmount including Strict Mode (all kept).

## Verification (revision 2)

- `npm run lint`, `npm run typecheck`, `npm run build` pass. Frontend: 56 tests
  pass. The backend suite could not run in this sandbox (pytest's temporary
  directory was access-denied); no backend file was changed by this work.
- `graph-physics.test.ts` asserts outcomes rather than constants: pointer
  ownership anywhere (including the focus), elastic lag and hop falloff, release
  stability, wrong-side drop recovery, refocus sides, dense cycle determinism
  without overlap or drift, and expansion locality. Mutation checks: making the
  drag rigid fails 2 tests; removing the directional force fails 5.
- A real headless Chrome was driven with DevTools pointer events against
  `next dev` and the sample-data preview: focal drags horizontally across the
  origin, vertically, diagonally and at 2x zoom tracked the pointer 1:1 (0-0.4
  px) and did not move after release; an ordinary reference dragged past the
  focus stayed where dropped and the focus resettled to its right; three
  expansions moved existing papers 0.3-38 flow units with no overlaps; new
  focuses re-sorted citing/cited papers to the correct sides; edge hover showed
  no paper popup and edge click opened the citation panel; no console errors.

## Files

Revision 1 (Codex) created or changed these files; revision 2 reworked the
first four:

- `apps/web/src/components/graph/citation-canvas.tsx`
- `apps/web/src/lib/graph-physics.ts`
- `apps/web/src/__tests__/graph-physics.test.ts`
- `apps/web/src/__tests__/graph-interactions.test.tsx`
- `apps/web/src/__tests__/graph-markers.test.tsx` (unchanged in revision 2)
- `docs/GRAPH_INTERACTION_PHYSICS.md` (this report)

## Remaining limits and coordination

Revision 1 could not run a browser. Revision 2 verified pointer interaction in
headless Chrome with sample data only (see Verification); live API graphs,
touch input and frame rate on large graphs remain unmeasured.

This is local settlement, not a global edge-routing optimizer. Dense graphs can
still have crossings or edges through unrelated nodes. In crowded, cyclic
networks the focus's neighbors reach the correct side but not always the full
resting clearance. Nodes are solid: pushing a node straight into another shoves
it ahead (moving around it crosses freely). Multiple-node group dragging is
wired but not separately tested. Existing focus fading and
very low zoom can still reduce perceived arrow visibility; styles were preserved.
No frame-rate claim is made for large live graphs.

The merge-conflict risk is `citation-canvas.tsx`: Developer 1 may be changing its
edge renderer, hover handlers, sizing, or drag/layout logic at the same time.
Coordinate that file's hunks before integration. The helper and tests are new,
additive files. Existing `graph-focus.ts`, stylesheet rules, layouts, classification
components, and backend work were not changed. No commit, push, merge, reset,
rebase, or branch switch was performed.
