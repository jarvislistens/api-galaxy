"""Break Lab: apply changes to a cloned graph and compute deterministic impact.

Severity propagation rules (documented here because the UI cites them):

* **Broken** — the changed node itself, and anything at distance 1 along a *contract*
  edge (a schema that contains the field, an operation that sends or returns that schema,
  an operation that explicitly depends on a removed operation). These cannot keep working
  without a code change.
* **Degraded** — distance 2. The contract still type-checks but the semantics moved, or
  the dependency is now slower/optional.
* **Potentially affected** — distance 3 and beyond, or anything reached only through an
  *inferred* edge. We say "potentially" because the evidence is weaker, and we say why.
* **Unaffected** — everything else.

Nothing here is a prediction about production. It is a statement about the specification
graph, and every export repeats that caveat.
"""

from __future__ import annotations

from api_galaxy.analysis.journeys import validate_all
from api_galaxy.contracts.analysis import Journey, JourneyValidation
from api_galaxy.contracts.graph import (
    Acceptance,
    EdgeType,
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    NodeType,
    Provenance,
    SourceKind,
)
from api_galaxy.contracts.ids import edge_id
from api_galaxy.contracts.scenario import (
    Change,
    ChangeKind,
    ImpactItem,
    ImpactReport,
    ImpactStatus,
    Repair,
    RepairStatus,
    Scenario,
)
from api_galaxy.graph.engine import NetworkXGraphRepository, QueryLimits

CONTRACT_EDGES = frozenset(
    {
        EdgeType.CONTAINS,
        EdgeType.USES_REQUEST,
        EdgeType.RETURNS,
        EdgeType.REFERENCES,
        EdgeType.EXPOSES,
        EdgeType.DEPENDS_ON,
        EdgeType.CALLS_OR_PRECEDES,
        EdgeType.PART_OF_JOURNEY,
    }
)

ASSUMPTIONS = [
    "Impact is computed from the specification graph, not from runtime traffic.",
    "A consumer is assumed to use every field of every schema it receives.",
    "Explicit x-api-galaxy-depends-on edges are treated as hard dependencies.",
    "Inferred relationships only ever produce 'potentially affected', never 'broken'.",
]

LIMITATIONS = [
    "Undocumented consumers cannot be seen, so real-world blast radius may be larger.",
    "Backwards-compatible client code (tolerant readers, defaulting) may absorb changes "
    "this analysis reports as broken.",
    "Latency and outage simulations model reachability only — no queueing or retry behaviour.",
]


def _scenario_provenance(change: Change) -> Provenance:
    return Provenance(
        source_kind=SourceKind.SCENARIO,
        explanation=change.describe(),
        rule_id=change.kind.value,
    )


# --------------------------------------------------------------------------------------
# Applying changes
# --------------------------------------------------------------------------------------


def apply_changes(base: KnowledgeGraph, scenario: Scenario) -> KnowledgeGraph:
    """Return a *new* graph with the scenario's changes applied. ``base`` is untouched."""
    graph = base.clone(scenario_id=scenario.id)
    for change in scenario.changes:
        _apply_one(graph, change)
    for repair in scenario.repairs:
        if repair.status is RepairStatus.APPLIED:
            _apply_repair(graph, repair)
    return graph


