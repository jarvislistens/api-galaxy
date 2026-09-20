"""The :class:`ReportBundle` — the single input every exporter is a pure function of.

Exports are the part of the product that leaves the building: they get pasted into
Confluence, attached to an architecture-review invite, and read by someone who was not
in the room. So the rule here is that an exporter may only read a bundle. It may not
reach back into the pipeline, the repository or the provider layer.

That buys three things:

* **Reproducibility** — same bundle in, same bytes out. A report can be regenerated and
  diffed against the one that was circulated.
* **Disclosure** — the fingerprint, app version, active scenario and provider live on
  the bundle, so no exporter can forget to state them.
* **Scoping** — :func:`scope_bundle` narrows the graph *once*, and every format then
  agrees on what "this journey" or "this domain" means.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from api_galaxy import __version__
from api_galaxy.analysis.impact import ASSUMPTIONS, LIMITATIONS
from api_galaxy.contracts.analysis import AliasCluster, Ambiguity, Journey, Risk
from api_galaxy.contracts.graph import (
    EdgeType,
    GraphNode,
    GraphStats,
    KnowledgeGraph,
    NodeType,
    SourceKind,
    utcnow,
)
from api_galaxy.contracts.providers import ArenaComparison, DecisionRecord
from api_galaxy.contracts.scenario import ImpactReport, Repair, Scenario
from api_galaxy.parsing.normalize import NormalizedEstate
from api_galaxy.pipeline import AnalysedProject

NO_PROVIDER = "none"
BUNDLED_PROVIDER = "Bundled Demo Analysis"

# Edges that mean "this node lives inside that node". Used when a scope has to be
# closed downwards — picking a domain has to bring its services, their operations, the
# schemas those operations use and the fields inside them.
_CONTAINMENT_EDGES = frozenset(
    {
        EdgeType.CONTAINS,
        EdgeType.EXPOSES,
        EdgeType.USES_REQUEST,
        EdgeType.RETURNS,
        EdgeType.REFERENCES,
        EdgeType.REQUIRES_SECURITY,
        EdgeType.PART_OF_JOURNEY,
    }
)


class LegendEntry(BaseModel):
    """One row of the fact-vs-inference key that every export must carry."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    stroke: str = Field(description="solid | dashed | dotted — matches GraphEdge.stroke.")
    dash_array: str = Field(description="SVG stroke-dasharray for this stroke.")
    meaning: str


