"""Bundled Demo Analysis.

The zero-setup promise is that *Explore the Demo Galaxy* is impressive with no Ollama, no
API key and no network. That means the semantic layer for NovaCart — business entities,
capabilities, curated journeys and the one relationship that is only inferable — has to
ship with the product.

It is loaded from ``samples/novacart/expected-*.json`` and labelled **Bundled Demo
Analysis** everywhere it appears. It is not presented as a model output and it is not
presented as a specification fact: it is a third, clearly-named provenance. If a provider
is configured, the user can regenerate the same layer and compare the two.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api_galaxy.contracts.analysis import Journey, JourneyStep
from api_galaxy.contracts.graph import (
    Acceptance,
    EdgeType,
    Evidence,
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    NodeType,
    Provenance,
    SourceKind,
)
from api_galaxy.contracts.ids import (
    capability_id,
    edge_id,
    entity_id,
    evidence_id,
    journey_id,
    journey_step_id,
    operation_id,
    schema_id,
    service_id,
    slugify,
)
from api_galaxy.parsing.normalize import NormalizedEstate

BUNDLED_LABEL = "Bundled Demo Analysis"


@dataclass
class BundledAnalysis:
    entities: list[dict[str, Any]] = field(default_factory=list)
    capabilities: list[dict[str, Any]] = field(default_factory=list)
    domains: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    journeys: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    source: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.entities or self.capabilities or self.journeys or self.relationships)


def load_bundled_analysis(directory: str | Path) -> BundledAnalysis:
    """Read the reference ontology and journeys shipped next to a sample estate."""
    root = Path(directory)
    ontology_path = root / "expected-ontology.json"
    journeys_path = root / "expected-journeys.json"
    if not ontology_path.is_file():
        return BundledAnalysis()

    ontology = json.loads(ontology_path.read_text(encoding="utf-8"))
    journeys: list[dict[str, Any]] = []
    if journeys_path.is_file():
        loaded = json.loads(journeys_path.read_text(encoding="utf-8"))
        journeys = loaded if isinstance(loaded, list) else loaded.get("journeys", [])

    notes = ontology.get("notes") or []
    if isinstance(notes, dict):
        notes = [f"{k}: {v}" for k, v in notes.items()]

    return BundledAnalysis(
        entities=ontology.get("business_entities") or [],
        capabilities=ontology.get("capabilities") or [],
        domains=ontology.get("domains") or [],
        relationships=ontology.get("relationships") or [],
        journeys=journeys,
        notes=[str(n) for n in notes],
        source=str(ontology_path.name),
    )


def _prov(explanation: str, confidence: float = 0.85) -> Provenance:
    return Provenance(
        source_kind=SourceKind.BUNDLED_ANALYSIS,
        explanation=explanation,
        confidence=confidence,
        provider=BUNDLED_LABEL,
        model="precomputed",
    )


def _operation_index(estate: NormalizedEstate) -> dict[str, str]:
    """Map ``service:operationId`` and bare ``operationId`` to graph node IDs."""
    index: dict[str, str] = {}
    for service in estate.services:
        for op in service.operations:
            node_id = operation_id(service.name, op.method, op.path)
            index.setdefault(f"{service.slug}:{op.operation_id}", node_id)
            index.setdefault(f"{service.name}:{op.operation_id}", node_id)
            index.setdefault(op.operation_id, node_id)
    return index


def apply_bundled_analysis(
    graph: KnowledgeGraph,
    estate: NormalizedEstate,
    bundle: BundledAnalysis,
) -> tuple[list[Journey], list[str]]:
    """Add the semantic layer to ``graph``. Returns (curated journeys, warnings).

    Every reference in the bundle is resolved against nodes that already exist. Anything
    that does not resolve is reported as a warning rather than silently creating a node —
    the same discipline applied to model output.
    """
    warnings: list[str] = []
    ops = _operation_index(estate)

    # --- business entities --------------------------------------------------------
    for raw in bundle.entities:
        name = str(raw.get("name") or "")
        if not name:
            continue
        eid = str(raw.get("id") or entity_id(name))
        graph.add_node(
            GraphNode(
                id=eid,
                type=NodeType.BUSINESS_ENTITY,
                label=name,
                project_id=graph.project_id,
                description=str(raw.get("description") or ""),
                acceptance=Acceptance.PROPOSED,
                provenance=_prov(
                    f"'{name}' was identified as a business entity by the bundled analysis."
                ),
                attrs={
                    "aliases": raw.get("aliases") or [],
                    "pii": bool(raw.get("pii")),
                    "owning_domain": raw.get("owning_domain"),
                    "analysis": BUNDLED_LABEL,
                },
            )
        )
        owning = str(raw.get("owning_domain") or "")
        if owning and graph.get(owning) is not None:
            _edge(graph, EdgeType.BELONGS_TO_DOMAIN, eid, owning,
                  f"{name} is owned by the {graph.get(owning).label} domain.")
        for target in raw.get("represented_by") or []:
            target_id = str(target)
            if graph.get(target_id) is None:
                warnings.append(f"entity '{name}' references unknown node '{target_id}'")
                continue
            _edge(
                graph,
                EdgeType.REPRESENTS,
                target_id,
                eid,
                f"{graph.get(target_id).label} is one representation of the {name} entity.",
            )

    # --- capabilities -------------------------------------------------------------
    for raw in bundle.capabilities:
        name = str(raw.get("name") or "")
        if not name:
            continue
        cid = str(raw.get("id") or capability_id(name))
        graph.add_node(
            GraphNode(
                id=cid,
                type=NodeType.CAPABILITY,
                label=name,
                project_id=graph.project_id,
                description=str(raw.get("description") or ""),
                acceptance=Acceptance.PROPOSED,
                provenance=_prov(f"'{name}' was identified as a business capability."),
                attrs={"analysis": BUNDLED_LABEL, "domain": raw.get("domain")},
            )
        )
        domain = str(raw.get("domain") or "")
        if domain and graph.get(domain) is not None:
            _edge(graph, EdgeType.BELONGS_TO_DOMAIN, cid, domain,
                  f"{name} sits in the {graph.get(domain).label} domain.")
        for reference in raw.get("operations") or []:
            node_id = ops.get(str(reference))
            if node_id is None or graph.get(node_id) is None:
                warnings.append(f"capability '{name}' references unknown operation '{reference}'")
                continue
            _edge(graph, EdgeType.CONTAINS, cid, node_id,
                  f"{graph.get(node_id).label} delivers part of '{name}'.")

    # --- relationships ------------------------------------------------------------
    for raw in bundle.relationships:
        source = _resolve_reference(graph, ops, str(raw.get("source") or ""))
        target = _resolve_reference(graph, ops, str(raw.get("target") or ""))
        if source is None or target is None:
            warnings.append(f"relationship {raw.get('source')} → {raw.get('target')} did not resolve")
            continue
        kind = str(raw.get("kind") or "inferable").lower()
        if kind == "explicit":
            # Already present as a specification fact; do not duplicate it as an inference.
            continue
        relation = str(raw.get("type") or "DEPENDS_ON").upper()
        edge_type = (
            EdgeType[relation] if relation in EdgeType.__members__ else EdgeType.INFERRED_RELATION
        )
        _edge(
            graph,
            edge_type,
            source,
            target,
            str(raw.get("rationale") or raw.get("reason") or
                "Suggested by the bundled analysis; there is no declared link in the specification."),
            acceptance=Acceptance.PROPOSED,
            attrs={"inferable_only": True, "analysis": BUNDLED_LABEL},
        )

    # --- curated journeys ---------------------------------------------------------
    journeys = _build_journeys(graph, estate, bundle, ops, warnings)
    return journeys, warnings


def _build_journeys(
    graph: KnowledgeGraph,
    estate: NormalizedEstate,
    bundle: BundledAnalysis,
    ops: dict[str, str],
    warnings: list[str],
) -> list[Journey]:
    journeys: list[Journey] = []
    for raw in bundle.journeys:
        name = str(raw.get("name") or "")
        if not name:
            continue
        jid = str(raw.get("id") or journey_id(name))
        steps: list[JourneyStep] = []
        for index, raw_step in enumerate(raw.get("steps") or [], start=1):
            service_hint = str(raw_step.get("service") or "")
            op_key = f"{slugify(service_hint)}:{raw_step.get('operationId')}"
            node_id = ops.get(op_key) or ops.get(str(raw_step.get("operationId")))
            if node_id is None or graph.get(node_id) is None:
                warnings.append(
                    f"journey '{name}' step {index} references unknown operation "
                    f"'{raw_step.get('operationId')}'"
                )
                continue
            op_node = graph.get(node_id)
            schema_ids = sorted(
                {
                    e.target
                    for e in graph.edges
                    if e.source == node_id
                    and e.type in (EdgeType.USES_REQUEST, EdgeType.RETURNS)
                    and graph.get(e.target) is not None
                }
            )
            svc_id = service_id(service_hint) if service_hint else None
            order = int(raw_step.get("order") or index)
            steps.append(
                JourneyStep(
                    id=journey_step_id(jid, order),
                    order=order,
                    label=str(raw_step.get("label") or op_node.attrs.get("summary") or op_node.label),
                    narration=str(raw_step.get("narration") or ""),
                    service_id=svc_id,
                    operation_id=node_id,
                    schema_ids=schema_ids,
                    node_ids=[node_id, *( [svc_id] if svc_id else [] ), *schema_ids],
                    technical_detail=str(
                        raw_step.get("technical_detail")
                        or f"{op_node.attrs.get('method')} {op_node.attrs.get('path')} "
                           f"on {service_hint} — {op_node.description}"
                    ).strip(),
                    deprecated=bool(op_node.attrs.get("deprecated")),
                    evidence=list(op_node.evidence[:1]),
                )
            )
        if not steps:
            continue
        journeys.append(
            Journey(
                id=jid,
                name=name,
                description=str(raw.get("description") or ""),
                steps=sorted(steps, key=lambda s: s.order),
                provenance=_prov(
                    f"'{name}' is a curated journey shipped with the NovaCart sample estate.",
                    confidence=0.95,
                ),
            )
        )
    return journeys


def _resolve_reference(
    graph: KnowledgeGraph, ops: dict[str, str], reference: str
) -> str | None:
    """Accept both fully-qualified node IDs and the shorthand used in the sample files.

    ``schema:customer-api:Address`` is a node ID; ``customer-api:Address`` and
    ``order-api:Order.cust_no`` are shorthand a human would naturally write. We try the
    plausible expansions in order and return the first that actually exists — a reference
    that resolves to nothing is reported, never invented.
    """
    reference = reference.strip()
    if not reference:
        return None
    if graph.get(reference) is not None:
        return reference
    if reference in ops and graph.get(ops[reference]) is not None:
        return ops[reference]

    tail = reference.split(":", 1)[-1]
    prefixes = ("field:", "schema:") if "." in tail else ("schema:", "field:")
    for prefix in (*prefixes, "svc:", "domain:", "entity:", "cap:", "op:"):
        candidate = f"{prefix}{reference}"
        if graph.get(candidate) is not None:
            return candidate
    return None


def _edge(
    graph: KnowledgeGraph,
    edge_type: EdgeType,
    source: str,
    target: str,
    explanation: str,
    *,
    acceptance: Acceptance = Acceptance.PROPOSED,
    attrs: dict[str, Any] | None = None,
) -> None:
    if graph.get(source) is None or graph.get(target) is None:
        return
    graph.add_edge(
        GraphEdge(
            id=edge_id(edge_type.value, source, target),
            type=edge_type,
            source=source,
            target=target,
            label=edge_type.value.replace("_", " ").lower(),
            acceptance=acceptance,
            provenance=_prov(explanation),
            attrs={"analysis": BUNDLED_LABEL, **(attrs or {})},
            evidence=[
                Evidence(
                    id=evidence_id(BUNDLED_LABEL, f"{source}->{target}"),
                    source_file=BUNDLED_LABEL,
                    pointer=f"/{edge_type.value}/{source}/{target}",
                    label="Bundled analysis",
                    excerpt=explanation,
                )
            ],
        )
    )


def enrich_schema_id(service: str, schema: str) -> str:
    return schema_id(service, schema)
