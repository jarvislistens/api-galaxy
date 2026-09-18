"""The canonical graph model: nodes, edges, provenance and the graph document itself.

Two rules are load-bearing for the whole product:

1. **Every** node and edge carries a :class:`Provenance` record. There is no way to add
   something to the graph without saying where it came from.
2. Deterministic facts and model inferences live in the same graph but are never merged.
   ``source_kind`` plus ``acceptance`` is what the UI renders as solid / dashed / dotted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

GRAPH_SCHEMA_VERSION = "1.0"


def utcnow() -> datetime:
    return datetime.now(UTC)


class NodeType(str, Enum):
    ESTATE = "Estate"
    DOMAIN = "Domain"
    SERVICE = "Service"
    SERVER = "Server"
    API_OPERATION = "APIOperation"
    ENDPOINT = "Endpoint"
    SCHEMA = "Schema"
    FIELD = "Field"
    SECURITY_SCHEME = "SecurityScheme"
    BUSINESS_ENTITY = "BusinessEntity"
    CAPABILITY = "Capability"
    JOURNEY = "Journey"
    JOURNEY_STEP = "JourneyStep"
    RISK = "Risk"
    SCENARIO = "Scenario"
    CHANGE = "Change"
    REPAIR = "Repair"
    EVIDENCE = "Evidence"


class EdgeType(str, Enum):
    CONTAINS = "CONTAINS"
    EXPOSES = "EXPOSES"
    USES_REQUEST = "USES_REQUEST"
    RETURNS = "RETURNS"
    REFERENCES = "REFERENCES"
    REQUIRES_SECURITY = "REQUIRES_SECURITY"
    BELONGS_TO_DOMAIN = "BELONGS_TO_DOMAIN"
    REPRESENTS = "REPRESENTS"
    CALLS_OR_PRECEDES = "CALLS_OR_PRECEDES"
    PART_OF_JOURNEY = "PART_OF_JOURNEY"
    DEPENDS_ON = "DEPENDS_ON"
    ALIAS_OF = "ALIAS_OF"
    CONTAINS_PII = "CONTAINS_PII"
    AFFECTS = "AFFECTS"
    BREAKS = "BREAKS"
    REPAIRED_BY = "REPAIRED_BY"
    INFERRED_RELATION = "INFERRED_RELATION"


class SourceKind(str, Enum):
    """Where a fact came from. This is the fact-vs-inference boundary."""

    SPECIFICATION = "specification"
    DETERMINISTIC_RULE = "deterministic_rule"
    BUNDLED_ANALYSIS = "bundled_analysis"
    AI_INFERENCE = "ai_inference"
    USER_EDIT = "user_edit"
    SCENARIO = "scenario"

    @property
    def is_fact(self) -> bool:
        return self in (SourceKind.SPECIFICATION, SourceKind.DETERMINISTIC_RULE)


class Acceptance(str, Enum):
    OBSERVED = "observed"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class Evidence(BaseModel):
    """A pointer back into the source material that justifies a node, edge or answer."""

    model_config = ConfigDict(frozen=True)

    id: str
    source_file: str
    pointer: str = Field(description="RFC 6901 JSON Pointer into the normalized spec.")
    excerpt: str = Field(default="", description="Short, escaped quote from the source.")
    label: str = ""

    @property
    def locator(self) -> str:
        return f"{self.source_file}#{self.pointer}"


class Provenance(BaseModel):
    """Why this object exists and how much you should trust it."""

    source_kind: SourceKind
    explanation: str = Field(description="Human-readable, one sentence, no jargon.")
    source_file: str | None = None
    source_pointer: str | None = None
    rule_id: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provider: str | None = None
    model: str | None = None
    prompt_template_version: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def is_fact(self) -> bool:
        return self.source_kind.is_fact


class GraphNode(BaseModel):
    id: str
    type: NodeType
    label: str
    project_id: str
    description: str = ""
    acceptance: Acceptance = Acceptance.OBSERVED
    provenance: Provenance
    attrs: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @property
    def is_fact(self) -> bool:
        return self.provenance.is_fact

    def display_group(self) -> str:
        """Which semantic-zoom level this node belongs to (1 = coarsest)."""
        return _ZOOM_LEVEL.get(self.type, "3")


class GraphEdge(BaseModel):
    id: str
    type: EdgeType
    source: str
    target: str
    label: str = ""
    acceptance: Acceptance = Acceptance.OBSERVED
    provenance: Provenance
    attrs: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)

    @property
    def is_fact(self) -> bool:
        return self.provenance.is_fact

    @property
    def stroke(self) -> str:
        """Visual encoding contract, computed once here so UI and export agree."""
        if self.provenance.source_kind is SourceKind.USER_EDIT:
            return "dotted"
        if self.provenance.source_kind in (SourceKind.AI_INFERENCE, SourceKind.BUNDLED_ANALYSIS):
            return "dashed"
        if self.provenance.source_kind is SourceKind.SCENARIO:
            return "dashed"
        return "solid"


_ZOOM_LEVEL: dict[NodeType, str] = {
    NodeType.ESTATE: "1",
    NodeType.DOMAIN: "1",
    NodeType.CAPABILITY: "1",
    NodeType.SERVICE: "2",
    NodeType.JOURNEY: "2",
    NodeType.BUSINESS_ENTITY: "2",
    NodeType.JOURNEY_STEP: "3",
    NodeType.API_OPERATION: "3",
    NodeType.ENDPOINT: "3",
    NodeType.SCHEMA: "3",
    NodeType.SERVER: "3",
    NodeType.SECURITY_SCHEME: "3",
    NodeType.RISK: "3",
    NodeType.FIELD: "4",
    NodeType.EVIDENCE: "4",
}


class GraphStats(BaseModel):
    nodes: int = 0
    edges: int = 0
    by_node_type: dict[str, int] = Field(default_factory=dict)
    by_edge_type: dict[str, int] = Field(default_factory=dict)
    observed_edges: int = Field(default=0, description="Stated by a specification or proved.")
    inferred_edges: int = Field(default=0, description="Suggested by a rule or a model.")
    user_edges: int = Field(default=0, description="Created or accepted by a person.")
    accepted_inferences: int = 0
    entities: int = 0
    capabilities: int = 0
    services: int = 0
    operations: int = 0
    schemas: int = 0
    fields: int = 0
    domains: int = 0
    journeys: int = 0
    risks: int = 0


class KnowledgeGraph(BaseModel):
    """A complete, self-describing graph document. This is what gets snapshotted."""

    model_config = ConfigDict(validate_assignment=False)

    schema_version: str = GRAPH_SCHEMA_VERSION
    project_id: str
    project_name: str
    spec_fingerprint: str = ""
    app_version: str = ""
    scenario_id: str | None = None
    generated_at: datetime = Field(default_factory=utcnow)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)

    # ---- indexing helpers -------------------------------------------------------
    #
    # `nodes`/`edges` stay plain lists so the document serialises cleanly, but every
    # lookup goes through a lazily-built dict. `_touch` invalidates it after mutation
    # through anything other than add_node/add_edge.

    _node_index: dict[str, GraphNode] = PrivateAttr(default_factory=dict)
    _edge_index: dict[str, GraphEdge] = PrivateAttr(default_factory=dict)

    def node_index(self) -> dict[str, GraphNode]:
        if len(self._node_index) != len(self.nodes):
            self._node_index = {node.id: node for node in self.nodes}
        return self._node_index

    def edge_index(self) -> dict[str, GraphEdge]:
        if len(self._edge_index) != len(self.edges):
            self._edge_index = {edge.id: edge for edge in self.edges}
        return self._edge_index

    def node_ids(self) -> set[str]:
        return set(self.node_index())

    def get(self, node_id: str) -> GraphNode | None:
        return self.node_index().get(node_id)

    def get_edge(self, edge_id_: str) -> GraphEdge | None:
        return self.edge_index().get(edge_id_)

    def nodes_of(self, node_type: NodeType) -> list[GraphNode]:
        return [n for n in self.nodes if n.type is node_type]

    def edges_of(self, edge_type: EdgeType) -> list[GraphEdge]:
        return [e for e in self.edges if e.type is edge_type]

    def add_node(self, node: GraphNode) -> GraphNode:
        """Idempotent insert. Re-adding an ID merges attrs but keeps first provenance."""
        existing = self.node_index().get(node.id)
        if existing is not None:
            existing.attrs.update(node.attrs)
            if node.description and not existing.description:
                existing.description = node.description
            for ev in node.evidence:
                if ev not in existing.evidence:
                    existing.evidence.append(ev)
            for tag in node.tags:
                if tag not in existing.tags:
                    existing.tags.append(tag)
            return existing
        self.nodes.append(node)
        self._node_index[node.id] = node
        return node

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        existing = self.edge_index().get(edge.id)
        if existing is not None:
            existing.attrs.update(edge.attrs)
            for ev in edge.evidence:
                if ev not in existing.evidence:
                    existing.evidence.append(ev)
            return existing
        self.edges.append(edge)
        self._edge_index[edge.id] = edge
        return edge

    def remove_node(self, node_id: str) -> None:
        """Remove a node and every edge incident to it. Used only by scenarios."""
        self.nodes = [n for n in self.nodes if n.id != node_id]
        self.edges = [e for e in self.edges if e.source != node_id and e.target != node_id]
        self._node_index = {}
        self._edge_index = {}

    def stats(self) -> GraphStats:
        stats = GraphStats(nodes=len(self.nodes), edges=len(self.edges))
        for node in self.nodes:
            stats.by_node_type[node.type.value] = stats.by_node_type.get(node.type.value, 0) + 1
        for edge in self.edges:
            stats.by_edge_type[edge.type.value] = stats.by_edge_type.get(edge.type.value, 0) + 1
            # "Observed" is the headline number the Overview contrasts with "inferred", so
            # it must mean *stated by the specification and not awaiting a human decision*.
            # A deterministic rule that only ever suggests (alias detection) belongs on the
            # inferred side even though its source kind is a fact.
            kind = edge.provenance.source_kind
            if kind is SourceKind.USER_EDIT:
                stats.user_edges += 1
            elif edge.acceptance is Acceptance.ACCEPTED:
                stats.accepted_inferences += 1
                stats.user_edges += 1
            elif kind.is_fact and edge.acceptance is Acceptance.OBSERVED:
                stats.observed_edges += 1
            elif edge.acceptance is Acceptance.REJECTED:
                pass
            else:
                stats.inferred_edges += 1
        stats.services = stats.by_node_type.get(NodeType.SERVICE.value, 0)
        stats.operations = stats.by_node_type.get(NodeType.API_OPERATION.value, 0)
        stats.schemas = stats.by_node_type.get(NodeType.SCHEMA.value, 0)
        stats.fields = stats.by_node_type.get(NodeType.FIELD.value, 0)
        stats.domains = stats.by_node_type.get(NodeType.DOMAIN.value, 0)
        stats.journeys = stats.by_node_type.get(NodeType.JOURNEY.value, 0)
        stats.risks = stats.by_node_type.get(NodeType.RISK.value, 0)
        stats.entities = stats.by_node_type.get(NodeType.BUSINESS_ENTITY.value, 0)
        stats.capabilities = stats.by_node_type.get(NodeType.CAPABILITY.value, 0)
        return stats

    def clone(self, *, scenario_id: str | None = None) -> KnowledgeGraph:
        """Deep copy. Scenarios always operate on a clone — the base is never mutated."""
        copy = self.model_copy(deep=True)
        # model_copy also deep-copies private attrs, which would leave the clone's index
        # pointing at *its own* stale snapshot. Reset it so lookups rebuild from `nodes`.
        copy._node_index = {}
        copy._edge_index = {}
        copy.scenario_id = scenario_id
        return copy
