"""Machine-readable exports: JSON-LD, GraphML and CSV.

These exist so the graph outlives API Galaxy. Someone should be able to load it into
Gephi, a notebook, a triple store or a spreadsheet five years from now without this
codebase. Three properties are therefore non-negotiable:

* **Provenance survives.** Every serialisation carries ``sourceKind``, confidence,
  provider, model and acceptance. A graph that loses the fact-vs-inference boundary on
  the way out is a graph that will be mistaken for ground truth.
* **The vocabulary is declared.** JSON-LD gets a real ``@context`` pointing at a stable
  namespace; GraphML declares a ``<key>`` for every attribute it emits, because readers
  that encounter an undeclared key are entitled to reject the file.
* **Spreadsheets are treated as hostile.** A cell beginning ``=``, ``+``, ``-`` or ``@``
  is a formula in Excel, Sheets and LibreOffice. Node labels come from user-supplied
  specifications, so every cell is neutralised on the way out.
"""

from __future__ import annotations

import csv
import io
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from api_galaxy.contracts.graph import GraphEdge, GraphNode, Provenance
from api_galaxy.exports.bundle import ReportBundle

NAMESPACE = "https://api-galaxy.local/ns#"

# Cells that a spreadsheet would evaluate rather than display. Tab and CR are included
# because they let an attacker break out of a cell in some importers.
_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

JSONLD_CONTEXT: dict[str, Any] = {
    "@vocab": NAMESPACE,
    "ag": NAMESPACE,
    "id": "@id",
    "type": "@type",
    "label": {"@id": "ag:label"},
    "description": {"@id": "ag:description"},
    "projectId": {"@id": "ag:projectId"},
    "nodeType": {"@id": "ag:nodeType"},
    "edgeType": {"@id": "ag:edgeType"},
    "source": {"@id": "ag:source", "@type": "@id"},
    "target": {"@id": "ag:target", "@type": "@id"},
    "acceptance": {"@id": "ag:acceptance"},
    "tags": {"@id": "ag:tag", "@container": "@set"},
    "attributes": {"@id": "ag:attributes"},
    "provenance": {"@id": "ag:provenance"},
    "sourceKind": {"@id": "ag:sourceKind"},
    "explanation": {"@id": "ag:explanation"},
    "sourceFile": {"@id": "ag:sourceFile"},
    "sourcePointer": {"@id": "ag:sourcePointer"},
    "ruleId": {"@id": "ag:ruleId"},
    "confidence": {"@id": "ag:confidence", "@type": "http://www.w3.org/2001/XMLSchema#double"},
    "provider": {"@id": "ag:provider"},
    "model": {"@id": "ag:model"},
    "promptTemplateVersion": {"@id": "ag:promptTemplateVersion"},
    "createdAt": {"@id": "ag:createdAt", "@type": "http://www.w3.org/2001/XMLSchema#dateTime"},
    "updatedAt": {"@id": "ag:updatedAt", "@type": "http://www.w3.org/2001/XMLSchema#dateTime"},
    "evidence": {"@id": "ag:evidence", "@container": "@set"},
    "locator": {"@id": "ag:locator"},
    "pointer": {"@id": "ag:pointer"},
    "excerpt": {"@id": "ag:excerpt"},
    "isFact": {"@id": "ag:isFact", "@type": "http://www.w3.org/2001/XMLSchema#boolean"},
    "severity": {"@id": "ag:severity"},
    "category": {"@id": "ag:category"},
    "heuristic": {"@id": "ag:heuristic"},
    "recommendation": {"@id": "ag:recommendation"},
    "affects": {"@id": "ag:affects", "@container": "@set", "@type": "@id"},
    "steps": {"@id": "ag:step", "@container": "@list"},
    "order": {"@id": "ag:order"},
    "narration": {"@id": "ag:narration"},
}


# --------------------------------------------------------------------------------------
# JSON-LD
# --------------------------------------------------------------------------------------


