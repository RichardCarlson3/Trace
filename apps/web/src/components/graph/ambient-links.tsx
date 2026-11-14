"use client";

import { useEffect, useRef } from "react";

const LINK_LIFETIME = 12_000;
const DOT_COUNT = 34;
const dots = Array.from({ length: DOT_COUNT }, (_, index) => ({
  x: 0.08 + ((index * 0.61803398875) % 1) * 0.84,
  y: 0.1 + ((index * 0.41421356237) % 1) * 0.8,
  phase: index * 0.82,
}));

type Link = { from: number; to: number; createdAt: number };

export function AmbientLinks() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

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
    let cursor: { x: number; y: number } | null = null;
    let lastDot: number | null = null;
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
          ctx.strokeStyle = "rgba(126, 118, 181, 0.1)";
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      });

      for (const link of links) {
        const age = (time - link.createdAt) / LINK_LIFETIME;
        const from = dotPosition(link.from, time);
        const to = dotPosition(link.to, time);
        ctx.beginPath();
        ctx.moveTo(from.x, from.y);
        ctx.lineTo(to.x, to.y);
        ctx.strokeStyle = `rgba(150, 139, 255, ${0.62 * (1 - age)})`;
        ctx.lineWidth = 1.5;
        ctx.stroke();
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
          ctx.strokeStyle = `rgba(117, 179, 255, ${0.32 * (1 - distance / 140)})`;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
        const pulse = reduceMotion ? 0 : Math.sin(time / 900 + dot.phase) * 0.7;
        ctx.beginPath();
        ctx.arc(position.x, position.y, 2.3 + pulse, 0, Math.PI * 2);
        ctx.fillStyle = distance < 140 ? "#b8caff" : "#6e719e";
        ctx.fill();
        if (index === lastDot) {
          ctx.beginPath();
          ctx.arc(position.x, position.y, 8, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(190, 175, 255, 0.75)";
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
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
        glow.addColorStop(0, "rgba(133, 112, 255, 0.15)");
        glow.addColorStop(1, "rgba(133, 112, 255, 0)");
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

    function connect(event: PointerEvent) {
      if (reduceMotion || !(event.target instanceof Element)) return;
      if (!host!.contains(event.target)) return;
      if (
        event.target.closest(
          ".react-flow__node, .react-flow__edge, .react-flow__controls, button, a, input, select",
        )
      ) {
        return;
      }
      const rect = host!.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const time = performance.now();
      let nearest = 0;
      let distance = Infinity;
      dots.forEach((_, index) => {
        const point = dotPosition(index, time);
        const nextDistance = Math.hypot(point.x - x, point.y - y);
        if (nextDistance < distance) {
          nearest = index;
          distance = nextDistance;
        }
      });
      if (lastDot !== null && lastDot !== nearest) {
        links.push({ from: lastDot, to: nearest, createdAt: time });
        links = links.slice(-40);
      }
      lastDot = nearest;
    }

    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();
    if (!reduceMotion) {
      window.addEventListener("pointermove", move, { passive: true });
      window.addEventListener("pointerdown", connect, { passive: true });
      frame = requestAnimationFrame(animate);
    }
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerdown", connect);
    };
  }, []);

  return (
    <canvas ref={canvasRef} className="ambient-links" aria-hidden="true" />
  );
}