def _apply_one(graph: KnowledgeGraph, change: Change) -> None:
    node = graph.get(change.target_id)
    prov = _scenario_provenance(change)

    if change.kind is ChangeKind.RENAME_FIELD and node is not None:
        old = node.attrs.get("name") or node.label
        new = str(change.params.get("new_name") or f"{old}_v2")
        node.attrs["renamed_from"] = old
        node.attrs["name"] = new
        node.label = node.label.rsplit(".", 1)[0] + "." + new if "." in node.label else new
        node.attrs["scenario_changed"] = True
        node.provenance = prov

    elif change.kind is ChangeKind.REMOVE_FIELD and node is not None:
        schema_ids = [e.source for e in graph.edges if e.type is EdgeType.CONTAINS and e.target == node.id]
        was_required = bool(node.attrs.get("required"))
        graph.remove_node(node.id)
        if was_required:
            for schema_node_id in schema_ids:
                graph.diagnostics.append(
                    {
                        "code": "scenario-removed-required-field",
                        "schema": schema_node_id,
                        "message": f"Required field '{node.label}' was removed.",
                    }
                )

    elif change.kind is ChangeKind.CHANGE_FIELD_TYPE and node is not None:
        node.attrs["type_changed_from"] = node.attrs.get("type_signature")
        node.attrs["type"] = change.params.get("new_type", "string")
        node.attrs["format"] = change.params.get("new_format")
        node.attrs["type_signature"] = (
            f"{node.attrs['type']}({node.attrs['format']})"
            if node.attrs.get("format")
            else str(node.attrs["type"])
        )
        node.attrs["scenario_changed"] = True
        node.provenance = prov

    elif change.kind is ChangeKind.SET_FIELD_REQUIRED and node is not None:
        node.attrs["required_changed_from"] = bool(node.attrs.get("required"))
        node.attrs["required"] = bool(change.params.get("required", True))
        node.attrs["scenario_changed"] = True
        node.provenance = prov

    elif change.kind is ChangeKind.REMOVE_ENDPOINT and node is not None:
        node.attrs["removed"] = True
        node.attrs["scenario_changed"] = True
        node.provenance = prov

    elif change.kind is ChangeKind.DEPRECATE_ENDPOINT and node is not None:
        node.attrs["deprecated"] = True
        node.attrs["scenario_changed"] = True
        node.provenance = prov

    elif change.kind is ChangeKind.CHANGE_RESPONSE and node is not None:
        responses = list(node.attrs.get("responses") or [])
        status = str(change.params.get("status", "200"))
        action = str(change.params.get("action", "remove"))
        if action == "remove":
            node.attrs["responses"] = [r for r in responses if r.get("status") != status]
            node.attrs["removed_response"] = status
        else:
            for response in responses:
                if response.get("status") == status:
                    response["schema"] = change.params.get("new_schema")
            node.attrs["responses"] = responses
            node.attrs["changed_response"] = status
        node.attrs["scenario_changed"] = True
        node.provenance = prov

    elif change.kind is ChangeKind.MOVE_ENTITY_DOMAIN and node is not None:
        target_domain = str(change.params.get("domain_id", ""))
        graph.edges = [
            e
            for e in graph.edges
            if not (e.type is EdgeType.BELONGS_TO_DOMAIN and e.source == node.id)
        ]
        graph._edge_index = {}
        if graph.get(target_domain) is not None:
            graph.add_edge(
                GraphEdge(
                    id=edge_id(EdgeType.BELONGS_TO_DOMAIN.value, node.id, target_domain),
                    type=EdgeType.BELONGS_TO_DOMAIN,
                    source=node.id,
                    target=target_domain,
                    label="moved",
                    acceptance=Acceptance.PROPOSED,
                    provenance=prov,
                )
            )
        node.attrs["scenario_changed"] = True

    elif change.kind in (ChangeKind.SERVICE_UNAVAILABLE, ChangeKind.SERVICE_LATENCY):
        service_id_ = change.target_id
        outage = change.kind is ChangeKind.SERVICE_UNAVAILABLE
        latency = int(change.params.get("latency_ms", 2000))
        service_node = graph.get(service_id_)
        if service_node is not None:
            service_node.attrs["unavailable" if outage else "latency_ms"] = (
                True if outage else latency
            )
            service_node.attrs["scenario_changed"] = True
        slug = service_node.attrs.get("slug") if service_node else None
        for candidate in graph.nodes:
            if candidate.type is not NodeType.API_OPERATION:
                continue
            if slug and candidate.attrs.get("service") != slug:
                continue
            if outage:
                candidate.attrs["unavailable"] = True
                candidate.attrs["unavailable_reason"] = (
                    f"{service_node.label if service_node else 'The service'} is simulated as down."
                )
            else:
                candidate.attrs["latency_ms"] = latency
            candidate.attrs["scenario_changed"] = True

    elif change.kind is ChangeKind.INTRODUCE_ALIAS:
        other = str(change.params.get("other_id", ""))
        if node is not None and graph.get(other) is not None:
            graph.add_edge(
                GraphEdge(
                    id=edge_id(EdgeType.ALIAS_OF.value, node.id, other),
                    type=EdgeType.ALIAS_OF,
                    source=node.id,
                    target=other,
                    label="alias of",
                    acceptance=Acceptance.PROPOSED,
                    provenance=prov,
                    attrs={"introduced_by_scenario": True},
                )
            )

    elif change.kind is ChangeKind.RESOLVE_ALIAS:
        other = str(change.params.get("other_id", ""))
        graph.edges = [
            e
            for e in graph.edges
            if not (
                e.type is EdgeType.ALIAS_OF
                and {e.source, e.target} == {change.target_id, other}
            )
        ]
        graph._edge_index = {}


