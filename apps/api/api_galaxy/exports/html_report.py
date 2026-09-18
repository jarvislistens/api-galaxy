"""The interactive HTML report: one file, no network, read-only.

This is the artifact that gets emailed, dropped on a share drive, or opened on a laptop
with the wifi off during an architecture review. Everything about it follows from that:

* **Single file, zero external requests.** CSS and JavaScript are read out of
  ``packages/report-runtime/src`` and inlined. No CDN, no webfont, no ``fetch``. A meta
  CSP of ``default-src 'none'`` makes that a rule the browser enforces rather than a
  promise this module makes.
* **Read-only.** It contains a snapshot, not a connection. Nothing it does can change
  the project it describes.
* **Escaped twice over.** The static markup is authored here and every interpolated
  value goes through :func:`html.escape`. The JSON payload has ``<``, ``>`` and ``&``
  replaced with their ``\\u00xx`` escapes, which is what stops a node labelled
  ``</script>`` from ending the data block early. The runtime then builds all dynamic
  DOM with ``textContent``.
* **Useful without JavaScript.** Every report section, and a full table of nodes and
  edges, is rendered server-side. If scripting is off you lose pan/zoom and the journey
  player; you do not lose the report.
"""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Any

from api_galaxy.contracts.analysis import RiskSeverity
from api_galaxy.contracts.graph import GraphNode, NodeType, SourceKind
from api_galaxy.contracts.scenario import ImpactStatus
from api_galaxy.exports.bundle import ReportBundle, legend_for
from api_galaxy.exports.diagrams import DEFAULT_MAX_NODES, render_svg
from api_galaxy.exports.support import ExportUnavailable, truncate

RUNTIME_ENV_VAR = "API_GALAXY_REPORT_RUNTIME"

PROVENANCE_GROUPS: dict[SourceKind, tuple[str, str]] = {
    SourceKind.SPECIFICATION: ("fact", "Specification fact"),
    SourceKind.DETERMINISTIC_RULE: ("fact", "Deterministic rule"),
    SourceKind.BUNDLED_ANALYSIS: ("inferred", "Bundled analysis"),
    SourceKind.AI_INFERENCE: ("inferred", "Model inference"),
    SourceKind.USER_EDIT: ("user", "Created by a person"),
    SourceKind.SCENARIO: ("scenario", "Scenario change"),
}

TABS = (
    ("explore", "Explore the map"),
    ("summary", "Summary"),
    ("domains", "Domains"),
    ("journeys", "Journeys"),
    ("risks", "Findings"),
    ("impact", "Scenario impact"),
    ("method", "Methodology"),
    ("data", "All data"),
)


# --------------------------------------------------------------------------------------
# Runtime assets
# --------------------------------------------------------------------------------------


def runtime_dir() -> Path:
    """Locate ``packages/report-runtime/src``.

    The exporter runs from a source checkout in normal use, so the repository-relative
    path is tried first; the environment variable is the escape hatch for a packaged
    install where the runtime sits somewhere else.
    """
    override = os.environ.get(RUNTIME_ENV_VAR)
    candidates = [Path(override)] if override else []
    here = Path(__file__).resolve()
    candidates.append(here.parents[4] / "packages" / "report-runtime" / "src")
    candidates.append(here.parents[1] / "report_runtime")
    for candidate in candidates:
        if (candidate / "report.js").is_file() and (candidate / "report.css").is_file():
            return candidate
    raise ExportUnavailable(
        "The interactive report runtime (packages/report-runtime/src/report.js and "
        f"report.css) could not be found. Set {RUNTIME_ENV_VAR} to its directory.",
        format_id="html",
    )


def _read_runtime() -> tuple[str, str]:
    directory = runtime_dir()
    return (
        (directory / "report.css").read_text(encoding="utf-8"),
        (directory / "report.js").read_text(encoding="utf-8"),
    )


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------