def to_jsonld(bundle: ReportBundle) -> dict[str, Any]:
    """A linked-data document with every node, edge, risk and journey in ``@graph``.

    ``@id`` values are the graph's own content-derived identifiers, prefixed so they are
    resolvable inside the namespace and unique across object kinds.
    """
    graph_items: list[dict[str, Any]] = [_jsonld_project(bundle)]
    graph_items.extend(_jsonld_node(node) for node in bundle.graph.nodes)
    graph_items.extend(_jsonld_edge(edge) for edge in bundle.graph.edges)
    graph_items.extend(_jsonld_risk(risk) for risk in bundle.risks)
    graph_items.extend(_jsonld_journey(journey) for journey in bundle.journeys)
    graph_items.extend(_jsonld_alias(cluster) for cluster in bundle.alias_clusters)
    if bundle.impact is not None:
        graph_items.append(_jsonld_impact(bundle))
    graph_items.extend(_jsonld_decision(record) for record in bundle.decisions)

    return {
        "@context": JSONLD_CONTEXT,
        "@id": f"urn:api-galaxy:project:{bundle.project_id}",
        "@type": "ag:Report",
        "generatedAt": bundle.generated_at.isoformat(),
        "specFingerprint": bundle.spec_fingerprint,
        "appVersion": bundle.app_version,
        "scope": bundle.scope_label,
        "activeScenario": bundle.active_scenario,
        "providerDisclosure": bundle.provider_disclosure,
        "legend": [entry.model_dump() for entry in bundle.legend],
        "methodology": [note.model_dump() for note in bundle.methodology],
        "limitations": list(bundle.limitations),
        "@graph": graph_items,
    }


def _jsonld_project(bundle: ReportBundle) -> dict[str, Any]:
    return {
        "@id": f"urn:api-galaxy:estate:{bundle.project_id}",
        "@type": "ag:Estate",
        "label": bundle.project_name,
        "projectId": bundle.project_id,
        "attributes": bundle.stats.model_dump(),
    }


def _jsonld_provenance(provenance: Provenance) -> dict[str, Any]:
    return {
        "@type": "ag:Provenance",
        "sourceKind": provenance.source_kind.value,
        "explanation": provenance.explanation,
        "sourceFile": provenance.source_file,
        "sourcePointer": provenance.source_pointer,
        "ruleId": provenance.rule_id,
        "confidence": provenance.confidence,
        "provider": provenance.provider,
        "model": provenance.model,
        "promptTemplateVersion": provenance.prompt_template_version,
        "createdAt": provenance.created_at.isoformat(),
        "updatedAt": provenance.updated_at.isoformat(),
        "isFact": provenance.is_fact,
    }


def _jsonld_evidence(items: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "@id": f"urn:api-galaxy:evidence:{item.id}",
            "@type": "ag:Evidence",
            "sourceFile": item.source_file,
            "pointer": item.pointer,
            "locator": item.locator,
            "label": item.label,
            "excerpt": item.excerpt,
        }
        for item in items
    ]


def _jsonld_node(node: GraphNode) -> dict[str, Any]:
    return {
        "@id": f"urn:api-galaxy:node:{node.id}",
        "@type": f"ag:{node.type.value}",
        "nodeType": node.type.value,
        "label": node.label,
        "description": node.description,
        "projectId": node.project_id,
        "acceptance": node.acceptance.value,
        "tags": list(node.tags),
        "attributes": _jsonable(node.attrs),
        "provenance": _jsonld_provenance(node.provenance),
        "evidence": _jsonld_evidence(node.evidence),
    }


def _jsonld_edge(edge: GraphEdge) -> dict[str, Any]:
    return {
        "@id": f"urn:api-galaxy:edge:{edge.id}",
        "@type": "ag:Relationship",
        "edgeType": edge.type.value,
        "label": edge.label,
        "source": f"urn:api-galaxy:node:{edge.source}",
        "target": f"urn:api-galaxy:node:{edge.target}",
        "acceptance": edge.acceptance.value,
        "attributes": _jsonable(edge.attrs),
        "provenance": _jsonld_provenance(edge.provenance),
        "evidence": _jsonld_evidence(edge.evidence),
    }