class MethodologyNote(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    body: str


LEGEND: tuple[LegendEntry, ...] = (
    LegendEntry(
        id="specification",
        label="Specification fact",
        stroke="solid",
        dash_array="none",
        meaning="Stated directly by an OpenAPI document you imported. Nothing was guessed.",
    ),
    LegendEntry(
        id="deterministic_rule",
        label="Deterministic rule",
        stroke="solid",
        dash_array="none",
        meaning="Derived by a rule that always produces the same answer for the same input.",
    ),
    LegendEntry(
        id="ai_inference",
        label="Model inference",
        stroke="dashed",
        dash_array="6 4",
        meaning="Suggested by a language model or the bundled analysis. Treat as a proposal "
        "until a person accepts it.",
    ),
    LegendEntry(
        id="user_edit",
        label="Created by a person",
        stroke="dotted",
        dash_array="2 3",
        meaning="Added, edited or accepted by you in this workspace.",
    ),
    LegendEntry(
        id="scenario",
        label="Scenario change",
        stroke="dashed",
        dash_array="6 4",
        meaning="Exists only inside a Break Lab scenario. It is not part of the real estate.",
    ),
)

_LEGEND_BY_SOURCE_KIND: dict[SourceKind, LegendEntry] = {
    SourceKind.SPECIFICATION: LEGEND[0],
    SourceKind.DETERMINISTIC_RULE: LEGEND[1],
    SourceKind.BUNDLED_ANALYSIS: LEGEND[2],
    SourceKind.AI_INFERENCE: LEGEND[2],
    SourceKind.USER_EDIT: LEGEND[3],
    SourceKind.SCENARIO: LEGEND[4],
}


def legend_for(source_kind: SourceKind) -> LegendEntry:
    return _LEGEND_BY_SOURCE_KIND.get(source_kind, LEGEND[0])


METHODOLOGY: tuple[MethodologyNote, ...] = (
    MethodologyNote(
        title="Deterministic parse first",
        body="Every specification is parsed, $ref-resolved and normalised before anything "
        "else runs. Services, endpoints, operations, schemas, fields, security schemes and "
        "declared dependencies are read straight out of the documents. This step involves no "
        "model and produces the same graph byte-for-byte on every run.",
    ),
    MethodologyNote(
        title="Rules next, and they are labelled",
        body="Deterministic rules add findings a parser cannot: unsecured operations, "
        "personally identifiable fields, inconsistent naming, unbounded collections. Rules "
        "that prove something are marked Deterministic; rules that recognise a pattern and "
        "may be wrong are marked Heuristic. Both carry the rule identifier that produced them.",
    ),
    MethodologyNote(
        title="A model is used only for semantics",
        body="Language models are asked one narrow question at a time — what business domain "
        "is this, what does this journey do, do these two field names mean the same thing — "
        "and are handed a whitelist of node identifiers they are allowed to reference. "
        "Anything they invent outside that list is discarded before it reaches the graph. "
        "A model never changes a fact read from a specification.",
    ),
    MethodologyNote(
        title="Provenance on everything",
        body="Every node and every relationship in this report carries a provenance record: "
        "where it came from, which rule or model produced it, how confident that source was, "
        "and a one-sentence explanation. The diagrams encode it as line style — solid for "
        "specification facts, dashed for inference, dotted for human edits — so you can see "
        "the boundary without reading a table.",
    ),
    MethodologyNote(
        title="Impact is a statement about the specification, not a prediction",
        body="Break Lab answers 'what does the specification say would stop matching if I "
        "made this change'. It is not a production forecast. It cannot see undocumented "
        "consumers, tolerant readers, feature flags, or traffic. Read the blast radius as a "
        "list of conversations to have, not as an outage estimate.",
    ),
)

EXPORT_LIMITATIONS: tuple[str, ...] = (
    "This report describes the specifications that were imported. Services, consumers or "
    "message flows that were never documented cannot appear in it.",
    "Business domains, journeys, capabilities and alias suggestions are inferences. They are "
    "labelled as such and should be reviewed by someone who owns the systems.",
    "Confidence scores are the producing source's own estimate. They are comparable within a "
    "single run and should not be read as probabilities.",
    "A diagram of a large estate is necessarily a summary. Where nodes were omitted to keep "
    "the picture readable, the report says so and the machine-readable exports still contain "
    "the full graph.",
)


class ReportBundle(BaseModel):
    """Everything any exporter is allowed to know, and nothing else."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_id: str
    project_name: str
    generated_at: datetime = Field(default_factory=utcnow)
    spec_fingerprint: str = ""
    app_version: str = __version__
    active_scenario: str | None = None
    # Carried so write-back can diff against the documents exactly as imported. Excluded
    # from every serialised report — it is the user's source, not report content.
    estate: NormalizedEstate | None = Field(default=None, exclude=True, repr=False)
    # The scenario object itself, for write-back. Reports render `impact` and `repairs`;
    # only the patch needs the raw change list. Excluded from serialisation alongside the
    # estate so no report grows a copy of it.
    scenario: Scenario | None = Field(default=None, exclude=True, repr=False)
    # The graph *before* the scenario was applied. `graph` holds the scenario graph so
    # reports show the changed estate, but applying a change rewrites the affected node's
    # provenance — so write-back has to read source locations from here instead.
    base_graph: KnowledgeGraph | None = Field(default=None, exclude=True, repr=False)
    provider_disclosure: str = Field(
        default=BUNDLED_PROVIDER,
        description="Which provider and model produced any inference in this report.",
    )
    scope_label: str = "Whole estate"

    graph: KnowledgeGraph
    stats: GraphStats
    risks: list[Risk] = Field(default_factory=list)
    journeys: list[Journey] = Field(default_factory=list)
    alias_clusters: list[AliasCluster] = Field(default_factory=list)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    impact: ImpactReport | None = None
    repairs: list[Repair] = Field(default_factory=list)
    arena: ArenaComparison | None = None
    decisions: list[DecisionRecord] = Field(default_factory=list)

    methodology: list[MethodologyNote] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    legend: list[LegendEntry] = Field(default_factory=list)

    _domains: dict[str, str] | None = PrivateAttr(default=None)

    # -- convenience used by every exporter ------------------------------------------

    @property
    def slug(self) -> str:
        from api_galaxy.contracts.ids import slugify

        return slugify(self.project_name or self.project_id)

    @property
    def generated_at_text(self) -> str:
        return self.generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")

    @property
    def filename_stem(self) -> str:
        stamp = self.generated_at.strftime("%Y%m%d-%H%M%S")
        return f"api-galaxy-{self.slug}-{stamp}"

    def nodes_of(self, node_type: NodeType) -> list[GraphNode]:
        return self.graph.nodes_of(node_type)

    def domain_of(self, node_id: str) -> str | None:
        return self._domain_map().get(node_id)

    def _domain_map(self) -> dict[str, str]:
        """node id → domain label, following BELONGS_TO_DOMAIN then containment."""
        if self._domains is not None:
            return self._domains
        index = self.graph.node_index()
        direct: dict[str, str] = {}
        for edge in self.graph.edges:
            if edge.type is not EdgeType.BELONGS_TO_DOMAIN:
                continue
            domain = index.get(edge.target)
            if domain is not None:
                direct.setdefault(edge.source, domain.label)
        # Children inherit their container's domain, which is what makes a per-domain
        # diagram able to include the schemas and fields under a service.
        for _ in range(4):
            for edge in self.graph.edges:
                if edge.type not in _CONTAINMENT_EDGES:
                    continue
                parent = direct.get(edge.source)
                if parent and edge.target not in direct:
                    direct[edge.target] = parent
        self._domains = direct
        return direct

    def journey(self, journey_id: str) -> Journey | None:
        return next((j for j in self.journeys if j.id == journey_id), None)

    def disclosure_rows(self) -> list[tuple[str, str]]:
        """The block every format prints near the top, in one place so they agree."""
        return [
            ("Project", self.project_name),
            ("Scope", self.scope_label),
            ("Generated", self.generated_at_text),
            ("Specification fingerprint", self.spec_fingerprint or "not recorded"),
            ("API Galaxy version", self.app_version),
            ("Active scenario", self.active_scenario or "none — this is the imported estate"),
            ("Semantic analysis by", self.provider_disclosure),
        ]


# --------------------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------------------


def build_bundle(
    project: AnalysedProject,
    *,
    scenario: Scenario | None = None,
    impact: ImpactReport | None = None,
    arena: ArenaComparison | None = None,
    decisions: Sequence[DecisionRecord] | None = None,
    provider_disclosure: str = BUNDLED_PROVIDER,
    graph: KnowledgeGraph | None = None,
) -> ReportBundle:
    """Snapshot an analysed project into the form every exporter consumes.

    ``graph`` lets a caller pass the *scenario* graph while the rest of the analysis
    still comes from the base project, which is exactly what the Break Lab export does.
    """
    source_graph = graph or project.graph
    limitations = list(EXPORT_LIMITATIONS)
    methodology = list(METHODOLOGY)

    if impact is not None:
        methodology.append(
            MethodologyNote(
                title="How this scenario was evaluated",
                body="The change was applied to a copy of the graph — the imported estate is "
                "never modified — and the blast radius was walked outwards along declared "
                "dependency edges. "
                + " ".join(impact.assumptions or ASSUMPTIONS),
            )
        )
        limitations.extend(impact.limitations or LIMITATIONS)
    else:
        limitations.extend(LIMITATIONS)

    return ReportBundle(
        project_id=project.project_id,
        project_name=project.project_name,
        generated_at=utcnow(),
        spec_fingerprint=project.fingerprint,
        app_version=__version__,
        active_scenario=scenario.name if scenario is not None else None,
        estate=project.estate,
        scenario=scenario,
        base_graph=project.graph,
        provider_disclosure=provider_disclosure or NO_PROVIDER,
        graph=source_graph,
        stats=source_graph.stats(),
        risks=list(project.risks),
        journeys=list(project.journeys),
        alias_clusters=list(project.alias_clusters),
        ambiguities=list(project.ambiguities),
        impact=impact,
        repairs=list(scenario.repairs) if scenario is not None else [],
        arena=arena,
        decisions=list(decisions or []),
        methodology=methodology,
        limitations=_dedupe(limitations),
        legend=list(LEGEND),
    )


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


# --------------------------------------------------------------------------------------
# Scoping
# --------------------------------------------------------------------------------------


def scope_bundle(
    bundle: ReportBundle,
    *,
    node_ids: Iterable[str] | None = None,
    journey_id: str | None = None,
    domain_id: str | None = None,
    label: str | None = None,
) -> ReportBundle:
    """Narrow a bundle to the current view, one journey, one domain or an explicit set.

    The returned bundle is a *complete* bundle: it keeps the disclosure block, the
    legend and the methodology, so a scoped export is still self-describing. Only the
    graph and the analysis products that reference it shrink.
    """
    keep: set[str] = set()
    scope_label = label or bundle.scope_label

    if node_ids is not None:
        keep |= {nid for nid in node_ids if bundle.graph.get(nid) is not None}
        scope_label = label or "Current view"

    if journey_id is not None:
        journey = bundle.journey(journey_id)
        if journey is None:
            raise KeyError(f"No journey '{journey_id}' in this bundle.")
        keep |= _journey_node_ids(bundle, journey)
        scope_label = label or f"Journey: {journey.name}"

    if domain_id is not None:
        domain = bundle.graph.get(domain_id)
        if domain is None:
            raise KeyError(f"No domain '{domain_id}' in this bundle.")
        keep |= _domain_node_ids(bundle, domain_id)
        scope_label = label or f"Domain: {domain.label}"

    if not keep:
        return bundle

    scoped_graph = KnowledgeGraph(
        schema_version=bundle.graph.schema_version,
        project_id=bundle.graph.project_id,
        project_name=bundle.graph.project_name,
        spec_fingerprint=bundle.graph.spec_fingerprint,
        app_version=bundle.graph.app_version,
        scenario_id=bundle.graph.scenario_id,
        generated_at=bundle.graph.generated_at,
        nodes=[n for n in bundle.graph.nodes if n.id in keep],
        edges=[e for e in bundle.graph.edges if e.source in keep and e.target in keep],
        diagnostics=list(bundle.graph.diagnostics),
    )

    journeys = [
        j
        for j in bundle.journeys
        if (journey_id is None or j.id == journey_id)
        and (not j.steps or any(keep & set(s.node_ids) for s in j.steps))
    ]

    scoped = bundle.model_copy(
        update={
            "graph": scoped_graph,
            "stats": scoped_graph.stats(),
            "scope_label": scope_label,
            "risks": [r for r in bundle.risks if not r.node_ids or keep & set(r.node_ids)],
            "journeys": journeys,
            "alias_clusters": [c for c in bundle.alias_clusters if keep & set(c.members)],
            "ambiguities": [a for a in bundle.ambiguities if keep & set(a.node_ids)],
        }
    )
    # model_copy carries the memoised domain map across, and it describes the *old*
    # graph. Clear it so the next lookup rebuilds against the scoped edges.
    scoped._domains = None
    return scoped


def _journey_node_ids(bundle: ReportBundle, journey: Journey) -> set[str]:
    """Everything a journey touches, plus the containers that make it readable."""
    keep: set[str] = {journey.id}
    for step in journey.steps:
        keep.add(step.id)
        keep.update(step.node_ids)
        keep.update(step.schema_ids)
        if step.service_id:
            keep.add(step.service_id)
        if step.operation_id:
            keep.add(step.operation_id)
    keep.update(journey.domain_ids)

    # One hop up to the owning domain so the diagram can group the steps. Computed from
    # the original `keep` so a domain does not then pull in unrelated siblings.
    anchored = set(keep)
    for edge in bundle.graph.edges:
        if edge.type is EdgeType.BELONGS_TO_DOMAIN and edge.source in anchored:
            keep.add(edge.target)

    index = bundle.graph.node_index()
    return {nid for nid in keep if nid in index}


def _domain_node_ids(bundle: ReportBundle, domain_id: str) -> set[str]:
    domain = bundle.graph.get(domain_id)
    if domain is None:
        return set()
    keep = {domain_id}
    keep |= {
        node_id
        for node_id, domain_label in bundle._domain_map().items()
        if domain_label == domain.label
    }
    index = bundle.graph.node_index()
    return {nid for nid in keep if nid in index}
