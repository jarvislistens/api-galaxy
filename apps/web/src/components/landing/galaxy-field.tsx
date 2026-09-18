"use client";

/**
 * The hero galaxy.
 *
 * A deterministic field of nodes standing in for schemas and endpoints, drifting slowly
 * and linking to their nearest neighbours. It is canvas rather than DOM because a few
 * hundred animated elements in the layout tree makes the whole page janky, and it is
 * seeded rather than random so the composition is the same every visit.
 *
 * With `prefers-reduced-motion` it draws one static frame and stops — motion is removed,
 * not slowed.
 */

import * as React from "react";

interface Star {
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  r: number;
  kind: 0 | 1 | 2; // 0 schema, 1 endpoint, 2 domain
}

const COLOURS = ["#8fa7c4", "#7c8cf8", "#55c8ea"];
const COUNT = 150;
const LINK_DISTANCE = 128;

/** A tiny deterministic PRNG so the field looks the same on every load. */
function mulberry(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function GalaxyField({ className }: { className?: string }) {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let width = 0;
    let height = 0;
    let dpr = 1;
    let stars: Star[] = [];
    let frame = 0;
    let running = true;

    const seed = mulberry(20260919);

    const build = () => {
      const rect = canvas.parentElement?.getBoundingClientRect();
      width = Math.max(320, Math.floor(rect?.width ?? window.innerWidth));
      height = Math.max(320, Math.floor(rect?.height ?? window.innerHeight));
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);

      const random = mulberry(20260919);
      stars = Array.from({ length: COUNT }, () => {
        const z = 0.35 + random() * 0.65;
        return {
          x: random() * width,
          y: random() * height,
          z,
          vx: (random() - 0.5) * 0.09 * z,
          vy: (random() - 0.5) * 0.09 * z,
          r: (random() < 0.08 ? 2.6 : random() < 0.4 ? 1.7 : 1.1) * z,
          kind: (random() < 0.08 ? 2 : random() < 0.5 ? 1 : 0) as 0 | 1 | 2,
        };
      });
      void seed;
    };

    const draw = () => {
      context.clearRect(0, 0, width, height);

      // Links first, so nodes sit on top of their own edges.
      context.lineWidth = 0.6;
      for (let i = 0; i < stars.length; i += 1) {
        const a = stars[i];
        for (let j = i + 1; j < stars.length; j += 1) {
          const b = stars[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const distance = Math.hypot(dx, dy);
          if (distance > LINK_DISTANCE) continue;
          const alpha = (1 - distance / LINK_DISTANCE) * 0.16 * Math.min(a.z, b.z);
          context.strokeStyle = `rgba(150, 168, 200, ${alpha.toFixed(3)})`;
          context.beginPath();
          context.moveTo(a.x, a.y);
          context.lineTo(b.x, b.y);
          context.stroke();
        }
      }

      for (const star of stars) {
        context.beginPath();
        context.fillStyle = COLOURS[star.kind];
        context.globalAlpha = 0.22 + star.z * 0.5;
        context.arc(star.x, star.y, star.r, 0, Math.PI * 2);
        context.fill();
        if (star.kind === 2) {
          context.globalAlpha = 0.09 * star.z;
          context.beginPath();
          context.arc(star.x, star.y, star.r * 5, 0, Math.PI * 2);
          context.fill();
        }
      }
      context.globalAlpha = 1;
    };

    const step = () => {
      if (!running) return;
      for (const star of stars) {
        star.x += star.vx;
        star.y += star.vy;
        if (star.x < -20) star.x = width + 20;
        if (star.x > width + 20) star.x = -20;
        if (star.y < -20) star.y = height + 20;
        if (star.y > height + 20) star.y = -20;
      }
      draw();
      frame = requestAnimationFrame(step);
    };

    build();
    if (reduceMotion) {
      draw();
    } else {
      frame = requestAnimationFrame(step);
    }

    const onResize = () => {
      build();
      if (reduceMotion) draw();
    };
    window.addEventListener("resize", onResize);

    // Pause when the tab is hidden — an invisible canvas should not cost battery.
    const onVisibility = () => {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(frame);
      } else if (!reduceMotion) {
        running = true;
        frame = requestAnimationFrame(step);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      running = false;
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", onResize);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      aria-hidden="true"
      role="presentation"
    />
  );
}
