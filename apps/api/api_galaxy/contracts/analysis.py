"""Analysis products: risks, journeys, alias clusters and journey validation."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from api_galaxy.contracts.graph import Evidence, Provenance


class RiskSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"high": 0, "medium": 1, "low": 2, "info": 3}[self.value]


class RiskCategory(str, Enum):
    SECURITY = "security"
    PRIVACY = "privacy"
    COMPATIBILITY = "compatibility"
    CONSISTENCY = "consistency"
    STRUCTURE = "structure"
    AMBIGUITY = "ambiguity"


class Risk(BaseModel):
    """A finding. ``heuristic`` is true when the rule guesses rather than proves."""

    id: str
    rule_id: str
    severity: RiskSeverity
    category: RiskCategory
    title: str
    description: str
    recommendation: str = ""
    heuristic: bool = False
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    provenance: Provenance

    @property
    def label(self) -> str:
        return "Heuristic finding" if self.heuristic else "Deterministic finding"


class JourneyStep(BaseModel):
    id: str
    order: int
    label: str
    narration: str = Field(description="Plain language, understandable by a non-engineer.")
    service_id: str | None = None
    operation_id: str | None = None
    schema_ids: list[str] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    technical_detail: str = ""
    deprecated: bool = False


class Journey(BaseModel):
    id: str
    name: str
    description: str = ""
    steps: list[JourneyStep] = Field(default_factory=list)
    domain_ids: list[str] = Field(default_factory=list)
    provenance: Provenance
    editable: bool = True

    @property
    def operation_ids(self) -> list[str]:
        return [s.operation_id for s in self.steps if s.operation_id]


class JourneyStepValidation(BaseModel):
    step_id: str
    ok: bool
    reasons: list[str] = Field(default_factory=list)


class JourneyValidation(BaseModel):
    """Result of replaying a journey against a (possibly modified) graph."""

    journey_id: str
    journey_name: str
    ok: bool
    broken_steps: list[str] = Field(default_factory=list)
    degraded_steps: list[str] = Field(default_factory=list)
    steps: list[JourneyStepValidation] = Field(default_factory=list)
    summary: str = ""


class AliasCluster(BaseModel):
    """A set of differently-named identifiers that probably mean the same thing."""

    id: str
    canonical_name: str
    members: list[str] = Field(default_factory=list, description="Field/schema node IDs.")
    member_labels: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    accepted: bool | None = None
    provenance: Provenance


class Ambiguity(BaseModel):
    id: str
    title: str
    description: str
    node_ids: list[str] = Field(default_factory=list)
    kind: str = "semantic"
    provenance: Provenance


class EstateOverview(BaseModel):
    """Everything the Overview screen needs in one payload."""

    project_id: str
    project_name: str
    counts: dict[str, int] = Field(default_factory=dict)
    domains: list[dict[str, Any]] = Field(default_factory=list)
    journeys: list[dict[str, Any]] = Field(default_factory=list)
    top_risks: list[Risk] = Field(default_factory=list)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    parse_coverage: dict[str, Any] = Field(default_factory=dict)
    enrichment: dict[str, Any] = Field(default_factory=dict)
    derivation: list[dict[str, str]] = Field(
        default_factory=list,
        description="Backs the 'How was this derived?' control.",
    )