def _apply_repair(graph: KnowledgeGraph, repair: Repair) -> None:
    prov = Provenance(
        source_kind=SourceKind.USER_EDIT,
        explanation=f"Repair applied: {repair.title}",
        confidence=repair.confidence,
        provider=repair.provenance.provider,
        model=repair.provenance.model,
    )
    if repair.kind == "add_alias_mapping" and len(repair.target_ids) >= 2:
        source, target = repair.target_ids[0], repair.target_ids[1]
        if graph.get(source) is not None and graph.get(target) is not None:
            graph.add_edge(
                GraphEdge(
                    id=edge_id(EdgeType.ALIAS_OF.value, source, target),
                    type=EdgeType.ALIAS_OF,
                    source=source,
                    target=target,
                    label="mapped",
                    acceptance=Acceptance.ACCEPTED,
                    provenance=prov,
                    attrs={"repair": repair.id},
                )
            )
    elif repair.kind == "restore_field_name":
        for node_id in repair.target_ids:
            node = graph.get(node_id)
            if node is None:
                continue
            original = node.attrs.pop("renamed_from", None)
            if original:
                node.attrs["name"] = original
                node.label = (
                    node.label.rsplit(".", 1)[0] + "." + original if "." in node.label else original
                )
    elif repair.kind == "restore_type":
        for node_id in repair.target_ids:
            node = graph.get(node_id)
            if node is None:
                continue
            original = node.attrs.pop("type_changed_from", None)
            if original:
                node.attrs["type_signature"] = original
                node.attrs["type"] = original.split("(")[0]
    elif repair.kind == "undeprecate_endpoint" or repair.kind == "restore_endpoint":
        for node_id in repair.target_ids:
            node = graph.get(node_id)
            if node is None:
                continue
            node.attrs.pop("removed", None)
            node.attrs["deprecated"] = False
    elif repair.kind == "restore_service":
        for node_id in repair.target_ids:
            node = graph.get(node_id)
            if node is not None:
                node.attrs.pop("unavailable", None)
                node.attrs.pop("unavailable_reason", None)
                node.attrs.pop("latency_ms", None)
        slug = None
        first = graph.get(repair.target_ids[0]) if repair.target_ids else None
        if first is not None:
            slug = first.attrs.get("slug")
        for candidate in graph.nodes:
            if candidate.type is NodeType.API_OPERATION and (
                slug is None or candidate.attrs.get("service") == slug
            ):
                candidate.attrs.pop("unavailable", None)
                candidate.attrs.pop("unavailable_reason", None)
                candidate.attrs.pop("latency_ms", None)
    elif repair.kind == "restore_response":
        for node_id in repair.target_ids:
            node = graph.get(node_id)
            if node is None:
                continue
            status = node.attrs.pop("removed_response", None)
            if status:
                responses = list(node.attrs.get("responses") or [])
                responses.append(
                    {
                        "status": status,
                        "schema": repair.params.get("schema"),
                        "description": "Restored by repair",
                        "array": False,
                        "example": False,
                    }
                )
                node.attrs["responses"] = responses


# --------------------------------------------------------------------------------------
# Impact
# --------------------------------------------------------------------------------------


