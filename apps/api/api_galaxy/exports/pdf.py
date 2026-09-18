"""The print-ready report: a static HTML document rendered to PDF.

The PDF is a *different document* from the interactive report, not a screenshot of it.
A page has no hover, no zoom and no scroll, so it gets its own markup: a cover page, a
table of contents whose page numbers are resolved by the layout engine, light colours
that survive a laser printer, and page breaks chosen deliberately rather than wherever
the content happened to run out.

Large estates are never drawn as one picture. A hundred and sixty boxes scaled to fit
A4 is a grey smear; instead the overview shows only the structural layer and each domain
gets its own diagram at a readable size.

If WeasyPrint is not installed, :func:`to_pdf` raises :class:`ExportUnavailable` and
:func:`to_pdf_html` stays available so the product can offer the browser's own
"Print to PDF" as a documented fallback. It is never described as interactive.
"""

from __future__ import annotations

import html
from typing import Any

from api_galaxy.contracts.analysis import RiskSeverity
from api_galaxy.contracts.graph import NodeType
from api_galaxy.contracts.scenario import ImpactStatus
from api_galaxy.exports.bundle import ReportBundle, legend_for, scope_bundle
from api_galaxy.exports.diagrams import render_print_svg
from api_galaxy.exports.support import ExportUnavailable, probe_weasyprint, truncate

# Below this many nodes the whole scope fits in one legible picture; above it, the
# report switches to an overview plus one diagram per domain.
SINGLE_DIAGRAM_LIMIT = 46

PAGE_CSS = """
@page {
  size: A4;
  margin: 20mm 16mm 18mm;
  @bottom-center {
    content: "Page " counter(page) " of " counter(pages);
    font: 8.5pt "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #4a5b6e;
  }
  @bottom-right {
    content: string(doctitle);
    font: 8pt "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #6b7a8c;
  }
}
@page :first { margin: 0; @bottom-center { content: ""; } @bottom-right { content: ""; } }

html { font-size: 10.5pt; }
body {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  color: #101820;
  background: #fff;
  line-height: 1.5;
  margin: 0;
}
h1, h2, h3, h4 { color: #0b1620; line-height: 1.25; }
h1 { font-size: 20pt; margin: 0 0 6pt; }
h2 { font-size: 14pt; margin: 0 0 8pt; border-bottom: 0.6pt solid #c9d3de; padding-bottom: 4pt; }
h3 { font-size: 11.5pt; margin: 14pt 0 4pt; }
p { margin: 5pt 0; }
code { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 8.5pt; word-break: break-all; }
a { color: #1b4f91; text-decoration: none; }

.cover {
  height: 297mm;
  padding: 34mm 22mm 20mm;
  background: #0b1620;
  color: #f2f6fa;
  break-after: page;
}
.cover h1 { color: #fff; font-size: 30pt; letter-spacing: -0.5pt; }
.cover .lede { font-size: 12pt; color: #b9c8d8; margin: 4pt 0 18mm; }
.cover dl { margin: 0; font-size: 9.5pt; }
.cover dt { color: #8ca0b6; text-transform: uppercase; letter-spacing: 0.06em; font-size: 7.5pt;
  margin-top: 7pt; }
.cover dd { margin: 1pt 0 0; color: #edf3f8; word-break: break-all; }
.cover .caveat { margin-top: 16mm; font-size: 9pt; color: #b9c8d8; border-left: 2pt solid #4a5b6e;
  padding-left: 8pt; }

.doctitle { string-set: doctitle content(); position: absolute; left: -9999pt; }

section { break-before: page; }
section.flow { break-before: auto; }

nav.toc ol { list-style: none; margin: 0; padding: 0; counter-reset: toc; }
nav.toc li { margin: 4pt 0; border-bottom: 0.4pt dotted #c9d3de; }
nav.toc a { display: block; }
nav.toc a::after { content: target-counter(attr(href), page); float: right; color: #4a5b6e; }
nav.toc .sub { padding-left: 10pt; font-size: 9.5pt; color: #33465a; }

table { border-collapse: collapse; width: 100%; font-size: 8.8pt; margin: 6pt 0 10pt; }
caption { text-align: left; font-size: 8.5pt; color: #4a5b6e; padding-bottom: 3pt; }
th, td { text-align: left; padding: 3.5pt 5pt; border-bottom: 0.4pt solid #d8e0e8;
  vertical-align: top; }
th { background: #eef3f8; color: #33465a; font-weight: 600; }
thead { display: table-header-group; }
tr { break-inside: avoid; }

.cards { display: flex; flex-wrap: wrap; gap: 6pt; margin: 8pt 0 12pt; }
.card { border: 0.6pt solid #c9d3de; border-radius: 4pt; padding: 6pt 9pt; min-width: 88pt;
  break-inside: avoid; }
.card .metric { font-size: 16pt; font-weight: 700; display: block; }
.card .label { font-size: 8pt; color: #4a5b6e; text-transform: uppercase;
  letter-spacing: 0.05em; }

.figure { break-inside: avoid; margin: 8pt 0 12pt; text-align: center; }
.figure svg { max-width: 100%; height: auto; }
.figure figcaption { font-size: 8.5pt; color: #4a5b6e; text-align: left; margin-top: 3pt; }

.legend { border: 0.6pt solid #c9d3de; border-radius: 4pt; padding: 7pt 10pt; margin: 8pt 0 12pt;
  break-inside: avoid; }
.legend ul { list-style: none; margin: 4pt 0 0; padding: 0; }
.legend li { margin: 3pt 0; font-size: 9pt; }
.legend .swatch { display: inline-block; width: 26pt; border-top: 1.4pt solid #1b4f91;
  margin-right: 6pt; vertical-align: middle; }
.legend .swatch.dashed { border-top-style: dashed; border-top-color: #8a5a00; }
.legend .swatch.dotted { border-top-style: dotted; border-top-color: #0f6b4f; }

.callout { border-left: 2.5pt solid #1b4f91; background: #f2f6fb; padding: 6pt 10pt;
  margin: 8pt 0; break-inside: avoid; font-size: 9.5pt; }
.callout.warn { border-left-color: #8c1f4b; background: #fbf2f5; }

.sev-high { color: #8c1f4b; font-weight: 700; }
.sev-medium { color: #8a5a00; font-weight: 700; }
.sev-low { color: #0d5f8a; font-weight: 600; }
.sev-info { color: #4a5b6e; }

.step { break-inside: avoid; margin: 5pt 0; }
.muted { color: #4a5b6e; }
.footnote { font-size: 8.5pt; color: #4a5b6e; }
"""


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------