def _jsonld_risk(risk: Any) -> dict[str, Any]:
    return {
        "@id": f"urn:api-galaxy:risk:{risk.id}",
        "@type": "ag:Risk",
        "label": risk.title,
        "description": risk.description,
        "severity": risk.severity.value,
        "category": risk.category.value,
        "ruleId": risk.rule_id,
        "heuristic": risk.heuristic,
        "recommendation": risk.recommendation,
        "affects": [f"urn:api-galaxy:node:{nid}" for nid in risk.node_ids],
        "provenance": _jsonld_provenance(risk.provenance),
        "evidence": _jsonld_evidence(risk.evidence),
    }


def _jsonld_journey(journey: Any) -> dict[str, Any]:
    return {
        "@id": f"urn:api-galaxy:journey:{journey.id}",
        "@type": "ag:Journey",
        "label": journey.name,
        "description": journey.description,
        "provenance": _jsonld_provenance(journey.provenance),
        "steps": [
            {
                "@id": f"urn:api-galaxy:journey-step:{step.id}",
                "@type": "ag:JourneyStep",
                "order": step.order,
                "label": step.label,
                "narration": step.narration,
                "affects": [f"urn:api-galaxy:node:{nid}" for nid in step.node_ids],
                "evidence": _jsonld_evidence(step.evidence),
            }
            for step in journey.steps
        ],
    }


def _jsonld_alias(cluster: Any) -> dict[str, Any]:
    return {
        "@id": f"urn:api-galaxy:alias:{cluster.id}",
        "@type": "ag:AliasCluster",
        "label": cluster.canonical_name,
        "description": cluster.rationale,
        "confidence": cluster.confidence,
        "affects": [f"urn:api-galaxy:node:{nid}" for nid in cluster.members],
        "provenance": _jsonld_provenance(cluster.provenance),
    }


def _jsonld_impact(bundle: ReportBundle) -> dict[str, Any]:
    impact = bundle.impact
    assert impact is not None
    return {
        "@id": f"urn:api-galaxy:impact:{impact.scenario_id}",
        "@type": "ag:ImpactReport",
        "label": bundle.active_scenario or impact.scenario_id,
        "attributes": {
            "counts": dict(impact.counts),
            "assumptions": list(impact.assumptions),
            "limitations": list(impact.limitations),
            "changes": [change.describe() for change in impact.changes],
        },
        "affects": [f"urn:api-galaxy:node:{item.node_id}" for item in impact.items],
    }


def _jsonld_decision(record: Any) -> dict[str, Any]:
    return {
        "@id": f"urn:api-galaxy:decision:{record.id}",
        "@type": "ag:DecisionRecord",
        "label": record.action,
        "description": record.subject,
        "provider": record.provider.value if record.provider else None,
        "model": record.model,
        "promptTemplateVersion": record.prompt_template_version,
        "createdAt": record.timestamp,
        "attributes": {
            "task": record.task,
            "editor": record.editor,
            "payloadFingerprint": record.payload_fingerprint,
            "sourceReferences": list(record.source_references),
        },
    }


