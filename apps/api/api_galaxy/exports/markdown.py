"""A Markdown technical report, written for a repository or a Confluence page.

The shape follows how the document actually gets read: someone opens it to answer a
question, so the disclosure block (what was analysed, when, by what, and how much of it
is inference) comes before anything they might quote. Mermaid blocks are used instead of
images because GitHub, GitLab and Confluence render them inline and a reviewer can edit
them in the pull request.
"""

from __future__ import annotations

from api_galaxy.contracts.analysis import RiskSeverity
from api_galaxy.contracts.graph import NodeType
from api_galaxy.contracts.scenario import ImpactStatus
from api_galaxy.exports.bundle import ReportBundle, legend_for
from api_galaxy.exports.diagrams import render_journey_mermaid, render_mermaid
from api_galaxy.exports.support import truncate

SEVERITY_ORDER = (
    RiskSeverity.HIGH,
    RiskSeverity.MEDIUM,
    RiskSeverity.LOW,
    RiskSeverity.INFO,
)


def to_markdown(bundle: ReportBundle, *, include_diagrams: bool = True) -> str:
    sections: list[str] = [
        _title(bundle),
        _disclosure(bundle),
        _summary(bundle),
        _inventory(bundle),
        _domains(bundle),
        _journeys(bundle, include_diagrams=include_diagrams),
        _risks(bundle),
        _ambiguity_appendix(bundle),
    ]
    if include_diagrams:
        sections.insert(5, _estate_diagram(bundle))
    if bundle.impact is not None:
        sections.append(_impact(bundle))
    if bundle.repairs:
        sections.append(_repairs(bundle))
    if bundle.arena is not None:
        sections.append(_arena(bundle))
    if bundle.decisions:
        sections.append(_decisions(bundle))
    sections.append(_methodology(bundle))
    sections.append(_limitations(bundle))
    return "\n\n".join(part for part in sections if part).rstrip() + "\n"


# --------------------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------------------


def _title(bundle: ReportBundle) -> str:
    return f"# {_esc(bundle.project_name)} — API estate report"


def _disclosure(bundle: ReportBundle) -> str:
    rows = "\n".join(f"| {_esc(key)} | {_esc(str(value))} |" for key, value in
                     bundle.disclosure_rows())
    legend_rows = "\n".join(
        f"| `{_esc(entry.stroke)}` | {_esc(entry.label)} | {_esc(entry.meaning)} |"
        for entry in bundle.legend
    )
    return (
        "## About this report\n\n"
        "| | |\n| --- | --- |\n"
        f"{rows}\n\n"
        "### Fact vs inference legend\n\n"
        "Everything below is labelled with where it came from. Nothing in this report is "
        "presented as a fact unless a specification said so.\n\n"
        "| Line style | Means | How to read it |\n| --- | --- | --- |\n"
        f"{legend_rows}"
    )


def _summary(bundle: ReportBundle) -> str:
    stats = bundle.stats
    total_relationships = max(1, stats.edges)
    inferred_share = round(100 * stats.inferred_edges / total_relationships)
    high = sum(1 for r in bundle.risks if r.severity is RiskSeverity.HIGH)
    heuristic = sum(1 for r in bundle.risks if r.heuristic)

    lines = [
        "## Executive summary",
        "",
        f"{_esc(bundle.project_name)} is described by {stats.services} "
        f"{_plural(stats.services, 'service specification')} exposing {stats.operations} "
        f"{_plural(stats.operations, 'operation')} over {stats.schemas} "
        f"{_plural(stats.schemas, 'schema')} and {stats.fields} "
        f"{_plural(stats.fields, 'field')}. These were grouped into {stats.domains} "
        f"business {_plural(stats.domains, 'domain')} and {len(bundle.journeys)} "
        f"end-to-end {_plural(len(bundle.journeys), 'journey')}.",
        "",
        f"Of {stats.edges} relationships in the model, {stats.observed_edges} are stated "
        f"directly by the specifications and {stats.inferred_edges} ({inferred_share}%) are "
        f"inferred and awaiting review.",
        "",
        f"{len(bundle.risks)} {_plural(len(bundle.risks), 'finding')} were raised, "
        f"{high} of them high severity. {heuristic} of the findings are heuristic — a rule "
        "recognised a pattern rather than proving a problem — and are marked as such in the "
        "table below.",
    ]
    if bundle.alias_clusters:
        lines += [
            "",
            f"{len(bundle.alias_clusters)} groups of differently-spelled identifiers appear to "
            "mean the same thing. They are listed in the appendix with the reasoning behind "
            "each suggestion.",
        ]
    if bundle.active_scenario:
        lines += [
            "",
            f"This report was generated with the scenario **{_esc(bundle.active_scenario)}** "
            "applied. It describes a hypothetical estate, not the one you imported.",
        ]
    return "\n".join(lines)