def compute_impact(
    base: KnowledgeGraph,
    scenario_graph: KnowledgeGraph,
    scenario: Scenario,
    journeys: list[Journey],
) -> ImpactReport:
    from api_galaxy.graph.engine import diff_graphs

    repo = NetworkXGraphRepository(base)
    index = base.node_index()
    inferred_edges = {
        (e.source, e.target)
        for e in base.edges
        if not e.is_fact
    }

    items: dict[str, ImpactItem] = {}
    for change in scenario.changes:
        origin = index.get(change.target_id)
        origin_ids = [change.target_id]
        if change.kind in (ChangeKind.SERVICE_UNAVAILABLE, ChangeKind.SERVICE_LATENCY):
            slug = origin.attrs.get("slug") if origin else None
            origin_ids += [
                n.id
                for n in base.nodes
                if n.type is NodeType.API_OPERATION and n.attrs.get("service") == slug
            ]

        degrade_only = change.kind in (
            ChangeKind.SERVICE_LATENCY,
            ChangeKind.DEPRECATE_ENDPOINT,
            ChangeKind.MOVE_ENTITY_DOMAIN,
            ChangeKind.INTRODUCE_ALIAS,
            ChangeKind.RESOLVE_ALIAS,
        )

        for origin_id in origin_ids:
            node = index.get(origin_id)
            if node is None:
                continue
            _record(
                items,
                ImpactItem(
                    node_id=origin_id,
                    node_label=node.label,
                    node_type=node.type.value,
                    status=ImpactStatus.DEGRADED if degrade_only else ImpactStatus.BROKEN,
                    distance=0,
                    reason=change.describe(),
                    chain=[origin_id],
                    chain_labels=[node.label],
                    evidence=node.evidence[:2],
                ),
            )

            for dependent_id, distance, chain in repo.dependents(
                origin_id, limits=QueryLimits(max_depth=5, max_nodes=800)
            ):
                dependent = index.get(dependent_id)
                if dependent is None:
                    continue
                via_inference = any(
                    (chain[i + 1], chain[i]) in inferred_edges or (chain[i], chain[i + 1]) in inferred_edges
                    for i in range(len(chain) - 1)
                )
                status = _status_for(distance, degrade_only=degrade_only, via_inference=via_inference)
                _record(
                    items,
                    ImpactItem(
                        node_id=dependent_id,
                        node_label=dependent.label,
                        node_type=dependent.type.value,
                        status=status,
                        distance=distance,
                        reason=_reason_for(status, distance, via_inference),
                        chain=list(reversed(chain)),
                        chain_labels=[
                            index[c].label for c in reversed(chain) if c in index
                        ],
                        evidence=dependent.evidence[:1],
                    ),
                )

    validations = validate_all(journeys, scenario_graph)
    affected = [v for v in validations if not v.ok or v.degraded_steps]

    diff = diff_graphs(base, scenario_graph)
    ordered = sorted(items.values(), key=lambda i: (i.status.rank, i.distance, i.node_label))
    counts = {status.value: 0 for status in ImpactStatus}
    for item in ordered:
        counts[item.status.value] += 1
    counts["unaffected"] = max(0, len(base.nodes) - len(ordered))
    counts["journeys_broken"] = sum(1 for v in validations if not v.ok)
    counts["journeys_total"] = len(validations)

    return ImpactReport(
        scenario_id=scenario.id,
        changes=list(scenario.changes),
        items=ordered,
        affected_journeys=affected,
        counts=counts,
        assumptions=list(ASSUMPTIONS),
        limitations=list(LIMITATIONS),
        added_nodes=diff.added_nodes,
        removed_nodes=diff.removed_nodes,
        changed_nodes=diff.changed_nodes,
        added_edges=diff.added_edges,
        removed_edges=diff.removed_edges,
    )


def _record(items: dict[str, ImpactItem], item: ImpactItem) -> None:
    """Keep the *worst* status and the *shortest* chain for each node."""
    existing = items.get(item.node_id)
    if existing is None or (item.status.rank, item.distance) < (
        existing.status.rank,
        existing.distance,
    ):
        items[item.node_id] = item


def _status_for(distance: int, *, degrade_only: bool, via_inference: bool) -> ImpactStatus:
    if via_inference:
        return ImpactStatus.POTENTIALLY_AFFECTED
    if degrade_only:
        return ImpactStatus.DEGRADED if distance <= 2 else ImpactStatus.POTENTIALLY_AFFECTED
    if distance <= 1:
        return ImpactStatus.BROKEN
    if distance == 2:
        return ImpactStatus.DEGRADED
    return ImpactStatus.POTENTIALLY_AFFECTED