def _jsonable(value: Any) -> Any:
    """Attrs come from YAML and may hold anything; coerce to JSON-safe primitives."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


# --------------------------------------------------------------------------------------
# GraphML
# --------------------------------------------------------------------------------------

# (key id, target, attribute name, type). Declared up front because a GraphML reader is
# allowed to reject data referencing a key it has not seen.
_NODE_KEYS = (
    ("n_label", "label", "string"),
    ("n_type", "type", "string"),
    ("n_description", "description", "string"),
    ("n_sourceKind", "sourceKind", "string"),
    ("n_acceptance", "acceptance", "string"),
    ("n_confidence", "confidence", "double"),
    ("n_provider", "provider", "string"),
    ("n_model", "model", "string"),
    ("n_explanation", "explanation", "string"),
    ("n_service", "service", "string"),
    ("n_domain", "domain", "string"),
    ("n_isFact", "isFact", "boolean"),
    ("n_evidence", "evidence", "string"),
)

_EDGE_KEYS = (
    ("e_id", "id", "string"),
    ("e_label", "label", "string"),
    ("e_type", "type", "string"),
    ("e_sourceKind", "sourceKind", "string"),
    ("e_acceptance", "acceptance", "string"),
    ("e_confidence", "confidence", "double"),
    ("e_explanation", "explanation", "string"),
    ("e_isFact", "isFact", "boolean"),
    ("e_stroke", "stroke", "string"),
)


def to_graphml(bundle: ReportBundle) -> str:
    """GraphML that opens in Gephi, yEd and Cytoscape and round-trips through NetworkX."""
    domains = bundle._domain_map()
    out: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns '
        'http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">',
        f"<!-- {escape(_graphml_banner(bundle))} -->",
    ]
    for key_id, name, kind in _NODE_KEYS:
        out.append(
            f'<key id="{key_id}" for="node" attr.name="{name}" attr.type="{kind}"/>'
        )
    for key_id, name, kind in _EDGE_KEYS:
        out.append(f'<key id="{key_id}" for="edge" attr.name="{name}" attr.type="{kind}"/>')

    out.append(f'<graph id={quoteattr(bundle.project_id)} edgedefault="directed">')
    for node in bundle.graph.nodes:
        out.append(f"<node id={quoteattr(node.id)}>")
        out.extend(
            _graphml_data(key, value)
            for key, value in (
                ("n_label", node.label),
                ("n_type", node.type.value),
                ("n_description", node.description),
                ("n_sourceKind", node.provenance.source_kind.value),
                ("n_acceptance", node.acceptance.value),
                ("n_confidence", node.provenance.confidence),
                ("n_provider", node.provenance.provider),
                ("n_model", node.provenance.model),
                ("n_explanation", node.provenance.explanation),
                ("n_service", node.attrs.get("service") or node.attrs.get("slug")),
                ("n_domain", domains.get(node.id)),
                ("n_isFact", node.is_fact),
                ("n_evidence", "; ".join(ev.locator for ev in node.evidence[:4])),
            )
            if value is not None and value != ""
        )
        out.append("</node>")

    node_ids = bundle.graph.node_ids()
    for edge in bundle.graph.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            continue
        out.append(
            f"<edge id={quoteattr(edge.id)} source={quoteattr(edge.source)} "
            f"target={quoteattr(edge.target)}>"
        )
        out.extend(
            _graphml_data(key, value)
            for key, value in (
                ("e_id", edge.id),
                ("e_label", edge.label or edge.type.value),
                ("e_type", edge.type.value),
                ("e_sourceKind", edge.provenance.source_kind.value),
                ("e_acceptance", edge.acceptance.value),
                ("e_confidence", edge.provenance.confidence),
                ("e_explanation", edge.provenance.explanation),
                ("e_isFact", edge.is_fact),
                ("e_stroke", edge.stroke),
            )
            if value is not None and value != ""
        )
        out.append("</edge>")

    out.append("</graph>")
    out.append("</graphml>")
    return "\n".join(out)


def _graphml_banner(bundle: ReportBundle) -> str:
    return (
        f"API Galaxy {bundle.app_version} · {bundle.project_name} · {bundle.scope_label} · "
        f"generated {bundle.generated_at_text} · fingerprint {bundle.spec_fingerprint} · "
        f"semantic analysis by {bundle.provider_disclosure}"
    )


def _graphml_data(key: str, value: Any) -> str:
    if isinstance(value, bool):
        rendered = "true" if value else "false"
    else:
        rendered = str(value)
    return f'<data key="{key}">{escape(rendered)}</data>'


# --------------------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------------------


def sanitise_cell(value: Any) -> str:
    """Neutralise spreadsheet formula injection without mangling legitimate text.

    A leading apostrophe is the conventional escape: Excel, Sheets and LibreOffice all
    display the original text and refuse to evaluate it.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    raw = str(value)
    # The dangerous-prefix check runs on the original string, before newlines and tabs
    # are flattened to spaces — otherwise a value starting with a tab would look
    # harmless by the time it is inspected.
    dangerous = raw.startswith(_INJECTION_PREFIXES)
    text = raw.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return "'" + text if dangerous else text


