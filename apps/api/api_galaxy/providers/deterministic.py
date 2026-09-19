"""The zero-model provider.

This exists so that *nothing* in API Galaxy requires a language model to be useful. It
answers the same interface as Ollama and Kimi, but every output is computed from the
graph by code — which means it is instant, reproducible, offline, and correct by
construction about facts (it just can't be creative about meaning).

It is also the fallback the Model Arena compares against, and the reason the bundled demo
works on a laptop with nothing installed.
"""

from __future__ import annotations

import time

from api_galaxy.analysis.aliases import looks_like_identifier
from api_galaxy.contracts.graph import EdgeType, KnowledgeGraph, NodeType
from api_galaxy.contracts.providers import (
    AnswerEvidence,
    EnrichmentRequest,
    EnrichmentResult,
    GraphAnswer,
    GraphQuestionRequest,
    InferredAlias,
    InferredCapability,
    InferredDomain,
    InferredEntity,
    InferredJourney,
    InferredRelation,
    ProviderHealth,
    ProviderKind,
    ProviderStatus,
    RepairProposal,
    RepairRequest,
)
from api_galaxy.graph.engine import NetworkXGraphRepository, QueryLimits

MODEL_NAME = "deterministic-v1"


class DeterministicProvider:
    """Graph-derived semantics. No network, no model, no variance."""

    kind = ProviderKind.DETERMINISTIC

    def __init__(self, graph: KnowledgeGraph | None = None) -> None:
        self.graph = graph

    def bind(self, graph: KnowledgeGraph) -> DeterministicProvider:
        """Attach a graph. The API rebinds per request rather than holding state."""
        self.graph = graph
        return self

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            kind=self.kind,
            status=ProviderStatus.READY,
            model=MODEL_NAME,
            detail="Always available. Computes semantics from the graph with no model.",
            external=False,
            latency_ms=0.0,
        )

    # ---------------------------------------------------------------- enrichment

    async def enrich(self, request: EnrichmentRequest) -> EnrichmentResult:
        started = time.perf_counter()
        graph = self.graph
        result = EnrichmentResult(
            provider=self.kind,
            model=MODEL_NAME,
            prompt_template_version="n/a",
            rationale="Derived from the parsed specification: schemas become entities, "
            "tags and services become domains and capabilities, declared dependency "
            "chains become journeys, and identifier stems become alias candidates.",
        )
        if graph is None:
            return result

        allowed = set(request.context.allowed_node_ids)
        index = graph.node_index()

        # Entities: schemas that other things point at are the ones that carry meaning.
        inbound: dict[str, int] = {}
        for edge in graph.edges:
            if edge.type in (EdgeType.RETURNS, EdgeType.USES_REQUEST, EdgeType.REFERENCES):
                inbound[edge.target] = inbound.get(edge.target, 0) + 1
        ranked = sorted(
            (n for n in graph.nodes_of(NodeType.SCHEMA) if n.id in allowed or not allowed),
            key=lambda n: (-inbound.get(n.id, 0), n.label),
        )
        for node in ranked[: request.max_items]:
            uses = inbound.get(node.id, 0)
            if uses == 0:
                continue
            result.entities.append(
                InferredEntity(
                    name=node.label,
                    description=node.description
                    or f"A {node.label} as modelled by {node.attrs.get('service', 'this estate')}.",
                    represented_by=[node.id],
                    confidence=min(0.9, 0.5 + uses / 20),
                )
            )

        for node in graph.nodes_of(NodeType.DOMAIN)[: request.max_items]:
            members = [
                e.source
                for e in graph.edges
                if e.type is EdgeType.BELONGS_TO_DOMAIN
                and e.target == node.id
                and e.source in index
                and index[e.source].type is NodeType.SERVICE
            ]
            result.domains.append(
                InferredDomain(
                    name=node.label,
                    description=node.description,
                    service_ids=members,
                    confidence=0.95,
                )
            )

        capabilities: dict[str, list[str]] = {}
        for node in graph.nodes_of(NodeType.API_OPERATION):
            for tag in node.tags or [str(node.attrs.get("service", "General"))]:
                capabilities.setdefault(tag, []).append(node.id)
        for name, operation_ids in sorted(capabilities.items())[: request.max_items]:
            result.capabilities.append(
                InferredCapability(
                    name=name,
                    description=f"Everything the estate can do under the '{name}' heading.",
                    operation_ids=operation_ids[:12],
                    confidence=0.8,
                )
            )

        for node in graph.nodes_of(NodeType.JOURNEY)[: request.max_items]:
            steps = sorted(
                (
                    index[e.source]
                    for e in graph.edges
                    if e.type is EdgeType.PART_OF_JOURNEY
                    and e.target == node.id
                    and e.source in index
                    and index[e.source].type is NodeType.JOURNEY_STEP
                ),
                key=lambda n: int(n.attrs.get("order", 0)),
            )
            result.journeys.append(
                InferredJourney(
                    name=node.label,
                    description=node.description,
                    operation_ids=[
                        str(s.attrs.get("operation_id")) for s in steps if s.attrs.get("operation_id")
                    ],
                    narrations=[str(s.attrs.get("narration", "")) for s in steps],
                    confidence=0.9,
                )
            )

        clusters: dict[str, list[str]] = {}
        for edge in graph.edges:
            if edge.type is not EdgeType.ALIAS_OF:
                continue
            canonical = str(edge.attrs.get("canonical") or "concept")
            members = clusters.setdefault(canonical, [])
            for node_id in (edge.source, edge.target):
                if node_id not in members:
                    members.append(node_id)
        for canonical, members in sorted(clusters.items()):
            result.aliases.append(
                InferredAlias(
                    canonical_name=canonical,
                    member_ids=members,
                    rationale="Identifier stems and descriptions resolve to the same concept.",
                    confidence=0.75,
                )
            )

        for edge in graph.edges:
            if edge.type is EdgeType.DEPENDS_ON and edge.source in index and edge.target in index:
                result.relations.append(
                    InferredRelation(
                        source_id=edge.source,
                        target_id=edge.target,
                        relation="DEPENDS_ON",
                        rationale=edge.provenance.explanation,
                        confidence=1.0 if edge.is_fact else 0.6,
                    )
                )
        result.relations = result.relations[: request.max_items]
        result.latency_ms = (time.perf_counter() - started) * 1000
        return result

    # ------------------------------------------------------------------- answers

    async def answer(self, request: GraphQuestionRequest) -> GraphAnswer:
        started = time.perf_counter()
        graph = self.graph
        if graph is None:
            return GraphAnswer(
                provider=self.kind,
                model=MODEL_NAME,
                answer="No project is loaded.",
                confidence=0.0,
            )

        question = request.question.strip()
        lowered = question.lower()
        index = graph.node_index()
        repo = NetworkXGraphRepository(graph)
        intent = classify_intent(lowered)

        # Intent is decided before any matcher runs. Without this, "what depends on
        # customer_id?" scores highly against the *Register Customer* journey — the words
        # overlap — and the user gets a tour instead of an answer.
        if intent == "ambiguity":
            return self._ambiguity_answer(graph, index, started)

        if intent == "risk":
            return self._risk_answer(graph, index, started)

        if intent == "dependency":
            targets = _match_fields(graph, lowered)
            if targets:
                return self._dependency_answer(
                    graph, index, repo, targets, question, lowered, started
                )
            # "Which endpoints touch customer data?" names no field. Fall back to the
            # schemas the question names and report the operations that exchange them.
            schemas = _match_schemas(graph, lowered)
            if schemas:
                return self._schema_usage_answer(graph, index, schemas, lowered, started)
            return self._search_answer(graph, index, question, started)

        # A question that explicitly asks for a flow gets a lower bar than a vague one.
        journey = _match_journey(
            graph, index, lowered, threshold=2.0 if intent == "journey" else 3.0
        )
        if journey is not None:
            return self._journey_answer(graph, index, journey, started)

        targets = _match_fields(graph, lowered)
        if targets:
            return self._dependency_answer(graph, index, repo, targets, question, lowered, started)

        return self._search_answer(graph, index, question, started)

    def _journey_answer(self, graph, index, journey, started) -> GraphAnswer:
        steps = sorted(
            (
                index[e.source]
                for e in graph.edges
                if e.type is EdgeType.PART_OF_JOURNEY
                and e.target == journey.id
                and e.source in index
                and index[e.source].type is NodeType.JOURNEY_STEP
            ),
            key=lambda n: int(n.attrs.get("order", 0)),
        )
        operations = [str(s.attrs.get("operation_id")) for s in steps if s.attrs.get("operation_id")]
        narration = " ".join(str(s.attrs.get("narration", "")).strip() for s in steps).strip()
        services = []
        for operation_id in operations:
            node = index.get(operation_id)
            if node is None:
                continue
            service = str(node.attrs.get("service", ""))
            if service and service not in services:
                services.append(service)

        return GraphAnswer(
            provider=self.kind,
            model=MODEL_NAME,
            answer=(
                f"{journey.label} runs in {len(steps)} steps across "
                f"{len(services)} service(s): {', '.join(services)}. "
                + (narration if narration else journey.description)
            ).strip(),
            technical_explanation="\n".join(
                f"{s.attrs.get('order')}. {s.attrs.get('technical_detail') or s.label}"
                for s in steps
            ),
            highlighted_node_ids=[journey.id, *[s.id for s in steps], *operations],
            path=operations,
            evidence=[
                AnswerEvidence(
                    node_id=operation_id,
                    label=index[operation_id].label if operation_id in index else operation_id,
                    why=f"Step {position} of {journey.label}.",
                )
                for position, operation_id in enumerate(operations, start=1)
                if operation_id in index
            ],
            inference_note=(
                ""
                if journey.provenance.source_kind.is_fact
                else f"The journey itself was proposed by {journey.provenance.provider or 'analysis'}; "
                "each individual step is a specification fact."
            ),
            confidence=0.9,
            coverage=1.0,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def _dependency_answer(self, graph, index, repo, targets, question, lowered, started) -> GraphAnswer:  # noqa: ARG002
        highlighted: list[str] = []
        evidence: list[AnswerEvidence] = []
        operations: list[str] = []
        services: set[str] = set()
        aliases: list[str] = []

        for target in targets[:6]:
            highlighted.append(target.id)
            for edge in graph.edges:
                if edge.type is EdgeType.ALIAS_OF and target.id in (edge.source, edge.target):
                    other = edge.target if edge.source == target.id else edge.source
                    if other in index and other not in aliases:
                        aliases.append(other)
            for dependent_id, distance, _chain in repo.dependents(
                target.id, limits=QueryLimits(max_depth=4, max_nodes=300)
            ):
                node = index.get(dependent_id)
                if node is None:
                    continue
                highlighted.append(dependent_id)
                if node.type is NodeType.API_OPERATION:
                    operations.append(dependent_id)
                    services.add(str(node.attrs.get("service", "")))
                    if len(evidence) < 14:
                        evidence.append(
                            AnswerEvidence(
                                node_id=dependent_id,
                                label=node.label,
                                why=f"Reaches '{target.label}' in {distance} hop(s).",
                            )
                        )

        highlighted.extend(aliases)
        names = sorted({t.label.split(".")[-1] for t in targets})
        # "Other" means a different spelling, not a different node. The same field name in
        # two services is one name; listing it as an alias of itself reads as nonsense.
        alias_labels = sorted(
            {index[a].label.split(".")[-1] for a in aliases if a in index} - set(names)
        )
        answer = (
            f"{', '.join(names)} is used by {len(set(operations))} operation(s) across "
            f"{len([s for s in services if s])} service(s)"
            + (f": {', '.join(sorted(s for s in services if s))}." if services else ".")
        )
        if alias_labels:
            answer += (
                f" It also appears under {len(alias_labels)} other name(s) — "
                f"{', '.join(alias_labels)} — so a change here reaches further than the name suggests."
            )
        if not operations:
            answer = (
                f"{', '.join(names)} exists in the estate but nothing in the specification "
                "declares a dependency on it."
            )

        return GraphAnswer(
            provider=self.kind,
            model=MODEL_NAME,
            answer=answer,
            technical_explanation="\n".join(
                f"- {index[o].label} ({index[o].attrs.get('service')})"
                for o in sorted(set(operations))
                if o in index
            ),
            highlighted_node_ids=_dedupe(highlighted)[:120],
            path=repo.evidence_path([targets[0].id, *sorted(set(operations))[:4]]),
            evidence=evidence,
            inference_note=(
                "Alias links are suggestions from the deterministic alias rule, not "
                "statements in the specification."
                if aliases
                else ""
            ),
            confidence=0.85 if operations else 0.5,
            coverage=min(1.0, len(set(operations)) / max(1, len(graph.nodes_of(NodeType.API_OPERATION)))),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def _schema_usage_answer(self, graph, index, schemas, lowered, started) -> GraphAnswer:
        """Which operations exchange the schemas the question named."""
        wants_sensitive = any(
            word in lowered for word in ("sensitive", "personal", "pii", "private", "data")
        )
        schema_ids = {s.id for s in schemas}
        operations: dict[str, str] = {}
        for edge in graph.edges:
            if edge.type not in (EdgeType.RETURNS, EdgeType.USES_REQUEST):
                continue
            if edge.target not in schema_ids:
                continue
            node = index.get(edge.source)
            if node is None or node.type is not NodeType.API_OPERATION:
                continue
            verb = "returns" if edge.type is EdgeType.RETURNS else "accepts"
            operations[edge.source] = f"{verb} {index[edge.target].label}"

        unsecured = [
            node_id for node_id in operations if not index[node_id].attrs.get("security")
        ]
        services = sorted({str(index[o].attrs.get("service", "")) for o in operations} - {""})
        names = ", ".join(sorted({s.label for s in schemas})[:6])
        answer = (
            f"{len(operations)} operation(s) across {len(services)} service(s) exchange "
            f"{names}: {', '.join(services)}."
        )
        if unsecured:
            answer += (
                f" {len(unsecured)} of them declare no authentication — "
                + ", ".join(index[o].label for o in unsecured[:3])
                + "."
            )
        elif wants_sensitive:
            answer += " All of them require authentication."

        return GraphAnswer(
            provider=self.kind,
            model=MODEL_NAME,
            answer=answer,
            technical_explanation="\n".join(
                f"- {index[o].label} ({index[o].attrs.get('service')}) {why}"
                for o, why in sorted(operations.items())
            ),
            highlighted_node_ids=_dedupe([*schema_ids, *operations])[:120],
            evidence=[
                AnswerEvidence(node_id=o, label=index[o].label, why=why)
                for o, why in sorted(operations.items())[:14]
            ],
            inference_note="",
            confidence=0.85 if operations else 0.4,
            coverage=min(
                1.0, len(operations) / max(1, len(graph.nodes_of(NodeType.API_OPERATION)))
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def _ambiguity_answer(self, graph, index, started) -> GraphAnswer:
        clusters = alias_clusters_of(graph, index)
        if not clusters:
            return GraphAnswer(
                provider=self.kind,
                model=MODEL_NAME,
                answer="No conflicting definitions were detected in this estate.",
                confidence=0.7,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        lines: list[str] = []
        highlighted: list[str] = []
        evidence: list[AnswerEvidence] = []
        for canonical, members in sorted(clusters.items()):
            names = sorted({index[m].label.split(".")[-1] for m in members if m in index})
            lines.append(f"'{canonical}' appears as {', '.join(names)}")
            highlighted.extend(members)
            for member in sorted(members)[:4]:
                if member in index:
                    evidence.append(
                        AnswerEvidence(
                            node_id=member,
                            label=index[member].label,
                            why=f"One spelling of '{canonical}'.",
                        )
                    )
        return GraphAnswer(
            provider=self.kind,
            model=MODEL_NAME,
            answer=f"{len(clusters)} concept(s) are spelled more than one way. " + "; ".join(lines) + ".",
            technical_explanation="\n".join(lines),
            highlighted_node_ids=_dedupe(highlighted)[:120],
            evidence=evidence,
            inference_note="These groupings are heuristic. Accept or reject each one in the "
            "inspector to make it part of the model.",
            confidence=0.7,
            coverage=1.0,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def _risk_answer(self, graph, index, started) -> GraphAnswer:
        risks = sorted(
            graph.nodes_of(NodeType.RISK),
            key=lambda n: {"high": 0, "medium": 1, "low": 2, "info": 3}.get(
                str(n.attrs.get("severity")), 4
            ),
        )
        if not risks:
            return GraphAnswer(
                provider=self.kind,
                model=MODEL_NAME,
                answer="No risks were detected by the deterministic rules.",
                confidence=0.6,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        top = risks[:6]
        affected: list[str] = []
        for risk in top:
            affected.extend(
                e.target for e in graph.edges if e.type is EdgeType.AFFECTS and e.source == risk.id
            )
        return GraphAnswer(
            provider=self.kind,
            model=MODEL_NAME,
            answer=(
                f"{len(risks)} finding(s). The most serious: "
                + "; ".join(f"{r.label} ({r.attrs.get('severity')})" for r in top[:3])
                + "."
            ),
            technical_explanation="\n".join(f"- [{r.attrs.get('severity')}] {r.label}: {r.description}" for r in top),
            highlighted_node_ids=_dedupe([r.id for r in top] + affected)[:120],
            evidence=[
                AnswerEvidence(
                    node_id=r.id,
                    label=r.label,
                    why=("Heuristic rule" if r.attrs.get("heuristic") else "Deterministic rule")
                    + f" '{r.attrs.get('rule_id')}'.",
                )
                for r in top
            ],
            inference_note="Findings marked heuristic are judgements, not proofs.",
            confidence=0.85,
            coverage=1.0,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def _search_answer(self, graph, index, question, started) -> GraphAnswer:
        repo = NetworkXGraphRepository(graph)
        hits = repo.search(question, limit=12)
        if not hits:
            terms = [t for t in question.lower().split() if len(t) > 3]
            for term in terms:
                hits = repo.search(term, limit=8)
                if hits:
                    break
        if not hits:
            return GraphAnswer(
                provider=self.kind,
                model=MODEL_NAME,
                answer=(
                    "Nothing in this estate matches that question. Try naming a service, an "
                    "endpoint, a schema or a field — or configure a local model in Settings "
                    "for free-form questions."
                ),
                confidence=0.2,
                grounded=True,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        by_type: dict[str, list[str]] = {}
        for node in hits:
            by_type.setdefault(node.type.value, []).append(node.label)
        summary = "; ".join(
            f"{len(labels)} {kind}(s): {', '.join(labels[:4])}" for kind, labels in by_type.items()
        )
        return GraphAnswer(
            provider=self.kind,
            model=MODEL_NAME,
            answer=f"{len(hits)} matching item(s) — {summary}.",
            technical_explanation="\n".join(f"- {n.type.value}: {n.label} — {n.description[:120]}" for n in hits),
            highlighted_node_ids=[n.id for n in hits],
            evidence=[
                AnswerEvidence(node_id=n.id, label=n.label, why=f"Matched on {n.type.value} name or description.")
                for n in hits[:10]
            ],
            inference_note="This is a lexical match over the graph, not a semantic reading. "
            "Configure Ollama in Settings for free-form questions.",
            confidence=0.5,
            coverage=min(1.0, len(hits) / max(1, len(graph.nodes))),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    # ------------------------------------------------------------------- repairs

    async def propose_repairs(self, request: RepairRequest) -> RepairProposal:
        """The deterministic repairs live in ``analysis.impact``; this provider adds none."""
        return RepairProposal(provider=self.kind, model=MODEL_NAME, repairs=[])


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def alias_clusters_of(graph: KnowledgeGraph, index) -> dict[str, set[str]]:
    """Connected components over ALIAS_OF edges, named by their best canonical label.

    Grouping by the edge's ``canonical`` attribute instead would split one real cluster in
    two whenever edges from different sources (the alias rule and the bundled analysis)
    disagree about the name — the user then sees the same three fields listed twice.
    """
    parent: dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    names: dict[str, list[str]] = {}
    for edge in graph.edges:
        if edge.type is not EdgeType.ALIAS_OF:
            continue
        a, b = find(edge.source), find(edge.target)
        if a != b:
            parent[b] = a
        canonical = str(edge.attrs.get("canonical") or "").strip()
        if canonical:
            names.setdefault(find(edge.source), []).append(canonical)

    components: dict[str, set[str]] = {}
    for member in list(parent):
        components.setdefault(find(member), set()).add(member)

    out: dict[str, set[str]] = {}
    for root, members in components.items():
        members = {m for m in members if m in index}
        if len(members) < 2:
            continue
        labelled = names.get(root) or []
        # Prefer the most-repeated name, then the most descriptive (longest).
        canonical = (
            max(sorted(set(labelled)), key=lambda n: (labelled.count(n), len(n)))
            if labelled
            else _infer_canonical(members, index)
        )
        out[canonical] = members
    return out


def _infer_canonical(members: set[str], index) -> str:
    labels = sorted(str(index[m].attrs.get("name") or index[m].label) for m in members if m in index)
    return labels[0] if labels else "concept"


def _dedupe(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)


DEPENDENCY_PHRASES = (
    "depend", "depends on", "affected", "impact", "touch", "consumers of", "who uses",
    "what uses", "where is", "used by", "used in", "reads", "writes", "breaks",
)
JOURNEY_PHRASES = (
    "how does", "how do", "walk me", "flow", "journey", "steps", "sequence", "happens when",
    "work", "works", "process", "end to end", "end-to-end",
)
AMBIGUITY_PHRASES = (
    "conflict", "ambiguous", "ambiguity", "inconsistent", "same thing", "alias",
    "different names", "spelled",
)
RISK_PHRASES = (
    "risk", "risky", "danger", "leak", "expose", "exposed", "sensitive", "security",
    "unsafe", "pii", "personal data", "vulnerab", "wrong",
)


def classify_intent(lowered: str) -> str:
    """Route a question to a handler before any fuzzy matching happens."""
    if any(phrase in lowered for phrase in AMBIGUITY_PHRASES):
        return "ambiguity"
    if any(phrase in lowered for phrase in RISK_PHRASES):
        return "risk"
    if any(phrase in lowered for phrase in DEPENDENCY_PHRASES):
        return "dependency"
    if any(phrase in lowered for phrase in JOURNEY_PHRASES):
        return "journey"
    return "unknown"


def _match_journey(graph: KnowledgeGraph, index, lowered: str, *, threshold: float = 3.0):
    """Score journeys over everything they touch, not just their title.

    "How does checkout work?" contains neither word of *Place Order*. It does, however,
    name an operation that journey traverses — `POST /carts/{cartId}/checkout` — so we
    build each journey's searchable text from its steps as well as its own description.
    """
    terms = {t for t in _content_terms(lowered) if len(t) > 3}
    if not terms:
        return None

    best = None
    best_score = 0.0
    for node in graph.nodes_of(NodeType.JOURNEY):
        name = node.label.lower()
        score = 0.0
        if name in lowered:
            score += 8
        score += 3 * sum(1 for t in terms if t in name)
        score += 1.5 * sum(1 for t in terms if t in node.description.lower())

        step_text: list[str] = []
        for edge in graph.edges:
            if edge.type is not EdgeType.PART_OF_JOURNEY or edge.target != node.id:
                continue
            step = index.get(edge.source)
            if step is None or step.type is not NodeType.JOURNEY_STEP:
                continue
            step_text.append(step.label.lower())
            step_text.append(str(step.attrs.get("narration", "")).lower())
            operation = index.get(str(step.attrs.get("operation_id") or ""))
            if operation is not None:
                step_text.append(operation.label.lower())
                step_text.append(str(operation.attrs.get("summary", "")).lower())
                # The service slug is what carries the domain word: "shipping flow" has to
                # find a journey whose steps live in `shipping-api`, even though every
                # label in it says "shipment".
                step_text.append(str(operation.attrs.get("service", "")).lower())
                step_text.append(operation.id.lower())
        corpus = " ".join(step_text)
        score += 2 * sum(1 for t in terms if t in corpus)

        if score > best_score:
            best, best_score = node, score
    return best if best_score >= threshold else None


def _content_terms(text: str) -> list[str]:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in text)
    stop = {
        "the", "a", "an", "of", "is", "are", "what", "which", "where", "how", "does", "do",
        "and", "or", "to", "in", "on", "for", "with", "that", "this", "it", "me", "show",
        "tell", "can", "my", "we", "work", "works", "walk", "through", "happen", "happens",
        "when", "there", "any", "all", "about", "give", "list",
    }
    return [t for t in cleaned.split() if t not in stop]


def _match_schemas(graph: KnowledgeGraph, lowered: str) -> list:
    """Schemas (and the entities standing for them) whose name appears in the question."""
    terms = {t for t in _content_terms(lowered) if len(t) > 3}
    if not terms:
        return []
    matched = []
    for node in graph.nodes_of(NodeType.SCHEMA):
        name = node.label.lower()
        if any(term in name or name in term for term in terms):
            matched.append(node)
    return matched


def _match_fields(graph: KnowledgeGraph, lowered: str) -> list:
    """Find field nodes the question names, preferring exact identifier mentions."""
    exact: list = []
    partial: list = []
    for node in graph.nodes_of(NodeType.FIELD):
        name = str(node.attrs.get("name") or node.label).lower()
        if len(name) < 3:
            continue
        if name in lowered:
            (exact if looks_like_identifier(name) else partial).append(node)
    return exact or partial