def to_html(bundle: ReportBundle, *, max_nodes: int = DEFAULT_MAX_NODES) -> str:
    css, js = _read_runtime()
    svg = render_svg(
        bundle,
        title=f"{bundle.project_name} — {bundle.scope_label}",
        width=1400,
        height=900,
        max_nodes=max_nodes,
        interactive=True,
    )
    payload = _payload(bundle)

    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        # Belt and braces: the page already contains no external reference, and this
        # stops one from ever working if a future edit slips through review.
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; "
        "font-src 'none'; connect-src 'none'; form-action 'none'; base-uri 'none'\">",
        f"<title>{_h(bundle.project_name)} — API Galaxy report</title>",
        f"<style>{css}</style>",
        "</head>",
        "<body>",
        '<a class="ag-skip" href="#ag-main">Skip to report</a>',
        _masthead(bundle),
        _tablist(),
        '<main id="ag-main">',
        _panel_explore(bundle, svg),
        _panel_summary(bundle),
        _panel_domains(bundle),
        _panel_journeys(bundle),
        _panel_risks(bundle),
        _panel_impact(bundle),
        _panel_method(bundle),
        _panel_data(bundle),
        "</main>",
        _footer(bundle),
        _data_block(payload),
        f"<script>{js}</script>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts)


# --------------------------------------------------------------------------------------
# Data block
# --------------------------------------------------------------------------------------