def to_pdf(bundle: ReportBundle) -> bytes:
    """Render the print document. Raises :class:`ExportUnavailable` without WeasyPrint."""
    reason = probe_weasyprint()
    if reason:
        raise ExportUnavailable(
            reason
            + ". In the meantime, export the print-ready HTML instead and use your "
            "browser's Print to PDF.",
            format_id="pdf",
        )

    from weasyprint import HTML

    document = HTML(string=to_pdf_html(bundle)).render()
    return document.write_pdf()


def to_pdf_html(bundle: ReportBundle) -> str:
    """The print document as HTML.

    Public because it is the documented fallback: a browser's Print to PDF renders this
    the same way WeasyPrint does, page numbers and breaks included.
    """
    sections = [
        _cover(bundle),
        _toc(bundle),
        _section("summary", "1. Executive summary", _summary_body(bundle)),
        _section("map", "2. Estate map", _map_body(bundle)),
        _section("inventory", "3. Estate inventory", _inventory_body(bundle)),
        _section("journeys", "4. End-to-end journeys", _journeys_body(bundle)),
        _section("risks", "5. Findings", _risks_body(bundle)),
    ]
    number = 6
    if bundle.impact is not None:
        sections.append(_section("impact", f"{number}. Scenario impact", _impact_body(bundle)))
        number += 1
    if bundle.alias_clusters or bundle.ambiguities:
        sections.append(
            _section("ambiguity", f"{number}. Ambiguities and inferences", _ambiguity_body(bundle))
        )
        number += 1
    sections.append(_section("method", f"{number}. Methodology", _method_body(bundle)))
    sections.append(_section("limits", f"{number + 1}. Limitations", _limits_body(bundle)))

    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>{_h(bundle.project_name)} — API estate report</title>"
        f"<style>{PAGE_CSS}</style></head><body>"
        f'<div class="doctitle">{_h(bundle.project_name)} — API estate report</div>'
        + "".join(sections)
        + "</body></html>"
    )


# --------------------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------------------


