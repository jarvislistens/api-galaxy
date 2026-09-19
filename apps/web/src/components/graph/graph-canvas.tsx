"use client";

/**
 * The interactive graph canvas.
 *
 * Cytoscape was chosen over React Flow because it gives us layouts (`fcose`, concentric,
 * breadthfirst) out of the box, runs headless so the exported HTML report can use the
 * same engine, and has native SVG/PNG export. See `docs/architecture/adr-001`.
 *
 * Three behaviours matter more than they look:
 *
 * 1. **The layout settles and then stops.** Physics that keeps nudging nodes after the
 *    user has oriented themselves is actively hostile, so the layout runs once per data
 *    change and then the simulation is done.
 * 2. **Highlighting never re-runs the layout.** Selecting a node, playing a journey or
 *    showing an impact shockwave only adds and removes classes, so positions are stable
 *    and the eye can track what moved — nothing.
 * 3. **The layout does not animate and does not fit; we do both, after it settles.**
 *    An animating layout fits the viewport from wherever the nodes happen to be
 *    mid-flight, which left the estate zoomed out in a corner. Instead the layout snaps
 *    to its final positions behind a hidden canvas, we fit once, and then fade in. The
 *    reveal is smoother than the physics ever was, and it is correct every time.
 */

import cytoscape, {
  type Core,
  type ElementDefinition,
  type EventObject,
  type NodeSingular,
} from "cytoscape";
import fcose from "cytoscape-fcose";
import * as React from "react";
import { buildStylesheet, provenanceBucket } from "@/components/graph/graph-style";
import type { GraphEdge, GraphNode } from "@/lib/types";

let registered = false;
function ensureExtensions() {
  if (registered) return;
  cytoscape.use(fcose as any);
  registered = true;
}

export type LayoutName = "force" | "hierarchy" | "circle" | "grid";

export interface GraphCanvasHandle {
  fit: () => void;
  center: (nodeId?: string) => void;
  zoomBy: (factor: number) => void;
  reset: () => void;
  exportPng: (scale?: number) => string | null;
  focus: (nodeId: string, depth?: number) => void;
  clearFocus: () => void;
  core: () => Core | null;
}

export interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId?: string | null;
  highlightNodes?: string[];
  highlightEdges?: string[];
  pathNodes?: string[];
  activeNodes?: string[];
  impact?: Record<string, string>;
  layout?: LayoutName;
  onSelectNode?: (nodeId: string | null) => void;
  onSelectEdge?: (edgeId: string) => void;
  onExpand?: (nodeId: string) => void;
  className?: string;
  ariaLabel?: string;
}

// Fit padding scales with the canvas. A fixed 56px is right for the full-width Galaxy
// but swallows most of the ~340px preview embedded in the journey player, which left
// that graph a tiny unreadable clump ringed by empty space.
const MAX_FIT_PADDING = 56;
const MIN_FIT_PADDING = 14;

function fitPadding(core: Core): number {
  const smallest = Math.min(core.width() || 0, core.height() || 0);
  if (!smallest) return MAX_FIT_PADDING;
  return Math.max(MIN_FIT_PADDING, Math.min(MAX_FIT_PADDING, Math.round(smallest * 0.075)));
}

const LAYOUTS: Record<LayoutName, any> = {
  force: {
    name: "fcose",
    quality: "default",
    animate: false,
    // `randomize: true` is load-bearing, not a default left alone.
    //
    // With it false, fcose seeds from existing positions — and since every element is
    // added fresh they all start at the same point, so a *connected* graph has no
    // asymmetry to resolve and the whole estate collapses into a diagonal line. That was
    // survivable only while journeys were disconnected islands and `packComponents` laid
    // them out separately, which masked it. Exports do not depend on this: `diagrams.py`
    // has its own deterministic layered layout.
    randomize: true,
    // Labels sit below their node and can be 110px wide, so separation has to be
    // generous or the text overlaps and the graph becomes unreadable.
    nodeSeparation: 160,
    idealEdgeLength: 150,
    nodeRepulsion: 12000,
    gravity: 0.22,
    packComponents: true,
    // Deterministic: the same graph laid out twice must look the same.
    fit: false,
    padding: MAX_FIT_PADDING,
  },
  hierarchy: {
    name: "breadthfirst",
    directed: true,
    animate: false,
    spacingFactor: 1.5,
    padding: MAX_FIT_PADDING,
    fit: false,
  },
  circle: { name: "concentric", animate: false, padding: MAX_FIT_PADDING, fit: false, minNodeSpacing: 46,
            concentric: (n: NodeSingular) => n.degree(false), levelWidth: () => 2 },
  grid: { name: "grid", animate: false, padding: MAX_FIT_PADDING, fit: false, avoidOverlapPadding: 26 },
};

