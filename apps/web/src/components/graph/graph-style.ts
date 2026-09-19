/**
 * The single visual contract for the graph.
 *
 * Shape and stroke pattern carry the meaning; colour reinforces it. Nothing here encodes
 * information by hue alone, because roughly one in twelve men cannot read that, and
 * because a printed report loses colour anyway.
 *
 *   solid edge  → stated by the specification
 *   dashed edge → inferred by a rule or a model
 *   dotted edge → created or accepted by a person
 */

// `StylesheetStyle` is the `{ selector, style }` form; `StylesheetCSS` is the `{ selector,
// css }` form. Both exist, and picking the wrong one makes every rule below a type error.
import type { StylesheetStyle } from "cytoscape";

export const NODE_COLOUR: Record<string, string> = {
  Estate: "#c3cad6",
  Domain: "#7c8cf8",
  Capability: "#bb8cf5",
  Service: "#55c8ea",
  Journey: "#45cf9b",
  BusinessEntity: "#bb8cf5",
  JourneyStep: "#38b98a",
  APIOperation: "#8fa7c4",
  Endpoint: "#6f7b8f",
  Schema: "#d7b36a",
  Field: "#8b94a4",
  SecurityScheme: "#e0a83c",
  Server: "#626b7b",
  Risk: "#f2585f",
  Scenario: "#e0a83c",
  Change: "#e0a83c",
  Repair: "#45cf9b",
};

/** Cytoscape shape per node type — the primary, colour-independent signal. */
export const NODE_SHAPE: Record<string, string> = {
  Estate: "round-rectangle",
  Domain: "hexagon",
  Capability: "round-hexagon",
  Service: "round-rectangle",
  Journey: "round-tag",
  BusinessEntity: "round-diamond",
  JourneyStep: "tag",
  APIOperation: "rectangle",
  Endpoint: "round-rectangle",
  Schema: "rhomboid",
  Field: "ellipse",
  SecurityScheme: "vee",
  Server: "barrel",
  Risk: "diamond",
  Scenario: "octagon",
  Change: "triangle",
  Repair: "star",
};

export const NODE_SIZE: Record<string, number> = {
  Estate: 64,
  Domain: 56,
  Capability: 44,
  Service: 48,
  Journey: 42,
  BusinessEntity: 38,
  JourneyStep: 28,
  APIOperation: 30,
  Endpoint: 25,
  Schema: 33,
  Field: 18,
  SecurityScheme: 25,
  Server: 22,
  Risk: 30,
  Scenario: 36,
  Change: 28,
  Repair: 28,
};

/**
 * A lighter version of each node colour, used for the rim and the halo.
 *
 * Cytoscape has no drop-shadow, so depth comes from a rim-light border plus a wide,
 * very transparent `outline` in the node's own hue. That is what stops the canvas
 * reading as flat stickers on black.
 */
function lighten(hex: string, amount: number): string {
  const value = hex.replace("#", "");
  const to = (i: number) => {
    const channel = parseInt(value.slice(i, i + 2), 16);
    return Math.round(channel + (255 - channel) * amount);
  };
  return `rgb(${to(0)}, ${to(2)}, ${to(4)})`;
}

export function nodeColour(type: string): string {
  return NODE_COLOUR[type] ?? "#8b94a4";
}

export function nodeRim(type: string): string {
  return lighten(nodeColour(type), 0.42);
}

export const STATUS_COLOUR: Record<string, string> = {
  broken: "#f2585f",
  degraded: "#e0a83c",
  potentially_affected: "#7f8798",
  unaffected: "transparent",
};