def _cover(bundle: ReportBundle) -> str:
    rows = "".join(
        f"<dt>{_h(key)}</dt><dd>{_h(str(value))}</dd>" for key, value in bundle.disclosure_rows()
    )
    return (
        '<div class="cover">'
        f"<h1>{_h(bundle.project_name)}</h1>"
        '<p class="lede">API estate report — what exists, how it fits together, and how '
        "much of that is fact.</p>"
        f"<dl>{rows}</dl>"
        '<p class="caveat">This document is a static report. Solid connections were stated '
        "by the specifications that were imported; dashed and dotted connections are "
        "inferences or human edits and are labelled as such wherever they appear. Nothing "
        "here is a prediction about production behaviour.</p>"
        "</div>"
    )


TOC_ENTRIES = (
    ("summary", "Executive summary"),
    ("map", "Estate map"),
    ("inventory", "Estate inventory"),
    ("journeys", "End-to-end journeys"),
    ("risks", "Findings"),
    ("impact", "Scenario impact"),
    ("ambiguity", "Ambiguities and inferences"),
    ("method", "Methodology"),
    ("limits", "Limitations"),
)


def _toc(bundle: ReportBundle) -> str:
    present = {"summary", "map", "inventory", "journeys", "risks", "method", "limits"}
    if bundle.impact is not None:
        present.add("impact")
    if bundle.alias_clusters or bundle.ambiguities:
        present.add("ambiguity")
    items = "".join(
        f'<li><a href="#{anchor}">{_h(label)}</a></li>'
        for anchor, label in TOC_ENTRIES
        if anchor in present
    )
    return (
        '<section class="flow" id="toc"><h2>Contents</h2>'
        f'<nav class="toc"><ol>{items}</ol></nav>'
        + _legend_block(bundle)
        + "</section>"
    )


def _legend_block(bundle: ReportBundle) -> str:
    items = "".join(
        f'<li><span class="swatch {_h(entry.stroke)}"></span>'
        f"<b>{_h(entry.label)}</b> — {_h(entry.meaning)}</li>"
        for entry in bundle.legend
    )
    return (
        '<div class="legend"><b>How to read this report</b>'
        f"<ul>{items}</ul></div>"
    )


def _section(anchor: str, heading: str, body: str) -> str:
    return f'<section id="{anchor}"><h2>{_h(heading)}</h2>{body}</section>'


def _summary_body(bundle: ReportBundle) -> str:
    stats = bundle.stats
    cards = (
        ("Services", stats.services),
        ("Operations", stats.operations),
        ("Schemas", stats.schemas),
        ("Fields", stats.fields),
        ("Domains", stats.domains),
        ("Journeys", len(bundle.journeys)),
        ("Findings", len(bundle.risks)),
        ("Inferred links", stats.inferred_edges),
    )
    card_html = "".join(
        f'<div class="card"><span class="metric">{value}</span>'
        f'<span class="label">{_h(label)}</span></div>'
        for label, value in cards
    )
    high = sum(1 for r in bundle.risks if r.severity is RiskSeverity.HIGH)
    scenario = ""
    if bundle.active_scenario:
        scenario = (
            '<div class="callout warn"><b>This report describes a hypothetical estate.</b> '
            f"The scenario “{_h(bundle.active_scenario)}” is applied, so some contracts shown "
            "here do not exist in the specifications that were imported.</div>"
        )
    return (
        f'<div class="cards">{card_html}</div>'
        + scenario
        + f"<p>{_h(bundle.project_name)} is described by {stats.services} service "
        f"specifications exposing {stats.operations} operations over {stats.schemas} schemas "
        f"and {stats.fields} fields. Analysis grouped these into {stats.domains} business "
        f"domains and {len(bundle.journeys)} end-to-end journeys.</p>"
        f"<p>Of {stats.edges} relationships, {stats.observed_edges} are stated directly by the "
        f"specifications and {stats.inferred_edges} are inferred and awaiting review. "
        f"{len(bundle.risks)} findings were raised, {high} of them high severity.</p>"
        f"<p>Semantic analysis was produced by <b>{_h(bundle.provider_disclosure)}</b>. The "
        f"specification fingerprint is <code>{_h(bundle.spec_fingerprint or 'not recorded')}"
        "</code>; regenerating this report from the same documents produces the same graph.</p>"
    )


