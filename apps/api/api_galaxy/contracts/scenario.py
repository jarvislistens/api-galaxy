"""Break Lab contracts: changes, scenarios, impact and repairs.

A scenario never mutates its base project. It stores an ordered list of
:class:`Change` records; applying them to a *clone* of the base graph produces the
scenario graph. That makes undo, reset, replay and before/after comparison trivial and
guarantees the source of truth stays clean.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from api_galaxy.contracts.analysis import JourneyValidation
from api_galaxy.contracts.graph import Evidence, Provenance, utcnow


class ChangeKind(str, Enum):
    RENAME_FIELD = "rename_field"
    REMOVE_FIELD = "remove_field"
    CHANGE_FIELD_TYPE = "change_field_type"
    SET_FIELD_REQUIRED = "set_field_required"
    REMOVE_ENDPOINT = "remove_endpoint"
    DEPRECATE_ENDPOINT = "deprecate_endpoint"
    CHANGE_RESPONSE = "change_response"
    MOVE_ENTITY_DOMAIN = "move_entity_domain"
    SERVICE_UNAVAILABLE = "service_unavailable"
    SERVICE_LATENCY = "service_latency"
    INTRODUCE_ALIAS = "introduce_alias"
    RESOLVE_ALIAS = "resolve_alias"


CHANGE_LABELS: dict[ChangeKind, str] = {
    ChangeKind.RENAME_FIELD: "Rename a field",
    ChangeKind.REMOVE_FIELD: "Remove a field",
    ChangeKind.CHANGE_FIELD_TYPE: "Change a datatype",
    ChangeKind.SET_FIELD_REQUIRED: "Make a field required / optional",
    ChangeKind.REMOVE_ENDPOINT: "Remove an endpoint",
    ChangeKind.DEPRECATE_ENDPOINT: "Deprecate an endpoint",
    ChangeKind.CHANGE_RESPONSE: "Change a response status or schema",
    ChangeKind.MOVE_ENTITY_DOMAIN: "Move an entity to another domain",
    ChangeKind.SERVICE_UNAVAILABLE: "Simulate a service outage",
    ChangeKind.SERVICE_LATENCY: "Simulate service latency",
    ChangeKind.INTRODUCE_ALIAS: "Introduce a semantic alias",
    ChangeKind.RESOLVE_ALIAS: "Resolve a semantic alias",
}


class Change(BaseModel):
    id: str
    kind: ChangeKind
    target_id: str = Field(description="Node ID the change applies to.")
    params: dict[str, Any] = Field(default_factory=dict)
    label: str = ""
    created_at: datetime = Field(default_factory=utcnow)

    def describe(self) -> str:
        if self.label:
            return self.label
        return f"{CHANGE_LABELS.get(self.kind, self.kind.value)} on {self.target_id}"


class ImpactStatus(str, Enum):
    BROKEN = "broken"
    DEGRADED = "degraded"
    POTENTIALLY_AFFECTED = "potentially_affected"
    UNAFFECTED = "unaffected"

    @property
    def rank(self) -> int:
        return {
            "broken": 0,
            "degraded": 1,
            "potentially_affected": 2,
            "unaffected": 3,
        }[self.value]


class ImpactItem(BaseModel):
    node_id: str
    node_label: str
    node_type: str
    status: ImpactStatus
    distance: int = Field(description="Hops from the changed node. 0 = the change itself.")
    reason: str
    chain: list[str] = Field(
        default_factory=list,
        description="Node IDs from the changed node to this one. Always `distance + 1` long.",
    )
    chain_labels: list[str] = Field(default_factory=list)
    via: list[str] = Field(
        default_factory=list,
        description="Edge type crossed at each hop, parallel to `chain`. One shorter than "
        "`chain`, because n nodes are joined by n-1 relationships.",
    )
    evidence: list[Evidence] = Field(default_factory=list)


class ImpactReport(BaseModel):
    scenario_id: str
    changes: list[Change] = Field(default_factory=list)
    items: list[ImpactItem] = Field(default_factory=list)
    affected_journeys: list[JourneyValidation] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    added_nodes: list[str] = Field(default_factory=list)
    removed_nodes: list[str] = Field(default_factory=list)
    changed_nodes: list[str] = Field(default_factory=list)
    added_edges: list[str] = Field(default_factory=list)
    removed_edges: list[str] = Field(default_factory=list)

    def by_status(self, status: ImpactStatus) -> list[ImpactItem]:
        return [i for i in self.items if i.status is status]


class RepairStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPLIED = "applied"


class Repair(BaseModel):
    id: str
    title: str
    rationale: str
    kind: str = Field(description="e.g. 'add_alias_mapping', 'restore_field', 'version_endpoint'")
    target_ids: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    deterministic: bool = True
    status: RepairStatus = RepairStatus.PROPOSED
    provenance: Provenance
    patch: list[str] = Field(
        default_factory=list, description="Unified-diff-style lines for the change summary."
    )
    migration_steps: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    id: str
    project_id: str
    name: str
    description: str = ""
    base_graph_ref: str = ""
    changes: list[Change] = Field(default_factory=list)
    repairs: list[Repair] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def applied_repairs(self) -> list[Repair]:
        return [r for r in self.repairs if r.status is RepairStatus.APPLIED]


class ScenarioComparison(BaseModel):
    """Before/after view used by the Break Lab compare panel and by exports."""

    scenario_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    delta: dict[str, int] = Field(default_factory=dict)
    journeys_before: list[JourneyValidation] = Field(default_factory=list)
    journeys_after: list[JourneyValidation] = Field(default_factory=list)