export function buildStylesheet(): StylesheetStyle[] {
  return [
    {
      selector: "node",
      style: {
        "background-color": (element: any) => nodeColour(element.data("type")),
        "background-opacity": 1,
        shape: (element: any) => (NODE_SHAPE[element.data("type")] ?? "ellipse") as any,
        width: (element: any) => NODE_SIZE[element.data("type")] ?? 20,
        height: (element: any) => NODE_SIZE[element.data("type")] ?? 20,
        label: "data(label)",
        color: "#e6eaf2",
        "font-size": (element: any) =>
          ["Estate", "Domain"].includes(element.data("type"))
            ? 13
            : ["Service", "Journey", "Capability", "BusinessEntity"].includes(element.data("type"))
              ? 12
              : 10.5,
        "font-family": "ui-sans-serif, -apple-system, system-ui, sans-serif",
        "font-weight": 500,
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 7,
        "text-wrap": "ellipsis",
        "text-max-width": "148px",
        // A dark outline on the glyphs themselves keeps labels legible where they cross
        // an edge, which a background box alone does not do once boxes start overlapping.
        "text-outline-color": "#0a0c10",
        "text-outline-width": 2.5,
        "text-outline-opacity": 0.9,
        "text-background-opacity": 0,
        // Rim light + wide transparent halo in the node's own hue. This is the whole
        // difference between "flat sticker" and "luminous body".
        "border-width": 1.5,
        "border-color": (element: any) => nodeRim(element.data("type")),
        "border-opacity": 0.85,
        "outline-width": 7,
        "outline-color": (element: any) => nodeColour(element.data("type")),
        "outline-opacity": 0.13,
        "outline-offset": 1,
        "overlay-opacity": 0,
        "transition-property":
          "background-color, border-color, border-width, outline-width, outline-opacity, opacity, width, height",
        "transition-duration": 220,
        "transition-timing-function": "ease-out-cubic",
      } as any,
    },
    {
      // Pointer affordance and a brighter halo while the cursor is over a node. Cytoscape
      // has no :hover selector, so the canvas toggles this class on mouseover/mouseout.
      selector: "node.hovered",
      style: {
        "outline-width": 13,
        "outline-opacity": 0.3,
        "border-width": 2.2,
        "z-index": 15,
      } as any,
    },
    {
      // Inferred nodes get a dashed outline, matching the edge language exactly.
      selector: 'node[provenance = "inferred"]',
      style: {
        "border-width": 1.6,
        "border-color": "#e0a83c",
        "border-style": "dashed",
        "background-opacity": 0.55,
      } as any,
    },
    {
      selector: 'node[provenance = "user"]',
      style: {
        "border-width": 1.6,
        "border-color": "#7c8cf8",
        "border-style": "dotted",
      } as any,
    },
    {
      selector: "node.dimmed",
      style: { opacity: 0.12, "text-opacity": 0, "outline-opacity": 0 } as any,
    },
    {
      selector: "node.highlighted",
      style: {
        "border-width": 2.6,
        "border-color": "#a7b3ff",
        "border-style": "solid",
        "border-opacity": 1,
        "outline-width": 14,
        "outline-color": "#7c8cf8",
        "outline-opacity": 0.34,
        "z-index": 20,
      } as any,
    },
    {
      selector: "node.active-step",
      style: {
        "border-width": 3,
        "border-color": "#7cf0c0",
        "border-opacity": 1,
        "outline-width": 20,
        "outline-color": "#45cf9b",
        "outline-opacity": 0.42,
        "z-index": 30,
      } as any,
    },
    {
      selector: "node:selected",
      style: {
        "border-width": 3,
        "border-color": "#f4f6fa",
        "border-opacity": 1,
        "outline-width": 16,
        "outline-color": "#f4f6fa",
        "outline-opacity": 0.26,
        "z-index": 40,
      } as any,
    },
    {
      selector: 'node[impact = "broken"]',
      style: { "border-width": 2.6, "border-color": "#f2585f", "border-style": "solid" } as any,
    },
    {
      selector: 'node[impact = "degraded"]',
      style: { "border-width": 2.2, "border-color": "#e0a83c", "border-style": "solid" } as any,
    },
    {
      selector: 'node[impact = "potentially_affected"]',
      style: { "border-width": 1.6, "border-color": "#7f8798", "border-style": "dashed" } as any,
    },

    {
      selector: "edge",
      style: {
        width: 1.4,
        "line-color": "#4b5567",
        "target-arrow-color": "#5a6479",
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.9,
        "curve-style": "bezier",
        // Multiple relationships between the same pair fan out instead of stacking into
        // one line that silently hides all but the last.
        "control-point-step-size": 44,
        opacity: 0.75,
        "line-cap": "round",
        "transition-property": "line-color, opacity, width, target-arrow-color",
        "transition-duration": 220,
        "transition-timing-function": "ease-out-cubic",
      } as any,
    },
    {
      selector: 'edge[stroke = "dashed"]',
      style: {
        "line-style": "dashed",
        "line-dash-pattern": [7, 5],
        "line-color": "#b08f3e",
        "target-arrow-color": "#b08f3e",
        opacity: 0.68,
      } as any,
    },
    {
      selector: 'edge[stroke = "dotted"]',
      style: {
        "line-style": "dotted",
        "line-color": "#8b93e8",
        "target-arrow-color": "#8b93e8",
        opacity: 0.8,
      } as any,
    },
    {
      selector: "edge.dimmed",
      style: { opacity: 0.06 } as any,
    },
    {
      selector: "edge.highlighted",
      style: {
        width: 2.6,
        "line-color": "#8e9dff",
        "target-arrow-color": "#8e9dff",
        opacity: 1,
        "z-index": 20,
      } as any,
    },
    {
      selector: "edge.path",
      style: {
        width: 3.2,
        "line-color": "#57e0ab",
        "target-arrow-color": "#57e0ab",
        "line-style": "solid",
        opacity: 1,
        "z-index": 25,
      } as any,
    },
    {
      selector: "edge.breaks",
      style: {
        width: 2.4,
        "line-color": "#f2585f",
        "target-arrow-color": "#f2585f",
        "line-style": "solid",
        opacity: 1,
      } as any,
    },
  ];
}

export const LEGEND_EDGES = [
  { stroke: "solid" as const, label: "Stated by the specification", tone: "fact" as const },
  { stroke: "dashed" as const, label: "Inferred — not stated anywhere", tone: "inferred" as const },
  { stroke: "dotted" as const, label: "Created or accepted by you", tone: "user" as const },
];

export const LEGEND_STATES = [
  { key: "broken", label: "Broken", detail: "Cannot work without a code change" },
  { key: "degraded", label: "Degraded", detail: "Still type-checks, meaning moved" },
  { key: "potentially_affected", label: "Possibly affected", detail: "Weaker evidence" },
];

/** Which provenance bucket a node or edge belongs to, for styling. */
export function provenanceBucket(sourceKind: string, acceptance: string): "fact" | "inferred" | "user" {
  if (sourceKind === "user_edit" || acceptance === "accepted") return "user";
  if (sourceKind === "specification") return "fact";
  if (sourceKind === "deterministic_rule" && acceptance === "observed") return "fact";
  return "inferred";
}