def _map_body(bundle: ReportBundle) -> str:
    """One picture if the scope is small; otherwise structure first, then per domain."""
    if len(bundle.graph.nodes) <= SINGLE_DIAGRAM_LIMIT:
        svg = render_print_svg(bundle, title=bundle.scope_label, max_nodes=SINGLE_DIAGRAM_LIMIT)
        return _figure(svg, f"{bundle.scope_label} — every node in scope.")

    structural = {
        node.id
        for node in bundle.graph.nodes
        if node.type
        in (NodeType.ESTATE, NodeType.DOMAIN, NodeType.SERVICE, NodeType.JOURNEY)
    }
    parts = [
        "<p>This estate is too large to draw legibly on one page. The first figure shows "
        "the structural layer — domains, services and journeys — and each domain then gets "
        "its own figure at a readable size. The machine-readable exports contain every "
        "node.</p>",
        _figure(
            render_print_svg(
                bundle,
                scope=structural,
                title="Structure — domains, services and journeys",
                max_nodes=60,
            ),
            "Structural overview. Solid lines were stated by a specification; dashed lines "
            "are inferences.",
        ),
    ]
    for domain in sorted(bundle.nodes_of(NodeType.DOMAIN), key=lambda n: n.label.lower()):
        scoped = scope_bundle(bundle, domain_id=domain.id)
        if len(scoped.graph.nodes) <= 1:
            continue
        parts.append(f"<h3>{_h(domain.label)}</h3>")
        entry = legend_for(domain.provenance.source_kind)
        parts.append(
            f'<p class="footnote">{_h(entry.label)} — {_h(domain.provenance.explanation)}</p>'
        )
        parts.append(
            _figure(
                render_print_svg(scoped, title=domain.label, max_nodes=34),
                f"{domain.label} — {len(scoped.graph.nodes)} nodes in this domain, "
                f"showing the most structural of them.",
            )
        )
    return "".join(parts)


def _figure(svg: str, caption: str) -> str:
    return f'<figure class="figure">{svg}<figcaption>{_h(caption)}</figcaption></figure>'


def _inventory_body(bundle: ReportBundle) -> str:
    rows = "".join(
        f"<tr><td>{_h(service.label)}</td>"
        f"<td>{_h(bundle.domain_of(service.id) or '—')}</td>"
        f"<td>{_h(str(service.attrs.get('version') or '—'))}</td>"
        f"<td>{service.attrs.get('operations', 0)}</td>"
        f"<td>{service.attrs.get('schemas', 0)}</td>"
        f"<td><code>{_h(str(service.attrs.get('source_file') or '—'))}</code></td></tr>"
        for service in sorted(bundle.nodes_of(NodeType.SERVICE), key=lambda n: n.label.lower())
    )
    breakdown = "".join(
        f"<tr><td>{_h(name)}</td><td>{count}</td></tr>"
        for name, count in sorted(bundle.stats.by_node_type.items(), key=lambda kv: -kv[1])
    )
    return (
        "<table><caption>Services in scope</caption><thead><tr><th>Service</th><th>Domain</th>"
        "<th>Version</th><th>Operations</th><th>Schemas</th><th>Source file</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        "<h3>What the model contains</h3>"
        "<table><thead><tr><th>Node type</th><th>Count</th></tr></thead>"
        f"<tbody>{breakdown}</tbody></table>"
    )


def _journeys_body(bundle: ReportBundle) -> str:
    if not bundle.journeys:
        return "<p>No journeys were derived for this scope.</p>"
    parts: list[str] = [
        "<p>A journey is a sequence of operations that together deliver something a person "
        "recognises. Each step names the operation that carries it out.</p>"
    ]
    for journey in bundle.journeys:
        entry = legend_for(journey.provenance.source_kind)
        parts.append(f"<h3>{_h(journey.name)}</h3>")
        parts.append(
            f'<p class="footnote">{_h(entry.label)} — {_h(journey.provenance.explanation)}</p>'
        )
        if journey.description:
            parts.append(f"<p>{_h(journey.description)}</p>")
        rows = "".join(
            f"<tr><td>{step.order}</td><td>{_h(step.label)}</td><td>{_h(step.narration)}</td>"
            f"<td><code>{_h(step.operation_id or '—')}</code></td></tr>"
            for step in journey.steps
        )
        parts.append(
            "<table><thead><tr><th>#</th><th>Step</th><th>What happens</th>"
            f"<th>Operation</th></tr></thead><tbody>{rows}</tbody></table>"
        )
    return "".join(parts)