def _data_block(payload: dict[str, Any]) -> str:
    """Embed the snapshot so that no value in it can close the script element."""
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    encoded = (
        encoded.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        # U+2028/U+2029 are literal line breaks to a JavaScript parser but not to
        # JSON.parse. Escaping them keeps both readers in agreement.
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    return (
        '<script type="application/json" id="api-galaxy-data">' + encoded + "</script>"
    )


def _payload(bundle: ReportBundle) -> dict[str, Any]:
    domains = bundle._domain_map()
    index = bundle.graph.node_index()

    nodes: dict[str, Any] = {}
    order: list[str] = []
    for node in bundle.graph.nodes:
        group, label = PROVENANCE_GROUPS.get(node.provenance.source_kind, ("fact", "Unknown"))
        order.append(node.id)
        nodes[node.id] = {
            "id": node.id,
            "type": node.type.value,
            "label": node.label,
            "description": node.description,
            "domain": domains.get(node.id),
            "service": node.attrs.get("service") or node.attrs.get("slug"),
            "sourceKind": node.provenance.source_kind.value,
            "sourceLabel": label,
            "provenanceGroup": group,
            "acceptance": node.acceptance.value,
            "confidence": node.provenance.confidence,
            "provider": node.provenance.provider,
            "model": node.provenance.model,
            "ruleId": node.provenance.rule_id,
            "explanation": node.provenance.explanation,
            "evidence": [
                {"locator": ev.locator, "label": ev.label, "excerpt": ev.excerpt}
                for ev in node.evidence[:6]
            ],
            "tags": list(node.tags),
        }

    adjacency: dict[str, list[dict[str, Any]]] = {nid: [] for nid in nodes}
    for edge in bundle.graph.edges:
        if edge.source not in nodes or edge.target not in nodes:
            continue
        group, label = PROVENANCE_GROUPS.get(edge.provenance.source_kind, ("fact", "Unknown"))
        relation = edge.label or edge.type.value.replace("_", " ").lower()
        adjacency[edge.source].append(
            {
                "id": edge.target,
                "label": relation,
                "direction": "→",
                "sourceKind": edge.provenance.source_kind.value,
                "sourceLabel": label,
            }
        )
        adjacency[edge.target].append(
            {
                "id": edge.source,
                "label": relation,
                "direction": "←",
                "sourceKind": edge.provenance.source_kind.value,
                "sourceLabel": label,
            }
        )

    journeys = [
        {
            "id": journey.id,
            "name": journey.name,
            "description": journey.description,
            "steps": [
                {
                    "order": step.order,
                    "label": step.label,
                    "narration": step.narration,
                    "technical": step.technical_detail,
                    "nodeIds": [nid for nid in step.node_ids if nid in index],
                }
                for step in journey.steps
            ],
        }
        for journey in bundle.journeys
    ]

    return {
        "project": {
            "id": bundle.project_id,
            "name": bundle.project_name,
            "scope": bundle.scope_label,
            "generatedAt": bundle.generated_at.isoformat(),
            "fingerprint": bundle.spec_fingerprint,
            "appVersion": bundle.app_version,
            "scenario": bundle.active_scenario,
            "provider": bundle.provider_disclosure,
        },
        "legend": [entry.model_dump() for entry in bundle.legend],
        "nodes": nodes,
        "nodeOrder": order,
        "adjacency": adjacency,
        "journeys": journeys,
    }


# --------------------------------------------------------------------------------------
# Static sections
# --------------------------------------------------------------------------------------


def _masthead(bundle: ReportBundle) -> str:
    chips = "".join(
        f"<li><b>{_h(key)}:</b> {_h(str(value))}</li>" for key, value in bundle.disclosure_rows()
    )
    return (
        '<header class="ag-masthead">'
        f"<h1>{_h(bundle.project_name)} — API estate report</h1>"
        f'<p class="ag-scope">{_h(bundle.scope_label)} · read-only snapshot · '
        "this file contains everything it needs and makes no network requests.</p>"
        f'<ul class="ag-disclosure">{chips}</ul>'
        '<p class="ag-footnote" id="ag-runtime-status">Static mode — enable JavaScript for '
        "search, pan and zoom, the node inspector and the journey player. Every section of "
        "the report is readable without it.</p>"
        "</header>"
    )


def _tablist() -> str:
    buttons = "".join(
        f'<button class="ag-tab" type="button" role="tab" id="tab-{tab}" '
        f'aria-controls="panel-{tab}" aria-selected="false" tabindex="-1">{_h(title)}</button>'
        for tab, title in TABS
    )
    return f'<nav class="ag-tabs" role="tablist" aria-label="Report sections">{buttons}</nav>'


def _panel(tab: str, body: str) -> str:
    return (
        f'<section class="ag-panel" id="panel-{tab}" role="tabpanel" '
        f'aria-labelledby="tab-{tab}" tabindex="0" hidden>{body}</section>'
    )


def _panel_explore(bundle: ReportBundle, svg: str) -> str:
    types = sorted({n.type.value for n in bundle.graph.nodes})
    domain_labels = sorted({label for label in bundle._domain_map().values() if label})
    provenance_options = [
        ("fact", "Specification facts only"),
        ("inferred", "Inferences only"),
        ("user", "Created by a person"),
        ("scenario", "Scenario changes"),
    ]

    toolbar = (
        '<div class="ag-toolbar">'
        '<div class="ag-field"><label for="ag-search">Search</label>'
        '<input id="ag-search" type="search" autocomplete="off" '
        'placeholder="service, operation, schema, field…" '
        'aria-label="Search nodes by name, type or description"></div>'
        + _select("ag-filter-type", "Type", types, "All types")
        + _select("ag-filter-domain", "Domain", domain_labels, "All domains")
        + _select(
            "ag-filter-provenance",
            "Provenance",
            provenance_options,
            "Facts and inferences",
        )
        + '<button class="ag-btn" type="button" id="ag-filter-reset">Reset filters</button>'
        '<p class="ag-count" id="ag-filter-count" role="status" aria-live="polite"></p>'
        "</div>"
    )

    canvas = (
        '<div class="ag-canvas-wrap">'
        '<div class="ag-canvas" id="ag-canvas" role="application" '
        'aria-label="Estate map. Drag to pan, scroll to zoom, arrow keys to move, '
        'plus and minus to zoom, zero to reset. A full text listing is in the All data '
        'tab.">' + svg + "</div>"
        '<div class="ag-canvas-controls">'
        '<button class="ag-btn" type="button" id="ag-zoom-in" aria-label="Zoom in">+</button>'
        '<button class="ag-btn" type="button" id="ag-zoom-out" aria-label="Zoom out">−</button>'
        '<button class="ag-btn" type="button" id="ag-zoom-fit" '
        'aria-label="Reset zoom and position">Fit</button>'
        "</div>"
        '<p class="ag-zoom-readout" id="ag-zoom-readout">100%</p>'
        "</div>"
    )

    # The matches list is the keyboard path to the same thing the map offers with a
    # pointer: it turns the filter into a focusable list of real buttons.
    side = (
        '<div class="ag-side">'
        '<section class="ag-matches" aria-label="Matching nodes">'
        "<h3>Matches</h3>"
        '<ul id="ag-results" class="ag-results"></ul>'
        "</section>"
        '<aside class="ag-inspector" id="ag-inspector" aria-live="polite" '
        'aria-label="Node inspector">'
        '<p class="ag-empty">Select a node in the map to inspect it.</p>'
        "</aside>"
        "</div>"
    )

    return _panel(
        "explore",
        '<div class="ag-section">'
        + toolbar
        + '<div class="ag-workspace">'
        + canvas
        + side
        + "</div>"
        + _player(bundle)
        + _legend_block(bundle)
        + "</div>",
    )


def _select(element_id: str, label: str, options: Any, blank: str) -> str:
    pairs = [(o, o) if isinstance(o, str) else o for o in options]
    rendered = "".join(f'<option value="{_h(v)}">{_h(t)}</option>' for v, t in pairs)
    return (
        f'<div class="ag-field"><label for="{element_id}">{_h(label)}</label>'
        f'<select id="{element_id}"><option value="">{_h(blank)}</option>{rendered}</select></div>'
    )


def _player(bundle: ReportBundle) -> str:
    if not bundle.journeys:
        return ""
    options = "".join(
        f'<option value="{_h(j.id)}">{_h(j.name)}</option>' for j in bundle.journeys
    )
    speeds = "".join(
        f'<option value="{value}"{" selected" if value == "1" else ""}>{_h(text)}</option>'
        for value, text in (("0.5", "0.5× slow"), ("1", "1× normal"), ("2", "2× fast"))
    )
    return (
        '<div class="ag-player">'
        "<h3>Journey player</h3>"
        '<div class="ag-player-controls">'
        '<div class="ag-field"><label for="ag-journey">Journey</label>'
        f'<select id="ag-journey">{options}</select></div>'
        '<button class="ag-btn" type="button" id="ag-play" aria-pressed="false">Play</button>'
        '<button class="ag-btn" type="button" id="ag-step-back" '
        'aria-label="Previous step">Back</button>'
        '<button class="ag-btn" type="button" id="ag-step-forward" '
        'aria-label="Next step">Step</button>'
        '<button class="ag-btn" type="button" id="ag-restart">Restart</button>'
        '<div class="ag-field"><label for="ag-speed">Speed</label>'
        f'<select id="ag-speed">{speeds}</select></div>'
        "</div>"
        '<div class="ag-progress"><span id="ag-progress-bar"></span></div>'
        '<div id="ag-step"><p class="ag-empty">Choose a journey and press Play.</p></div>'
        '<p class="ag-footnote" id="ag-player-live" role="status" aria-live="polite"></p>'
        "</div>"
    )


def _legend_block(bundle: ReportBundle) -> str:
    items = "".join(
        f'<li><span class="ag-legend-swatch" data-stroke="{_h(entry.stroke)}" aria-hidden="true">'
        f"</span><span><b>{_h(entry.label)}</b> — {_h(entry.meaning)}</span></li>"
        for entry in bundle.legend
    )
    return (
        '<div class="ag-section"><h2>How to read this map</h2>'
        f'<ul class="ag-legend-list">{items}</ul></div>'
    )


def _panel_summary(bundle: ReportBundle) -> str:
    stats = bundle.stats
    cards = [
        ("Services", stats.services, "OpenAPI documents imported"),
        ("Operations", stats.operations, "HTTP operations described"),
        ("Schemas", stats.schemas, "Named data contracts"),
        ("Fields", stats.fields, "Individual properties"),
        ("Domains", stats.domains, "Business areas"),
        ("Journeys", len(bundle.journeys), "End-to-end flows"),
        ("Findings", len(bundle.risks), "Issues raised by rules"),
        (
            "Inferred links",
            stats.inferred_edges,
            f"of {stats.edges} relationships await review",
        ),
    ]
    card_html = "".join(
        f'<div class="ag-card"><p class="ag-metric">{value}</p>'
        f"<h4>{_h(title)}</h4><p>{_h(note)}</p></div>"
        for title, value, note in cards
    )
    scenario = ""
    if bundle.active_scenario:
        scenario = (
            "<p><b>This report describes a hypothetical estate.</b> The scenario "
            f"“{_h(bundle.active_scenario)}” is applied, so some contracts shown here do not "
            "exist in the specifications you imported.</p>"
        )
    return _panel(
        "summary",
        '<div class="ag-section"><h2>At a glance</h2>'
        f'<div class="ag-cards">{card_html}</div></div>'
        '<div class="ag-section"><h2>What was analysed</h2>'
        f'<div class="ag-prose">{scenario}'
        f"<p>{_h(bundle.project_name)} is described by {stats.services} service "
        f"{_plural(stats.services, 'specification')} exposing {stats.operations} "
        f"{_plural(stats.operations, 'operation')} over {stats.schemas} "
        f"{_plural(stats.schemas, 'schema')}. Of {stats.edges} relationships in the model, "
        f"{stats.observed_edges} come straight from the specifications and "
        f"{stats.inferred_edges} are inferred and marked as proposals.</p>"
        f"<p>Semantic analysis in this report was produced by "
        f"<b>{_h(bundle.provider_disclosure)}</b>. The specification fingerprint is "
        f"<code>{_h(bundle.spec_fingerprint or 'not recorded')}</code>; regenerating this "
        "report from the same documents will produce the same graph.</p>"
        "</div></div>",
    )


def _panel_domains(bundle: ReportBundle) -> str:
    membership = bundle._domain_map()
    blocks: list[str] = []
    for domain in sorted(bundle.nodes_of(NodeType.DOMAIN), key=lambda n: n.label.lower()):
        entry = legend_for(domain.provenance.source_kind)
        services = sorted(
            {
                node.label
                for node_id, label in membership.items()
                if label == domain.label
                and (node := bundle.graph.get(node_id)) is not None
                and node.type is NodeType.SERVICE
            }
        )
        blocks.append(
            '<div class="ag-card">'
            f"<h4>{_h(domain.label)}</h4>"
            f'<p><span class="ag-chip" data-kind="{_h(domain.provenance.source_kind.value)}">'
            f"{_h(entry.label)}</span></p>"
            f"<p>{_h(domain.description or domain.provenance.explanation)}</p>"
            f"<p><b>Services:</b> {_h(', '.join(services) or 'none recorded')}</p>"
            "</div>"
        )
    body = (
        '<div class="ag-section"><h2>Business domains</h2>'
        '<div class="ag-prose"><p>Domains group services by the part of the business they '
        "serve. A domain a specification declared is a fact; a domain that analysis proposed "
        "is labelled as an inference.</p></div>"
        f'<div class="ag-cards">{"".join(blocks) or "<p>No domains in this scope.</p>"}</div>'
        "</div>"
    )
    return _panel("domains", body)


def _panel_journeys(bundle: ReportBundle) -> str:
    blocks: list[str] = []
    for journey in bundle.journeys:
        entry = legend_for(journey.provenance.source_kind)
        rows = "".join(
            f"<tr><td>{step.order}</td><td>{_h(step.label)}</td>"
            f"<td>{_h(step.narration)}</td>"
            f"<td><code>{_h(step.operation_id or '—')}</code></td></tr>"
            for step in journey.steps
        )
        blocks.append(
            '<details class="ag-details" open>'
            f"<summary>{_h(journey.name)} — {len(journey.steps)} "
            f"{_plural(len(journey.steps), 'step')}</summary>"
            f'<p><span class="ag-chip" data-kind="{_h(journey.provenance.source_kind.value)}">'
            f"{_h(entry.label)}</span> {_h(journey.provenance.explanation)}</p>"
            + (f"<p>{_h(journey.description)}</p>" if journey.description else "")
            + '<div class="ag-table-wrap"><table class="ag-table">'
            "<thead><tr><th>#</th><th>Step</th><th>What happens</th><th>Operation</th></tr>"
            f"</thead><tbody>{rows}</tbody></table></div></details>"
        )
    return _panel(
        "journeys",
        '<div class="ag-section"><h2>End-to-end journeys</h2>'
        '<div class="ag-prose"><p>A journey is a sequence of operations that together '
        "deliver something a person recognises. Use the player on the Explore tab to watch "
        "one move across the map.</p></div>"
        + ("".join(blocks) or "<p>No journeys in this scope.</p>")
        + "</div>",
    )


def _panel_risks(bundle: ReportBundle) -> str:
    sections: list[str] = []
    for severity in (
        RiskSeverity.HIGH,
        RiskSeverity.MEDIUM,
        RiskSeverity.LOW,
        RiskSeverity.INFO,
    ):
        group = [r for r in bundle.risks if r.severity is severity]
        if not group:
            continue
        rows = "".join(
            f'<tr><td><span class="ag-sev" data-severity="{_h(risk.severity.value)}">'
            f"{_h(risk.severity.value)}</span></td>"
            f"<td><b>{_h(risk.title)}</b><br>{_h(risk.description)}</td>"
            f"<td>{_h(risk.label.replace(' finding', ''))}</td>"
            f"<td><code>{_h(risk.rule_id)}</code></td>"
            f"<td>{_h(risk.recommendation or '—')}</td>"
            f"<td>{len(risk.node_ids)}</td></tr>"
            for risk in sorted(group, key=lambda r: (r.rule_id, r.id))
        )
        sections.append(
            f"<h3>{_h(severity.value.title())} ({len(group)})</h3>"
            '<div class="ag-table-wrap"><table class="ag-table">'
            "<thead><tr><th>Severity</th><th>Finding</th><th>Basis</th><th>Rule</th>"
            "<th>What to do</th><th>Affects</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>"
        )
    appendix = _ambiguity_block(bundle)
    return _panel(
        "risks",
        '<div class="ag-section"><h2>Findings</h2>'
        '<div class="ag-prose"><p>The <b>Basis</b> column separates rules that prove a '
        "problem from rules that recognise a pattern and may be wrong.</p></div>"
        + ("".join(sections) or "<p>No findings were raised for this scope.</p>")
        + "</div>"
        + appendix,
    )


def _ambiguity_block(bundle: ReportBundle) -> str:
    if not bundle.alias_clusters and not bundle.ambiguities:
        return ""
    parts = ['<div class="ag-section"><h2>Ambiguities and open questions</h2>']
    parts.append(
        '<div class="ag-prose"><p>Everything here is a proposal. None of it has been '
        "applied to the model as fact.</p></div>"
    )
    if bundle.alias_clusters:
        rows = "".join(
            f"<tr><td><b>{_h(cluster.canonical_name)}</b></td>"
            f"<td>{_h(', '.join(cluster.member_labels[:10]))}</td>"
            f"<td>{cluster.confidence:.0%}</td>"
            f"<td>{_h(cluster.rationale)}</td></tr>"
            for cluster in bundle.alias_clusters
        )
        parts.append(
            '<div class="ag-table-wrap"><table class="ag-table">'
            "<caption>Identifiers that may mean the same thing</caption>"
            "<thead><tr><th>Suggested name</th><th>Members</th><th>Confidence</th>"
            f"<th>Reasoning</th></tr></thead><tbody>{rows}</tbody></table></div>"
        )
    if bundle.ambiguities:
        items = "".join(
            f"<li><b>{_h(a.title)}</b> — {_h(a.description)}</li>" for a in bundle.ambiguities
        )
        parts.append(f"<h3>Open questions</h3><ul>{items}</ul>")
    parts.append("</div>")
    return "".join(parts)


def _panel_impact(bundle: ReportBundle) -> str:
    impact = bundle.impact
    if impact is None:
        return _panel(
            "impact",
            '<div class="ag-section"><h2>Scenario impact</h2>'
            '<div class="ag-prose"><p>No scenario was applied. This report describes the '
            "estate exactly as the specifications describe it.</p></div></div>",
        )
    counts = "".join(
        f'<div class="ag-card"><p class="ag-metric">{impact.counts.get(status.value, 0)}</p>'
        f"<h4>{_h(status.value.replace('_', ' ').title())}</h4></div>"
        for status in ImpactStatus
    )
    changes = "".join(f"<li>{_h(change.describe())}</li>" for change in impact.changes)
    rows = "".join(
        f"<tr><td>{_h(item.node_label)}</td><td>{_h(item.node_type)}</td>"
        f"<td>{_h(item.status.value.replace('_', ' '))}</td><td>{item.distance}</td>"
        f"<td>{_h(item.reason)}</td>"
        f"<td>{_h(' → '.join(item.chain_labels[:5]) or '—')}</td></tr>"
        for item in impact.items
        if item.status is not ImpactStatus.UNAFFECTED
    )
    journeys = "".join(
        f"<li><b>{_h(v.journey_name)}</b> — {'broken' if not v.ok else 'degraded'}. "
        f"{_h(v.summary)}</li>"
        for v in impact.affected_journeys
    )
    return _panel(
        "impact",
        '<div class="ag-section"><h2>Scenario impact</h2>'
        '<div class="ag-prose"><p><b>This is a statement about the specification graph, '
        "not a prediction about production.</b> It says what would stop matching the "
        "published contract. It cannot see undocumented consumers, tolerant clients or "
        "traffic.</p></div>"
        f"<h3>Changes made</h3><ul>{changes}</ul>"
        f'<div class="ag-cards">{counts}</div>'
        '<h3>Blast radius</h3><div class="ag-table-wrap"><table class="ag-table">'
        "<thead><tr><th>Thing</th><th>Type</th><th>Status</th><th>Hops</th><th>Why</th>"
        f"<th>Dependency chain</th></tr></thead><tbody>{rows}</tbody></table></div>"
        + (f"<h3>Journeys affected</h3><ul>{journeys}</ul>" if journeys else "")
        + "</div>",
    )


def _panel_method(bundle: ReportBundle) -> str:
    notes = "".join(
        f"<h3>{_h(note.title)}</h3><p>{_h(note.body)}</p>" for note in bundle.methodology
    )
    limits = "".join(f"<li>{_h(item)}</li>" for item in bundle.limitations)
    return _panel(
        "method",
        '<div class="ag-section"><h2>Methodology</h2>'
        f'<div class="ag-prose">{notes}</div></div>'
        '<div class="ag-section"><h2>Limitations</h2>'
        '<div class="ag-prose"><p>What this report cannot tell you:</p>'
        f"<ul>{limits}</ul></div></div>",
    )


def _panel_data(bundle: ReportBundle) -> str:
    """Server-rendered tables: the accessible fallback and the no-JavaScript path."""
    index = bundle.graph.node_index()
    domains = bundle._domain_map()
    node_rows = "".join(
        f"<tr><td>{_h(node.label)}</td><td>{_h(node.type.value)}</td>"
        f"<td>{_h(domains.get(node.id) or '—')}</td>"
        f"<td>{_h(_source_label(node))}</td>"
        f"<td>{_h(node.provenance.explanation)}</td>"
        f"<td><code>{_h(node.id)}</code></td></tr>"
        for node in bundle.graph.nodes
    )
    edge_rows = "".join(
        f"<tr><td>{_h(index[e.source].label if e.source in index else e.source)}</td>"
        f"<td>{_h(e.label or e.type.value)}</td>"
        f"<td>{_h(index[e.target].label if e.target in index else e.target)}</td>"
        f"<td>{_h(e.type.value)}</td>"
        f"<td>{_h(PROVENANCE_GROUPS.get(e.provenance.source_kind, ('fact', 'Unknown'))[1])}</td>"
        f"<td>{_h(truncate(e.provenance.explanation, 160))}</td></tr>"
        for e in bundle.graph.edges
    )
    return _panel(
        "data",
        '<div class="ag-section"><h2>All data</h2>'
        '<div class="ag-prose"><p>The complete contents of this report as plain tables. '
        "This is the screen-reader path and the view that works with JavaScript "
        "disabled.</p></div>"
        '<div class="ag-table-wrap"><table class="ag-table">'
        f"<caption>Nodes ({len(bundle.graph.nodes)})</caption>"
        "<thead><tr><th>Name</th><th>Type</th><th>Domain</th><th>Source</th>"
        f"<th>Why it exists</th><th>Identifier</th></tr></thead><tbody>{node_rows}"
        "</tbody></table></div>"
        '<div class="ag-table-wrap"><table class="ag-table">'
        f"<caption>Relationships ({len(bundle.graph.edges)})</caption>"
        "<thead><tr><th>From</th><th>Relationship</th><th>To</th><th>Kind</th>"
        f"<th>Source</th><th>Why it exists</th></tr></thead><tbody>{edge_rows}"
        "</tbody></table></div></div>",
    )


def _footer(bundle: ReportBundle) -> str:
    return (
        f'<footer class="ag-panel"><p class="ag-footnote">Generated by API Galaxy '
        f"{_h(bundle.app_version)} on {_h(bundle.generated_at_text)} from "
        f"<code>{_h(bundle.spec_fingerprint or 'an unrecorded fingerprint')}</code>. "
        "This file is a read-only snapshot: it contains no live connection to the project "
        "it describes and makes no network requests.</p></footer>"
    )


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def external_references(document: str) -> list[str]:
    """Every construct in ``document`` that would make a browser fetch something.

    This is the invariant the whole format rests on, so it is expressed as code that the
    tests and the API can both call rather than as a comment.

    Note what it deliberately does *not* flag: an ``https://`` that appears as escaped
    text. Imported specifications declare server URLs, and those are shown in the estate
    tables as what they are — text. A URL the browser never resolves is not a request,
    and silently mangling the user's own data to make a grep pass would be dishonest.
    """
    patterns = (
        r"<script[^>]+\ssrc\s*=",
        r"<link[^>]+rel\s*=\s*[\"']?stylesheet",
        r"<(?:img|iframe|embed|object|audio|video|source|track)\b[^>]*\ssrc\s*=",
        r"<use\b[^>]*\shref\s*=",
        r"@import\b",
        r"url\(\s*[\"']?(?:https?:)?//",
        r"(?:src|href|data|action|poster|srcset)\s*=\s*[\"'](?:https?:)?//",
        r"\bfetch\s*\(",
        r"\bXMLHttpRequest\b",
        r"\bWebSocket\b",
        r"\bEventSource\b",
        r"\bsendBeacon\b",
        r"\bimportScripts\b",
    )
    found: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, document, flags=re.IGNORECASE):
            found.append(match.group(0))
    return found


def _h(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _source_label(node: GraphNode) -> str:
    return PROVENANCE_GROUPS.get(node.provenance.source_kind, ("fact", "Unknown"))[1]


def _plural(count: int, noun: str) -> str:
    return noun if count == 1 else f"{noun}s"
