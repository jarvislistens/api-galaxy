"""Diagrams for every export: a deterministic layout, hand-written SVG, PNG and Mermaid.

There is no browser here on purpose. A headless Chrome is hundreds of megabytes, needs a
network install and produces a different picture on every machine; this module is a few
hundred lines of arithmetic that produces byte-identical output for the same graph. That
matters because a report is meant to be regenerated and diffed.

The layout is a cut-down Sugiyama: nodes are assigned to layers by what *kind* of thing
they are (a domain is always left of a service, which is always left of an operation),
ordering inside each layer is improved by repeated barycentre sweeps to reduce edge
crossings, and coordinates fall out of the final ordering. Type-based layering rather
than longest-path layering is deliberate — an architecture diagram is more legible when
the rows mean something than when they are merely topologically minimal.

The fact-vs-inference boundary is carried in ``stroke-dasharray``, not in colour alone,
so the picture survives being printed in greyscale.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

from api_galaxy.contracts.analysis import Journey
from api_galaxy.contracts.graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    SourceKind,
)
from api_galaxy.exports.bundle import LEGEND, ReportBundle, legend_for
from api_galaxy.exports.support import ExportUnavailable, probe_cairosvg, truncate

# --------------------------------------------------------------------------------------
# Geometry and theme
# --------------------------------------------------------------------------------------

NODE_WIDTH = 188
NODE_HEIGHT = 46
LAYER_GAP = 96
ROW_GAP = 22
MARGIN = 32
HEADER_HEIGHT = 96
LEGEND_HEIGHT = 112
BARYCENTRE_PASSES = 4
DEFAULT_MAX_NODES = 160

LAYER_RANK: dict[NodeType, int] = {
    NodeType.ESTATE: 0,
    NodeType.DOMAIN: 0,
    NodeType.CAPABILITY: 0,
    NodeType.SERVICE: 1,
    NodeType.JOURNEY: 1,
    NodeType.BUSINESS_ENTITY: 1,
    NodeType.SCENARIO: 1,
    NodeType.API_OPERATION: 2,
    NodeType.ENDPOINT: 2,
    NodeType.JOURNEY_STEP: 2,
    NodeType.RISK: 2,
    NodeType.CHANGE: 2,
    NodeType.SCHEMA: 3,
    NodeType.SECURITY_SCHEME: 3,
    NodeType.SERVER: 3,
    NodeType.REPAIR: 3,
    NodeType.FIELD: 4,
    NodeType.EVIDENCE: 4,
}

LAYER_TITLES = (
    "Business areas",
    "Systems & journeys",
    "Operations",
    "Contracts",
    "Fields",
)

# When a diagram has to be trimmed, the least structural things go first. Losing a field
# costs the reader almost nothing; losing a domain destroys the shape of the picture.
_KEEP_PRIORITY: dict[NodeType, int] = {
    NodeType.ESTATE: 0,
    NodeType.DOMAIN: 1,
    NodeType.SERVICE: 2,
    NodeType.JOURNEY: 3,
    NodeType.CAPABILITY: 4,
    NodeType.BUSINESS_ENTITY: 5,
    NodeType.API_OPERATION: 6,
    NodeType.SCHEMA: 7,
    NodeType.RISK: 8,
    NodeType.SCENARIO: 8,
    NodeType.CHANGE: 9,
    NodeType.JOURNEY_STEP: 10,
    NodeType.ENDPOINT: 11,
    NodeType.SECURITY_SCHEME: 12,
    NodeType.REPAIR: 12,
    NodeType.SERVER: 13,
    NodeType.FIELD: 14,
    NodeType.EVIDENCE: 15,
}

THEME = {
    "bg": "#0B0F14",
    "panel": "#121A24",
    "grid": "#1B2734",
    "text": "#E6EDF3",
    "muted": "#8B9AAC",
    "fact": "#5AA2F5",
    "inferred": "#F0B429",
    "user": "#6EE7B7",
    "scenario": "#F472B6",
}

TYPE_COLOURS: dict[NodeType, str] = {
    NodeType.ESTATE: "#94A3B8",
    NodeType.DOMAIN: "#A78BFA",
    NodeType.CAPABILITY: "#C4B5FD",
    NodeType.SERVICE: "#5AA2F5",
    NodeType.JOURNEY: "#FBBF24",
    NodeType.JOURNEY_STEP: "#FCD34D",
    NodeType.BUSINESS_ENTITY: "#67E8F9",
    NodeType.API_OPERATION: "#38BDF8",
    NodeType.ENDPOINT: "#7DD3FC",
    NodeType.SCHEMA: "#34D399",
    NodeType.FIELD: "#94A3B8",
    NodeType.SECURITY_SCHEME: "#FCA5A5",
    NodeType.SERVER: "#A3A3A3",
    NodeType.RISK: "#F472B6",
    NodeType.SCENARIO: "#F472B6",
    NodeType.CHANGE: "#FB7185",
    NodeType.REPAIR: "#6EE7B7",
    NodeType.EVIDENCE: "#64748B",
}

DASH_FOR_STROKE = {"solid": "none", "dashed": "6 4", "dotted": "2 3"}

# Relationships that add noise without adding meaning at diagram scale.
_MUTED_EDGE_TYPES = frozenset({EdgeType.REQUIRES_SECURITY, EdgeType.AFFECTS})


@dataclass(frozen=True)
class DiagramData:
    """A laid-out, already-trimmed picture, ready for any renderer."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    positions: dict[str, tuple[float, float]]
    width: float
    height: float
    omitted: int = 0
    layers: tuple[int, ...] = ()


