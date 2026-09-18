"""The ingestion pipeline: specifications in, analysed knowledge graph out.

This is the single place that defines the order of operations, so the API, the CLI, the
tests and the demo loader all produce byte-identical results for the same input.

    parse → build graph → deterministic rules → alias clusters → journeys → attach

AI enrichment is deliberately *not* part of this function. It runs afterwards, adds
separately-labelled nodes and edges, and can be re-run or discarded without re-parsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from api_galaxy import __version__
from api_galaxy.analysis.aliases import detect_alias_clusters
from api_galaxy.analysis.journeys import attach_journeys_to_graph, derive_journeys
from api_galaxy.analysis.pii import PiiDictionary
from api_galaxy.analysis.rules import attach_risks_to_graph, risk_id, run_rules
from api_galaxy.contracts.analysis import (
    AliasCluster,
    Ambiguity,
    Journey,
    Risk,
    RiskCategory,
    RiskSeverity,
)
from api_galaxy.contracts.graph import (
    Acceptance,
    EdgeType,
    GraphEdge,
    KnowledgeGraph,
    Provenance,
    SourceKind,
)
from api_galaxy.contracts.ids import edge_id, slugify
from api_galaxy.enrichment.bundled import BUNDLED_LABEL, apply_bundled_analysis, load_bundled_analysis
from api_galaxy.graph.builder import build_graph
from api_galaxy.parsing.loader import load_estate_manifest
from api_galaxy.parsing.normalize import NormalizedEstate
from api_galaxy.parsing.openapi import parse_estate


@dataclass
class AnalysedProject:
    """Everything the product knows about one project, before any model runs."""

    project_id: str
    project_name: str
    estate: NormalizedEstate
    graph: KnowledgeGraph
    risks: list[Risk] = field(default_factory=list)
    journeys: list[Journey] = field(default_factory=list)
    alias_clusters: list[AliasCluster] = field(default_factory=list)
    ambiguities: list[Ambiguity] = field(default_factory=list)
    enrichment_label: str = "none"
    enrichment_warnings: list[str] = field(default_factory=list)

    @property
    def fingerprint(self) -> str:
        return self.estate.fingerprint


def analyse(
    estate: NormalizedEstate,
    *,
    project_id: str,
    project_name: str,
    dictionary: PiiDictionary | None = None,
    bundled_dir: str | Path | None = None,
) -> AnalysedProject:
    graph = build_graph(estate, project_id=project_id, project_name=project_name)
    graph.app_version = __version__

    risks = run_rules(estate, graph, dictionary=dictionary)
    clusters = detect_alias_clusters(estate)
    alias_risks, ambiguities = _alias_findings(clusters)
    risks.extend(alias_risks)
    risks.sort(key=lambda r: (r.severity.rank, r.rule_id, r.id))

    _attach_alias_edges(graph, clusters)
    attach_risks_to_graph(graph, risks)

    journeys = derive_journeys(estate)
    enrichment_label = "none"
    warnings: list[str] = []

    if bundled_dir is not None:
        bundle = load_bundled_analysis(bundled_dir)
        if not bundle.is_empty:
            curated, warnings = apply_bundled_analysis(graph, estate, bundle)
            if curated:
                # Curated journeys fully replace the mechanically-derived ones: showing
                # both would mean two "Place Order"s in the sidebar, one of them worse.
                journeys = curated
            enrichment_label = BUNDLED_LABEL

    attach_journeys_to_graph(graph, journeys)

    return AnalysedProject(
        project_id=project_id,
        project_name=project_name,
        estate=estate,
        graph=graph,
        risks=risks,
        journeys=journeys,
        alias_clusters=clusters,
        ambiguities=ambiguities,
        enrichment_label=enrichment_label,
        enrichment_warnings=warnings,
    )


def analyse_paths(
    paths: list[tuple[str, str, str | None]],
    *,
    project_id: str,
    project_name: str,
    estate_name: str | None = None,
    description: str = "",
    bundled_dir: str | Path | None = None,
) -> AnalysedProject:
    estate = parse_estate(
        paths, name=estate_name or project_name, description=description, from_paths=True
    )
    return analyse(
        estate, project_id=project_id, project_name=project_name, bundled_dir=bundled_dir
    )


def analyse_manifest(
    manifest_path: str | Path,
    *,
    project_id: str,
    project_name: str | None = None,
    use_bundled_analysis: bool = True,
) -> AnalysedProject:
    """Import a multi-file estate. If reference analysis files sit next to the manifest,
    they are loaded as the Bundled Demo Analysis so the demo works with no model."""
    manifest = load_estate_manifest(manifest_path)
    sources = [(svc.file, svc.name, svc.domain) for svc in manifest.services]
    return analyse_paths(
        sources,
        project_id=project_id,
        project_name=project_name or manifest.name,
        estate_name=manifest.name,
        description=manifest.description,
        bundled_dir=Path(manifest_path).resolve().parent if use_bundled_analysis else None,
    )


# --------------------------------------------------------------------------------------
# Alias findings
# --------------------------------------------------------------------------------------


def _alias_findings(clusters: list[AliasCluster]) -> tuple[list[Risk], list[Ambiguity]]:
    risks: list[Risk] = []
    ambiguities: list[Ambiguity] = []
    for cluster in clusters:
        distinct_names = {label.rsplit(".", 1)[-1] for label in cluster.member_labels}
        if len(distinct_names) < 2:
            continue
        risks.append(
            Risk(
                id=risk_id("alias-ambiguity", cluster.id),
                rule_id="alias-ambiguity",
                severity=RiskSeverity.MEDIUM,
                category=RiskCategory.AMBIGUITY,
                title=f"'{cluster.canonical_name}' is spelled {len(distinct_names)} different ways",
                description=(
                    f"{', '.join(sorted(distinct_names))} all appear to identify the same "
                    f"{cluster.canonical_name}. {cluster.rationale}"
                ),
                recommendation="Agree one canonical name, publish a mapping for the others, "
                "and record the decision so it survives the next refactor.",
                heuristic=True,
                node_ids=list(cluster.members),
                provenance=cluster.provenance,
            )
        )
        ambiguities.append(
            Ambiguity(
                id=f"ambiguity:{cluster.id.split(':', 1)[-1]}",
                title=f"Conflicting names for '{cluster.canonical_name}'",
                description=cluster.rationale,
                node_ids=list(cluster.members),
                kind="alias",
                provenance=cluster.provenance,
            )
        )
    return risks, ambiguities


def _attach_alias_edges(graph: KnowledgeGraph, clusters: list[AliasCluster]) -> None:
    """Alias edges are *proposed*, never observed — a human accepts them in the inspector."""
    for cluster in clusters:
        members = [m for m in cluster.members if graph.get(m) is not None]
        for index, source in enumerate(members):
            for target in members[index + 1 :]:
                graph.add_edge(
                    GraphEdge(
                        id=edge_id(EdgeType.ALIAS_OF.value, source, target),
                        type=EdgeType.ALIAS_OF,
                        source=source,
                        target=target,
                        label="may be the same as",
                        acceptance=Acceptance.PROPOSED,
                        provenance=Provenance(
                            source_kind=SourceKind.DETERMINISTIC_RULE,
                            rule_id="alias-detection",
                            explanation=cluster.rationale,
                            confidence=cluster.confidence,
                        ),
                        attrs={
                            "cluster": cluster.id,
                            "canonical": cluster.canonical_name,
                            "confidence": cluster.confidence,
                        },
                    )
                )


def demo_project_id(name: str = "NovaCart") -> str:
    return f"demo-{slugify(name)}"