function toElements(nodes: GraphNode[], edges: GraphEdge[], impact?: Record<string, string>) {
  const ids = new Set(nodes.map((n) => n.id));
  const nodeElements: ElementDefinition[] = nodes.map((node) => ({
    group: "nodes",
    data: {
      id: node.id,
      label: node.label,
      type: node.type,
      service: node.attrs?.service ?? "",
      provenance: provenanceBucket(node.provenance.source_kind, node.acceptance),
      impact: impact?.[node.id] ?? "",
      deprecated: node.attrs?.deprecated ? "1" : "",
    },
  }));
  const edgeElements: ElementDefinition[] = edges
    .filter((edge) => ids.has(edge.source) && ids.has(edge.target))
    .map((edge) => ({
      group: "edges",
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: edge.type,
        label: edge.label,
        stroke: edge.stroke ?? "solid",
      },
    }));
  return [...nodeElements, ...edgeElements];
}

export const GraphCanvas = React.forwardRef<GraphCanvasHandle, GraphCanvasProps>(
  function GraphCanvas(
    {
      nodes,
      edges,
      selectedId,
      highlightNodes,
      highlightEdges,
      pathNodes,
      activeNodes,
      impact,
      layout = "force",
      onSelectNode,
      onSelectEdge,
      onExpand,
      className,
      ariaLabel,
    },
    ref,
  ) {
    const containerRef = React.useRef<HTMLDivElement | null>(null);
    const coreRef = React.useRef<Core | null>(null);
    const [ready, setReady] = React.useState(false);
    // True once the user has panned or zoomed by hand. Resizing the window then leaves
    // their view alone instead of snapping it back to a fit.
    const userAdjustedRef = React.useRef(false);

    // --- create once ---------------------------------------------------------
    React.useEffect(() => {
      ensureExtensions();
      const container = containerRef.current;
      if (!container) return;

      const core = cytoscape({
        container,
        style: buildStylesheet(),
        minZoom: 0.08,
        maxZoom: 3.5,
        wheelSensitivity: 0.22,
        boxSelectionEnabled: false,
        pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
      });
      coreRef.current = core;
      setReady(true);

      return () => {
        core.destroy();
        coreRef.current = null;
      };
    }, []);

    // --- data ----------------------------------------------------------------
    React.useEffect(() => {
      const core = coreRef.current;
      if (!core || !ready) return;
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      core.batch(() => {
        core.elements().remove();
        core.add(toElements(nodes, edges, impact));
      });

      if (core.nodes().length === 0) return;
      // New data or a new layout means a new view; whatever zoom the user had chosen no
      // longer refers to anything.
      userAdjustedRef.current = false;
      const container = core.container();
      // Hide the canvas while it settles so the fit never reads as a jump.
      if (container && !reduceMotion) container.style.opacity = "0";

      const run = core.layout({ ...LAYOUTS[layout] });
      run.one("layoutstop", () => {
        // Re-measure, then fit exactly once. The layouts deliberately do neither: an
        // animated layout fit computes its zoom from mid-flight positions, which is what
        // parked the whole estate in the top-left corner.
        core.resize();
        core.fit(undefined, fitPadding(core));
        if (container) {
          container.style.transition = reduceMotion ? "" : "opacity 420ms ease-out";
          container.style.opacity = "1";
        }
      });
      run.run();
      // Deliberately not re-run after this: see the module docstring.
    }, [nodes, edges, impact, layout, ready]);

    // --- keep the viewport in step with the container -------------------------
    React.useEffect(() => {
      const container = containerRef.current;
      const core = coreRef.current;
      if (!container || !core || !ready) return;
      if (typeof ResizeObserver === "undefined") return;

      // Opening the inspector, collapsing the filter rail and resizing the window all
      // change the canvas box without remounting it. Without this the renderer keeps the
      // stale size and the graph drifts out of view.
      let frame = 0;
      let previous = { width: 0, height: 0 };
      const observer = new ResizeObserver((entries) => {
        const box = entries[0]?.contentRect;
        if (!box || box.width < 1 || box.height < 1) return;
        // Sub-pixel reflow churn would otherwise re-fit on every frame.
        if (Math.abs(box.width - previous.width) < 2 && Math.abs(box.height - previous.height) < 2) {
          return;
        }
        previous = { width: box.width, height: box.height };
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => {
          core.resize();
          // Re-fit unless the user has chosen their own zoom or pan. Never re-fitting
          // leaves the graph hanging off the edge when the window shrinks; always
          // re-fitting throws away the view they deliberately set up. Tracking the
          // gesture is what lets us do the right thing in both cases.
          if (!userAdjustedRef.current) core.fit(undefined, fitPadding(core));
        });
      });
      observer.observe(container);
      return () => {
        cancelAnimationFrame(frame);
        observer.disconnect();
      };
    }, [ready]);

    // --- selection and highlight (class changes only, never a relayout) ------
    React.useEffect(() => {
      const core = coreRef.current;
      if (!core || !ready) return;

      core.batch(() => {
        core.elements().removeClass("highlighted dimmed path active-step");

        const highlighted = new Set([...(highlightNodes ?? []), ...(pathNodes ?? [])]);
        const active = new Set(activeNodes ?? []);

        if (highlighted.size || active.size) {
          core.elements().addClass("dimmed");
          for (const id of highlighted) {
            const element = core.getElementById(id);
            if (element.nonempty()) element.removeClass("dimmed").addClass("highlighted");
          }
          for (const id of active) {
            const element = core.getElementById(id);
            if (element.nonempty()) element.removeClass("dimmed").addClass("active-step");
          }
          for (const id of highlightEdges ?? []) {
            const element = core.getElementById(id);
            if (element.nonempty()) element.removeClass("dimmed").addClass("highlighted");
          }
          // Edges that run between two highlighted nodes light up too, so the path reads
          // as a path rather than a scatter of dots.
          core.edges().forEach((edge) => {
            if (highlighted.has(edge.source().id()) && highlighted.has(edge.target().id())) {
              edge.removeClass("dimmed").addClass("highlighted");
            }
          });
          const ordered = pathNodes ?? [];
          for (let i = 0; i < ordered.length - 1; i += 1) {
            const between = core
              .edges()
              .filter(
                (edge) =>
                  (edge.source().id() === ordered[i] && edge.target().id() === ordered[i + 1]) ||
                  (edge.target().id() === ordered[i] && edge.source().id() === ordered[i + 1]),
              );
            between.removeClass("dimmed highlighted").addClass("path");
          }
        }

        core.nodes().unselect();
        if (selectedId) {
          const node = core.getElementById(selectedId);
          if (node.nonempty()) node.select();
        }
      });
    }, [selectedId, highlightNodes, highlightEdges, pathNodes, activeNodes, ready]);

    // --- events --------------------------------------------------------------
    React.useEffect(() => {
      const core = coreRef.current;
      if (!core || !ready) return;

      const onTapNode = (event: EventObject) => onSelectNode?.(event.target.id());
      const onTapEdge = (event: EventObject) => onSelectEdge?.(event.target.id());
      const onTapBackground = (event: EventObject) => {
        if (event.target === core) onSelectNode?.(null);
      };
      const onDoubleTap = (event: EventObject) => onExpand?.(event.target.id());

      // Cytoscape has no :hover selector and draws to a canvas, so the pointer cursor and
      // the hover halo both have to be driven by hand.
      const container = core.container();
      const onEnter = (event: EventObject) => {
        event.target.addClass("hovered");
        if (container) container.style.cursor = "pointer";
      };
      const onLeave = (event: EventObject) => {
        event.target.removeClass("hovered");
        if (container) container.style.cursor = "";
      };

      core.on("tap", "node", onTapNode);
      core.on("tap", "edge", onTapEdge);
      core.on("tap", onTapBackground);
      core.on("dbltap", "node", onDoubleTap);
      core.on("mouseover", "node", onEnter);
      core.on("mouseout", "node", onLeave);

      // Native listeners rather than Cytoscape's `zoom`/`pan` events, because those also
      // fire for our own programmatic fits — which would immediately mark the view as
      // user-adjusted and defeat the whole point.
      const markAdjusted = () => {
        userAdjustedRef.current = true;
      };
      container?.addEventListener("wheel", markAdjusted, { passive: true });
      container?.addEventListener("mousedown", markAdjusted);
      container?.addEventListener("touchstart", markAdjusted, { passive: true });

      return () => {
        container?.removeEventListener("wheel", markAdjusted);
        container?.removeEventListener("mousedown", markAdjusted);
        container?.removeEventListener("touchstart", markAdjusted);
        core.off("tap", "node", onTapNode);
        core.off("tap", "edge", onTapEdge);
        core.off("tap", onTapBackground);
        core.off("dbltap", "node", onDoubleTap);
        core.off("mouseover", "node", onEnter);
        core.off("mouseout", "node", onLeave);
        if (container) container.style.cursor = "";
      };
    }, [onSelectNode, onSelectEdge, onExpand, ready]);

    // --- imperative handle ---------------------------------------------------
    React.useImperativeHandle(
      ref,
      () => ({
        core: () => coreRef.current,
        fit: () => {
          const core = coreRef.current;
          if (!core) return;
          userAdjustedRef.current = false;
          core.animate(
            { fit: { eles: core.elements(), padding: fitPadding(core) } },
            { duration: 300 },
          );
        },
        center: (nodeId?: string) => {
          const core = coreRef.current;
          if (!core) return;
          const target = nodeId ? core.getElementById(nodeId) : core.elements();
          if (target.nonempty()) core.animate({ center: { eles: target }, zoom: nodeId ? 1.25 : undefined }, { duration: 300 });
        },
        zoomBy: (factor: number) => {
          const core = coreRef.current;
          if (!core) return;
          core.zoom({ level: core.zoom() * factor, renderedPosition: { x: (core.width() ?? 0) / 2, y: (core.height() ?? 0) / 2 } });
        },
        reset: () => {
          const core = coreRef.current;
          if (!core) return;
          core.elements().removeClass("highlighted dimmed path active-step");
          userAdjustedRef.current = false;
          core.fit(undefined, fitPadding(core));
        },
        exportPng: (scale = 2) => coreRef.current?.png({ full: true, scale, bg: "#0a0c10" }) ?? null,
        focus: (nodeId: string, depth = 1) => {
          const core = coreRef.current;
          if (!core) return;
          const root = core.getElementById(nodeId);
          if (root.empty()) return;
          let neighbourhood = root.closedNeighborhood();
          for (let i = 1; i < depth; i += 1) neighbourhood = neighbourhood.closedNeighborhood();
          core.batch(() => {
            core.elements().addClass("dimmed");
            neighbourhood.removeClass("dimmed").addClass("highlighted");
          });
          core.animate({ fit: { eles: neighbourhood, padding: 60 } }, { duration: 320 });
        },
        clearFocus: () => coreRef.current?.elements().removeClass("dimmed highlighted"),
      }),
      [],
    );

    return (
      <div
        ref={containerRef}
        className={className}
        role="application"
        aria-label={
          ariaLabel ??
          `Interactive API graph with ${nodes.length} nodes and ${edges.length} relationships. ` +
            "Use the node list beside this canvas to navigate with a keyboard."
        }
        data-testid="graph-canvas"
      />
    );
  },
);