def _inventory(bundle: ReportBundle) -> str:
    rows: list[str] = []
    for service in sorted(bundle.nodes_of(NodeType.SERVICE), key=lambda n: n.label.lower()):
        attrs = service.attrs
        rows.append(
            "| {label} | {domain} | {version} | {ops} | {schemas} | {source} |".format(
                label=_esc(service.label),
                domain=_esc(bundle.domain_of(service.id) or "—"),
                version=_esc(str(attrs.get("version") or "—")),
                ops=attrs.get("operations", 0),
                schemas=attrs.get("schemas", 0),
                source=f"`{_esc(str(attrs.get('source_file') or '—'))}`",
            )
        )
    counts = bundle.stats.by_node_type
    breakdown = ", ".join(
        f"{count} {_esc(name)}" for name, count in sorted(counts.items(), key=lambda kv: -kv[1])
    )
    return (
        "## Estate inventory\n\n"
        "| Service | Domain | Version | Operations | Schemas | Source file |\n"
        "| --- | --- | --- | ---: | ---: | --- |\n" + "\n".join(rows) + "\n\n"
        f"Node types in the model: {breakdown}."
    )


def _domains(bundle: ReportBundle) -> str:
    domain_nodes = sorted(bundle.nodes_of(NodeType.DOMAIN), key=lambda n: n.label.lower())
    if not domain_nodes:
        return ""
    lines = [
        "## Business domains",
        "",
        "Domains group services by what part of the business they serve. Where a "
        "specification declared its own domain that is a fact; where one was proposed by "
        "analysis it is marked as an inference.",
        "",
    ]
    membership = bundle._domain_map()
    for domain in domain_nodes:
        entry = legend_for(domain.provenance.source_kind)
        members = sorted(
            {
                bundle.graph.get(node_id).label
                for node_id, label in membership.items()
                if label == domain.label
                and bundle.graph.get(node_id) is not None
                and bundle.graph.get(node_id).type is NodeType.SERVICE
            }
        )
        lines.append(f"### {_esc(domain.label)}")
        lines.append("")
        lines.append(f"*{_esc(entry.label)} — {_esc(domain.provenance.explanation)}*")
        lines.append("")
        if domain.description:
            lines.append(_esc(domain.description))
            lines.append("")
        lines.append(f"Services: {', '.join(_esc(m) for m in members) or 'none recorded'}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _estate_diagram(bundle: ReportBundle) -> str:
    return (
        "## Estate map\n\n"
        "Solid arrows are relationships the specifications stated. Dotted arrows are "
        "inferences that a person should confirm.\n\n"
        "```mermaid\n" + render_mermaid(bundle) + "\n```"
    )


def _journeys(bundle: ReportBundle, *, include_diagrams: bool) -> str:
    if not bundle.journeys:
        return ""
    lines = ["## End-to-end journeys", ""]
    for journey in bundle.journeys:
        entry = legend_for(journey.provenance.source_kind)
        lines.append(f"### {_esc(journey.name)}")
        lines.append("")
        lines.append(f"*{_esc(entry.label)} — {_esc(journey.provenance.explanation)}*")
        lines.append("")
        if journey.description:
            lines.append(_esc(journey.description))
            lines.append("")
        if include_diagrams:
            lines.append("```mermaid")
            lines.append(render_journey_mermaid(journey))
            lines.append("```")
            lines.append("")
        lines.append("| # | Step | What happens | Operation |")
        lines.append("| ---: | --- | --- | --- |")
        for step in journey.steps:
            lines.append(
                f"| {step.order} | {_esc(step.label)} | {_esc(step.narration)} | "
                f"`{_esc(step.operation_id or '—')}` |"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def _risks(bundle: ReportBundle) -> str:
    if not bundle.risks:
        return "## Findings\n\nNo findings were raised for this scope."
    lines = [
        "## Findings",
        "",
        "Grouped by severity. The *Basis* column separates rules that prove a problem "
        "from rules that recognise a pattern and may be wrong.",
        "",
    ]
    for severity in SEVERITY_ORDER:
        group = [r for r in bundle.risks if r.severity is severity]
        if not group:
            continue
        lines.append(f"### {severity.value.title()} ({len(group)})")
        lines.append("")
        lines.append("| Finding | Basis | Rule | What to do | Affects |")
        lines.append("| --- | --- | --- | --- | ---: |")
        for risk in sorted(group, key=lambda r: (r.rule_id, r.id)):
            lines.append(
                f"| **{_esc(risk.title)}**<br>{_esc(truncate(risk.description, 240))} "
                f"| {_esc(risk.label.replace(' finding', ''))} | `{_esc(risk.rule_id)}` "
                f"| {_esc(truncate(risk.recommendation, 200)) or '—'} "
                f"| {len(risk.node_ids)} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def _ambiguity_appendix(bundle: ReportBundle) -> str:
    if not bundle.ambiguities and not bundle.alias_clusters:
        return ""
    lines = [
        "## Appendix — ambiguities and inferences",
        "",
        "Everything in this section is a proposal. None of it has been applied to the "
        "model as fact.",
        "",
    ]
    if bundle.alias_clusters:
        lines.append("### Identifiers that may mean the same thing")
        lines.append("")
        lines.append("| Suggested canonical name | Members | Confidence | Reasoning |")
        lines.append("| --- | --- | ---: | --- |")
        for cluster in bundle.alias_clusters:
            members = ", ".join(f"`{_esc(m)}`" for m in cluster.member_labels[:8])
            extra = "" if len(cluster.member_labels) <= 8 else f" +{len(cluster.member_labels) - 8}"
            lines.append(
                f"| **{_esc(cluster.canonical_name)}** | {members}{extra} "
                f"| {cluster.confidence:.0%} | {_esc(truncate(cluster.rationale, 220))} |"
            )
        lines.append("")
    if bundle.ambiguities:
        lines.append("### Open questions")
        lines.append("")
        for ambiguity in bundle.ambiguities:
            entry = legend_for(ambiguity.provenance.source_kind)
            lines.append(f"- **{_esc(ambiguity.title)}** ({_esc(entry.label)}) — "
                         f"{_esc(ambiguity.description)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _impact(bundle: ReportBundle) -> str:
    impact = bundle.impact
    if impact is None:
        return ""
    lines = [
        "## Scenario impact",
        "",
        f"Scenario: **{_esc(bundle.active_scenario or impact.scenario_id)}**",
        "",
        "This is a statement about the specification graph, not a prediction about "
        "production. It says what would stop matching the published contract.",
        "",
        "### Changes made",
        "",
    ]
    for change in impact.changes:
        lines.append(f"- {_esc(change.describe())}")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("| --- | ---: |")
    for status in ImpactStatus:
        lines.append(f"| {status.value.replace('_', ' ').title()} "
                     f"| {impact.counts.get(status.value, 0)} |")
    lines.append("")

    ranked = [i for i in impact.items if i.status is not ImpactStatus.UNAFFECTED][:40]
    if ranked:
        lines.append("### Blast radius")
        lines.append("")
        lines.append("| Thing | Type | Status | Hops | Why | Dependency chain |")
        lines.append("| --- | --- | --- | ---: | --- | --- |")
        for item in ranked:
            chain = " → ".join(_esc(label) for label in item.chain_labels[:5]) or "—"
            lines.append(
                f"| {_esc(item.node_label)} | {_esc(item.node_type)} "
                f"| {_esc(item.status.value.replace('_', ' '))} | {item.distance} "
                f"| {_esc(truncate(item.reason, 160))} | {chain} |"
            )
        lines.append("")
    if impact.affected_journeys:
        lines.append("### Journeys affected")
        lines.append("")
        for validation in impact.affected_journeys:
            state = "broken" if not validation.ok else "degraded"
            lines.append(f"- **{_esc(validation.journey_name)}** — {state}. "
                         f"{_esc(validation.summary)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _repairs(bundle: ReportBundle) -> str:
    lines = ["## Suggested repairs", ""]
    for repair in bundle.repairs:
        basis = "Deterministic" if repair.deterministic else "Suggested by a model"
        lines.append(f"### {_esc(repair.title)}")
        lines.append("")
        lines.append(f"*{basis} · status {_esc(repair.status.value)}* — {_esc(repair.rationale)}")
        lines.append("")
        if repair.patch:
            lines.append("```diff")
            lines.extend(_esc_raw(line) for line in repair.patch)
            lines.append("```")
            lines.append("")
        for index, step in enumerate(repair.migration_steps, start=1):
            lines.append(f"{index}. {_esc(step)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _arena(bundle: ReportBundle) -> str:
    arena = bundle.arena
    if arena is None:
        return ""
    lines = [
        "## Model comparison",
        "",
        "Two providers were asked the same bounded question over the same graph context. "
        "Agreement is not correctness — it means two models made the same guess.",
        "",
        "| Provider | Model | OK | Latency (ms) | Valid JSON | Entities | Relations | "
        "Invented references |",
        "| --- | --- | --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for metric in arena.metrics:
        lines.append(
            f"| {_esc(metric.provider.value)} | {_esc(metric.model or '—')} "
            f"| {'yes' if metric.ok else 'no'} | {metric.latency_ms:.0f} "
            f"| {'yes' if metric.valid_structured_output else 'no'} | {metric.entities} "
            f"| {metric.relations} | {metric.hallucinated_references} |"
        )
    lines.append("")
    lines.append(
        f"Consensus relationships: {len(arena.consensus)} · only provider A: "
        f"{len(arena.only_a)} · only provider B: {len(arena.only_b)} · conflicting: "
        f"{len(arena.conflicts)}."
    )
    for note in arena.notes:
        lines.append(f"- {_esc(note)}")
    return "\n".join(lines).rstrip()


def _decisions(bundle: ReportBundle) -> str:
    lines = [
        "## Decision log",
        "",
        "Every accepted or rejected inference, recorded once and never edited.",
        "",
        "| When | Task | Action | Subject | Provider | Model | Fingerprint |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in bundle.decisions:
        lines.append(
            f"| {_esc(record.timestamp)} | {_esc(record.task)} | {_esc(record.action)} "
            f"| {_esc(truncate(record.subject, 60))} "
            f"| {_esc(record.provider.value if record.provider else '—')} "
            f"| {_esc(record.model or '—')} | `{_esc(record.payload_fingerprint[:16] or '—')}` |"
        )
    return "\n".join(lines)


def _methodology(bundle: ReportBundle) -> str:
    lines = ["## Methodology", ""]
    for note in bundle.methodology:
        lines.append(f"### {_esc(note.title)}")
        lines.append("")
        lines.append(_esc(note.body))
        lines.append("")
    return "\n".join(lines).rstrip()


def _limitations(bundle: ReportBundle) -> str:
    lines = ["## Limitations", "", "What this report cannot tell you:", ""]
    lines.extend(f"- {_esc(item)}" for item in bundle.limitations)
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _esc(value: str) -> str:
    """Neutralise the Markdown characters that would break a table cell or inject HTML."""
    text = " ".join(str(value).split())
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _esc_raw(value: str) -> str:
    """Inside a fenced block only the fence itself is dangerous."""
    return str(value).replace("```", "'''")


def _plural(count: int, noun: str) -> str:
    return noun if count == 1 else f"{noun}s"
