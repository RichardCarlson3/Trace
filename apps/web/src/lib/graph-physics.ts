import type { Citation } from "./types";

export interface LayoutNode {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

type Point = { x: number; y: number };
/** Minimum clearance between two paper circles (collision gap). */
const GAP = 30;
/** Horizontal clearance between the focus and a direct neighbor at rest. */
export const DIRECTION_GAP = 60;
/** Settling budget after the pointer is released or the graph changes. */
export const MAX_STEPS = 480;
/** Per-step speed limit, so no body can jump across the canvas. */
export const MAX_SPEED = 36;

// Force model. Units are canvas pixels per 16 ms step.
const LINK_GAP = 110; // spring rest length beyond the two radii
const SPRING = 0.035;
const REPEL_GAP = 150; // soft repulsion range beyond the collision gap
const REPULSION = 0.012;
const DIRECTION = 0.1; // focus <-> direct neighbor side preference
const INDIRECT_DIRECTION = 0.01; // weak preference for every other citation
const MAX_FORCE = 8;
const DAMPING = 0.78; // velocity retained per step
const COLLISION_SHARE = 0.5; // fraction of an overlap resolved per pass
const MAX_COLLISION_STEP = 24;
const COLLISION_PASSES = 3;
/** Upper bound on how far any body can move in one step (no teleporting). */
export const MAX_STEP_DISTANCE =
  MAX_SPEED + COLLISION_PASSES * MAX_COLLISION_STEP;
const FOCUS_MASS = 3;
const IDLE_MOBILITY = 0.25; // bodies away from the interaction respond gently
const REST_SPEED = 0.15;
const COOLING_START = 180;
const QUIET_STEPS = 12;
/** Immediate share of a drag displacement passed to nodes N hops away. */
const CARRY = [1, 0.45, 0.2, 0.08];

export function uniqueCitations(citations: Citation[]): Citation[] {
  const seen = new Set<string>();
  return citations.filter(({ source, target }) => {
    const key = `${source}:${target}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function circle(node: LayoutNode) {
  return {
    x: node.x + node.width / 2,
    y: node.y + node.height / 2,
    radius: Math.max(node.width, node.height) / 2,
  };
}

export function citationGeometry(
  source: LayoutNode,
  target: LayoutNode,
  reciprocal = false,
) {
  const a = circle(source);
  const b = circle(target);
  const angle = Math.atan2(b.y - a.y, b.x - a.x);
  const turn = reciprocal ? 0.18 : 0;
  const startAngle = angle + turn;
  const endAngle = angle + Math.PI - turn;
  const side = (theta: number): "left" | "right" | "top" | "bottom" =>
    Math.abs(Math.cos(theta)) >= Math.abs(Math.sin(theta))
      ? Math.cos(theta) >= 0
        ? "right"
        : "left"
      : Math.sin(theta) >= 0
        ? "bottom"
        : "top";
  return {
    sourceX: a.x + Math.cos(startAngle) * (a.radius + 12),
    sourceY: a.y + Math.sin(startAngle) * (a.radius + 12),
    targetX: b.x + Math.cos(endAngle) * (b.radius + 12),
    targetY: b.y + Math.sin(endAngle) * (b.radius + 12),
    sourceSide: side(startAngle),
    targetSide: side(endAngle),
  };
}

export function placeNear(
  node: LayoutNode,
  originId: string | null,
  placed: LayoutNode[],
  citations: Citation[],
): Point {
  const relation =
    citations.find(
      (edge) =>
        (edge.source === originId && edge.target === node.id) ||
        (edge.target === originId && edge.source === node.id),
    ) ??
    citations.find(
      (edge) =>
        (edge.source === node.id &&
          placed.some((item) => item.id === edge.target)) ||
        (edge.target === node.id &&
          placed.some((item) => item.id === edge.source)),
    );
  const anchorId = relation
    ? relation.source === node.id
      ? relation.target
      : relation.source
    : originId;
  const anchor = placed.find((item) => item.id === anchorId) ?? placed[0];
  if (!anchor) return { x: 0, y: 0 };
  const center = circle(anchor);
  const radius = circle(node).radius;
  const side = relation?.source === anchor.id ? -1 : 1;
  const spacing = Math.max(240, radius * 2 + GAP);
  for (let index = 0; ; index += 1) {
    const row = index % 9;
    const offset = row === 0 ? 0 : Math.ceil(row / 2) * (row % 2 ? 1 : -1);
    const candidate = {
      x:
        center.x +
        side * (center.radius + radius + 110 + Math.floor(index / 9) * spacing),
      y: center.y + offset * spacing,
    };
    if (
      placed.every((item) => {
        const other = circle(item);
        return (
          Math.hypot(other.x - candidate.x, other.y - candidate.y) >=
          other.radius + radius + GAP
        );
      })
    )
      return {
        x: candidate.x - node.width / 2,
        y: candidate.y - node.height / 2,
      };
  }
}

export interface PhysicsOptions {
  /** Nodes that changed (added, dragged, refocused). Their neighborhood is fully mobile. */
  active?: Iterable<string>;
  /** Velocities carried over from a previous simulation, for seamless restarts. */
  velocities?: Map<string, Point>;
}

/**
 * Elastic citation-network simulation.
 *
 * Positions are soft: springs, repulsion, collisions and directional
 * preferences are all forces or bounded per-step corrections. Nothing is
 * clamped to a coordinate, so any node can be dragged anywhere. A dragged
 * node is held exactly at the pointer; its graph neighborhood receives a
 * decaying share of each pointer movement immediately and catches up through
 * the springs. A released node stays where it was dropped for the rest of the
 * settling episode, and the rest of the layout adjusts around it.
 */
export function createPhysics(
  nodes: LayoutNode[],
  citations: Citation[],
  focusId: string | null,
  options: PhysicsOptions = {},
) {
  const compareId = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
  const bodies = [...nodes]
    .sort((a, b) => compareId(a.id, b.id))
    .map((node) => {
      const center = circle(node);
      const velocity = options.velocities?.get(node.id);
      return {
        id: node.id,
        width: node.width,
        height: node.height,
        radius: center.radius,
        x: center.x,
        y: center.y,
        px: center.x,
        py: center.y,
        vx: velocity?.x ?? 0,
        vy: velocity?.y ?? 0,
        fx: 0,
        fy: 0,
        mass: node.id === focusId ? FOCUS_MASS : 1,
        mobility: 1,
        fixed: false,
      };
    });
  type Body = (typeof bodies)[number];
  const lookup = new Map(bodies.map((body) => [body.id, body]));

  // One spring per connected pair; reciprocal citations share a spring.
  const pairs = new Map<
    string,
    { a: Body; b: Body; aCitesB: boolean; bCitesA: boolean }
  >();
  for (const { source, target } of uniqueCitations(citations)) {
    const s = lookup.get(source),
      t = lookup.get(target);
    if (!s || !t || s === t) continue;
    const [a, b] = compareId(s.id, t.id) < 0 ? [s, t] : [t, s];
    const key = `${a.id}:${b.id}`;
    const pair = pairs.get(key) ?? { a, b, aCitesB: false, bCitesA: false };
    if (s === a) pair.aCitesB = true;
    else pair.bCitesA = true;
    pairs.set(key, pair);
  }
  const springs = [...pairs.entries()]
    .sort(([a], [b]) => compareId(a, b))
    .map(([, pair]) => pair);
  const adjacency = new Map(bodies.map((body) => [body, [] as Body[]]));
  for (const { a, b } of springs) {
    adjacency.get(a)!.push(b);
    adjacency.get(b)!.push(a);
  }
  const degree = (body: Body) => Math.max(1, adjacency.get(body)!.length);
  // All pairwise forces are equal and opposite, so the network never drifts
  // on its own. Hubs and the focus respond less because they are heavier.
  for (const body of bodies) body.mass *= Math.sqrt(degree(body));

  // Directional preferences: the citing paper sits to the right of the paper
  // it cites. Strong around the focus, weak elsewhere, absent for reciprocal
  // pairs. They are forces, never coordinate clamps.
  const rules = springs
    .filter(({ aCitesB, bCitesA }) => aCitesB !== bCitesA)
    .map(({ a, b, aCitesB }) => {
      const citing = aCitesB ? a : b,
        cited = aCitesB ? b : a;
      const direct = citing.id === focusId || cited.id === focusId;
      return {
        citing,
        cited,
        strength: direct ? DIRECTION : INDIRECT_DIRECTION,
        separation: direct
          ? citing.radius + cited.radius + DIRECTION_GAP
          : (citing.radius + cited.radius) / 2,
      };
    });

  function within(starts: Body[], maxHops: number) {
    const hops = new Map<Body, number>(starts.map((body) => [body, 0]));
    const queue = [...starts];
    for (let index = 0; index < queue.length; index += 1) {
      const body = queue[index],
        hop = hops.get(body)!;
      if (hop >= maxHops) continue;
      for (const next of adjacency.get(body)!) {
        if (hops.has(next)) continue;
        hops.set(next, hop + 1);
        queue.push(next);
      }
    }
    return hops;
  }
  function activate(ids: Iterable<string>) {
    const starts = [...ids].flatMap((id) => lookup.get(id) ?? []);
    if (!starts.length) return;
    const near = within(starts, 2);
    for (const body of bodies)
      body.mobility = near.has(body) ? 1 : IDLE_MOBILITY;
  }
  activate(options.active ?? []);

  let dragged: Body | null = null;
  let carry = new Map<Body, number>();
  let steps = 0,
    quiet = 0;
  const positions = new Map<string, Point>();
  function publish() {
    for (const body of bodies) {
      const point = positions.get(body.id);
      const x = body.x - body.width / 2,
        y = body.y - body.height / 2;
      if (point) {
        point.x = x;
        point.y = y;
      } else positions.set(body.id, { x, y });
    }
  }
  publish();

  function separate(a: Body, b: Body, i: number, j: number) {
    let dx = b.x - a.x,
      dy = b.y - a.y,
      distance = Math.hypot(dx, dy);
    if (distance < 0.01) {
      // Deterministic escape direction for coincident bodies.
      const angle = (i * 7 + j * 13) * 2.39996;
      dx = Math.cos(angle);
      dy = Math.sin(angle);
      distance = 1;
    }
    return { ux: dx / distance, uy: dy / distance, distance };
  }

  function collide() {
    for (let pass = 0; pass < COLLISION_PASSES; pass += 1) {
      for (let i = 0; i < bodies.length; i += 1) {
        const a = bodies[i];
        for (let j = i + 1; j < bodies.length; j += 1) {
          const b = bodies[j];
          const minimum = a.radius + b.radius + GAP;
          if (Math.abs(b.x - a.x) >= minimum || Math.abs(b.y - a.y) >= minimum)
            continue;
          const { ux, uy, distance } = separate(a, b, i, j);
          const overlap = minimum - distance;
          if (overlap <= 0) continue;
          const wa = a.fixed ? 0 : 1 / a.mass,
            wb = b.fixed ? 0 : 1 / b.mass;
          if (!wa && !wb) continue;
          const push = Math.min(MAX_COLLISION_STEP, overlap * COLLISION_SHARE);
          const sa = wa / (wa + wb),
            sb = wb / (wa + wb);
          a.x -= ux * push * sa;
          a.y -= uy * push * sa;
          b.x += ux * push * sb;
          b.y += uy * push * sb;
          // Inelastic contact: cancel the approaching velocity so springs
          // cannot keep driving bodies into each other.
          const closing = (b.vx - a.vx) * ux + (b.vy - a.vy) * uy;
          if (closing < 0) {
            a.vx += ux * closing * sa;
            a.vy += uy * closing * sa;
            b.vx -= ux * closing * sb;
            b.vy -= uy * closing * sb;
          }
          // Contact wakes a resting body so it moves out of the way fully.
          a.mobility = b.mobility = 1;
        }
      }
    }
  }

  const running = () =>
    dragged !== null || (steps < MAX_STEPS && quiet < QUIET_STEPS);

  return {
    positions,
    /**
     * Hold `id` at the pointer (top-left `point`). With `lead`, nearby graph
     * neighbors receive a decaying share of the movement right away; the
     * springs then pull them the rest of the way.
     */
    drag(id: string, point: Point, lead = true) {
      const body = lookup.get(id);
      if (!body) return;
      const x = point.x + body.width / 2,
        y = point.y + body.height / 2;
      if (lead && dragged !== body) {
        dragged = body;
        carry = new Map(
          [...within([body], CARRY.length - 1)].map(([other, hop]) => [
            other,
            CARRY[hop],
          ]),
        );
        activate([id]);
      }
      if (lead) {
        const dx = x - body.x,
          dy = y - body.y;
        for (const [other, share] of carry) {
          if (other === body || other.fixed) continue;
          other.x += dx * (share / other.mass);
          other.y += dy * (share / other.mass);
        }
      }
      body.fixed = true;
      body.x = body.px = x;
      body.y = body.py = y;
      body.vx = body.vy = 0;
      steps = quiet = 0;
      publish();
    },
    /** End the pointer drag. Released bodies stay where they were dropped. */
    release() {
      dragged = null;
      steps = quiet = 0;
    },
    get dragging() {
      return dragged?.id ?? null;
    },
    velocities() {
      return new Map(
        bodies.map((body) => [body.id, { x: body.vx, y: body.vy }]),
      );
    },
    step() {
      if (!running()) return false;
      steps += 1;
      for (const body of bodies) {
        body.fx = body.fy = 0;
        body.px = body.x;
        body.py = body.y;
      }
      for (const { a, b } of springs) {
        const { ux, uy, distance } = separate(a, b, 0, 1);
        const rest = a.radius + b.radius + LINK_GAP;
        const force = Math.max(
          -MAX_FORCE,
          Math.min(MAX_FORCE, (distance - rest) * SPRING),
        );
        a.fx += ux * force;
        a.fy += uy * force;
        b.fx -= ux * force;
        b.fy -= uy * force;
      }
      for (let i = 0; i < bodies.length; i += 1) {
        const a = bodies[i];
        for (let j = i + 1; j < bodies.length; j += 1) {
          const b = bodies[j];
          const range = a.radius + b.radius + GAP + REPEL_GAP;
          if (Math.abs(b.x - a.x) >= range || Math.abs(b.y - a.y) >= range)
            continue;
          const { ux, uy, distance } = separate(a, b, i, j);
          if (distance >= range) continue;
          const force = Math.min(MAX_FORCE, (range - distance) * REPULSION);
          a.fx -= ux * force;
          a.fy -= uy * force;
          b.fx += ux * force;
          b.fy += uy * force;
        }
      }
      for (const { citing, cited, strength, separation } of rules) {
        // While the user drags an ordinary node, its side preference is
        // suspended so it never resists the pointer; it resumes on release.
        if (dragged && dragged.id !== focusId)
          if (citing === dragged || cited === dragged) continue;
        const violation = separation - (citing.x - cited.x);
        if (violation <= 0) continue;
        const force = Math.min(
          strength === DIRECTION ? MAX_FORCE * 3 : MAX_FORCE,
          violation * strength,
        );
        citing.fx += force;
        cited.fx -= force;
        // A small vertical component lets a node slide around the papers
        // between it and its side instead of pressing straight into them.
        const lift = (citing.y >= cited.y ? 1 : -1) * force * 0.3;
        citing.fy += lift;
        cited.fy -= lift;
      }
      // Late in a settling episode, friction rises so frustrated layouts
      // (dense cycles) come to rest gradually instead of stopping abruptly.
      const cooling =
        dragged || steps <= COOLING_START
          ? 1
          : 1 - (0.6 * (steps - COOLING_START)) / (MAX_STEPS - COOLING_START);
      for (const body of bodies) {
        if (body.fixed) {
          body.vx = body.vy = 0;
          continue;
        }
        const scale = body.mobility / body.mass;
        body.vx = (body.vx + body.fx * scale) * DAMPING * cooling;
        body.vy = (body.vy + body.fy * scale) * DAMPING * cooling;
        const speed = Math.hypot(body.vx, body.vy);
        if (speed > MAX_SPEED) {
          body.vx *= MAX_SPEED / speed;
          body.vy *= MAX_SPEED / speed;
        }
        body.x += body.vx;
        body.y += body.vy;
      }
      collide();
      let motion = 0;
      for (const body of bodies)
        motion = Math.max(
          motion,
          Math.hypot(body.x - body.px, body.y - body.py),
        );
      quiet = motion < REST_SPEED ? quiet + 1 : 0;
      publish();
      return running();
    },
  };
}