def _reason_for(status: ImpactStatus, distance: int, via_inference: bool) -> str:
    if via_inference:
        return (
            "Reached only through an inferred relationship, so this is a possibility rather "
            "than a certainty."
        )
    if status is ImpactStatus.BROKEN:
        return f"Directly consumes the changed contract ({distance} hop)."
    if status is ImpactStatus.DEGRADED:
        return "Two hops away — the contract still matches but the meaning has moved."
    return f"{distance} hops away along declared dependencies."


# --------------------------------------------------------------------------------------
# Deterministic repairs
# --------------------------------------------------------------------------------------


def propose_deterministic_repairs(
    base: KnowledgeGraph, scenario: Scenario, impact: ImpactReport
) -> list[Repair]:
    """Repairs that follow mechanically from the change, with no model involved."""
    repairs: list[Repair] = []
    index = base.node_index()

    for position, change in enumerate(scenario.changes):
        node = index.get(change.target_id)
        label = node.label if node else change.target_id
        rid = f"rep:{scenario.id.split(':', 1)[-1]}:{position}"
        prov = Provenance(
            source_kind=SourceKind.DETERMINISTIC_RULE,
            rule_id=f"repair-{change.kind.value}",
            explanation="Derived mechanically from the change that was made.",
            confidence=1.0,
        )

        if change.kind is ChangeKind.RENAME_FIELD:
            new_name = str(change.params.get("new_name", "new_name"))
            old_name = (node.attrs.get("name") if node else None) or label.split(".")[-1]
            repairs.append(
                Repair(
                    id=rid,
                    title=f"Map '{old_name}' to '{new_name}' at the boundary",
                    rationale=(
                        "Add an alias so every consumer that still sends or reads the old "
                        "name keeps working while they migrate."
                    ),
                    kind="add_alias_mapping",
                    target_ids=[change.target_id, *_alias_candidates(base, change.target_id)],
                    params={"from": old_name, "to": new_name},
                    deterministic=True,
                    provenance=prov,
                    patch=[
                        f"--- {label}",
                        f"-  {old_name}",
                        f"+  {new_name}",
                        f"+  # alias: {old_name} -> {new_name} (transitional)",
                    ],
                    migration_steps=[
                        f"Publish '{new_name}' alongside '{old_name}' and accept both on input.",
                        "Announce the deprecation window and update the changelog.",
                        f"Update consumers listed in the impact table to read '{new_name}'.",
                        f"Remove '{old_name}' only after the window closes.",
                    ],
                )
            )
            repairs.append(
                Repair(
                    id=f"{rid}b",
                    title=f"Revert the rename of '{old_name}'",
                    rationale="Safest option if the rename is not yet published.",
                    kind="restore_field_name",
                    target_ids=[change.target_id],
                    deterministic=True,
                    provenance=prov,
                    patch=[f"--- {label}", f"-  {new_name}", f"+  {old_name}"],
                    migration_steps=["Revert the specification change and re-publish."],
                )
            )

        elif change.kind is ChangeKind.CHANGE_FIELD_TYPE:
            repairs.append(
                Repair(
                    id=rid,
                    title=f"Restore the original type of '{label}'",
                    rationale="A type change is breaking for every generated client.",
                    kind="restore_type",
                    target_ids=[change.target_id],
                    deterministic=True,
                    provenance=prov,
                    patch=[f"--- {label}", "-  type: <new>", "+  type: <original>"],
                    migration_steps=[
                        "Revert the type, or introduce a new versioned field and deprecate the old.",
                    ],
                )
            )

        elif change.kind in (ChangeKind.REMOVE_ENDPOINT, ChangeKind.DEPRECATE_ENDPOINT):
            repairs.append(
                Repair(
                    id=rid,
                    title=f"Reinstate {label} behind a deprecation window",
                    rationale="Consumers in the impact table have no alternative path yet.",
                    kind="restore_endpoint",
                    target_ids=[change.target_id],
                    deterministic=True,
                    provenance=prov,
                    patch=[f"--- {label}", "+  deprecated: true", "+  sunset: <date>"],
                    migration_steps=[
                        "Restore the operation and mark it deprecated with a sunset header.",
                        "Publish the replacement operation and migrate consumers.",
                    ],
                )
            )

        elif change.kind is ChangeKind.REMOVE_FIELD:
            repairs.append(
                Repair(
                    id=rid,
                    title=f"Keep '{label}' and mark it deprecated instead of removing it",
                    rationale="Removal is immediately breaking; deprecation is not.",
                    kind="restore_field",
                    target_ids=[change.target_id],
                    deterministic=True,
                    provenance=prov,
                    patch=[f"--- {label}", "+  deprecated: true"],
                    migration_steps=[
                        "Restore the field, mark it deprecated, and stop populating it later.",
                    ],
                )
            )

        elif change.kind in (ChangeKind.SERVICE_UNAVAILABLE, ChangeKind.SERVICE_LATENCY):
            repairs.append(
                Repair(
                    id=rid,
                    title=f"Restore {label}",
                    rationale="Clears the simulated outage or latency for this service.",
                    kind="restore_service",
                    target_ids=[change.target_id],
                    deterministic=True,
                    provenance=prov,
                    migration_steps=[
                        "In production this maps to a circuit breaker plus a documented "
                        "degraded mode for the journeys listed above.",
                    ],
                )
            )

        elif change.kind is ChangeKind.CHANGE_RESPONSE:
            repairs.append(
                Repair(
                    id=rid,
                    title=f"Restore the {change.params.get('status', '200')} response on {label}",
                    rationale="Removing a documented status code breaks clients that branch on it.",
                    kind="restore_response",
                    target_ids=[change.target_id],
                    params={"schema": change.params.get("new_schema")},
                    deterministic=True,
                    provenance=prov,
                    migration_steps=["Re-declare the response, then deprecate it explicitly."],
                )
            )

    return repairs


