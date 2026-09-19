"""Graph query, inspection, search and the accept/reject decision on an inference."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from api_galaxy import PROMPT_TEMPLATE_VERSION
from api_galaxy.app.errors import NotFoundError, ValidationFailure
from api_galaxy.app.state import get_state
from api_galaxy.contracts.graph import (
    Acceptance,
    EdgeType,
    GraphEdge,
    KnowledgeGraph,
    NodeType,
    Provenance,
    SourceKind,
)
from api_galaxy.contracts.ids import edge_id
from api_galaxy.graph.engine import NetworkXGraphRepository, QueryLimits

router = APIRouter(prefix="/api/v1/projects/{project_id}/graph", tags=["graph"])

# Semantic zoom: which node types are visible at each level.
ZOOM_LEVELS: dict[int, set[NodeType]] = {
    1: {NodeType.ESTATE, NodeType.DOMAIN, NodeType.CAPABILITY},
    2: {NodeType.ESTATE, NodeType.DOMAIN, NodeType.CAPABILITY, NodeType.SERVICE,
        NodeType.JOURNEY, NodeType.BUSINESS_ENTITY},
    3: {NodeType.ESTATE, NodeType.DOMAIN, NodeType.CAPABILITY, NodeType.SERVICE,
        NodeType.JOURNEY, NodeType.BUSINESS_ENTITY, NodeType.JOURNEY_STEP,
        NodeType.API_OPERATION, NodeType.ENDPOINT, NodeType.SCHEMA, NodeType.RISK,
        NodeType.SECURITY_SCHEME, NodeType.SERVER},
    4: set(NodeType),
}


def _load(project_id: str, scenario_id: str | None = None) -> KnowledgeGraph:
    state = get_state()
    live = state.get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    if not scenario_id:
        return live.graph
    scenario = live.scenarios.get(scenario_id)
    if scenario is None:
        raise NotFoundError(f"No scenario with id '{scenario_id}'.")
    from api_galaxy.analysis.impact import apply_changes

    return apply_changes(live.graph, scenario)


def _serialise(graph: KnowledgeGraph, nodes, edges, *, truncated=False, reason="") -> dict[str, Any]:
    return {
        "nodes": [
            {
                **node.model_dump(mode="json"),
                "zoom": node.display_group(),
                "is_fact": node.is_fact,
            }
            for node in nodes
        ],
        "edges": [
            {**edge.model_dump(mode="json"), "stroke": edge.stroke, "is_fact": edge.is_fact}
            for edge in edges
        ],
        "truncated": truncated,
        "truncation_reason": reason,
        "stats": graph.stats().model_dump(),
    }


@router.get("")
async def get_graph(
    project_id: str,
    level: int = Query(default=2, ge=1, le=4),
    domain: str | None = None,
    service: str | None = None,
    search: str | None = None,
    include_inferred: bool = True,
    scenario: str | None = None,
    max_nodes: int = Query(default=600, ge=10, le=5000),
) -> dict[str, Any]:
    """The main graph query. Semantic zoom is applied by filtering node types, which is
    what keeps level 1 a readable dozen boxes instead of a hairball."""
    graph = _load(project_id, scenario)
    repo = NetworkXGraphRepository(graph)
    result = repo.filter(
        node_types=ZOOM_LEVELS.get(level, ZOOM_LEVELS[2]),
        domains={domain} if domain else None,
        services={s.strip() for s in service.split(",")} if service else None,
        search=search,
        include_inferred=include_inferred,
        limits=QueryLimits(max_nodes=max_nodes),
    )
    return {
        **_serialise(graph, result.nodes, result.edges,
                     truncated=result.truncated, reason=result.truncation_reason),
        "level": level,
        "scenario_id": scenario,
    }


@router.get("/node/{node_id:path}")
async def get_node(project_id: str, node_id: str, scenario: str | None = None) -> dict[str, Any]:
    """Everything the inspector shows for one node."""
    graph = _load(project_id, scenario)
    node = graph.get(node_id)
    if node is None:
        raise NotFoundError(f"No node with id '{node_id}'.")
    index = graph.node_index()
    repo = NetworkXGraphRepository(graph)

    incoming = [e for e in graph.edges if e.target == node_id]
    outgoing = [e for e in graph.edges if e.source == node_id]

    risks = [
        index[e.source].model_dump(mode="json")
        for e in incoming
        if e.type is EdgeType.AFFECTS and e.source in index
    ]
    dependents = repo.dependents(node_id, limits=QueryLimits(max_depth=3, max_nodes=120))

    return {
        "node": {**node.model_dump(mode="json"), "is_fact": node.is_fact},
        "evidence": [e.model_dump(mode="json") for e in node.evidence],
        "incoming": [
            {
                **e.model_dump(mode="json"),
                "stroke": e.stroke,
                "other": index[e.source].label if e.source in index else e.source,
                "other_id": e.source,
                "other_type": index[e.source].type.value if e.source in index else "",
            }
            for e in incoming
            if e.type is not EdgeType.AFFECTS
        ],
        "outgoing": [
            {
                **e.model_dump(mode="json"),
                "stroke": e.stroke,
                "other": index[e.target].label if e.target in index else e.target,
                "other_id": e.target,
                "other_type": index[e.target].type.value if e.target in index else "",
            }
            for e in outgoing
        ],
        "risks": risks,
        "dependents": [
            {
                "id": path.node_id,
                "label": index[path.node_id].label,
                "type": index[path.node_id].type.value,
                "distance": path.distance,
                # What kind of relationship reached it — a contract it consumes, or a
                # semantic link that merely means the same thing.
                "via": [hop.edge_type.value for hop in path.hops],
                "contract_only": path.all_contract,
                "stated_only": path.all_stated,
            }
            for path in dependents[:40]
            if path.node_id in index
        ],
        "aliases": _aliases_of(graph, index, node_id),
    }


def _aliases_of(graph: KnowledgeGraph, index, node_id: str) -> list[dict[str, Any]]:
    """One entry per *other node*, not per edge.

    The alias rule and the bundled analysis can both propose the same pair, and a field
    can be linked to several siblings; listing edges would show 'customer_id' three times
    with no way to tell the entries apart.
    """
    seen: dict[str, dict[str, Any]] = {}
    for edge in graph.edges:
        if edge.type is not EdgeType.ALIAS_OF:
            continue
        if node_id not in (edge.source, edge.target):
            continue
        other_id = edge.target if edge.source == node_id else edge.source
        other = index.get(other_id)
        if other is None:
            continue
        entry = {
            "id": other_id,
            "label": other.label,
            "name": other.attrs.get("name") or other.label,
            "service": other.attrs.get("service"),
            "confidence": edge.attrs.get("confidence"),
            "acceptance": edge.acceptance.value,
            "edge_id": edge.id,
            "rationale": edge.provenance.explanation,
            "source": edge.provenance.source_kind.value,
        }
        existing = seen.get(other_id)
        # Keep the entry a human has already ruled on over a fresh suggestion.
        if existing is None or (
            existing["acceptance"] == Acceptance.PROPOSED.value
            and entry["acceptance"] != Acceptance.PROPOSED.value
        ):
            seen[other_id] = entry
    return sorted(seen.values(), key=lambda a: (str(a["service"]), str(a["name"])))


@router.get("/edge/{edge_ref:path}")
async def get_edge(project_id: str, edge_ref: str, scenario: str | None = None) -> dict[str, Any]:
    graph = _load(project_id, scenario)
    edge = graph.get_edge(edge_ref)
    if edge is None:
        raise NotFoundError(f"No edge with id '{edge_ref}'.")
    index = graph.node_index()
    return {
        "edge": {**edge.model_dump(mode="json"), "stroke": edge.stroke, "is_fact": edge.is_fact},
        "source": index[edge.source].model_dump(mode="json") if edge.source in index else None,
        "target": index[edge.target].model_dump(mode="json") if edge.target in index else None,
        "kind": "fact" if edge.is_fact and edge.acceptance is Acceptance.OBSERVED else "inference",
    }


@router.get("/neighbors/{node_id:path}")
async def neighbors(
    project_id: str,
    node_id: str,
    depth: int = Query(default=1, ge=1, le=6),
    max_nodes: int = Query(default=200, ge=5, le=2000),
    scenario: str | None = None,
) -> dict[str, Any]:
    graph = _load(project_id, scenario)
    if graph.get(node_id) is None:
        raise NotFoundError(f"No node with id '{node_id}'.")
    repo = NetworkXGraphRepository(graph)
    result = repo.neighbors(
        node_id, depth=depth, limits=QueryLimits(max_depth=depth, max_nodes=max_nodes)
    )
    return _serialise(
        graph, result.nodes, result.edges,
        truncated=result.truncated, reason=result.truncation_reason,
    )


@router.get("/search")
async def search(project_id: str, q: str = Query(min_length=1), limit: int = 25) -> dict[str, Any]:
    graph = _load(project_id)
    repo = NetworkXGraphRepository(graph)
    hits = repo.search(q, limit=min(limit, 60))
    return {
        "query": q,
        "results": [
            {
                "id": n.id,
                "label": n.label,
                "type": n.type.value,
                "description": n.description[:200],
                "service": n.attrs.get("service"),
                "is_fact": n.is_fact,
            }
            for n in hits
        ],
    }


@router.get("/path")
async def path(
    project_id: str,
    source: str = Query(alias="from"),
    target: str = Query(alias="to"),
    alternatives: int = Query(default=1, ge=1, le=5),
) -> dict[str, Any]:
    graph = _load(project_id)
    repo = NetworkXGraphRepository(graph)
    index = graph.node_index()
    if source not in index or target not in index:
        raise NotFoundError("One or both endpoints of the path do not exist.")
    paths = (
        repo.k_shortest_paths(source, target, k=alternatives)
        if alternatives > 1
        else [repo.shortest_path(source, target)]
    )
    paths = [p for p in paths if p]
    return {
        "paths": [
            {
                "nodes": p,
                "labels": [index[n].label for n in p if n in index],
                "length": len(p) - 1,
            }
            for p in paths
        ],
        "found": bool(paths),
    }


@router.get("/cycles")
async def cycles(project_id: str) -> dict[str, Any]:
    graph = _load(project_id)
    repo = NetworkXGraphRepository(graph)
    index = graph.node_index()
    found = repo.cycles(limit=25)
    return {
        "cycles": [
            {"nodes": c, "labels": [index[n].label for n in c if n in index]} for c in found
        ]
    }


@router.get("/legend")
async def legend(project_id: str) -> dict[str, Any]:  # noqa: ARG001
    """The single source of truth for how the graph is drawn, used by the UI and exports."""
    return {
        "edges": [
            {"stroke": "solid", "meaning": "Stated by the specification",
             "detail": "A fact the parser read directly out of the document."},
            {"stroke": "dashed", "meaning": "Inferred",
             "detail": "Suggested by a rule or a model. Not stated anywhere."},
            {"stroke": "dotted", "meaning": "Created by you",
             "detail": "A relationship you added or accepted."},
        ],
        "states": [
            {"key": "conflict", "colour": "red", "icon": "alert-octagon",
             "meaning": "Confirmed conflict or break"},
            {"key": "warning", "colour": "amber", "icon": "alert-triangle",
             "meaning": "Ambiguity, warning, or a low-confidence inference"},
            {"key": "active", "colour": "accent", "icon": "play",
             "meaning": "Currently traversed by an answer, journey or impact path"},
        ],
        "nodes": [
            {"type": t.value, "zoom": z}
            for z, types in ZOOM_LEVELS.items()
            for t in sorted(types, key=lambda x: x.value)
            if z == min(level for level, group in ZOOM_LEVELS.items() if t in group)
        ],
        "note": "Meaning is never carried by colour alone: every state also has a stroke "
        "pattern, an icon and a text label.",
    }


# --------------------------------------------------------------------------------------
# Human authority over inferences
# --------------------------------------------------------------------------------------


class EdgeDecision(BaseModel):
    action: str = Field(description="accept | reject | edit")
    label: str | None = None
    relation: str | None = None
    note: str = ""


@router.post("/edges/{edge_ref:path}/decision")
async def decide_edge(project_id: str, edge_ref: str, decision: EdgeDecision) -> dict[str, Any]:
    """Accept, reject or edit an inferred relationship.

    Accepting does not turn an inference into a specification fact — it records that a
    person agreed with it. The provenance changes to `user_edit`, the stroke changes to
    dotted, and the decision is written to the immutable log.
    """
    state = get_state()
    live = state.get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    graph = live.graph
    edge = graph.get_edge(edge_ref)
    if edge is None:
        raise NotFoundError(f"No edge with id '{edge_ref}'.")
    if edge.acceptance is Acceptance.OBSERVED and edge.is_fact and decision.action != "reject":
        raise ValidationFailure(
            "This relationship is a specification fact, so there is nothing to accept. "
            "Facts can only be changed by changing the document."
        )

    action = decision.action.lower()
    if action == "accept":
        edge.acceptance = Acceptance.ACCEPTED
        edge.provenance = Provenance(
            source_kind=SourceKind.USER_EDIT,
            explanation=f"Accepted by you. Originally: {edge.provenance.explanation}",
            confidence=1.0,
            provider=edge.provenance.provider,
            model=edge.provenance.model,
            prompt_template_version=edge.provenance.prompt_template_version,
        )
    elif action == "reject":
        edge.acceptance = Acceptance.REJECTED
        edge.attrs["rejected_note"] = decision.note
    elif action == "edit":
        if decision.relation and decision.relation.upper() in EdgeType.__members__:
            new_type = EdgeType[decision.relation.upper()]
            graph.edges = [e for e in graph.edges if e.id != edge.id]
            graph._edge_index = {}
            edited = GraphEdge(
                id=edge_id(new_type.value, edge.source, edge.target),
                type=new_type,
                source=edge.source,
                target=edge.target,
                label=decision.label or new_type.value.replace("_", " ").lower(),
                acceptance=Acceptance.ACCEPTED,
                provenance=Provenance(
                    source_kind=SourceKind.USER_EDIT,
                    explanation=decision.note or "Edited by you.",
                    confidence=1.0,
                ),
                attrs={**edge.attrs, "edited_from": edge.type.value},
            )
            graph.add_edge(edited)
            edge = edited
        else:
            edge.label = decision.label or edge.label
            edge.acceptance = Acceptance.ACCEPTED
    else:
        raise ValidationFailure("action must be one of: accept, reject, edit.")

    state.persist(live.analysed)
    index = graph.node_index()
    record = state.storage.record_decision(
        project_id=project_id,
        provider=edge.provenance.provider or "",
        model=edge.provenance.model or "",
        prompt_template_version=edge.provenance.prompt_template_version or PROMPT_TEMPLATE_VERSION,
        task="relationship",
        action=action,
        subject=f"{index.get(edge.source).label if edge.source in index else edge.source} "
        f"→ {index.get(edge.target).label if edge.target in index else edge.target} "
        f"({edge.type.value})",
        accepted_payload={
            "edge_id": edge.id,
            "type": edge.type.value,
            "source": edge.source,
            "target": edge.target,
            "note": decision.note,
        },
        source_references=[e.locator for e in edge.evidence],
    )
    return {
        "edge": {**edge.model_dump(mode="json"), "stroke": edge.stroke},
        "decision": record,
    }
