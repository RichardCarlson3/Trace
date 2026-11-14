import { describe, expect, it } from "vitest";
import {
  citationGeometry,
  circle,
  createPhysics,
  DIRECTION_GAP,
  MAX_SPEED,
  MAX_STEP_DISTANCE,
  MAX_STEPS,
  placeNear,
  uniqueCitations,
  type LayoutNode,
} from "@/lib/graph-physics";
import type { Citation } from "@/lib/types";

// Synthetic geometry fixtures; no scholarly evidence or model outputs.
// These tests assert observable physical outcomes (pointer ownership, lag,
// falloff, rest state, sides, overlap) rather than internal force constants.
type Simulation = ReturnType<typeof createPhysics>;
type Point = { x: number; y: number };
const node = (id: string, x: number, y = 0, size = 164): LayoutNode => ({
  id,
  x,
  y,
  width: size,
  height: size,
});
const edge = (
  source: string,
  target: string,
  id = `${source}-${target}`,
): Citation => ({
  id,
  source,
  target,
  intent: null,
  confidence: null,
  context_text: null,
  context_source_url: null,
});
const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
const snapshot = (sim: Simulation) =>
  new Map([...sim.positions].map(([id, point]) => [id, { ...point }]));
function finish(sim: Simulation) {
  let steps = 0;
  while (sim.step()) {
    steps += 1;
    if (steps > MAX_STEPS) throw new Error("Unbounded simulation");
  }
  return steps;
}
function settle(nodes: LayoutNode[], links: Citation[], focus: string) {
  const sim = createPhysics(nodes, links, focus, {
    active: nodes.map((item) => item.id),
  });
  finish(sim);
  return sim;
}
function centerOf(sim: Simulation, nodes: LayoutNode[], id: string) {
  const item = nodes.find((candidate) => candidate.id === id)!;
  return circle({ ...item, ...sim.positions.get(id)! });
}
function centerDistance(
  sim: Simulation,
  nodes: LayoutNode[],
  a: string,
  b: string,
) {
  return distance(centerOf(sim, nodes, a), centerOf(sim, nodes, b));
}
function expectNoOverlap(sim: Simulation, nodes: LayoutNode[]) {
  for (let i = 0; i < nodes.length; i += 1)
    for (let j = i + 1; j < nodes.length; j += 1) {
      const a = centerOf(sim, nodes, nodes[i].id),
        b = centerOf(sim, nodes, nodes[j].id);
      expect(distance(a, b)).toBeGreaterThan(a.radius + b.radius);
    }
}
/** Citing papers sit right of the focus, cited papers left (reciprocal pairs excepted). */
function expectSides(
  sim: Simulation,
  nodes: LayoutNode[],
  links: Citation[],
  focus: string,
  clearance = DIRECTION_GAP / 2,
) {
  const pairs = new Set(links.map((item) => `${item.source}:${item.target}`));
  for (const { source, target } of links) {
    if (source === target || (source !== focus && target !== focus)) continue;
    if (pairs.has(`${target}:${source}`)) continue;
    const citing = centerOf(sim, nodes, source),
      cited = centerOf(sim, nodes, target);
    const required = clearance ? citing.radius + cited.radius + clearance : 0;
    expect(citing.x - cited.x, `${source} -> ${target}`).toBeGreaterThan(
      required,
    );
  }
}
const starLinks = [
  edge("f", "r1"),
  edge("f", "r2"),
  edge("f", "r3"),
  edge("c1", "f"),
  edge("c2", "f"),
  edge("c3", "f"),
];
function star() {
  const placed: LayoutNode[] = [node("f", 0, 0, 208)];
  for (const id of ["r1", "r2", "r3", "c1", "c2", "c3"]) {
    const next = node(id, 0);
    placed.push({ ...next, ...placeNear(next, "f", placed, starLinks) });
  }
  return placed;
}

