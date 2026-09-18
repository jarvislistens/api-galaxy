"""Journey derivation, materialisation and validation.

A journey is an ordered walk through operations that together accomplish something a
business person would recognise ("place an order"). We derive candidates deterministically
from declared dependencies and tags; a model may propose more, and a user may edit any of
them. Validation replays a journey against a graph and reports what broke — that is what
makes "Journey restored" an assertion rather than a claim.
"""

from __future__ import annotations

from api_galaxy.contracts.analysis import (
    Journey,
    JourneyStep,
    JourneyStepValidation,
    JourneyValidation,
)
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
    edge_id,
    evidence_id,
    journey_id,
    journey_step_id,
    operation_id,
    schema_id,
    service_id,
)
from api_galaxy.parsing.normalize import NormalizedEstate, NormalizedService, NormOperation

MAX_JOURNEY_STEPS = 12


def _prov(kind: SourceKind, explanation: str, confidence: float | None = None) -> Provenance:
    return Provenance(source_kind=kind, explanation=explanation, confidence=confidence,
                      rule_id="journey-derivation" if kind is SourceKind.DETERMINISTIC_RULE else None)


# --------------------------------------------------------------------------------------
# Derivation
# --------------------------------------------------------------------------------------


def derive_journeys(estate: NormalizedEstate) -> list[Journey]:
    """Candidate journeys from declared dependency chains, then from tags as a fallback."""
    journeys = _journeys_from_dependencies(estate)
    covered = {op_id for j in journeys for op_id in j.operation_ids}
    journeys.extend(_journeys_from_tags(estate, covered))
    return journeys


def _journeys_from_dependencies(estate: NormalizedEstate) -> list[Journey]:
    index: dict[str, tuple[NormalizedService, NormOperation]] = {}
    for service in estate.services:
        for op in service.operations:
            index.setdefault(f"{service.slug}:{op.operation_id}", (service, op))
            index.setdefault(op.operation_id, (service, op))

    is_target: set[str] = set()
    for service in estate.services:
        for op in service.operations:
            for dep in op.depends_on:
                is_target.add(dep.operation_id)

    journeys: list[Journey] = []
    for service in estate.services:
        for op in service.operations:
            if not op.depends_on or op.operation_id in is_target:
                continue
            ordered = _closure(index, service, op)
            if len(ordered) < 2:
                continue
            journeys.append(
                _materialise(
                    name=op.summary or f"{op.method.upper()} {op.path}",
                    description=op.description
                    or f"Derived from the dependencies declared by {op.operation_id}.",
                    chain=ordered,
                    source=SourceKind.DETERMINISTIC_RULE,
                    explanation="Built by following the x-api-galaxy-depends-on chain "
                    f"declared on {op.operation_id}.",
                )
            )
    return journeys


def _closure(
    index: dict[str, tuple[NormalizedService, NormOperation]],
    service: NormalizedService,
    root: NormOperation,
) -> list[tuple[NormalizedService, NormOperation]]:
    """Dependencies first, root last — a depth-first post-order with cycle protection."""
    ordered: list[tuple[NormalizedService, NormOperation]] = []
    seen: set[str] = set()

    def visit(svc: NormalizedService, op: NormOperation, depth: int) -> None:
        key = f"{svc.slug}:{op.operation_id}"
        if key in seen or depth > MAX_JOURNEY_STEPS:
            return
        seen.add(key)
        for dep in op.depends_on:
            found = index.get(f"{_slug(dep.service)}:{dep.operation_id}") or index.get(
                dep.operation_id
            )
            if found:
                visit(found[0], found[1], depth + 1)
        ordered.append((svc, op))

    visit(service, root, 0)
    return ordered[:MAX_JOURNEY_STEPS]


def _slug(value: str) -> str:
    from api_galaxy.contracts.ids import slugify

    return slugify(value)


def _journeys_from_tags(
    estate: NormalizedEstate, covered: set[str]
) -> list[Journey]:
    """One 'lifecycle' journey per service whose operations are not already in a journey."""
    journeys: list[Journey] = []
    method_order = {"post": 0, "get": 1, "put": 2, "patch": 3, "delete": 4}
    for service in estate.services:
        remaining = [
            op
            for op in service.operations
            if op.kind == "path"
            and operation_id(service.name, op.method, op.path) not in covered
        ]
        if len(remaining) < 2:
            continue
        remaining.sort(key=lambda op: (method_order.get(op.method, 9), op.path))
        chain = [(service, op) for op in remaining[:MAX_JOURNEY_STEPS]]
        journeys.append(
            _materialise(
                name=f"Work with {service.title or service.name}",
                description=f"The typical lifecycle of {service.title or service.name} "
                "resources, ordered create → read → update → delete.",
                chain=chain,
                source=SourceKind.DETERMINISTIC_RULE,
                explanation="No dependency chain covered this service, so its operations "
                "were ordered by HTTP method to form a lifecycle.",
            )
        )
    return journeys


