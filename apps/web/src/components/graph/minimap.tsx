"use client";

/**
 * The minimap.
 *
 * It reads node positions straight off the live cytoscape core rather than keeping a
 * second copy of the layout, so it cannot drift out of sync with what is on screen.
 * Sampling is throttled and capped: at 400 dots the map is already saturated, and a
 * 60-times-a-second redraw of a 4000-node estate would cost more than the map is worth.
 *
 * Click to recentre. Arrow keys pan, so it is not a mouse-only control.
 */

import type { Core } from "cytoscape";
import * as React from "react";
import { NODE_COLOUR } from "@/components/graph/graph-style";
import { cx } from "@/components/ui/primitives";

const MAX_DOTS = 400;
const THROTTLE_MS = 90;

interface Snapshot {
  dots: { x: number; y: number; c: string }[];
  box: { x1: number; y1: number; w: number; h: number };
  view: { x1: number; y1: number; w: number; h: number };
  total: number;
}

export function Minimap({
  getCore,
  version,
  className,
}: {
  getCore: () => Core | null;
  /** Bumped by the page whenever the displayed graph changes, to force a re-attach. */
  version: number;
  className?: string;
}) {
  const [snapshot, setSnapshot] = React.useState<Snapshot | null>(null);

  React.useEffect(() => {
    let disposed = false;
    let core: Core | null = null;
    let frame = 0;
    let last = 0;

    const sample = () => {
      if (disposed || !core || core.destroyed()) return;
      const nodes = core.nodes();
      if (!nodes.length) {
        setSnapshot(null);
        return;
      }
      const box = core.elements().boundingBox();
      if (!Number.isFinite(box.w) || box.w <= 0 || box.h <= 0) return;

      const step = Math.max(1, Math.ceil(nodes.length / MAX_DOTS));
      const dots: Snapshot["dots"] = [];
      for (let index = 0; index < nodes.length; index += step) {
        const node = nodes[index];
        const position = node.position();
        dots.push({
          x: position.x,
          y: position.y,
          c: NODE_COLOUR[node.data("type") as string] ?? "#8b94a4",
        });
      }

      const extent = core.extent();
      setSnapshot({
        dots,
        box: { x1: box.x1, y1: box.y1, w: box.w, h: box.h },
        view: { x1: extent.x1, y1: extent.y1, w: extent.w, h: extent.h },
        total: nodes.length,
      });
    };

    const schedule = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        const now = performance.now();
        if (now - last < THROTTLE_MS) {
          // Too soon; come back on a later frame rather than dropping the update.
          window.setTimeout(schedule, THROTTLE_MS - (now - last));
          return;
        }
        last = now;
        sample();
      });
    };

    // The canvas creates its core on mount, so the ref can still be empty on this pass.
    const attach = window.setInterval(() => {
      if (disposed || core) return;
      const candidate = getCore();
      if (!candidate) return;
      core = candidate;
      window.clearInterval(attach);
      core.on("render", schedule);
      core.on("position add remove layoutstop", schedule);
      schedule();
    }, 120);

    return () => {
      disposed = true;
      window.clearInterval(attach);
      if (frame) window.cancelAnimationFrame(frame);
      if (core && !core.destroyed()) {
        core.off("render", schedule);
        core.off("position add remove layoutstop", schedule);
      }
    };
  }, [getCore, version]);

  const pad = snapshot ? Math.max(snapshot.box.w, snapshot.box.h) * 0.06 + 8 : 0;
  const viewBox = snapshot
    ? `${snapshot.box.x1 - pad} ${snapshot.box.y1 - pad} ${snapshot.box.w + pad * 2} ${
        snapshot.box.h + pad * 2
      }`
    : "0 0 100 100";
  const unit = snapshot ? Math.max(snapshot.box.w, snapshot.box.h) / 130 : 1;

  const centreOn = React.useCallback(
    (modelX: number, modelY: number) => {
      const core = getCore();
      if (!core || core.destroyed()) return;
      const zoom = core.zoom();
      core.animate(
        {
          pan: {
            x: core.width() / 2 - modelX * zoom,
            y: core.height() / 2 - modelY * zoom,
          },
        },
        { duration: 220 },
      );
    },
    [getCore],
  );

  const onClick = (event: React.MouseEvent<SVGSVGElement>) => {
    if (!snapshot) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const fx = (event.clientX - rect.left) / rect.width;
    const fy = (event.clientY - rect.top) / rect.height;
    centreOn(
      snapshot.box.x1 - pad + fx * (snapshot.box.w + pad * 2),
      snapshot.box.y1 - pad + fy * (snapshot.box.h + pad * 2),
    );
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!snapshot) return;
    const stepX = snapshot.view.w * 0.25;
    const stepY = snapshot.view.h * 0.25;
    const centreX = snapshot.view.x1 + snapshot.view.w / 2;
    const centreY = snapshot.view.y1 + snapshot.view.h / 2;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-stepX, 0],
      ArrowRight: [stepX, 0],
      ArrowUp: [0, -stepY],
      ArrowDown: [0, stepY],
    };
    const move = moves[event.key];
    if (!move) return;
    event.preventDefault();
    centreOn(centreX + move[0], centreY + move[1]);
  };

  return (
    <div
      className={cx("panel-raised overflow-hidden", className)}
      role="group"
      aria-label="Minimap. Click to recentre the canvas; arrow keys pan it."
      tabIndex={0}
      onKeyDown={onKeyDown}
    >
      <div className="flex items-center justify-between gap-2 px-2 py-1">
        <span className="label-eyebrow">Minimap</span>
        <span className="numeral text-[10px] text-[var(--color-dim)]">
          {snapshot ? snapshot.total : 0}
        </span>
      </div>
      <div className="relative h-[108px] w-[160px] border-t border-[var(--color-line)]">
        {snapshot ? (
          <svg
            viewBox={viewBox}
            preserveAspectRatio="xMidYMid meet"
            className="h-full w-full cursor-crosshair"
            onClick={onClick}
            aria-hidden
          >
            {snapshot.dots.map((dot, index) => (
              <circle
                key={index}
                cx={dot.x}
                cy={dot.y}
                r={unit * 1.6}
                fill={dot.c}
                fillOpacity={0.75}
              />
            ))}
            <rect
              x={snapshot.view.x1}
              y={snapshot.view.y1}
              width={snapshot.view.w}
              height={snapshot.view.h}
              fill="var(--color-accent)"
              fillOpacity={0.08}
              stroke="var(--color-accent)"
              strokeOpacity={0.9}
              strokeWidth={unit * 1.1}
            />
          </svg>
        ) : (
          <p className="flex h-full items-center justify-center px-2 text-center text-[10.5px] leading-tight text-[var(--color-dim)]">
            Nothing laid out yet
          </p>
        )}
      </div>
    </div>
  );
}
