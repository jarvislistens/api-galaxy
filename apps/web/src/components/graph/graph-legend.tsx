"use client";

/**
 * The legend, always within reach.
 *
 * A graph whose key lives in a help page is a graph nobody reads correctly. This panel
 * is pinned to the canvas and collapsible rather than hidden, and it draws the *actual*
 * strokes and shapes the canvas uses — not coloured squares standing in for them — so
 * the mapping can be checked by eye.
 */

import { ChevronDown } from "lucide-react";
import * as React from "react";
import {
  LEGEND_EDGES,
  LEGEND_STATES,
  NODE_COLOUR,
  NODE_SHAPE,
  STATUS_COLOUR,
} from "@/components/graph/graph-style";
import { cx } from "@/components/ui/primitives";

/** The node types worth explaining. The rest follow the same shape language. */
const LEGEND_TYPES: { type: string; label: string }[] = [
  { type: "Domain", label: "Domain" },
  { type: "Capability", label: "Capability" },
  { type: "Service", label: "Service" },
  { type: "Journey", label: "Journey" },
  { type: "BusinessEntity", label: "Business entity" },
  { type: "APIOperation", label: "Operation" },
  { type: "Schema", label: "Schema" },
  { type: "Field", label: "Field" },
  { type: "SecurityScheme", label: "Security scheme" },
  { type: "Risk", label: "Finding" },
];

const DASH: Record<"solid" | "dashed" | "dotted", string | undefined> = {
  solid: undefined,
  dashed: "5 3",
  dotted: "1.5 3",
};

const EDGE_COLOUR: Record<"fact" | "inferred" | "user", string> = {
  fact: "var(--color-fact)",
  inferred: "var(--color-inferred)",
  user: "var(--color-user)",
};

const STATE_DASH: Record<string, string | undefined> = {
  broken: undefined,
  degraded: "4 2",
  potentially_affected: "1.5 2.5",
};