def _materialise(
    *,
    name: str,
    description: str,
    chain: list[tuple[NormalizedService, NormOperation]],
    source: SourceKind,
    explanation: str,
    confidence: float | None = None,
) -> Journey:
    jid = journey_id(name)
    steps: list[JourneyStep] = []
    for order, (service, op) in enumerate(chain, start=1):
        schemas: list[str] = []
        if op.request_body and op.request_body.schema_ref:
            schemas.append(schema_id(service.name, op.request_body.schema_ref))
        for response in op.responses:
            if response.status.startswith("2") and response.schema_ref:
                schemas.append(schema_id(service.name, response.schema_ref))
        oid = operation_id(service.name, op.method, op.path)
        steps.append(
            JourneyStep(
                id=journey_step_id(jid, order),
                order=order,
                label=op.summary or f"{op.method.upper()} {op.path}",
                narration=_narrate(service, op),
                service_id=service_id(service.name),
                operation_id=oid,
                schema_ids=sorted(set(schemas)),
                node_ids=[oid, service_id(service.name), *sorted(set(schemas))],
                technical_detail=(
                    f"{op.method.upper()} {op.path} on {service.title or service.name}"
                    + (f" — {op.description}" if op.description else "")
                ),
                deprecated=op.deprecated,
                evidence=[
                    Evidence(
                        id=evidence_id(service.source_file, op.pointer),
                        source_file=service.source_file,
                        pointer=op.pointer,
                        label=f"{op.method.upper()} {op.path}",
                        excerpt=op.summary or op.description,
                    )
                ],
            )
        )
    return Journey(
        id=jid,
        name=name,
        description=description,
        steps=steps,
        provenance=_prov(source, explanation, confidence),
    )


def _narrate(service: NormalizedService, op: NormOperation) -> str:
    if op.summary:
        base = op.summary.rstrip(".")
        subject = service.title or service.name
        return f"{subject} handles: {base.lower()}."
    verb = {
        "get": "reads",
        "post": "creates",
        "put": "replaces",
        "patch": "updates",
        "delete": "removes",
    }.get(op.method, "calls")
    noun = op.path.strip("/").split("/")[0].replace("-", " ") or "resource"
    return f"{service.title or service.name} {verb} {noun}."


# --------------------------------------------------------------------------------------
# Graph materialisation
# --------------------------------------------------------------------------------------


def attach_journeys_to_graph(graph: KnowledgeGraph, journeys: list[Journey]) -> None:
    for journey in journeys:
        graph.add_node(
            GraphNode(
                id=journey.id,
                type=NodeType.JOURNEY,
                label=journey.name,
                project_id=graph.project_id,
                description=journey.description,
                acceptance=Acceptance.OBSERVED
                if journey.provenance.source_kind.is_fact
                else Acceptance.PROPOSED,
                provenance=journey.provenance,
                attrs={"steps": len(journey.steps), "editable": journey.editable},
            )
        )
        for step in journey.steps:
            graph.add_node(
                GraphNode(
                    id=step.id,
                    type=NodeType.JOURNEY_STEP,
                    label=f"{step.order}. {step.label}",
                    project_id=graph.project_id,
                    description=step.narration,
                    provenance=journey.provenance,
                    attrs={
                        "order": step.order,
                        "operation_id": step.operation_id,
                        "service_id": step.service_id,
                        "schema_ids": step.schema_ids,
                        "narration": step.narration,
                        "technical_detail": step.technical_detail,
                        "deprecated": step.deprecated,
                    },
                    evidence=step.evidence,
                )
            )
            graph.add_edge(
                GraphEdge(
                    id=edge_id(EdgeType.PART_OF_JOURNEY.value, step.id, journey.id),
                    type=EdgeType.PART_OF_JOURNEY,
                    source=step.id,
                    target=journey.id,
                    label=f"step {step.order}",
                    provenance=journey.provenance,
                    attrs={"order": step.order},
                )
            )
            if step.operation_id and graph.get(step.operation_id) is not None:
                graph.add_edge(
                    GraphEdge(
                        id=edge_id(EdgeType.PART_OF_JOURNEY.value, step.operation_id, step.id),
                        type=EdgeType.PART_OF_JOURNEY,
                        source=step.operation_id,
                        target=step.id,
                        label="performed by",
                        provenance=journey.provenance,
                    )
                )

        # A journey depends on every service it crosses.
        #
        # Without this the only path from a journey into the rest of the graph runs through
        # its steps, which live one semantic-zoom level deeper — so at the services level a
        # journey is an unconnected island, and the layout packs all six of them into an
        # unreadable pile. It is also simply true, and it makes "what breaks this journey?"
        # answerable in one hop instead of three.
        for service_node_id in dict.fromkeys(
            step.service_id for step in journey.steps if step.service_id
        ):
            if graph.get(service_node_id) is None:
                continue
            graph.add_edge(
                GraphEdge(
                    id=edge_id(EdgeType.DEPENDS_ON.value, journey.id, service_node_id),
                    type=EdgeType.DEPENDS_ON,
                    source=journey.id,
                    target=service_node_id,
                    label="crosses",
                    acceptance=Acceptance.OBSERVED
                    if journey.provenance.source_kind.is_fact
                    else Acceptance.PROPOSED,
                    provenance=journey.provenance,
                    attrs={"derived_from_steps": True},
                )
            )