def _risks_body(bundle: ReportBundle) -> str:
    if not bundle.risks:
        return "<p>No findings were raised for this scope.</p>"
    parts = [
        "<p>The <b>Basis</b> column separates rules that prove a problem from rules that "
        "recognise a pattern and may be wrong.</p>"
    ]
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
            f'<tr><td class="sev-{_h(risk.severity.value)}">{_h(risk.severity.value)}</td>'
            f"<td><b>{_h(risk.title)}</b><br>{_h(truncate(risk.description, 400))}</td>"
            f"<td>{_h(risk.label.replace(' finding', ''))}</td>"
            f"<td><code>{_h(risk.rule_id)}</code></td>"
            f"<td>{_h(truncate(risk.recommendation, 300) or '—')}</td></tr>"
            for risk in sorted(group, key=lambda r: (r.rule_id, r.id))
        )
        parts.append(f"<h3>{_h(severity.value.title())} ({len(group)})</h3>")
        parts.append(
            "<table><thead><tr><th>Severity</th><th>Finding</th><th>Basis</th><th>Rule</th>"
            f"<th>What to do</th></tr></thead><tbody>{rows}</tbody></table>"
        )
    return "".join(parts)


def _impact_body(bundle: ReportBundle) -> str:
    impact = bundle.impact
    if impact is None:
        return ""
    changes = "".join(f"<li>{_h(change.describe())}</li>" for change in impact.changes)
    cards = "".join(
        f'<div class="card"><span class="metric">{impact.counts.get(status.value, 0)}</span>'
        f'<span class="label">{_h(status.value.replace("_", " "))}</span></div>'
        for status in ImpactStatus
    )
    rows = "".join(
        f"<tr><td>{_h(item.node_label)}</td><td>{_h(item.node_type)}</td>"
        f"<td>{_h(item.status.value.replace('_', ' '))}</td><td>{item.distance}</td>"
        f"<td>{_h(truncate(item.reason, 180))}</td></tr>"
        for item in impact.items
        if item.status is not ImpactStatus.UNAFFECTED
    )
    journeys = "".join(
        f"<li><b>{_h(v.journey_name)}</b> — {'broken' if not v.ok else 'degraded'}. "
        f"{_h(v.summary)}</li>"
        for v in impact.affected_journeys
    )
    return (
        '<div class="callout warn"><b>This is a statement about the specification graph, not '
        "a prediction about production.</b> It describes what would stop matching the "
        "published contract. It cannot see undocumented consumers, tolerant clients, feature "
        "flags or traffic.</div>"
        f"<h3>Changes made</h3><ul>{changes}</ul>"
        f'<div class="cards">{cards}</div>'
        "<h3>Blast radius</h3>"
        "<table><thead><tr><th>Thing</th><th>Type</th><th>Status</th><th>Hops</th>"
        f"<th>Why</th></tr></thead><tbody>{rows}</tbody></table>"
        + (f"<h3>Journeys affected</h3><ul>{journeys}</ul>" if journeys else "")
    )


def _ambiguity_body(bundle: ReportBundle) -> str:
    parts = [
        '<div class="callout">Everything in this section is a proposal. None of it has been '
        "applied to the model as fact.</div>"
    ]
    if bundle.alias_clusters:
        rows = "".join(
            f"<tr><td><b>{_h(cluster.canonical_name)}</b></td>"
            f"<td>{_h(', '.join(cluster.member_labels[:10]))}</td>"
            f"<td>{cluster.confidence:.0%}</td><td>{_h(cluster.rationale)}</td></tr>"
            for cluster in bundle.alias_clusters
        )
        parts.append(
            "<table><caption>Identifiers that may mean the same thing</caption>"
            "<thead><tr><th>Suggested name</th><th>Members</th><th>Confidence</th>"
            f"<th>Reasoning</th></tr></thead><tbody>{rows}</tbody></table>"
        )
    if bundle.ambiguities:
        items = "".join(
            f"<li><b>{_h(a.title)}</b> — {_h(a.description)}</li>" for a in bundle.ambiguities
        )
        parts.append(f"<h3>Open questions</h3><ul>{items}</ul>")
    return "".join(parts)


def _method_body(bundle: ReportBundle) -> str:
    return "".join(
        f"<h3>{_h(note.title)}</h3><p>{_h(note.body)}</p>" for note in bundle.methodology
    )


def _limits_body(bundle: ReportBundle) -> str:
    items = "".join(f"<li>{_h(item)}</li>" for item in bundle.limitations)
    return (
        "<p>What this report cannot tell you:</p>"
        f"<ul>{items}</ul>"
        f'<p class="footnote">Generated by API Galaxy {_h(bundle.app_version)} on '
        f"{_h(bundle.generated_at_text)} from "
        f"<code>{_h(bundle.spec_fingerprint or 'an unrecorded fingerprint')}</code>.</p>"
    )


def _h(value: Any) -> str:
    return html.escape(str(value), quote=True)