def _alias_candidates(graph: KnowledgeGraph, node_id: str) -> list[str]:
    """Other identifier fields already linked to this one, used as mapping targets."""
    out: list[str] = []
    for edge in graph.edges:
        if edge.type is not EdgeType.ALIAS_OF:
            continue
        if edge.source == node_id:
            out.append(edge.target)
        elif edge.target == node_id:
            out.append(edge.source)
    return out[:4]


def summarise_validations(validations: list[JourneyValidation]) -> str:
    broken = [v for v in validations if not v.ok]
    if not broken:
        return f"All {len(validations)} journeys validate."
    return f"{len(broken)} of {len(validations)} journeys are broken: " + ", ".join(
        v.journey_name for v in broken[:4]
    )


def attach_impact_to_graph(graph: KnowledgeGraph, impact: ImpactReport, scenario: Scenario) -> None:
    """Materialise the scenario, its changes and the BREAKS edges for visualisation."""
    prov = Provenance(
        source_kind=SourceKind.SCENARIO,
        explanation=f"Scenario '{scenario.name}'.",
    )
    graph.add_node(
        GraphNode(
            id=scenario.id,
            type=NodeType.SCENARIO,
            label=scenario.name,
            project_id=graph.project_id,
            description=scenario.description,
            acceptance=Acceptance.PROPOSED,
            provenance=prov,
            attrs={"changes": len(scenario.changes), "counts": impact.counts},
        )
    )
    for position, change in enumerate(scenario.changes):
        change_node_id = change.id or f"chg:{scenario.id}:{position}"
        graph.add_node(
            GraphNode(
                id=change_node_id,
                type=NodeType.CHANGE,
                label=change.describe(),
                project_id=graph.project_id,
                acceptance=Acceptance.PROPOSED,
                provenance=prov,
                attrs={"kind": change.kind.value, "target": change.target_id, **change.params},
            )
        )
        graph.add_edge(
            GraphEdge(
                id=edge_id(EdgeType.CONTAINS.value, scenario.id, change_node_id),
                type=EdgeType.CONTAINS,
                source=scenario.id,
                target=change_node_id,
                label="change",
                provenance=prov,
            )
        )
        for item in impact.items:
            if item.status is not ImpactStatus.BROKEN:
                continue
            if graph.get(item.node_id) is None:
                continue
            graph.add_edge(
                GraphEdge(
                    id=edge_id(EdgeType.BREAKS.value, change_node_id, item.node_id),
                    type=EdgeType.BREAKS,
                    source=change_node_id,
                    target=item.node_id,
                    label="breaks",
                    acceptance=Acceptance.PROPOSED,
                    provenance=prov,
                    attrs={"distance": item.distance, "reason": item.reason},
                )
            )
