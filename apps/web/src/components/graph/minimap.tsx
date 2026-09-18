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
const MAP_W = 160;
const MAP_H = 108;
const ASPECT = MAP_W / MAP_H;

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

    // A timer rather than an animation frame: requestAnimationFrame stops firing in a
    // background tab and in headless rendering, and a minimap that silently stops being
    // true is worse than one that updates a beat late.
    const schedule = () => {
      if (frame) return;
      const wait = Math.max(0, THROTTLE_MS - (performance.now() - last));
      frame = window.setTimeout(() => {
        frame = 0;
        last = performance.now();
        sample();
      }, wait);
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
      sample();
    }, 120);

    // The layout animates for a few hundred milliseconds after the data lands, and a
    // graph nobody is touching emits no events at all. A slow heartbeat keeps the map
    // honest in both cases for a cost that does not register.
    const heartbeat = window.setInterval(schedule, 1000);

    return () => {
      disposed = true;
      window.clearInterval(attach);
      window.clearInterval(heartbeat);
      if (frame) window.clearTimeout(frame);
      if (core && !core.destroyed()) {
        core.off("render", schedule);
        core.off("position add remove layoutstop", schedule);
      }
    };
  }, [getCore, version]);

  // The frame is the union of the graph and the current viewport, so zooming out never
  // squeezes the estate into a corner and zooming in never pushes the viewport rectangle
  // off the edge of the map.
  const frame = React.useMemo(() => {
    if (!snapshot) return null;
    const { box, view } = snapshot;
    const x1 = Math.min(box.x1, view.x1);
    const y1 = Math.min(box.y1, view.y1);
    const x2 = Math.max(box.x1 + box.w, view.x1 + view.w);
    const y2 = Math.max(box.y1 + box.h, view.y1 + view.h);
    const pad = Math.max(x2 - x1, y2 - y1, 1) * 0.05;
    let w = Math.max(x2 - x1, 1) + pad * 2;
    let h = Math.max(y2 - y1, 1) + pad * 2;
    const cx = (x1 + x2) / 2;
    const cy = (y1 + y2) / 2;
    // Match the frame to the map's own aspect ratio, so the SVG fills it exactly and a
    // click maps back to a model coordinate without having to undo any letterboxing.
    if (w / h > ASPECT) h = w / ASPECT;
    else w = h * ASPECT;
    return { x: cx - w / 2, y: cy - h / 2, w, h };
  }, [snapshot]);

  const viewBox = frame ? `${frame.x} ${frame.y} ${frame.w} ${frame.h}` : "0 0 100 100";
  const unit = frame ? Math.max(frame.w, frame.h) / 130 : 1;

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
    if (!frame) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const fx = (event.clientX - rect.left) / rect.width;
    const fy = (event.clientY - rect.top) / rect.height;
    centreOn(frame.x + fx * frame.w, frame.y + fy * frame.h);
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
      <div
        className="relative border-t border-[var(--color-line)]"
        style={{ width: MAP_W, height: MAP_H }}
      >
        {snapshot ? (
          <svg
            viewBox={viewBox}
            preserveAspectRatio="none"
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
