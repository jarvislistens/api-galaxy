"""Journeys: list, inspect, create, edit, and the playback timeline."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api_galaxy.analysis.journeys import attach_journeys_to_graph, validate_all, validate_journey
from api_galaxy.app.errors import NotFoundError, ValidationFailure
from api_galaxy.app.state import get_state
from api_galaxy.contracts.analysis import Journey, JourneyStep
from api_galaxy.contracts.graph import EdgeType, NodeType, Provenance, SourceKind
from api_galaxy.contracts.ids import journey_id, journey_step_id

router = APIRouter(prefix="/api/v1/projects/{project_id}/journeys", tags=["journeys"])


class StepInput(BaseModel):
    operation_id: str
    label: str = ""
    narration: str = ""


class JourneyInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    steps: list[StepInput] = Field(min_length=1, max_length=24)


def _live(project_id: str):
    live = get_state().get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    return live


@router.get("")
async def list_journeys(project_id: str, scenario: str | None = None) -> dict[str, Any]:
    live = _live(project_id)
    graph = live.graph
    if scenario:
        from api_galaxy.analysis.impact import apply_changes

        scenario_obj = live.scenarios.get(scenario)
        if scenario_obj is None:
            raise NotFoundError(f"No scenario with id '{scenario}'.")
        graph = apply_changes(live.graph, scenario_obj)

    validations = {v.journey_id: v for v in validate_all(live.analysed.journeys, graph)}
    index = graph.node_index()
    return {
        "journeys": [
            {
                **journey.model_dump(mode="json"),
                "validation": validations[journey.id].model_dump(mode="json"),
                "services": sorted(
                    {
                        str(index[s.operation_id].attrs.get("service"))
                        for s in journey.steps
                        if s.operation_id and s.operation_id in index
                    }
                ),
            }
            for journey in live.analysed.journeys
        ],
        "scenario_id": scenario,
    }


@router.get("/{journey_ref:path}/playback")
async def playback(project_id: str, journey_ref: str, scenario: str | None = None) -> dict[str, Any]:
    """A frame-by-frame timeline the player can step through without further requests."""
    live = _live(project_id)
    journey = next((j for j in live.analysed.journeys if j.id == journey_ref), None)
    if journey is None:
        raise NotFoundError(f"No journey with id '{journey_ref}'.")

    graph = live.graph
    if scenario:
        from api_galaxy.analysis.impact import apply_changes

        scenario_obj = live.scenarios.get(scenario)
        if scenario_obj is None:
            raise NotFoundError(f"No scenario with id '{scenario}'.")
        graph = apply_changes(live.graph, scenario_obj)

    index = graph.node_index()
    validation = validate_journey(journey, graph)
    by_step = {s.step_id: s for s in validation.steps}

    frames = []
    cumulative: list[str] = []
    for step in journey.steps:
        operation = index.get(step.operation_id or "")
        highlight = [n for n in step.node_ids if n in index]
        cumulative.extend(highlight)
        edges = [
            e.id
            for e in graph.edges
            if e.source in set(highlight) and e.target in set(highlight)
        ]
        step_validation = by_step.get(step.id)
        frames.append(
            {
                "order": step.order,
                "step_id": step.id,
                "label": step.label,
                "narration": step.narration,
                "technical_detail": step.technical_detail,
                "operation_id": step.operation_id,
                "service_id": step.service_id,
                "service": str(operation.attrs.get("service")) if operation else None,
                "method": str(operation.attrs.get("method")) if operation else None,
                "path": str(operation.attrs.get("path")) if operation else None,
                "schema_ids": step.schema_ids,
                "schemas": [index[s].label for s in step.schema_ids if s in index],
                "highlight_nodes": highlight,
                "highlight_edges": edges,
                "trail": list(dict.fromkeys(cumulative)),
                "deprecated": step.deprecated,
                "ok": step_validation.ok if step_validation else True,
                "problems": step_validation.reasons if step_validation else [],
                "evidence": [e.model_dump(mode="json") for e in step.evidence],
            }
        )

    return {
        "journey": {
            "id": journey.id,
            "name": journey.name,
            "description": journey.description,
            "source": journey.provenance.source_kind.value,
            "explanation": journey.provenance.explanation,
        },
        "frames": frames,
        "validation": validation.model_dump(mode="json"),
        "scenario_id": scenario,
    }


@router.post("", status_code=201)
async def create_journey(project_id: str, payload: JourneyInput) -> dict[str, Any]:
    """User-authored journeys sit alongside derived ones and are provenance-tagged as yours."""
    state = get_state()
    live = _live(project_id)
    graph = live.graph
    index = graph.node_index()

    jid = journey_id(payload.name)
    if any(j.id == jid for j in live.analysed.journeys):
        raise ValidationFailure(f"A journey called '{payload.name}' already exists.")

    steps: list[JourneyStep] = []
    for order, raw in enumerate(payload.steps, start=1):
        operation = index.get(raw.operation_id)
        if operation is None or operation.type is not NodeType.API_OPERATION:
            raise ValidationFailure(
                f"Step {order} references '{raw.operation_id}', which is not an operation "
                "in this project."
            )
        schema_ids = sorted(
            {
                e.target
                for e in graph.edges
                if e.source == operation.id
                and e.type in (EdgeType.USES_REQUEST, EdgeType.RETURNS)
            }
        )
        steps.append(
            JourneyStep(
                id=journey_step_id(jid, order),
                order=order,
                label=raw.label or str(operation.attrs.get("summary") or operation.label),
                narration=raw.narration or operation.description[:200],
                service_id=f"svc:{operation.attrs.get('service')}",
                operation_id=operation.id,
                schema_ids=schema_ids,
                node_ids=[operation.id, *schema_ids],
                technical_detail=f"{operation.attrs.get('method')} {operation.attrs.get('path')}",
                deprecated=bool(operation.attrs.get("deprecated")),
                evidence=list(operation.evidence[:1]),
            )
        )

    journey = Journey(
        id=jid,
        name=payload.name,
        description=payload.description,
        steps=steps,
        provenance=Provenance(
            source_kind=SourceKind.USER_EDIT,
            explanation="You created this journey.",
            confidence=1.0,
        ),
    )
    live.analysed.journeys.append(journey)
    attach_journeys_to_graph(graph, [journey])
    state.persist(live.analysed)
    return {"journey": journey.model_dump(mode="json")}


@router.put("/{journey_ref:path}")
async def update_journey(
    project_id: str, journey_ref: str, payload: JourneyInput
) -> dict[str, Any]:
    state = get_state()
    live = _live(project_id)
    existing = next((j for j in live.analysed.journeys if j.id == journey_ref), None)
    if existing is None:
        raise NotFoundError(f"No journey with id '{journey_ref}'.")
    live.analysed.journeys = [j for j in live.analysed.journeys if j.id != journey_ref]
    # Remove the old step nodes so the graph does not accumulate orphans.
    for step in existing.steps:
        live.graph.remove_node(step.id)
    live.graph.remove_node(existing.id)
    state.persist(live.analysed)
    return await create_journey(project_id, payload)


@router.delete("/{journey_ref:path}")
async def delete_journey(project_id: str, journey_ref: str) -> dict[str, Any]:
    state = get_state()
    live = _live(project_id)
    existing = next((j for j in live.analysed.journeys if j.id == journey_ref), None)
    if existing is None:
        raise NotFoundError(f"No journey with id '{journey_ref}'.")
    live.analysed.journeys = [j for j in live.analysed.journeys if j.id != journey_ref]
    for step in existing.steps:
        live.graph.remove_node(step.id)
    live.graph.remove_node(existing.id)
    state.persist(live.analysed)
    return {"deleted": True, "journey_id": journey_ref}