/**
 * The keyboard- and screen-reader-accessible equivalent of the canvas.
 *
 * A canvas is opaque to assistive technology, so the same data is always available as a
 * real list: focusable, arrow-navigable, and announcing type and provenance as text.
 */
export function GraphNodeList({
  nodes,
  selectedId,
  onSelect,
  emptyLabel = "No nodes match the current filters.",
}: {
  nodes: GraphNode[];
  selectedId?: string | null;
  onSelect: (nodeId: string) => void;
  emptyLabel?: string;
}) {
  if (!nodes.length) {
    return <p className="px-3 py-4 text-[12.5px] text-[var(--color-dim)]">{emptyLabel}</p>;
  }
  return (
    <ul className="divide-y divide-[var(--color-line)]" role="listbox" aria-label="Graph nodes">
      {nodes.map((node) => {
        const bucket = provenanceBucket(node.provenance.source_kind, node.acceptance);
        return (
          <li key={node.id}>
            <button
              role="option"
              aria-selected={selectedId === node.id}
              onClick={() => onSelect(node.id)}
              className={
                "flex w-full items-start gap-2 px-3 py-2 text-left transition-colors " +
                (selectedId === node.id
                  ? "bg-[var(--color-surface-3)]"
                  : "hover:bg-[var(--color-surface-2)]")
              }
            >
              <span className="mt-[3px] shrink-0 text-[10px] uppercase tracking-wide text-[var(--color-dim)]">
                {node.type.slice(0, 3)}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] text-[var(--color-ink)]">
                  {node.label}
                </span>
                <span className="block truncate text-[11px] text-[var(--color-dim)]">
                  {node.type}
                  {bucket !== "fact" ? ` · ${bucket}` : ""}
                  {node.attrs?.service ? ` · ${node.attrs.service}` : ""}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