# --------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------


def validate_journey(journey: Journey, graph: KnowledgeGraph) -> JourneyValidation:
    """Replay a journey against a graph and report exactly what no longer works."""
    index = graph.node_index()
    broken: list[str] = []
    degraded: list[str] = []
    step_results: list[JourneyStepValidation] = []

    # Only a mapping created to *address a change* lets a renamed field still resolve.
    #
    # This is narrower than "has any accepted alias", deliberately. Agreeing that
    # `customer_id` and `cust_no` are the same concept says nothing about whether anyone
    # published a translation for the brand-new name a rename introduced — and if the two
    # were conflated, accepting an unrelated alias would silently mark a broken checkout
    # as healthy. A mapping counts only when a repair or a scenario put it there.
    alias_targets: set[str] = set()
    for edge in graph.edges:
        if edge.type is not EdgeType.ALIAS_OF:
            continue
        if not (edge.attrs.get("repair") or edge.attrs.get("introduced_by_scenario")):
            continue
        if edge.acceptance in (Acceptance.ACCEPTED, Acceptance.OBSERVED):
            alias_targets.add(edge.source)
            alias_targets.add(edge.target)

    for step in journey.steps:
        reasons: list[str] = []
        severity = "ok"

        node = index.get(step.operation_id) if step.operation_id else None
        if step.operation_id and node is None:
            reasons.append("The operation this step calls no longer exists.")
            severity = "broken"
        elif node is not None:
            if node.attrs.get("removed"):
                reasons.append("The operation has been removed in this scenario.")
                severity = "broken"
            if node.attrs.get("unavailable"):
                reasons.append(
                    f"{node.attrs.get('unavailable_reason', 'The service is unavailable.')}"
                )
                severity = "broken"
            if node.attrs.get("latency_ms"):
                reasons.append(
                    f"Responds {node.attrs['latency_ms']} ms slower in this scenario."
                )
                severity = "degraded" if severity == "ok" else severity
            if node.attrs.get("deprecated"):
                reasons.append("The operation is deprecated.")
                severity = "degraded" if severity == "ok" else severity

        for schema_node_id in step.schema_ids:
            if index.get(schema_node_id) is None:
                reasons.append("A schema this step exchanges no longer exists.")
                severity = "broken"

        # Required fields that were removed or renamed without a mapping.
        for schema_node_id in step.schema_ids:
            for edge in graph.edges:
                if edge.type is not EdgeType.CONTAINS or edge.source != schema_node_id:
                    continue
                field_node = index.get(edge.target)
                if field_node is None or field_node.type is not NodeType.FIELD:
                    continue
                if field_node.attrs.get("renamed_from") and field_node.id not in alias_targets:
                    reasons.append(
                        f"'{field_node.attrs['renamed_from']}' was renamed to "
                        f"'{field_node.attrs.get('name')}' with no mapping in place."
                    )
                    severity = "broken"
                if field_node.attrs.get("type_changed_from") and field_node.attrs.get("required"):
                    reasons.append(
                        f"Required field '{field_node.attrs.get('name')}' changed type from "
                        f"{field_node.attrs['type_changed_from']} to "
                        f"{field_node.attrs.get('type_signature')}."
                    )
                    severity = "broken" if severity != "broken" else severity
            for removed in graph.diagnostics:
                if (
                    isinstance(removed, dict)
                    and removed.get("code") == "scenario-removed-required-field"
                    and removed.get("schema") == schema_node_id
                ):
                    reasons.append(str(removed.get("message", "A required field was removed.")))
                    severity = "broken"

        if severity == "broken":
            broken.append(step.id)
        elif severity == "degraded":
            degraded.append(step.id)
        step_results.append(
            JourneyStepValidation(step_id=step.id, ok=severity == "ok", reasons=reasons)
        )

    ok = not broken
    if ok and not degraded:
        summary = f"All {len(journey.steps)} steps resolve against the current graph."
    elif ok:
        summary = f"{len(degraded)} step(s) still work but are degraded."
    else:
        summary = f"{len(broken)} of {len(journey.steps)} steps are broken."
    return JourneyValidation(
        journey_id=journey.id,
        journey_name=journey.name,
        ok=ok,
        broken_steps=broken,
        degraded_steps=degraded,
        steps=step_results,
        summary=summary,
    )


def validate_all(journeys: list[Journey], graph: KnowledgeGraph) -> list[JourneyValidation]:
    return [validate_journey(journey, graph) for journey in journeys]