def to_csv_bundle(bundle: ReportBundle) -> dict[str, str]:
    """Six CSVs keyed by filename. Every cell passes through :func:`sanitise_cell`."""
    domains = bundle._domain_map()
    index = bundle.graph.node_index()

    nodes = _csv(
        [
            "id",
            "type",
            "label",
            "description",
            "domain",
            "service",
            "source_kind",
            "is_fact",
            "acceptance",
            "confidence",
            "provider",
            "model",
            "explanation",
            "evidence",
            "tags",
        ],
        (
            [
                node.id,
                node.type.value,
                node.label,
                node.description,
                domains.get(node.id),
                node.attrs.get("service") or node.attrs.get("slug"),
                node.provenance.source_kind.value,
                node.is_fact,
                node.acceptance.value,
                node.provenance.confidence,
                node.provenance.provider,
                node.provenance.model,
                node.provenance.explanation,
                "; ".join(ev.locator for ev in node.evidence[:4]),
                "; ".join(node.tags),
            ]
            for node in bundle.graph.nodes
        ),
    )

    edges = _csv(
        [
            "id",
            "type",
            "source_id",
            "source_label",
            "target_id",
            "target_label",
            "label",
            "source_kind",
            "is_fact",
            "acceptance",
            "confidence",
            "stroke",
            "explanation",
        ],
        (
            [
                edge.id,
                edge.type.value,
                edge.source,
                index[edge.source].label if edge.source in index else "",
                edge.target,
                index[edge.target].label if edge.target in index else "",
                edge.label,
                edge.provenance.source_kind.value,
                edge.is_fact,
                edge.acceptance.value,
                edge.provenance.confidence,
                edge.stroke,
                edge.provenance.explanation,
            ]
            for edge in bundle.graph.edges
        ),
    )

    risks = _csv(
        [
            "id",
            "severity",
            "category",
            "rule_id",
            "finding_kind",
            "title",
            "description",
            "recommendation",
            "affected_nodes",
            "evidence",
        ],
        (
            [
                risk.id,
                risk.severity.value,
                risk.category.value,
                risk.rule_id,
                risk.label,
                risk.title,
                risk.description,
                risk.recommendation,
                "; ".join(risk.node_ids[:12]),
                "; ".join(ev.locator for ev in risk.evidence[:4]),
            ]
            for risk in bundle.risks
        ),
    )

    journeys = _csv(
        ["journey_id", "journey", "step_order", "step", "narration", "service", "operation",
         "source_kind", "evidence"],
        (
            [
                journey.id,
                journey.name,
                step.order,
                step.label,
                step.narration,
                step.service_id,
                step.operation_id,
                journey.provenance.source_kind.value,
                "; ".join(ev.locator for ev in step.evidence[:3]),
            ]
            for journey in bundle.journeys
            for step in journey.steps
        ),
    )

    decisions = _csv(
        ["id", "timestamp", "task", "action", "subject", "provider", "model",
         "prompt_template_version", "editor", "payload_fingerprint"],
        (
            [
                record.id,
                record.timestamp,
                record.task,
                record.action,
                record.subject,
                record.provider.value if record.provider else "",
                record.model,
                record.prompt_template_version,
                record.editor,
                record.payload_fingerprint,
            ]
            for record in bundle.decisions
        ),
    )

    metadata = _csv(
        ["key", "value"],
        [
            [key, value]
            for key, value in [
                *bundle.disclosure_rows(),
                ("Nodes", bundle.stats.nodes),
                ("Relationships", bundle.stats.edges),
                ("Specification-derived relationships", bundle.stats.observed_edges),
                ("Inferred relationships", bundle.stats.inferred_edges),
                ("Risks", len(bundle.risks)),
                ("Journeys", len(bundle.journeys)),
            ]
        ],
    )

    return {
        "metadata.csv": metadata,
        "nodes.csv": nodes,
        "edges.csv": edges,
        "risks.csv": risks,
        "journeys.csv": journeys,
        "decisions.csv": decisions,
    }


def _csv(header: list[str], rows: Any) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([sanitise_cell(cell) for cell in row])
    return buffer.getvalue()
