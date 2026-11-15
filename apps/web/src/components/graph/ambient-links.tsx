"use client";

import { useEffect, useRef } from "react";

const LINK_LIFETIME = 12_000;
const DOT_COUNT = 34;
const dots = Array.from({ length: DOT_COUNT }, (_, index) => ({
  x: 0.08 + ((index * 0.61803398875) % 1) * 0.84,
  y: 0.1 + ((index * 0.41421356237) % 1) * 0.8,
  phase: index * 0.82,
}));

type Point = { x: number; y: number; createdAt: number };
type Link = { from: Point; to: Point; createdAt: number };

export function AmbientLinks({ canDraw = true }: { canDraw?: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const canDrawRef = useRef(canDraw);

  useEffect(() => {
    canDrawRef.current = canDraw;
  }, [canDraw]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const host = canvas?.parentElement;
    if (!canvas || !host) return;

    let context: CanvasRenderingContext2D | null = null;
    try {
      context = canvas.getContext("2d");
    } catch {
      return;
    }
    if (!context) return;
    const ctx = context;
    const reduceMotion =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    let width = 0;
    let height = 0;
    let frame = 0;
    const expiryTimers: number[] = [];
    let cursor: { x: number; y: number } | null = null;
    let lastPoint: Point | null = null;
    let points: Point[] = [];
    let links: Link[] = [];

    function resize() {
      const rect = host!.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      const scale = Math.min(window.devicePixelRatio || 1, 2);
      canvas!.width = Math.max(1, Math.round(width * scale));
      canvas!.height = Math.max(1, Math.round(height * scale));
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      if (reduceMotion) draw(performance.now());
    }

    function dotPosition(index: number, time: number) {
      const dot = dots[index];
      const drift = reduceMotion ? 0 : Math.sin(time / 1600 + dot.phase) * 7;
      return { x: dot.x * width + drift, y: dot.y * height - drift * 0.6 };
    }

    function draw(time: number) {
      ctx.clearRect(0, 0, width, height);
      links = links.filter((link) => time - link.createdAt < LINK_LIFETIME);
      points = points.filter((point) => time - point.createdAt < LINK_LIFETIME);
      if (lastPoint && time - lastPoint.createdAt >= LINK_LIFETIME)
        lastPoint = null;

      // A quiet network moves behind the real citation graph at all times.
      dots.forEach((_, index) => {
        const from = dotPosition(index, time);
        let nearest: {
          point: { x: number; y: number };
          distance: number;
        } | null = null;
        for (let next = index + 1; next < dots.length; next += 1) {
          const point = dotPosition(next, time);
          const distance = Math.hypot(from.x - point.x, from.y - point.y);
          if (distance < 190 && (!nearest || distance < nearest.distance)) {
            nearest = { point, distance };
          }
        }
        if (nearest) {
          ctx.beginPath();
          ctx.moveTo(from.x, from.y);
          ctx.lineTo(nearest.point.x, nearest.point.y);
          ctx.strokeStyle = "rgba(168, 75, 84, 0.12)";
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      });

      for (const link of links) {
        const age = (time - link.createdAt) / LINK_LIFETIME;
        const from = { x: link.from.x * width, y: link.from.y * height };
        const to = { x: link.to.x * width, y: link.to.y * height };
        ctx.beginPath();
        ctx.moveTo(from.x, from.y);
        ctx.lineTo(to.x, to.y);
        ctx.strokeStyle = `rgba(212, 91, 101, ${0.62 * (1 - age)})`;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      for (const point of points) {
        const age = (time - point.createdAt) / LINK_LIFETIME;
        const x = point.x * width;
        const y = point.y * height;
        ctx.beginPath();
        ctx.arc(x, y, 7, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(226, 174, 180, ${0.7 * (1 - age)})`;
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(x, y, 2.8, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(248, 240, 241, ${1 - age})`;
        ctx.fill();
      }

      dots.forEach((dot, index) => {
        const position = dotPosition(index, time);
        const distance = cursor
          ? Math.hypot(position.x - cursor.x, position.y - cursor.y)
          : Infinity;
        if (cursor && distance < 140 && !reduceMotion) {
          ctx.beginPath();
          ctx.moveTo(position.x, position.y);
          ctx.lineTo(cursor.x, cursor.y);
          ctx.strokeStyle = `rgba(194, 70, 82, ${0.32 * (1 - distance / 140)})`;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
        const pulse = reduceMotion ? 0 : Math.sin(time / 900 + dot.phase) * 0.7;
        ctx.beginPath();
        ctx.arc(position.x, position.y, 2.3 + pulse, 0, Math.PI * 2);
        ctx.fillStyle = distance < 140 ? "#f6f0f1" : "#938387";
        ctx.fill();
      });

      if (cursor && !reduceMotion) {
        const glow = ctx.createRadialGradient(
          cursor.x,
          cursor.y,
          0,
          cursor.x,
          cursor.y,
          90,
        );
        glow.addColorStop(0, "rgba(163, 40, 51, 0.15)");
        glow.addColorStop(1, "rgba(163, 40, 51, 0)");
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(cursor.x, cursor.y, 90, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    function animate(time: number) {
      if (!document.hidden) draw(time);
      frame = requestAnimationFrame(animate);
    }

    function move(event: PointerEvent) {
      const rect = host!.getBoundingClientRect();
      cursor =
        event.clientX >= rect.left &&
        event.clientX <= rect.right &&
        event.clientY >= rect.top &&
        event.clientY <= rect.bottom
          ? { x: event.clientX - rect.left, y: event.clientY - rect.top }
          : null;
    }

    function connect(event: MouseEvent) {
      if (
        !canDrawRef.current ||
        event.button !== 0 ||
        event.detail > 1 ||
        !(event.target instanceof Element)
      )
        return;
      if (!host!.contains(event.target)) return;
      if (
        event.target.closest(
          ".react-flow__node, .react-flow__edge, .react-flow__controls, button, a, input, select",
        )
      ) {
        return;
      }
      const rect = host!.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width;
      const y = (event.clientY - rect.top) / rect.height;
      const time = performance.now();
      if (x < 0 || x > 1 || y < 0 || y > 1) return;
      const point = { x, y, createdAt: time };
      if (lastPoint && time - lastPoint.createdAt < LINK_LIFETIME) {
        lastPoint.createdAt = time;
        links.push({ from: lastPoint, to: point, createdAt: time });
        links = links.slice(-80);
      }
      points.push(point);
      points = points.slice(-81);
      lastPoint = point;
      if (reduceMotion) {
        draw(time);
        expiryTimers.push(
          window.setTimeout(() => draw(performance.now()), LINK_LIFETIME + 20),
        );
      }
    }

    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();
    window.addEventListener("click", connect);
    if (!reduceMotion) {
      window.addEventListener("pointermove", move, { passive: true });
      frame = requestAnimationFrame(animate);
    }
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      expiryTimers.forEach((timer) => window.clearTimeout(timer));
      window.removeEventListener("pointermove", move);
      window.removeEventListener("click", connect);
    };
  }, []);

  return (
    <canvas ref={canvasRef} className="ambient-links" aria-hidden="true" />
  );
}
