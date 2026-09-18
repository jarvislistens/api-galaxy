"""Provider-facing contracts.

Every model task in API Galaxy is a *bounded* request with a *strict* JSON response
schema. The model is handed a whitelist of node IDs and is only allowed to reference
those; anything else is discarded before it can reach the graph.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProviderKind(str, Enum):
    DETERMINISTIC = "deterministic"
    OLLAMA = "ollama"
    KIMI = "kimi"


class ProviderStatus(str, Enum):
    READY = "ready"
    NOT_CONFIGURED = "not_configured"
    UNREACHABLE = "unreachable"
    DISABLED = "disabled"
    ERROR = "error"


class ProviderHealth(BaseModel):
    kind: ProviderKind
    status: ProviderStatus
    model: str | None = None
    base_url: str | None = None
    detail: str = ""
    setup_hint: str = ""
    external: bool = False
    latency_ms: float | None = None
    available_models: list[str] = Field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status is ProviderStatus.READY


class TaskKind(str, Enum):
    ENRICH = "enrich"
    ANSWER = "answer"
    REPAIR = "repair"
    NARRATE = "narrate"


# --------------------------------------------------------------------------------------
# Bounded graph context
# --------------------------------------------------------------------------------------


class ContextOperation(BaseModel):
    id: str
    service: str
    method: str
    path: str
    summary: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    request_schema: str | None = None
    response_schemas: list[str] = Field(default_factory=list)
    deprecated: bool = False
    secured: bool = True


class ContextSchema(BaseModel):
    id: str
    service: str
    name: str
    description: str = ""
    fields: list[dict[str, str]] = Field(default_factory=list)


class GraphContext(BaseModel):
    """The *only* thing a model ever sees. Bounded, sanitized, ID-addressable."""

    project_name: str
    chunk_label: str = "estate"
    services: list[dict[str, str]] = Field(default_factory=list)
    operations: list[ContextOperation] = Field(default_factory=list)
    schemas: list[ContextSchema] = Field(default_factory=list)
    existing_domains: list[str] = Field(default_factory=list)
    allowed_node_ids: list[str] = Field(default_factory=list)

    def fingerprint_payload(self) -> str:
        return self.model_dump_json(exclude={"allowed_node_ids"})


# --------------------------------------------------------------------------------------
# Enrichment
# --------------------------------------------------------------------------------------


class InferredEntity(BaseModel):
    name: str
    description: str = ""
    represented_by: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class InferredDomain(BaseModel):
    name: str
    description: str = ""
    service_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class InferredCapability(BaseModel):
    name: str
    description: str = ""
    operation_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class InferredJourney(BaseModel):
    name: str
    description: str = ""
    operation_ids: list[str] = Field(default_factory=list)
    narrations: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class InferredAlias(BaseModel):
    canonical_name: str
    member_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class InferredRelation(BaseModel):
    source_id: str
    target_id: str
    relation: str = "DEPENDS_ON"
    rationale: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class InferredRisk(BaseModel):
    title: str
    description: str = ""
    severity: str = "medium"
    node_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class EnrichmentRequest(BaseModel):
    project_id: str
    context: GraphContext
    tasks: list[str] = Field(
        default_factory=lambda: ["entities", "domains", "capabilities", "journeys", "aliases",
                                 "relations", "risks"]
    )
    max_items: int = 24


class EnrichmentResult(BaseModel):
    """Versioned so a cached result can be invalidated when the schema changes."""

    schema_version: str = "1.0"
    provider: ProviderKind
    model: str = ""
    prompt_template_version: str = ""
    entities: list[InferredEntity] = Field(default_factory=list)
    domains: list[InferredDomain] = Field(default_factory=list)
    capabilities: list[InferredCapability] = Field(default_factory=list)
    journeys: list[InferredJourney] = Field(default_factory=list)
    aliases: list[InferredAlias] = Field(default_factory=list)
    relations: list[InferredRelation] = Field(default_factory=list)
    risks: list[InferredRisk] = Field(default_factory=list)
    rationale: str = Field(default="", description="Concise summary. Never chain-of-thought.")
    latency_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    valid_json: bool = True
    retries: int = 0
    dropped_references: list[str] = Field(
        default_factory=list, description="IDs the model invented; discarded before use."
    )
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Question answering
# --------------------------------------------------------------------------------------


class GraphQuestionRequest(BaseModel):
    project_id: str
    question: str
    context: GraphContext
    scenario_id: str | None = None


class AnswerEvidence(BaseModel):
    node_id: str
    label: str = ""
    why: str = ""


class GraphAnswer(BaseModel):
    schema_version: str = "1.0"
    provider: ProviderKind
    model: str = ""
    answer: str
    technical_explanation: str = ""
    highlighted_node_ids: list[str] = Field(default_factory=list)
    highlighted_edge_ids: list[str] = Field(default_factory=list)
    path: list[str] = Field(default_factory=list)
    evidence: list[AnswerEvidence] = Field(default_factory=list)
    inference_note: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    dropped_references: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    grounded: bool = True


# --------------------------------------------------------------------------------------
# Repairs
# --------------------------------------------------------------------------------------


class RepairRequest(BaseModel):
    project_id: str
    scenario_id: str
    change_summaries: list[str] = Field(default_factory=list)
    broken_node_ids: list[str] = Field(default_factory=list)
    broken_journeys: list[str] = Field(default_factory=list)
    context: GraphContext


class ProposedRepair(BaseModel):
    title: str
    rationale: str
    kind: str = "semantic_mapping"
    target_ids: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    migration_steps: list[str] = Field(default_factory=list)


class RepairProposal(BaseModel):
    schema_version: str = "1.0"
    provider: ProviderKind
    model: str = ""
    repairs: list[ProposedRepair] = Field(default_factory=list)
    latency_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    dropped_references: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Model Arena
# --------------------------------------------------------------------------------------


class ProviderRunMetrics(BaseModel):
    provider: ProviderKind
    model: str = ""
    ok: bool = True
    error: str = ""
    latency_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    valid_structured_output: bool = True
    retries: int = 0
    entities: int = 0
    relations: int = 0
    aliases: int = 0
    domains: int = 0
    risks: int = 0
    hallucinated_references: int = 0
    rationale: str = ""


class ArenaRelation(BaseModel):
    source_id: str
    target_id: str
    relation: str
    providers: list[ProviderKind] = Field(default_factory=list)
    confidences: dict[str, float] = Field(default_factory=dict)
    rationales: dict[str, str] = Field(default_factory=dict)
    verdict: str = "consensus"  # consensus | ollama_only | kimi_only | conflict


class ArenaComparison(BaseModel):
    schema_version: str = "1.0"
    project_id: str
    task: TaskKind = TaskKind.ENRICH
    metrics: list[ProviderRunMetrics] = Field(default_factory=list)
    consensus: list[ArenaRelation] = Field(default_factory=list)
    only_a: list[ArenaRelation] = Field(default_factory=list)
    only_b: list[ArenaRelation] = Field(default_factory=list)
    conflicts: list[ArenaRelation] = Field(default_factory=list)
    alias_agreement: dict[str, Any] = Field(default_factory=dict)
    domain_agreement: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class DecisionRecord(BaseModel):
    """Immutable audit entry. Written once, never edited."""

    id: str
    project_id: str
    timestamp: str
    provider: ProviderKind | None = None
    model: str = ""
    prompt_template_version: str = ""
    task: str = ""
    action: str = Field(description="accept_ollama | accept_kimi | merge | reject_both | edit")
    subject: str = ""
    accepted_payload: dict[str, Any] = Field(default_factory=dict)
    editor: str = "local-user"
    source_references: list[str] = Field(default_factory=list)
    payload_fingerprint: str = ""
