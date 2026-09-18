"""Break Lab: scenarios, impact, repairs, comparison, reset.

A scenario is an ordered list of changes against a *clone* of the project graph. The base
project is never mutated, which is what makes undo, reset, replay and before/after
comparison trivial rather than delicate.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api_galaxy.analysis.impact import (
    apply_changes,
    attach_impact_to_graph,
    compute_impact,
    propose_deterministic_repairs,
)
from api_galaxy.analysis.journeys import validate_all
from api_galaxy.app.errors import (
    ConsentMissingError,
    NotFoundError,
    ValidationFailure,
)
from api_galaxy.app.state import get_state
from api_galaxy.contracts.graph import NodeType, Provenance, SourceKind
from api_galaxy.contracts.providers import ProviderKind, RepairRequest
from api_galaxy.contracts.scenario import (
    CHANGE_LABELS,
    Change,
    ChangeKind,
    Repair,
    RepairStatus,
    Scenario,
)
from api_galaxy.missions import chaos_candidates
from api_galaxy.providers.base import ProviderError
from api_galaxy.providers.context import build_context
from api_galaxy.providers.kimi import ConsentRequired

router = APIRouter(prefix="/api/v1/projects/{project_id}/scenarios", tags=["break-lab"])


class ScenarioInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""


class ChangeInput(BaseModel):
    kind: ChangeKind
    target_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    label: str = ""


def _live(project_id: str):
    live = get_state().get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    return live


def _scenario(project_id: str, scenario_id: str) -> tuple[Any, Scenario]:
    live = _live(project_id)
    scenario = live.scenarios.get(scenario_id)
    if scenario is None:
        raise NotFoundError(f"No scenario with id '{scenario_id}'.")
    return live, scenario


def _impact_payload(live, scenario: Scenario) -> dict[str, Any]:
    scenario_graph = apply_changes(live.graph, scenario)
    impact = compute_impact(live.graph, scenario_graph, scenario, live.analysed.journeys)
    attach_impact_to_graph(scenario_graph, impact, scenario)
    index = live.graph.node_index()
    return {
        "scenario": scenario.model_dump(mode="json"),
        "impact": impact.model_dump(mode="json"),
        # The same shape as `impact.items`, deliberately. An earlier version renamed
        # `node_label`/`node_type` to `label`/`type` here, which meant one concept had two
        # field names on one response — the client typed both as ImpactItem, compiled
        # cleanly, and rendered `undefined`.
        "shockwave": [item.model_dump(mode="json") for item in impact.items],
        "journeys": [v.model_dump(mode="json") for v in impact.affected_journeys],
        "all_journeys": [
            v.model_dump(mode="json") for v in validate_all(live.analysed.journeys, scenario_graph)
        ],
        "changed_nodes": [
            {"id": node_id, "label": index[node_id].label}
            for node_id in impact.changed_nodes
            if node_id in index
        ],
    }


# --------------------------------------------------------------------------------------


@router.get("/change-kinds")
async def change_kinds(project_id: str) -> dict[str, Any]:  # noqa: ARG001
    return {
        "kinds": [
            {
                "id": kind.value,
                "label": CHANGE_LABELS[kind],
                "target_types": _target_types(kind),
                "params": _param_hints(kind),
            }
            for kind in ChangeKind
        ]
    }


@router.get("")
async def list_scenarios(project_id: str) -> dict[str, Any]:
    live = _live(project_id)
    return {
        "scenarios": [
            {
                **scenario.model_dump(mode="json"),
                "change_count": len(scenario.changes),
                "applied_repairs": len(scenario.applied_repairs()),
            }
            for scenario in live.scenarios.values()
        ]
    }


@router.post("", status_code=201)
async def create_scenario(project_id: str, payload: ScenarioInput) -> dict[str, Any]:
    state = get_state()
    live = _live(project_id)
    scenario = Scenario(
        id=f"scn:{uuid.uuid4().hex[:10]}",
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        base_graph_ref=live.graph.spec_fingerprint,
    )
    state.save_scenario(project_id, scenario)
    return {"scenario": scenario.model_dump(mode="json")}


@router.post("/{scenario_id}/changes")
async def add_change(project_id: str, scenario_id: str, payload: ChangeInput) -> dict[str, Any]:
    state = get_state()
    live, scenario = _scenario(project_id, scenario_id)
    target = live.graph.get(payload.target_id)
    if target is None:
        raise NotFoundError(f"No node with id '{payload.target_id}' to change.")
    expected = _target_types(payload.kind)
    if expected and target.type.value not in expected:
        raise ValidationFailure(
            f"'{CHANGE_LABELS[payload.kind]}' applies to {', '.join(expected)}, "
            f"but '{target.label}' is a {target.type.value}."
        )
    if payload.kind is ChangeKind.RENAME_FIELD and not payload.params.get("new_name"):
        raise ValidationFailure("A rename needs a 'new_name' parameter.")

    change = Change(
        id=f"chg:{scenario_id.split(':', 1)[-1]}:{len(scenario.changes)}",
        kind=payload.kind,
        target_id=payload.target_id,
        params=payload.params,
        label=payload.label or f"{CHANGE_LABELS[payload.kind]} — {target.label}",
    )
    scenario.changes.append(change)
    scenario.repairs = []  # a new change invalidates the previously proposed repairs
    state.save_scenario(project_id, scenario)
    return _impact_payload(live, scenario)


@router.delete("/{scenario_id}/changes/{index}")
async def undo_change(project_id: str, scenario_id: str, index: int) -> dict[str, Any]:
    state = get_state()
    live, scenario = _scenario(project_id, scenario_id)
    if index < 0 or index >= len(scenario.changes):
        raise NotFoundError(f"Change {index} does not exist in this scenario.")
    scenario.changes.pop(index)
    scenario.repairs = []
    state.save_scenario(project_id, scenario)
    return _impact_payload(live, scenario)


@router.get("/{scenario_id}/impact")
async def impact(project_id: str, scenario_id: str) -> dict[str, Any]:
    live, scenario = _scenario(project_id, scenario_id)
    return _impact_payload(live, scenario)


@router.get("/{scenario_id}/compare")
async def compare(project_id: str, scenario_id: str) -> dict[str, Any]:
    """Before/after, computed on both graphs so the numbers are directly comparable."""
    live, scenario = _scenario(project_id, scenario_id)
    before_graph = live.graph
    after_graph = apply_changes(before_graph, scenario)
    before = validate_all(live.analysed.journeys, before_graph)
    after = validate_all(live.analysed.journeys, after_graph)
    before_stats = before_graph.stats()
    after_stats = after_graph.stats()
    return {
        "scenario_id": scenario_id,
        "before": {
            "stats": before_stats.model_dump(),
            "journeys": [v.model_dump(mode="json") for v in before],
            "journeys_ok": sum(1 for v in before if v.ok),
        },
        "after": {
            "stats": after_stats.model_dump(),
            "journeys": [v.model_dump(mode="json") for v in after],
            "journeys_ok": sum(1 for v in after if v.ok),
        },
        "delta": {
            "nodes": after_stats.nodes - before_stats.nodes,
            "edges": after_stats.edges - before_stats.edges,
            "journeys_ok": sum(1 for v in after if v.ok) - sum(1 for v in before if v.ok),
        },
    }


@router.post("/{scenario_id}/reset")
async def reset_scenario(project_id: str, scenario_id: str) -> dict[str, Any]:
    state = get_state()
    live, scenario = _scenario(project_id, scenario_id)
    scenario.changes = []
    scenario.repairs = []
    state.save_scenario(project_id, scenario)
    return _impact_payload(live, scenario)


@router.delete("/{scenario_id}")
async def delete_scenario(project_id: str, scenario_id: str) -> dict[str, Any]:
    state = get_state()
    live, _ = _scenario(project_id, scenario_id)
    live.scenarios.pop(scenario_id, None)
    state.storage.delete_scenario(scenario_id)
    return {"deleted": True, "scenario_id": scenario_id}


# --------------------------------------------------------------------------------------
# Repairs
# --------------------------------------------------------------------------------------


class RepairProposalRequest(BaseModel):
    provider: str = ProviderKind.DETERMINISTIC.value


@router.post("/{scenario_id}/repairs/propose")
async def propose_repairs(
    project_id: str, scenario_id: str, payload: RepairProposalRequest
) -> dict[str, Any]:
    """Deterministic repairs always; a model may add semantic ones on top."""
    state = get_state()
    live, scenario = _scenario(project_id, scenario_id)
    scenario_graph = apply_changes(live.graph, scenario)
    impact = compute_impact(live.graph, scenario_graph, scenario, live.analysed.journeys)

    repairs = propose_deterministic_repairs(live.graph, scenario, impact)
    warnings: list[str] = []

    kind = ProviderKind(payload.provider) if payload.provider else ProviderKind.DETERMINISTIC
    if kind is not ProviderKind.DETERMINISTIC:
        broken = [i.node_id for i in impact.items if i.status.value == "broken"][:30]
        request = RepairRequest(
            project_id=project_id,
            scenario_id=scenario_id,
            change_summaries=[c.describe() for c in scenario.changes],
            broken_node_ids=broken,
            broken_journeys=[v.journey_name for v in impact.affected_journeys if not v.ok],
            context=build_context(
                live.graph,
                chunk_label="repair",
                node_ids=set(broken) | {c.target_id for c in scenario.changes},
            ),
        )
        provider = state.provider(kind, live.graph)
        try:
            proposal = await provider.propose_repairs(request)
            for position, proposed in enumerate(proposal.repairs):
                repairs.append(
                    Repair(
                        id=f"rep:{scenario_id.split(':', 1)[-1]}:ai{position}",
                        title=proposed.title,
                        rationale=proposed.rationale,
                        kind=proposed.kind,
                        target_ids=proposed.target_ids,
                        params=proposed.params,
                        confidence=proposed.confidence,
                        deterministic=False,
                        provenance=Provenance(
                            source_kind=SourceKind.AI_INFERENCE,
                            explanation=f"Proposed by {kind.value} ({proposal.model}).",
                            confidence=proposed.confidence,
                            provider=kind.value,
                            model=proposal.model,
                        ),
                        migration_steps=proposed.migration_steps,
                    )
                )
        except ConsentRequired as exc:
            raise ConsentMissingError(str(exc), project_id=project_id) from exc
        except ProviderError as exc:
            warnings.append(f"{kind.value} could not propose repairs: {exc.message}")

    scenario.repairs = repairs
    state.save_scenario(project_id, scenario)
    return {
        "repairs": [r.model_dump(mode="json") for r in repairs],
        "warnings": warnings,
        "deterministic_count": sum(1 for r in repairs if r.deterministic),
    }


class RepairDecision(BaseModel):
    action: str = Field(description="apply | reject")
    params: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None


@router.post("/{scenario_id}/repairs/{repair_id:path}/decision")
async def decide_repair(
    project_id: str, scenario_id: str, repair_id: str, decision: RepairDecision
) -> dict[str, Any]:
    """Apply, edit or reject a repair, then re-validate every journey.

    The response carries `journeys_restored`, and the UI only shows "Journey restored"
    when that is true — it is a validation result, never an assumption.
    """
    state = get_state()
    live, scenario = _scenario(project_id, scenario_id)
    repair = next((r for r in scenario.repairs if r.id == repair_id), None)
    if repair is None:
        raise NotFoundError(f"No repair with id '{repair_id}' in this scenario.")

    before = validate_all(live.analysed.journeys, apply_changes(live.graph, scenario))

    if decision.action == "apply":
        if decision.params:
            repair.params.update(decision.params)
        if decision.title:
            repair.title = decision.title
        repair.status = RepairStatus.APPLIED
    elif decision.action == "reject":
        repair.status = RepairStatus.REJECTED
    else:
        raise ValidationFailure("action must be 'apply' or 'reject'.")

    state.save_scenario(project_id, scenario)
    after_graph = apply_changes(live.graph, scenario)
    after = validate_all(live.analysed.journeys, after_graph)

    state.storage.record_decision(
        project_id=project_id,
        provider=repair.provenance.provider or "",
        model=repair.provenance.model or "",
        prompt_template_version=repair.provenance.prompt_template_version or "",
        task="repair",
        action=decision.action,
        subject=repair.title,
        accepted_payload={"repair_id": repair.id, "kind": repair.kind,
                          "targets": repair.target_ids, "params": repair.params},
        source_references=repair.target_ids,
    )

    restored = [
        v.journey_name
        for v in after
        if v.ok and any(b.journey_id == v.journey_id and not b.ok for b in before)
    ]
    return {
        "repair": repair.model_dump(mode="json"),
        "journeys_before": [v.model_dump(mode="json") for v in before],
        "journeys_after": [v.model_dump(mode="json") for v in after],
        "journeys_restored": restored,
        "all_valid": all(v.ok for v in after),
        "patch": repair.patch,
        "migration_steps": repair.migration_steps,
        "impact": _impact_payload(live, scenario)["impact"],
    }


@router.get("/{scenario_id}/change-summary")
async def change_summary(project_id: str, scenario_id: str) -> dict[str, Any]:
    """A patch-style summary plus the migration checklist, ready to paste into a ticket."""
    live, scenario = _scenario(project_id, scenario_id)
    index = live.graph.node_index()
    applied = scenario.applied_repairs()
    lines: list[str] = [f"# {scenario.name}", ""]
    lines.append("## Changes")
    for change in scenario.changes:
        target = index.get(change.target_id)
        lines.append(f"- {change.describe()}" + (f"  ({target.type.value})" if target else ""))
    if applied:
        lines.append("")
        lines.append("## Repairs applied")
        for repair in applied:
            lines.append(f"- {repair.title} — {repair.rationale}")
            lines.extend(f"  {line}" for line in repair.patch)
    checklist = [step for repair in applied for step in repair.migration_steps]
    if checklist:
        lines.append("")
        lines.append("## Migration checklist")
        lines.extend(f"- [ ] {step}" for step in checklist)
    return {
        "markdown": "\n".join(lines),
        "patch": [line for repair in applied for line in repair.patch],
        "migration_steps": checklist,
    }


# --------------------------------------------------------------------------------------
# Chaos
# --------------------------------------------------------------------------------------


class ChaosRequest(BaseModel):
    seed: int = Field(default=0, ge=0, le=999)


@router.post("/chaos")
async def chaos(project_id: str, payload: ChaosRequest) -> dict[str, Any]:
    """Apply one safe, reproducible breaking change without telling the caller which.

    The choice is an index into a deterministic ranked list rather than a random draw, so
    the same seed always yields the same scenario and a mission can be replayed.
    """
    state = get_state()
    live = _live(project_id)
    candidates = chaos_candidates(live.graph)
    if not candidates:
        raise ValidationFailure("This estate has no field safe to break automatically.")
    chosen = candidates[payload.seed % len(candidates)]

    scenario = Scenario(
        id=f"scn:chaos-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        name="Chaos run",
        description="A safe random breaking change. The origin is hidden until you guess.",
    )
    scenario.changes.append(
        Change(
            id=f"chg:{scenario.id.split(':', 1)[-1]}:0",
            kind=ChangeKind.RENAME_FIELD,
            target_id=chosen["node_id"],
            params={"new_name": f"{chosen['label'].split('.')[-1]}_v2"},
            label="A field somewhere was renamed.",
        )
    )
    state.save_scenario(project_id, scenario)
    payload_out = _impact_payload(live, scenario)
    # Deliberately omit the origin from the response: the mission is to find it.
    payload_out["shockwave"] = [
        {**item, "chain": [], "chain_labels": []}
        for item in payload_out["shockwave"]
        if item["distance"] > 0
    ]
    payload_out["scenario"]["changes"] = [
        {**c, "target_id": "hidden", "params": {}}
        for c in payload_out["scenario"]["changes"]
    ]
    payload_out["hidden_origin_token"] = chosen["node_id"]
    payload_out["candidates"] = [
        {"id": c["node_id"], "label": c["label"], "service": c["service"]} for c in candidates
    ]
    return payload_out


# --------------------------------------------------------------------------------------


def _target_types(kind: ChangeKind) -> list[str]:
    if kind in (
        ChangeKind.RENAME_FIELD,
        ChangeKind.REMOVE_FIELD,
        ChangeKind.CHANGE_FIELD_TYPE,
        ChangeKind.SET_FIELD_REQUIRED,
        ChangeKind.INTRODUCE_ALIAS,
        ChangeKind.RESOLVE_ALIAS,
    ):
        return [NodeType.FIELD.value]
    if kind in (ChangeKind.REMOVE_ENDPOINT, ChangeKind.DEPRECATE_ENDPOINT, ChangeKind.CHANGE_RESPONSE):
        return [NodeType.API_OPERATION.value]
    if kind in (ChangeKind.SERVICE_UNAVAILABLE, ChangeKind.SERVICE_LATENCY):
        return [NodeType.SERVICE.value]
    if kind is ChangeKind.MOVE_ENTITY_DOMAIN:
        return [NodeType.BUSINESS_ENTITY.value, NodeType.SERVICE.value, NodeType.SCHEMA.value]
    return []


def _param_hints(kind: ChangeKind) -> list[dict[str, str]]:
    hints = {
        ChangeKind.RENAME_FIELD: [{"name": "new_name", "type": "string", "required": "true"}],
        ChangeKind.CHANGE_FIELD_TYPE: [
            {"name": "new_type", "type": "string", "required": "true"},
            {"name": "new_format", "type": "string", "required": "false"},
        ],
        ChangeKind.SET_FIELD_REQUIRED: [{"name": "required", "type": "boolean", "required": "true"}],
        ChangeKind.CHANGE_RESPONSE: [
            {"name": "status", "type": "string", "required": "true"},
            {"name": "action", "type": "'remove' | 'replace'", "required": "true"},
            {"name": "new_schema", "type": "string", "required": "false"},
        ],
        ChangeKind.SERVICE_LATENCY: [{"name": "latency_ms", "type": "integer", "required": "true"}],
        ChangeKind.MOVE_ENTITY_DOMAIN: [
            {"name": "domain_id", "type": "string", "required": "true"}
        ],
        ChangeKind.INTRODUCE_ALIAS: [{"name": "other_id", "type": "string", "required": "true"}],
        ChangeKind.RESOLVE_ALIAS: [{"name": "other_id", "type": "string", "required": "true"}],
    }
    return hints.get(kind, [])
