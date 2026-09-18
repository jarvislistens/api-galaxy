"use client";

/**
 * The shockwave, on the graph.
 *
 * The canvas is decorative for assistive technology — the shockwave table underneath is the
 * equivalent, and it is the thing that is keyboard navigable. That is stated in the caption
 * rather than left for the reader to discover.
 */

import { Crosshair, Maximize2, ZoomIn, ZoomOut } from "lucide-react";
import * as React from "react";
import { GraphCanvas, type GraphCanvasHandle } from "@/components/graph/graph-canvas";
import { STATUS_COLOUR } from "@/components/graph/graph-style";
import { Button, Card, LoadingBlock, SectionTitle } from "@/components/ui/primitives";
import type { GraphPayload } from "@/lib/types";
import { STATUS_META } from "@/components/break-lab/shockwave";

const LEGEND = ["broken", "degraded", "potentially_affected"] as const;

export function ImpactGraph({
  graph,
  impact,
  selectedId,
  onSelect,
  loading,
}: {
  graph: GraphPayload | undefined;
  impact: Record<string, string>;
  selectedId: string | null;
  onSelect: (nodeId: string | null) => void;
  loading?: boolean;
}) {
  const canvas = React.useRef<GraphCanvasHandle | null>(null);
  const affected = Object.keys(impact).length;

  return (
    <Card className="overflow-hidden p-0">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--color-line)] px-4 py-3">
        <SectionTitle>Blast radius on the graph</SectionTitle>
        <div className="mb-3 flex items-center gap-1">
          <Button variant="ghost" size="sm" aria-label="Zoom in" onClick={() => canvas.current?.zoomBy(1.25)}>
            <ZoomIn size={13} />
          </Button>
          <Button variant="ghost" size="sm" aria-label="Zoom out" onClick={() => canvas.current?.zoomBy(0.8)}>
            <ZoomOut size={13} />
          </Button>
          <Button variant="ghost" size="sm" aria-label="Fit the graph to the view" onClick={() => canvas.current?.fit()}>
            <Maximize2 size={13} />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-label="Centre on the selected node"
            disabled={!selectedId}
            onClick={() => selectedId && canvas.current?.center(selectedId)}
          >
            <Crosshair size={13} />
          </Button>
        </div>
      </div>

      <div className="relative h-[420px] w-full bg-[var(--color-base)]">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[var(--color-base)]/80">
            <div className="w-56">
              <LoadingBlock rows={3} label="Loading the scenario graph" />
            </div>
          </div>
        )}
        {graph && (
          <GraphCanvas
            ref={canvas}
            nodes={graph.nodes}
            edges={graph.edges}
            impact={impact}
            selectedId={selectedId}
            onSelectNode={onSelect}
            className="h-full w-full"
            ariaLabel={
              `Scenario graph with ${graph.nodes.length} nodes; ${affected} of them are affected by ` +
              "this change. The shockwave table below this canvas is the keyboard-navigable equivalent."
            }
          />
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-[var(--color-line)] px-4 py-2.5">
        {LEGEND.map((status) => {
          const meta = STATUS_META[status];
          const Icon = meta.icon;
          return (
            <span key={status} className="flex items-center gap-1.5 text-[11.5px] text-[var(--color-muted)]">
              <span
                aria-hidden
                className="inline-block h-2.5 w-2.5 rounded-full border-2"
                style={{ borderColor: STATUS_COLOUR[status], borderStyle: status === "potentially_affected" ? "dashed" : "solid" }}
              />
              <Icon size={11} aria-hidden style={{ color: STATUS_COLOUR[status] }} />
              {meta.word}
            </span>
          );
        })}
        {graph?.truncated && (
          <span className="ml-auto text-[11.5px] text-[var(--color-degraded)]">
            {graph.truncation_reason || "The graph was truncated to keep the canvas responsive."}
          </span>
        )}
      </div>
    </Card>
  );
}
