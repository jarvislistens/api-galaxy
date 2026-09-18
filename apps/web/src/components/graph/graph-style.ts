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
  Estate: 46,
  Domain: 40,
  Capability: 32,
  Service: 34,
  Journey: 30,
  BusinessEntity: 28,
  JourneyStep: 20,
  APIOperation: 22,
  Endpoint: 18,
  Schema: 24,
  Field: 13,
  SecurityScheme: 18,
  Server: 16,
  Risk: 22,
  Scenario: 26,
  Change: 20,
  Repair: 20,
};

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
        "background-color": (element: any) => NODE_COLOUR[element.data("type")] ?? "#8b94a4",
        "background-opacity": 0.88,
        shape: (element: any) => (NODE_SHAPE[element.data("type")] ?? "ellipse") as any,
        width: (element: any) => NODE_SIZE[element.data("type")] ?? 16,
        height: (element: any) => NODE_SIZE[element.data("type")] ?? 16,
        label: "data(label)",
        color: "#c3cad6",
        "font-size": (element: any) =>
          ["Domain", "Estate", "Service"].includes(element.data("type")) ? 11 : 9,
        "font-family": "ui-sans-serif, -apple-system, system-ui, sans-serif",
        "font-weight": 500,
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 4,
        "text-wrap": "ellipsis",
        "text-max-width": "110px",
        "text-background-color": "#0a0c10",
        "text-background-opacity": 0.72,
        "text-background-padding": "2px",
        "text-background-shape": "roundrectangle",
        "border-width": 1,
        "border-color": "#0a0c10",
        "overlay-opacity": 0,
        "transition-property": "background-color, border-color, border-width, opacity",
        "transition-duration": 180,
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
      style: { opacity: 0.16, "text-opacity": 0 } as any,
    },
    {
      selector: "node.highlighted",
      style: {
        "border-width": 2.4,
        "border-color": "#7c8cf8",
        "border-style": "solid",
        "background-opacity": 1,
        "z-index": 20,
        "font-size": 11,
      } as any,
    },
    {
      selector: "node.active-step",
      style: {
        "border-width": 3,
        "border-color": "#45cf9b",
        "background-opacity": 1,
        "z-index": 30,
      } as any,
    },
    {
      selector: "node:selected",
      style: {
        "border-width": 2.6,
        "border-color": "#f4f6fa",
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
        width: 1,
        "line-color": "#39414f",
        "target-arrow-color": "#39414f",
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.55,
        "curve-style": "bezier",
        opacity: 0.55,
        "transition-property": "line-color, opacity, width",
        "transition-duration": 180,
      } as any,
    },
    {
      selector: 'edge[stroke = "dashed"]',
      style: { "line-style": "dashed", "line-color": "#8a7333", "target-arrow-color": "#8a7333" } as any,
    },
    {
      selector: 'edge[stroke = "dotted"]',
      style: { "line-style": "dotted", "line-color": "#5b64ad", "target-arrow-color": "#5b64ad" } as any,
    },
    {
      selector: "edge.dimmed",
      style: { opacity: 0.05 } as any,
    },
    {
      selector: "edge.highlighted",
      style: {
        width: 2.2,
        "line-color": "#7c8cf8",
        "target-arrow-color": "#7c8cf8",
        opacity: 1,
        "z-index": 20,
      } as any,
    },
    {
      selector: "edge.path",
      style: {
        width: 2.6,
        "line-color": "#45cf9b",
        "target-arrow-color": "#45cf9b",
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