export function GraphLegend({ className }: { className?: string }) {
  const [open, setOpen] = React.useState(true);
  const panelId = React.useId();

  return (
    <div
      className={cx(
        "panel-raised w-[254px] overflow-hidden backdrop-blur-[2px]",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left transition-colors duration-150 hover:bg-[var(--color-surface-2)]"
      >
        <span className="label-eyebrow">Legend</span>
        <ChevronDown
          size={14}
          aria-hidden
          className={cx(
            "text-[var(--color-dim)] transition-transform duration-200",
            open ? "rotate-180" : "",
          )}
        />
      </button>

      <div
        id={panelId}
        hidden={!open}
        className="max-h-[46vh] overflow-y-auto border-t border-[var(--color-line)] px-3 py-2.5"
      >
        <Group title="Relationships">
          <ul className="space-y-1.5">
            {LEGEND_EDGES.map((entry) => (
              <li key={entry.stroke} className="flex items-center gap-2.5">
                <svg width="34" height="10" viewBox="0 0 34 10" className="shrink-0" aria-hidden>
                  <line
                    x1="1"
                    y1="5"
                    x2="26"
                    y2="5"
                    stroke={EDGE_COLOUR[entry.tone]}
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeDasharray={DASH[entry.stroke]}
                  />
                  <path d="M26 2 L33 5 L26 8 Z" fill={EDGE_COLOUR[entry.tone]} />
                </svg>
                <span className="min-w-0 text-[11.5px] leading-tight text-[var(--color-ink-2)]">
                  {entry.label}
                  <span className="block text-[10.5px] text-[var(--color-dim)]">
                    {entry.stroke}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </Group>

        <Group title="Impact states">
          <ul className="space-y-1.5">
            {LEGEND_STATES.map((entry) => (
              <li key={entry.key} className="flex items-start gap-2.5">
                <svg width="34" height="14" viewBox="0 0 34 14" className="shrink-0" aria-hidden>
                  <rect
                    x="1.5"
                    y="1.5"
                    width="31"
                    height="11"
                    rx="3"
                    fill="none"
                    stroke={STATUS_COLOUR[entry.key] ?? "var(--color-dim)"}
                    strokeWidth="1.8"
                    strokeDasharray={STATE_DASH[entry.key]}
                  />
                </svg>
                <span className="min-w-0 text-[11.5px] leading-tight text-[var(--color-ink-2)]">
                  {entry.label}
                  <span className="block text-[10.5px] leading-tight text-[var(--color-dim)]">
                    {entry.detail}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </Group>

        <Group title="Node types">
          <ul className="grid grid-cols-2 gap-x-2 gap-y-1">
            {LEGEND_TYPES.map((entry) => (
              <li key={entry.type} className="flex items-center gap-1.5">
                <ShapeSwatch type={entry.type} />
                <span className="truncate text-[11px] text-[var(--color-ink-2)]">
                  {entry.label}
                </span>
              </li>
            ))}
          </ul>
        </Group>

        <p className="mt-2.5 border-t border-[var(--color-line)] pt-2 text-[10.5px] leading-snug text-[var(--color-dim)]">
          Meaning is never carried by colour alone. Shape says what a node is, stroke
          pattern says where it came from.
        </p>
      </div>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-2.5 last:mb-0">
      <h3 className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--color-dim)]">
        {title}
      </h3>
      {children}
    </section>
  );
}

/**
 * The cytoscape shape names, redrawn in SVG at 16px. Kept in one place so a shape added
 * to `graph-style.ts` only has to be drawn once.
 */
function ShapeSwatch({ type }: { type: string }) {
  const colour = NODE_COLOUR[type] ?? "#8b94a4";
  const shape = NODE_SHAPE[type] ?? "ellipse";
  return (
    <svg width="16" height="16" viewBox="0 0 18 18" className="shrink-0" aria-hidden>
      {renderShape(shape, colour)}
    </svg>
  );
}

function renderShape(shape: string, colour: string) {
  const fill = { fill: colour, fillOpacity: 0.88, stroke: colour, strokeWidth: 1 };
  switch (shape) {
    case "round-rectangle":
      return <rect x="2" y="4.5" width="14" height="9" rx="2.5" {...fill} />;
    case "rectangle":
      return <rect x="2" y="4.5" width="14" height="9" {...fill} />;
    case "barrel":
      return <rect x="2.5" y="4.5" width="13" height="9" rx="4.5" {...fill} />;
    case "hexagon":
      return <polygon points="9,2 15.1,5.5 15.1,12.5 9,16 2.9,12.5 2.9,5.5" {...fill} />;
    case "round-hexagon":
      return (
        <polygon
          points="9,2 15.1,5.5 15.1,12.5 9,16 2.9,12.5 2.9,5.5"
          strokeLinejoin="round"
          {...fill}
          strokeWidth={2.4}
        />
      );
    case "tag":
      return <polygon points="2,3.5 12.5,3.5 16,9 12.5,14.5 2,14.5" {...fill} />;
    case "round-tag":
      return (
        <polygon
          points="2.5,4 12.5,4 15.5,9 12.5,14 2.5,14"
          strokeLinejoin="round"
          {...fill}
          strokeWidth={2.2}
        />
      );
    case "diamond":
      return <polygon points="9,1.8 16.2,9 9,16.2 1.8,9" {...fill} />;
    case "round-diamond":
      return (
        <polygon points="9,2.4 15.6,9 9,15.6 2.4,9" strokeLinejoin="round" {...fill} strokeWidth={2.4} />
      );
    case "rhomboid":
      return <polygon points="4.5,4 17,4 13.5,14 1,14" {...fill} />;
    case "vee":
      return <polygon points="2,3 9,13.5 16,3 9,8" {...fill} />;
    case "octagon":
      return <polygon points="6,2 12,2 16,6 16,12 12,16 6,16 2,12 2,6" {...fill} />;
    case "triangle":
      return <polygon points="9,2 16.5,15 1.5,15" {...fill} />;
    case "star":
      return (
        <polygon
          points="9,1.5 11.1,6.7 16.7,7.1 12.4,10.7 13.8,16.1 9,13.1 4.2,16.1 5.6,10.7 1.3,7.1 6.9,6.7"
          {...fill}
        />
      );
    case "ellipse":
    default:
      return <circle cx="9" cy="9" r="6.2" {...fill} />;
  }
}