# --------------------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------------------


def select(
    bundle: ReportBundle,
    *,
    scope: Iterable[str] | None = None,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> tuple[list[GraphNode], list[GraphEdge], int]:
    """Pick which nodes a picture will show. Returns ``(nodes, edges, omitted)``."""
    nodes = list(bundle.graph.nodes)
    if scope is not None:
        wanted = set(scope)
        nodes = [n for n in nodes if n.id in wanted]

    omitted = 0
    if len(nodes) > max_nodes:
        ordered = sorted(
            nodes, key=lambda n: (_KEEP_PRIORITY.get(n.type, 20), n.label.lower(), n.id)
        )
        omitted = len(nodes) - max_nodes
        nodes = ordered[:max_nodes]

    keep = {n.id for n in nodes}
    edges = [
        e
        for e in bundle.graph.edges
        if e.source in keep and e.target in keep and e.type not in _MUTED_EDGE_TYPES
    ]
    nodes.sort(key=lambda n: (layer_of(n), n.label.lower(), n.id))
    return nodes, edges, omitted


def layer_of(node: GraphNode) -> int:
    return LAYER_RANK.get(node.type, 2)


# --------------------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------------------


def layout(
    nodes: Sequence[GraphNode],
    edges: Sequence[GraphEdge],
    *,
    passes: int = BARYCENTRE_PASSES,
) -> dict[str, tuple[float, float]]:
    """Layered layout. Same graph in, same coordinates out — no randomness anywhere.

    Ordering starts from a stable sort on ``(label, id)`` so that two runs begin from
    the same permutation, then alternating downward/upward barycentre sweeps pull each
    node towards the average position of its neighbours in the adjacent layer. Ties are
    broken by the node's previous index, which keeps the sort stable.
    """
    if not nodes:
        return {}

    by_layer: dict[int, list[str]] = {}
    layer_of_id: dict[str, int] = {}
    for node in sorted(nodes, key=lambda n: (layer_of(n), n.label.lower(), n.id)):
        rank = layer_of(node)
        layer_of_id[node.id] = rank
        by_layer.setdefault(rank, []).append(node.id)

    present = set(layer_of_id)
    upward: dict[str, list[str]] = {nid: [] for nid in present}
    downward: dict[str, list[str]] = {nid: [] for nid in present}
    for edge in edges:
        if edge.source not in present or edge.target not in present:
            continue
        if layer_of_id[edge.source] == layer_of_id[edge.target]:
            continue
        upper, lower = edge.source, edge.target
        if layer_of_id[upper] > layer_of_id[lower]:
            upper, lower = lower, upper
        downward[upper].append(lower)
        upward[lower].append(upper)

    ranks = sorted(by_layer)
    for sweep in range(max(1, passes)):
        order = ranks if sweep % 2 == 0 else list(reversed(ranks))
        for rank in order:
            reference = upward if sweep % 2 == 0 else downward
            neighbour_rank = rank - 1 if sweep % 2 == 0 else rank + 1
            if neighbour_rank not in by_layer:
                continue
            index_in_neighbour = {nid: i for i, nid in enumerate(by_layer[neighbour_rank])}
            current = {nid: i for i, nid in enumerate(by_layer[rank])}

            # Barycentres are materialised before sorting rather than computed inside the
            # key function, so the sort key cannot depend on a partially reordered layer.
            centres: dict[str, float] = {}
            for node_id in by_layer[rank]:
                neighbours = [
                    index_in_neighbour[n]
                    for n in reference[node_id]
                    if n in index_in_neighbour
                ]
                centres[node_id] = (
                    sum(neighbours) / len(neighbours)
                    if neighbours
                    else float(current[node_id])
                )
            by_layer[rank] = sorted(by_layer[rank], key=lambda nid: (centres[nid], current[nid]))

    tallest = max(len(ids) for ids in by_layer.values())
    column_height = tallest * NODE_HEIGHT + (tallest - 1) * ROW_GAP

    positions: dict[str, tuple[float, float]] = {}
    for rank in ranks:
        ids = by_layer[rank]
        span = len(ids) * NODE_HEIGHT + (len(ids) - 1) * ROW_GAP
        top = MARGIN + HEADER_HEIGHT + (column_height - span) / 2
        x = MARGIN + rank * (NODE_WIDTH + LAYER_GAP)
        for index, node_id in enumerate(ids):
            positions[node_id] = (x, top + index * (NODE_HEIGHT + ROW_GAP))
    return positions


def build_diagram(
    bundle: ReportBundle,
    *,
    scope: Iterable[str] | None = None,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> DiagramData:
    nodes, edges, omitted = select(bundle, scope=scope, max_nodes=max_nodes)
    positions = layout(nodes, edges)
    if positions:
        width = max(x for x, _ in positions.values()) + NODE_WIDTH + MARGIN
        height = max(y for _, y in positions.values()) + NODE_HEIGHT + MARGIN + LEGEND_HEIGHT
    else:
        width, height = 640.0, 240.0
    layers = tuple(sorted({layer_of(n) for n in nodes}))
    return DiagramData(
        nodes=nodes,
        edges=edges,
        positions=positions,
        width=max(width, 640.0),
        height=max(height, 240.0),
        omitted=omitted,
        layers=layers,
    )


# --------------------------------------------------------------------------------------
# SVG
# --------------------------------------------------------------------------------------


def render_svg(
    bundle: ReportBundle,
    *,
    scope: Iterable[str] | None = None,
    title: str = "",
    width: int = 1280,
    height: int = 800,
    max_nodes: int = DEFAULT_MAX_NODES,
    interactive: bool = False,
) -> str:
    """A standalone SVG with its own stylesheet and legend.

    ``interactive`` prepares the markup for embedding in the HTML report rather than for
    standing alone: it wraps the drawing in a ``<g class="ag-viewport">`` for pan/zoom,
    tags every node with ``data-node-id`` for the inspector, and omits the XML namespace
    declaration. That last part matters — inside an HTML document the parser already
    places ``<svg>`` in the SVG namespace, and leaving the declaration in would put an
    ``http://`` URL in a report whose entire promise is that it references nothing
    outside itself.
    """
    diagram = build_diagram(bundle, scope=scope, max_nodes=max_nodes)
    heading = title or f"{bundle.project_name} — {bundle.scope_label}"
    namespace = "" if interactive else 'xmlns="http://www.w3.org/2000/svg" '

    parts: list[str] = [
        f"<svg {namespace}"
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {diagram.width:.0f} {diagram.height:.0f}" '
        'preserveAspectRatio="xMidYMid meet" role="img" '
        f"aria-label={quoteattr(heading)}>",
        f"<title>{escape(heading)}</title>",
        f"<desc>{escape(_description(bundle, diagram))}</desc>",
        _svg_style(),
        _svg_defs(),
        f'<rect class="ag-bg" x="0" y="0" width="{diagram.width:.0f}" '
        f'height="{diagram.height:.0f}"/>',
    ]

    parts.append(f'<g class="ag-header"><text class="ag-title" x="{MARGIN}" y="{MARGIN + 6}">')
    parts.append(escape(truncate(heading, 96)))
    parts.append("</text>")
    parts.append(
        f'<text class="ag-subtitle" x="{MARGIN}" y="{MARGIN + 28}">'
        + escape(_description(bundle, diagram))
        + "</text></g>"
    )

    parts.append('<g class="ag-viewport">' if interactive else "<g>")
    parts.append(_svg_layer_bands(diagram))
    parts.append(_svg_edges(diagram))
    parts.append(_svg_nodes(bundle, diagram, interactive=interactive))
    parts.append("</g>")

    parts.append(_svg_legend(diagram))
    parts.append("</svg>")
    return "".join(parts)


def _description(bundle: ReportBundle, diagram: DiagramData) -> str:
    bits = [
        f"{len(diagram.nodes)} of {bundle.stats.nodes} nodes",
        f"{len(diagram.edges)} relationships",
        f"fingerprint {bundle.spec_fingerprint or 'not recorded'}",
    ]
    if diagram.omitted:
        bits.append(f"{diagram.omitted} lower-level nodes omitted for legibility")
    if bundle.active_scenario:
        bits.append(f"scenario '{bundle.active_scenario}'")
    return " · ".join(bits)


def _svg_style() -> str:
    colour_rules = "".join(
        f".ag-t-{_css_token(node_type.value)} .ag-shape{{stroke:{colour};}}"
        f".ag-t-{_css_token(node_type.value)} .ag-chip{{fill:{colour};}}"
        for node_type, colour in TYPE_COLOURS.items()
    )
    return (
        "<style>"
        f".ag-bg{{fill:{THEME['bg']};}}"
        f".ag-title{{fill:{THEME['text']};font:600 17px system-ui,-apple-system,"
        "'Segoe UI',Roboto,sans-serif;}"
        f".ag-subtitle{{fill:{THEME['muted']};font:400 11px system-ui,-apple-system,"
        "'Segoe UI',Roboto,sans-serif;}"
        f".ag-band{{fill:{THEME['panel']};opacity:.55;}}"
        f".ag-band-label{{fill:{THEME['muted']};font:600 10px system-ui,sans-serif;"
        "letter-spacing:.08em;text-transform:uppercase;}"
        f".ag-shape{{fill:{THEME['panel']};stroke:{THEME['grid']};stroke-width:1.5;}}"
        f".ag-label{{fill:{THEME['text']};font:500 11px system-ui,-apple-system,"
        "'Segoe UI',Roboto,sans-serif;}"
        f".ag-sublabel{{fill:{THEME['muted']};font:400 9.5px system-ui,sans-serif;}}"
        f".ag-edge{{fill:none;stroke:{THEME['fact']};stroke-width:1.3;opacity:.72;}}"
        f".ag-edge-inferred{{stroke:{THEME['inferred']};}}"
        f".ag-edge-user{{stroke:{THEME['user']};}}"
        f".ag-edge-scenario{{stroke:{THEME['scenario']};}}"
        f".ag-legend-box{{fill:{THEME['panel']};stroke:{THEME['grid']};stroke-width:1;}}"
        f".ag-legend-title{{fill:{THEME['text']};font:600 11px system-ui,sans-serif;}}"
        f".ag-legend-text{{fill:{THEME['muted']};font:400 10px system-ui,sans-serif;}}"
        f".ag-legend-line{{stroke:{THEME['text']};stroke-width:1.8;fill:none;}}"
        ".ag-node{cursor:default;}"
        f"{colour_rules}"
        "</style>"
    )


def _svg_defs() -> str:
    markers = "".join(
        f'<marker id="ag-arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{colour}" opacity="0.85"/></marker>'
        for name, colour in (
            ("fact", THEME["fact"]),
            ("inferred", THEME["inferred"]),
            ("user", THEME["user"]),
            ("scenario", THEME["scenario"]),
        )
    )
    return f"<defs>{markers}</defs>"


def _svg_layer_bands(diagram: DiagramData) -> str:
    if not diagram.positions:
        return ""
    out: list[str] = ['<g class="ag-bands">']
    for rank in diagram.layers:
        x = MARGIN + rank * (NODE_WIDTH + LAYER_GAP) - 10
        band_height = diagram.height - LEGEND_HEIGHT - MARGIN - HEADER_HEIGHT
        out.append(
            f'<rect class="ag-band" x="{x:.0f}" y="{MARGIN + HEADER_HEIGHT - 22:.0f}" '
            f'width="{NODE_WIDTH + 20}" height="{max(band_height, 40):.0f}" rx="12"/>'
        )
        title = LAYER_TITLES[rank] if rank < len(LAYER_TITLES) else f"Layer {rank}"
        out.append(
            f'<text class="ag-band-label" x="{x + 10:.0f}" '
            f'y="{MARGIN + HEADER_HEIGHT - 30:.0f}">{escape(title)}</text>'
        )
    out.append("</g>")
    return "".join(out)


def _stroke_class(edge: GraphEdge) -> tuple[str, str, str]:
    """Return ``(css class, dasharray, marker name)`` for an edge."""
    kind = edge.provenance.source_kind
    if kind is SourceKind.USER_EDIT:
        return "ag-edge-user", DASH_FOR_STROKE["dotted"], "user"
    if kind is SourceKind.SCENARIO:
        return "ag-edge-scenario", DASH_FOR_STROKE["dashed"], "scenario"
    if kind in (SourceKind.AI_INFERENCE, SourceKind.BUNDLED_ANALYSIS):
        return "ag-edge-inferred", DASH_FOR_STROKE["dashed"], "inferred"
    return "", DASH_FOR_STROKE["solid"], "fact"


def _edge_path(source: tuple[float, float], target: tuple[float, float]) -> str:
    """A cubic from one node box to another.

    Three cases, because the degenerate one is the ugly one: left-to-right leaves the
    right edge, right-to-left leaves the left edge, and same-layer bows out to the left
    rather than collapsing into a loop on top of the nodes.
    """
    y1 = source[1] + NODE_HEIGHT / 2
    y2 = target[1] + NODE_HEIGHT / 2
    if abs(target[0] - source[0]) < 1:
        x = source[0]
        bow = max(30.0, min(abs(y2 - y1) * 0.5, 120.0))
        return (
            f"M {x:.1f} {y1:.1f} C {x - bow:.1f} {y1:.1f}, "
            f"{x - bow:.1f} {y2:.1f}, {x:.1f} {y2:.1f}"
        )
    if target[0] < source[0]:
        x1, x2 = source[0], target[0] + NODE_WIDTH
    else:
        x1, x2 = source[0] + NODE_WIDTH, target[0]
    control = abs(x2 - x1) * 0.45 or 40
    direction = 1 if x2 > x1 else -1
    return (
        f"M {x1:.1f} {y1:.1f} C {x1 + direction * control:.1f} {y1:.1f}, "
        f"{x2 - direction * control:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}"
    )


def _svg_edges(diagram: DiagramData) -> str:
    out: list[str] = ['<g class="ag-edges">']
    for edge in diagram.edges:
        source = diagram.positions.get(edge.source)
        target = diagram.positions.get(edge.target)
        if source is None or target is None:
            continue
        path = _edge_path(source, target)
        css, dash, marker = _stroke_class(edge)
        dash_attr = "" if dash == "none" else f' stroke-dasharray="{dash}"'
        title = f"{edge.label or edge.type.value} — {edge.provenance.explanation}"
        out.append(
            f'<path class="ag-edge {css}" d="{path}"{dash_attr} '
            f'marker-end="url(#ag-arrow-{marker})" '
            f"data-edge-id={quoteattr(edge.id)} data-source={quoteattr(edge.source)} "
            f"data-target={quoteattr(edge.target)} "
            f"data-source-kind={quoteattr(edge.provenance.source_kind.value)}>"
            f"<title>{escape(truncate(title, 180))}</title></path>"
        )
    out.append("</g>")
    return "".join(out)


def _svg_nodes(bundle: ReportBundle, diagram: DiagramData, *, interactive: bool) -> str:
    domains = bundle._domain_map()
    out: list[str] = ['<g class="ag-nodes">']
    for node in diagram.nodes:
        position = diagram.positions.get(node.id)
        if position is None:
            continue
        x, y = position
        entry = legend_for(node.provenance.source_kind)
        dash = DASH_FOR_STROKE.get(entry.stroke, "none")
        dash_attr = "" if dash == "none" else f' stroke-dasharray="{dash}"'
        sub = domains.get(node.id) or node.type.value
        tooltip = f"{node.label} · {node.type.value} · {entry.label}. {node.provenance.explanation}"

        attrs = (
            f'class="ag-node ag-t-{_css_token(node.type.value)}" '
            f"data-node-id={quoteattr(node.id)} "
            f"data-node-type={quoteattr(node.type.value)} "
            f"data-source-kind={quoteattr(node.provenance.source_kind.value)}"
        )
        if interactive:
            attrs += ' tabindex="0" role="button"'
        out.append(f"<g {attrs}>")
        out.append(f"<title>{escape(truncate(tooltip, 240))}</title>")
        out.append(_shape_for(node, x, y, dash_attr))
        out.append(
            f'<text class="ag-label" x="{x + 14:.0f}" y="{y + 20:.0f}">'
            f"{escape(truncate(node.label, 26))}</text>"
        )
        out.append(
            f'<text class="ag-sublabel" x="{x + 14:.0f}" y="{y + 34:.0f}">'
            f"{escape(truncate(sub, 30))}</text>"
        )
        out.append("</g>")
    out.append("</g>")
    return "".join(out)


def _shape_for(node: GraphNode, x: float, y: float, dash_attr: str) -> str:
    """Shape encodes type; the stroke pattern encodes where the node came from."""
    w, h = NODE_WIDTH, NODE_HEIGHT
    if node.type is NodeType.DOMAIN or node.type is NodeType.CAPABILITY:
        notch = 14
        points = (
            f"{x + notch:.0f},{y:.0f} {x + w - notch:.0f},{y:.0f} {x + w:.0f},{y + h / 2:.0f} "
            f"{x + w - notch:.0f},{y + h:.0f} {x + notch:.0f},{y + h:.0f} "
            f"{x:.0f},{y + h / 2:.0f}"
        )
        return f'<polygon class="ag-shape" points="{points}"{dash_attr}/>'
    if node.type is NodeType.SCHEMA:
        skew = 16
        points = (
            f"{x + skew:.0f},{y:.0f} {x + w:.0f},{y:.0f} {x + w - skew:.0f},{y + h:.0f} "
            f"{x:.0f},{y + h:.0f}"
        )
        return f'<polygon class="ag-shape" points="{points}"{dash_attr}/>'
    if node.type is NodeType.RISK or node.type is NodeType.CHANGE:
        points = (
            f"{x + w / 2:.0f},{y:.0f} {x + w:.0f},{y + h / 2:.0f} "
            f"{x + w / 2:.0f},{y + h:.0f} {x:.0f},{y + h / 2:.0f}"
        )
        return f'<polygon class="ag-shape" points="{points}"{dash_attr}/>'
    if node.type is NodeType.FIELD or node.type is NodeType.EVIDENCE:
        # An ellipse rather than a true circle: a circle wide enough to hold a field
        # label would be taller than the row, and the row height is what keeps the
        # layers aligned. It still reads as "the round one" next to the other shapes.
        return (
            f'<ellipse class="ag-shape" cx="{x + w / 2:.0f}" cy="{y + h / 2:.0f}" '
            f'rx="{w / 2:.0f}" ry="{h / 2:.0f}"{dash_attr}/>'
        )
    if node.type in (NodeType.API_OPERATION, NodeType.ENDPOINT, NodeType.JOURNEY_STEP):
        return (
            f'<rect class="ag-shape" x="{x:.0f}" y="{y:.0f}" width="{w}" height="{h}"'
            f"{dash_attr}/>"
        )
    return (
        f'<rect class="ag-shape" x="{x:.0f}" y="{y:.0f}" width="{w}" height="{h}" '
        f'rx="11" ry="11"{dash_attr}/>'
    )


def _svg_legend(diagram: DiagramData) -> str:
    top = diagram.height - LEGEND_HEIGHT
    box_width = max(520.0, min(diagram.width - 2 * MARGIN, 1100))
    column_width = (box_width - 40) / 2
    out = [
        '<g class="ag-legend" role="list" aria-label="How to read this diagram">',
        f'<rect class="ag-legend-box" x="{MARGIN}" y="{top:.0f}" width="{box_width:.0f}" '
        f'height="{LEGEND_HEIGHT - 20}" rx="10"/>',
        f'<text class="ag-legend-title" x="{MARGIN + 16}" y="{top + 22:.0f}">'
        "How to read this diagram — line style shows where each thing came from</text>",
    ]
    for index, entry in enumerate(LEGEND[:4]):
        row_y = top + 46 + (index % 2) * 20
        col_x = MARGIN + 16 + (index // 2) * (column_width + 8)
        dash = "" if entry.dash_array == "none" else f' stroke-dasharray="{entry.dash_array}"'
        # ~5.3px per character at 10px system-ui; the label and separator eat into the
        # budget before the meaning gets what is left.
        budget = int((column_width - 40) / 5.3) - len(entry.label) - 3
        out.append(
            f'<line class="ag-legend-line" x1="{col_x:.0f}" y1="{row_y - 4:.0f}" '
            f'x2="{col_x + 26:.0f}" y2="{row_y - 4:.0f}"{dash}/>'
        )
        out.append(
            f'<text class="ag-legend-text" x="{col_x + 34:.0f}" y="{row_y:.0f}">'
            f"{escape(entry.label)} — {escape(truncate(entry.meaning, max(24, budget)))}</text>"
        )
    if diagram.omitted:
        out.append(
            f'<text class="ag-legend-text" x="{MARGIN + 16}" '
            f'y="{top + LEGEND_HEIGHT - 28:.0f}">'
            f"{diagram.omitted} lower-level nodes were omitted to keep this readable. "
            "The machine-readable exports contain all of them.</text>"
        )
    out.append("</g>")
    return "".join(out)


def _css_token(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value).strip("-").lower()


# --------------------------------------------------------------------------------------
# Print SVG
# --------------------------------------------------------------------------------------

# A4 at 96 CSS pixels per inch, less the print stylesheet's 16mm side and 20/18mm
# vertical margins, less room for a heading and a caption. A figure larger than this
# does not fit on the page and the layout engine will break or drop it.
A4_CONTENT_WIDTH_PX = 660
A4_FIGURE_HEIGHT_PX = 800

PRINT_THEME = {
    "bg": "#FFFFFF",
    "panel": "#F4F7FA",
    "line": "#B7C4D2",
    "text": "#101820",
    "muted": "#4A5B6E",
    "fact": "#1B4F91",
    "inferred": "#8A5A00",
    "user": "#0F6B4F",
    "scenario": "#8C1F4B",
}

PRINT_TYPE_COLOURS: dict[NodeType, str] = {
    NodeType.DOMAIN: "#5B3FA8",
    NodeType.CAPABILITY: "#6D4FC0",
    NodeType.SERVICE: "#1B4F91",
    NodeType.JOURNEY: "#8A5A00",
    NodeType.JOURNEY_STEP: "#8A5A00",
    NodeType.BUSINESS_ENTITY: "#0B5D6B",
    NodeType.API_OPERATION: "#0D5F8A",
    NodeType.ENDPOINT: "#0D5F8A",
    NodeType.SCHEMA: "#0F6B4F",
    NodeType.FIELD: "#4A5B6E",
    NodeType.RISK: "#8C1F4B",
    NodeType.CHANGE: "#8C1F4B",
}


def render_print_svg(
    bundle: ReportBundle,
    *,
    scope: Iterable[str] | None = None,
    title: str = "",
    max_width: int = A4_CONTENT_WIDTH_PX,
    max_height: int = A4_FIGURE_HEIGHT_PX,
    max_nodes: int = 46,
) -> str:
    """A light-theme SVG for paper, styled entirely with presentation attributes.

    Three reasons this is not just ``render_svg`` with different colours. Paper needs
    dark ink on white, not the screen's white-on-black. The PDF engine's SVG renderer
    supports only a subset of CSS, so nothing here relies on a ``<style>`` block — every
    fill, stroke and dash is an attribute on the element that needs it. And the rendered
    box is explicitly fitted inside one A4 figure area, because a figure taller than the
    page is silently dropped or split by the layout engine.
    """
    diagram = build_diagram(bundle, scope=scope, max_nodes=max_nodes)
    height = diagram.height - LEGEND_HEIGHT + 30
    fit = min(max_width / diagram.width, max_height / height, 1.0)
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {diagram.width:.0f} '
        f'{height:.0f}" width="{diagram.width * fit:.0f}" height="{height * fit:.0f}" '
        'preserveAspectRatio="xMidYMid meet" role="img" '
        f"aria-label={quoteattr(title or bundle.scope_label)}>",
        f"<title>{escape(title or bundle.scope_label)}</title>",
        f'<rect x="0" y="0" width="{diagram.width:.0f}" height="{height:.0f}" '
        f'fill="{PRINT_THEME["bg"]}"/>',
    ]
    if title:
        parts.append(
            f'<text x="{MARGIN}" y="{MARGIN + 4}" fill="{PRINT_THEME["text"]}" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="15" font-weight="600">'
            f"{escape(truncate(title, 78))}</text>"
        )

    for edge in diagram.edges:
        source = diagram.positions.get(edge.source)
        target = diagram.positions.get(edge.target)
        if source is None or target is None:
            continue
        _, dash, marker = _stroke_class(edge)
        colour = PRINT_THEME.get(marker, PRINT_THEME["fact"])
        dash_attr = "" if dash == "none" else f' stroke-dasharray="{dash}"'
        parts.append(
            f'<path d="{_edge_path(source, target)}" fill="none" '
            f'stroke="{colour}" stroke-width="1.1" opacity="0.75"{dash_attr}/>'
        )

    for node in diagram.nodes:
        position = diagram.positions.get(node.id)
        if position is None:
            continue
        x, y = position
        colour = PRINT_TYPE_COLOURS.get(node.type, PRINT_THEME["muted"])
        entry = legend_for(node.provenance.source_kind)
        dash = DASH_FOR_STROKE.get(entry.stroke, "none")
        dash_attr = "" if dash == "none" else f' stroke-dasharray="{dash}"'
        shape = _shape_for(node, x, y, dash_attr)
        shape = shape.replace(
            'class="ag-shape"',
            f'fill="{PRINT_THEME["panel"]}" stroke="{colour}" stroke-width="1.4"',
        )
        parts.append(shape)
        parts.append(
            f'<text x="{x + 12:.0f}" y="{y + 20:.0f}" fill="{PRINT_THEME["text"]}" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="10.5">'
            f"{escape(truncate(node.label, 27))}</text>"
        )
        parts.append(
            f'<text x="{x + 12:.0f}" y="{y + 33:.0f}" fill="{PRINT_THEME["muted"]}" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="8.5">'
            f"{escape(truncate(node.type.value, 28))}</text>"
        )

    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------------------
# PNG
# --------------------------------------------------------------------------------------


def render_png(svg: str, *, scale: int = 2, background: str | None = None) -> bytes:
    """Rasterise an SVG. Requires cairosvg; there is no silent fallback on purpose.

    Scale 1 is for the web, 2 for retina and documents, 3 for a slide someone will
    project. A fake rasteriser producing a blank or approximate image would be worse
    than an honest error, so an unavailable dependency raises.
    """
    if scale not in (1, 2, 3):
        raise ValueError("PNG scale must be 1, 2 or 3.")
    reason = probe_cairosvg()
    if reason:
        raise ExportUnavailable(reason, format_id="png")

    import cairosvg

    return cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        scale=scale,
        background_color=background or THEME["bg"],
    )


# --------------------------------------------------------------------------------------
# Mermaid
# --------------------------------------------------------------------------------------

_MERMAID_TYPES = frozenset(
    {
        NodeType.DOMAIN,
        NodeType.SERVICE,
        NodeType.API_OPERATION,
        NodeType.SCHEMA,
        NodeType.JOURNEY,
        NodeType.BUSINESS_ENTITY,
    }
)


def render_mermaid(
    bundle: ReportBundle,
    *,
    scope: Iterable[str] | None = None,
    max_nodes: int = 90,
) -> str:
    """A ``flowchart LR`` that renders in GitHub, GitLab and Confluence out of the box.

    Fields are collapsed away: at Mermaid's level of detail a hundred leaf properties
    make the picture unreadable, and the machine-readable exports still carry them.
    """
    wanted: set[str] | None = set(scope) if scope is not None else None
    nodes = [
        n
        for n in bundle.graph.nodes
        if n.type in _MERMAID_TYPES and (wanted is None or n.id in wanted)
    ]
    nodes.sort(key=lambda n: (_KEEP_PRIORITY.get(n.type, 20), n.label.lower(), n.id))
    omitted = max(0, len(nodes) - max_nodes)
    nodes = nodes[:max_nodes]
    keep = {n.id for n in nodes}
    edges = [
        e
        for e in bundle.graph.edges
        if e.source in keep and e.target in keep and e.type not in _MUTED_EDGE_TYPES
    ]

    domains = {n.id: n for n in nodes if n.type is NodeType.DOMAIN}
    domain_of = bundle._domain_map()
    grouped: dict[str, list[GraphNode]] = {}
    loose: list[GraphNode] = []
    for node in nodes:
        if node.type is NodeType.DOMAIN:
            continue
        label = domain_of.get(node.id)
        owner = next((d for d in domains.values() if d.label == label), None)
        if owner is None:
            loose.append(node)
        else:
            grouped.setdefault(owner.id, []).append(node)

    lines = ["flowchart LR"]
    for domain_id, members in sorted(grouped.items()):
        domain = domains[domain_id]
        lines.append(f'  subgraph {_mid(domain_id)}["{_mlabel(domain.label)}"]')
        lines.append("    direction LR")
        for member in members:
            lines.append(f"    {_mnode(member)}")
        lines.append("  end")
    for node in loose:
        lines.append(f"  {_mnode(node)}")
    for domain in domains.values():
        if domain.id not in grouped:
            lines.append(f"  {_mnode(domain)}")

    for edge in edges:
        if edge.source in domains or edge.target in domains:
            # Membership is already expressed by the subgraph box.
            if edge.type in (EdgeType.BELONGS_TO_DOMAIN, EdgeType.CONTAINS):
                continue
        label = _mlabel(edge.label or edge.type.value.replace("_", " ").lower())
        if edge.provenance.is_fact and edge.acceptance.value == "observed":
            lines.append(f'  {_mid(edge.source)} -->|"{label}"| {_mid(edge.target)}')
        else:
            lines.append(f'  {_mid(edge.source)} -. "{label} (inferred)" .-> {_mid(edge.target)}')

    lines.append(f"  %% {_mcomment(bundle.project_name)} — {_mcomment(bundle.scope_label)}")
    lines.append(f"  %% fingerprint {_mcomment(bundle.spec_fingerprint or 'not recorded')}")
    lines.append("  %% solid = specification fact, dotted = inference awaiting review")
    if omitted:
        lines.append(f"  %% {omitted} further nodes omitted; see the machine-readable export")
    return "\n".join(lines)


def render_journey_mermaid(journey: Journey, *, actor: str = "Customer") -> str:
    """A ``sequenceDiagram`` with one participant per service and narration as notes.

    Every step is drawn as a call from the actor, not from the previous service: a
    journey is a sequence of things a person (or the storefront acting for them) causes
    to happen, and chaining service-to-service would assert a call the specification
    never stated.
    """
    actor_id = _mid(actor) or "Actor"
    participants: list[tuple[str, str]] = [(actor_id, _participant_label(actor))]
    seen = {actor_id}
    for step in journey.steps:
        if not step.service_id:
            continue
        pid = _mid(step.service_id)
        if pid not in seen:
            seen.add(pid)
            participants.append((pid, _participant_label(step.service_id.split(":", 1)[-1])))

    lines = ["sequenceDiagram", "    autonumber"]
    for pid, label in participants:
        lines.append(f"    participant {pid} as {label}")

    for step in journey.steps:
        target = _mid(step.service_id) if step.service_id else actor_id
        lines.append(f"    {actor_id}->>{target}: {_mlabel(step.label)}")
        if step.narration:
            lines.append(f"    Note over {target}: {_mlabel(truncate(step.narration, 110))}")
        if step.deprecated:
            lines.append(f"    Note right of {target}: deprecated operation")

    lines.append(f"    %% {_mcomment(journey.name)}")
    lines.append(f"    %% derived by: {_mcomment(journey.provenance.explanation)}")
    return "\n".join(lines)


def _participant_label(raw: str) -> str:
    """Participant aliases are unquoted in Mermaid, so keep them to safe characters."""
    cleaned = "".join(ch if (ch.isalnum() or ch in " -_") else " " for ch in str(raw))
    return truncate(cleaned, 40) or "Service"


def _mid(raw: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw)
    return cleaned if cleaned and not cleaned[0].isdigit() else f"n_{cleaned}"


def _mlabel(raw: str) -> str:
    """Mermaid labels are quoted, so quotes, newlines and brackets must not survive."""
    text = " ".join(str(raw).split())
    text = text.replace('"', "#quot;").replace("'", "#39;")
    text = text.replace("[", "#91;").replace("]", "#93;")
    text = text.replace("{", "#123;").replace("}", "#125;")
    text = text.replace("|", "#124;").replace("`", "#96;")
    return truncate(text, 70)


def _mnode(node: GraphNode) -> str:
    label = _mlabel(node.label)
    nid = _mid(node.id)
    if node.type is NodeType.SERVICE:
        return f'{nid}("{label}")'
    if node.type is NodeType.SCHEMA:
        return f'{nid}[/"{label}"/]'
    if node.type is NodeType.JOURNEY:
        return f'{nid}(["{label}"])'
    if node.type is NodeType.BUSINESS_ENTITY:
        return f'{nid}[("{label}")]'
    return f'{nid}["{label}"]'


def _mcomment(raw: str) -> str:
    return " ".join(str(raw).split()).replace("\n", " ")