describe("elastic citation physics", () => {
  it("seeds references left and citing papers right without moving existing nodes", () => {
    const anchor = node("focus", 600, 400, 208);
    const original = { ...anchor };
    const placed = [anchor];
    const links = [edge("focus", "reference"), edge("citing", "focus")];
    const reference = {
      ...node("reference", 0),
      ...placeNear(node("reference", 0), "focus", placed, links),
    };
    placed.push(reference);
    const citing = {
      ...node("citing", 0),
      ...placeNear(node("citing", 0), "focus", placed, links),
    };
    expect(circle(reference).x).toBeLessThan(circle(anchor).x);
    expect(circle(citing).x).toBeGreaterThan(circle(anchor).x);
    expect(anchor).toEqual(original);
  });

  it("spaces a large expansion using rendered dimensions, and shared papers stay unique", () => {
    const placed = [node("focus", 0, 0, 208)];
    const links = Array.from({ length: 40 }, (_, i) => edge("focus", `r${i}`));
    for (let i = 0; i < 40; i += 1) {
      const next = node(`r${i}`, 0, 0, 208);
      placed.push({ ...next, ...placeNear(next, "focus", placed, links) });
    }
    for (let i = 0; i < placed.length; i += 1)
      for (let j = i + 1; j < placed.length; j += 1) {
        const a = circle(placed[i]),
          b = circle(placed[j]);
        expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThanOrEqual(
          a.radius + b.radius + 29.9,
        );
      }
    expect(
      uniqueCitations([
        edge("a", "b"),
        edge("a", "b", "duplicate"),
        edge("b", "a"),
      ]),
    ).toHaveLength(2);
  });

  it("separates coincident unequal nodes smoothly, with bounded steps, then comes to rest", () => {
    const nodes = [
      node("focus", 0, 0, 208),
      node("a", 0),
      node("b", 0, 0, 146),
      node("c", 0, 0, 96),
    ];
    const sim = createPhysics(nodes, [], "focus", {
      active: nodes.map((item) => item.id),
    });
    let previous = snapshot(sim);
    let steps = 0;
    while (sim.step()) {
      steps += 1;
      for (const [id, point] of sim.positions)
        expect(distance(point, previous.get(id)!)).toBeLessThanOrEqual(
          MAX_STEP_DISTANCE + 1e-8,
        );
      previous = snapshot(sim);
    }
    expect(steps).toBeLessThan(MAX_STEPS);
    expectNoOverlap(sim, nodes);
    const rest = snapshot(sim);
    expect(sim.step()).toBe(false);
    expect(snapshot(sim)).toEqual(rest);
  });

  it("clamps an over-limit velocity to MAX_SPEED within one step", () => {
    // Regression: this clamp branch once referenced an undefined MAX_STEP and
    // threw a ReferenceError in the browser. A lone body has no forces, so its
    // injected velocity (after damping) still exceeds the limit and must clamp.
    for (const injected of [
      { x: 1000, y: 0 },
      { x: -600, y: 800 },
    ]) {
      const nodes = [node("solo", 0)];
      const sim = createPhysics(nodes, [], null, {
        active: ["solo"],
        velocities: new Map([["solo", injected]]),
      });
      const before = snapshot(sim).get("solo")!;
      expect(() => sim.step()).not.toThrow();
      const velocity = sim.velocities().get("solo")!;
      expect(Math.hypot(velocity.x, velocity.y)).toBeCloseTo(MAX_SPEED, 8);
      // Direction is preserved; only the magnitude is limited.
      expect(Math.atan2(velocity.y, velocity.x)).toBeCloseTo(
        Math.atan2(injected.y, injected.x),
        8,
      );
      expect(distance(snapshot(sim).get("solo")!, before)).toBeCloseTo(
        MAX_SPEED,
        8,
      );
    }
  });

  it("holds any dragged node exactly at the pointer anywhere, including the selected paper and across the origin", () => {
    const nodes = star();
    for (const id of ["f", "r1", "c1"]) {
      const sim = createPhysics(nodes, starLinks, "f");
      // Far across the origin, through the opposite side, diagonally.
      for (const point of [
        { x: 1500, y: 0 },
        { x: -1800, y: -600 },
        { x: 40, y: 1200 },
        { x: -3, y: -2 },
      ]) {
        sim.drag(id, point);
        expect(sim.positions.get(id)).toEqual(point);
        for (let i = 0; i < 20; i += 1) {
          expect(sim.step()).toBe(true); // stays awake while dragging
          expect(sim.positions.get(id)).toEqual(point);
        }
      }
      const drop = { x: 420, y: -260 };
      sim.drag(id, drop);
      sim.release();
      finish(sim);
      expect(sim.positions.get(id)).toEqual(drop);
    }
  });

  it("pulls the connected network elastically instead of translating it as a rigid block", () => {
    const nodes = [...star(), node("deep", -900, 104), node("remote", 6000)];
    const links = [...starLinks, edge("r1", "deep")];
    const settled = settle(nodes, links, "f");
    const before = snapshot(settled);
    const sim = createPhysics(
      nodes.map((item) => ({ ...item, ...before.get(item.id)! })),
      links,
      "f",
    );
    const start = before.get("f")!;
    const moved = (id: string) =>
      distance(sim.positions.get(id)!, before.get(id)!);
    // Drag the focus 600px right in 30 pointer moves, one physics step each.
    for (let k = 1; k <= 30; k += 1) {
      sim.drag("f", { x: start.x + 20 * k, y: start.y });
      sim.step();
      if (k === 10) {
        // Neighbors respond immediately but trail the pointer (springs
        // stretch), and the response fades with graph distance.
        expect(moved("r1")).toBeGreaterThan(60);
        expect(moved("r1")).toBeLessThan(moved("f") - 20);
        expect(moved("deep")).toBeLessThan(moved("r1"));
        expect(moved("deep")).toBeGreaterThan(5);
        const offsets = ["r1", "r2", "c1", "deep"].map((id) =>
          Math.round(sim.positions.get(id)!.x - before.get(id)!.x),
        );
        expect(new Set(offsets).size).toBeGreaterThan(1);
      }
    }
    sim.release();
    finish(sim);
    expect(sim.positions.get("f")).toEqual({ x: start.x + 600, y: start.y });
    // The network caught up: every neighbor is back within spring range.
    for (const id of ["r1", "r2", "r3", "c1", "c2", "c3"])
      expect(centerDistance(sim, nodes, "f", id)).toBeLessThan(420);
    expect(moved("r1")).toBeGreaterThan(450);
    expectSides(sim, nodes, starLinks, "f");
    // Unconnected, far-away papers are not dragged along.
    expect(moved("remote")).toBeLessThan(2);
  });

  it("keeps a neighbor dropped on the wrong side where released and reorganizes the rest around it", () => {
    const nodes = star();
    const before = snapshot(settle(nodes, starLinks, "f"));
    const sim = createPhysics(
      nodes.map((item) => ({ ...item, ...before.get(item.id)! })),
      starLinks,
      "f",
    );
    // Drag reference r1 from the left of the focus to well past its right.
    const from = before.get("r1")!;
    for (let k = 1; k <= 30; k += 1) {
      sim.drag("r1", { x: from.x + 25 * k, y: from.y + 4 * k });
      sim.step();
    }
    const drop = { ...sim.positions.get("r1")! };
    expect(centerOf(sim, nodes, "r1").x).toBeGreaterThan(
      centerOf(sim, nodes, "f").x,
    );
    sim.release();
    expect(finish(sim)).toBeLessThan(MAX_STEPS);
    expect(sim.positions.get("r1")).toEqual(drop);
    expectSides(sim, nodes, starLinks, "f");
    expectNoOverlap(sim, nodes);
  });

  it("reorganizes direct relationships around a newly selected focus", () => {
    // a cites b, b cites c, d cites b; all start stacked in one column.
    const nodes = [
      node("a", 0, -400),
      node("b", 0, 0, 208),
      node("c", 0, 400),
      node("d", 0, 800),
    ];
    const links = [edge("a", "b"), edge("b", "c"), edge("d", "b")];
    const sim = settle(nodes, links, "b");
    expectSides(sim, nodes, links, "b");
    expectNoOverlap(sim, nodes);
    // Now select c: b (which cites c) must end up on c's right.
    const refocused = settle(
      nodes.map((item) => ({ ...item, ...sim.positions.get(item.id)! })),
      links,
      "c",
    );
    expectSides(refocused, nodes, links, "c");
  });

  it("settles dense shared references and cycles deterministically, without overlap, drift or flipped directions", () => {
    const sizes = (i: number) => 120 + (i % 4) * 24;
    const links: Citation[] = [];
    for (let i = 0; i < 24; i += 1)
      links.push(
        i % 2 ? edge(`n${i}`, "f") : edge("f", `n${i}`),
        edge(`n${i}`, `n${(i + 1) % 24}`),
        edge(`n${i}`, "n0"),
      );
    links.push(edge("n0", "f"), edge("f", "f"));
    const placed: LayoutNode[] = [node("f", 0, 0, 208)];
    for (let i = 0; i < 24; i += 1) {
      const next = node(`n${i}`, 0, 0, sizes(i));
      placed.push({ ...next, ...placeNear(next, "f", placed, links) });
    }
    const original = structuredClone(links);
    const run = (reverse: boolean) => {
      const sim = createPhysics(
        reverse ? [...placed].reverse() : placed,
        reverse ? [...links].reverse() : links,
        "f",
        { active: placed.map((item) => item.id) },
      );
      expect(finish(sim)).toBeLessThanOrEqual(MAX_STEPS);
      return sim;
    };
    const sim = run(false);
    expect(snapshot(run(true))).toEqual(snapshot(sim));
    expectNoOverlap(sim, placed);
    // Only single-direction direct relationships have a side; n0 <-> f is
    // reciprocal (f cites n0 and n0 cites f), so it has no preferred side.
    // Crowded: require the correct side, not the full resting clearance.
    expectSides(sim, placed, links, "f", 0);
    expect(distance(sim.positions.get("f")!, { x: 0, y: 0 })).toBeLessThan(300);
    expect(links).toEqual(original);
  });

  it("lets an expansion settle locally while distant parts of the network stay put", () => {
    const base = [
      node("f", 0, 0, 208),
      node("r", -330, 22),
      node("rr", -660, 22),
      node("rrr", -990, 22),
      node("far", -1320, 22),
    ];
    const chain = [
      edge("f", "r"),
      edge("r", "rr"),
      edge("rr", "rrr"),
      edge("rrr", "far"),
    ];
    const rest = snapshot(settle(base, chain, "f"));
    const placed = base.map((item) => ({ ...item, ...rest.get(item.id)! }));
    const added = ["n1", "n2", "n3", "n4", "n5", "c1", "c2"];
    const links = [
      ...chain,
      ...added.map((id) => (id[0] === "c" ? edge(id, "f") : edge("f", id))),
    ];
    for (const id of added) {
      const next = node(id, 0);
      placed.push({ ...next, ...placeNear(next, "f", placed, links) });
    }
    const sim = createPhysics(placed, links, "f", { active: added });
    finish(sim);
    expect(distance(sim.positions.get("far")!, rest.get("far")!)).toBeLessThan(
      40,
    );
    expectNoOverlap(sim, placed);
    expectSides(sim, placed, links, "f");
  });

  it("routes arrow tips outside actual circular bounds and updates as targets cross sides", () => {
    const source = node("BART", 0, 0, 208),
      target = node("Word2Vec", -350);
    const before = citationGeometry(source, target);
    expect(before.sourceSide).toBe("left");
    expect(before.targetSide).toBe("right");
    expect(before.targetX).toBeGreaterThan(target.x + target.width);
    const after = citationGeometry(source, { ...target, x: 600, y: 200 });
    expect(after.sourceSide).toBe("right");
    expect(after.targetSide).toBe("left");
    expect(after.targetX).not.toBe(before.targetX);
    const a = citationGeometry(source, target, true),
      b = citationGeometry(target, source, true);
    expect(a.sourceY).not.toBe(b.targetY);
  });
});
