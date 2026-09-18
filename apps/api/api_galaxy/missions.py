"""Mission Mode — short challenges that teach the product by using it.

This is a teaching layer, not a game skin. Missions never hide or soften technical truth:
every answer is checked against the same graph the rest of the app uses, hints point at
real controls, and a mission you fail simply tells you what the graph actually says.

Missions are resolved against the *demo* estate's node IDs where they name something
specific, and fall back to a structural check (rather than a hard-coded ID) so they also
work on an imported estate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from api_galaxy.contracts.graph import EdgeType, KnowledgeGraph, NodeType


@dataclass
class MissionResult:
    correct: bool
    message: str
    reveal: list[str] = field(default_factory=list)
    reveal_labels: list[str] = field(default_factory=list)
    score: int = 0


@dataclass
class Mission:
    id: str
    title: str
    tagline: str
    brief: str
    difficulty: str  # gentle | tricky | hard
    estimated_seconds: int
    answer_kind: str  # node | nodes | scenario | alias
    hints: list[str]
    where: str
    points: int
    check: Callable[[KnowledgeGraph, dict[str, Any]], MissionResult]
    teaches: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "tagline": self.tagline,
            "brief": self.brief,
            "difficulty": self.difficulty,
            "estimated_seconds": self.estimated_seconds,
            "answer_kind": self.answer_kind,
            "hints": self.hints,
            "where": self.where,
            "points": self.points,
            "teaches": self.teaches,
        }


# --------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------


def _labels(graph: KnowledgeGraph, ids: list[str]) -> list[str]:
    index = graph.node_index()
    return [index[i].label for i in ids if i in index]


def _alias_members(graph: KnowledgeGraph) -> dict[str, set[str]]:
    from api_galaxy.providers.deterministic import alias_clusters_of

    return alias_clusters_of(graph, graph.node_index())


def check_hidden_dependency(graph: KnowledgeGraph, payload: dict[str, Any]) -> MissionResult:
    """The answer is any field that is an alias of a customer identifier in *another* service."""
    answer = str(payload.get("node_id") or "")
    clusters = _alias_members(graph)
    index = graph.node_index()
    target: set[str] = set()
    for canonical, members in clusters.items():
        if "customer" in canonical.lower() or any(
            "customer" in str(index[m].attrs.get("name", "")).lower() for m in members
        ):
            target |= members
    # The interesting answers are the ones NOT literally called customer_id.
    surprises = {
        m for m in target
        if "customer" not in str(index[m].attrs.get("name", "")).lower()
    }
    if not surprises:
        return MissionResult(
            False,
            "This estate has no hidden customer alias, so there is nothing to find here.",
            reveal=sorted(target),
            reveal_labels=_labels(graph, sorted(target)),
        )
    if answer in surprises:
        node = index[answer]
        return MissionResult(
            True,
            f"Found it. '{node.attrs.get('name')}' in {node.attrs.get('service')} is the same "
            "customer concept under a different name — nothing in the specification says so.",
            reveal=sorted(surprises),
            reveal_labels=_labels(graph, sorted(surprises)),
            score=100,
        )
    return MissionResult(
        False,
        "Not that one. Look for an identifier whose name never mentions the customer.",
        reveal=[],
    )


def check_data_leak(graph: KnowledgeGraph, payload: dict[str, Any]) -> MissionResult:
    """The answer is an operation with no security that returns a PII-bearing schema."""
    answer = str(payload.get("node_id") or "")
    offenders: set[str] = set()
    index = graph.node_index()
    pii_schemas = {
        edge.target
        for risk in graph.nodes_of(NodeType.RISK)
        if risk.attrs.get("rule_id") == "pii-in-schema"
        for edge in graph.edges
        if edge.type is EdgeType.AFFECTS and edge.source == risk.id
    }
    for node in graph.nodes_of(NodeType.API_OPERATION):
        if node.attrs.get("security"):
            continue
        returns = {
            e.target for e in graph.edges if e.source == node.id and e.type is EdgeType.RETURNS
        }
        if returns & pii_schemas:
            offenders.add(node.id)

    if not offenders:
        return MissionResult(
            False, "Nothing in this estate exposes personal data without authentication."
        )
    if answer in offenders:
        node = index[answer]
        return MissionResult(
            True,
            f"Correct. {node.label} declares `security: []` and still returns personal data.",
            reveal=sorted(offenders),
            reveal_labels=_labels(graph, sorted(offenders)),
            score=100,
        )
    return MissionResult(
        False,
        "That endpoint is authenticated, or it returns nothing sensitive. Filter the galaxy "
        "by 'no auth' and look at what each one returns.",
    )


def check_survive_rename(graph: KnowledgeGraph, payload: dict[str, Any]) -> MissionResult:
    """Passed only when the caller reports every journey validating *after* a rename."""
    renamed = bool(payload.get("rename_applied"))
    journeys_ok = bool(payload.get("all_journeys_valid"))
    repairs = int(payload.get("repairs_applied") or 0)
    if not renamed:
        return MissionResult(False, "Apply the rename in Break Lab first.")
    if not journeys_ok:
        return MissionResult(
            False,
            "Checkout is still broken. Try the alias mapping repair — it keeps old consumers "
            "working instead of asking everyone to change at once.",
        )
    if repairs == 0:
        return MissionResult(
            False,
            "The journeys pass, but you got there by undoing the change rather than repairing "
            "it. Re-apply the rename and fix it with a mapping.",
        )
    return MissionResult(
        True,
        "Checkout survives the rename. You shipped a breaking change without breaking anyone.",
        score=150,
    )


def check_untangle_twins(graph: KnowledgeGraph, payload: dict[str, Any]) -> MissionResult:
    selected = {str(x) for x in (payload.get("node_ids") or [])}
    clusters = _alias_members(graph)
    for canonical, members in clusters.items():
        if len(members) < 3:
            continue
        if selected and selected <= members and len(selected) >= 3:
            return MissionResult(
                True,
                f"All three are the same '{canonical}'. Accepting the cluster teaches the graph "
                "so every future impact calculation follows it.",
                reveal=sorted(members),
                reveal_labels=_labels(graph, sorted(members)),
                score=120,
            )
    biggest = max(clusters.values(), key=len, default=set())
    return MissionResult(
        False,
        "Not quite — those are not all the same concept. Open Ask and try "
        "'which concepts have conflicting definitions?'.",
        reveal=sorted(biggest) if len(biggest) >= 3 else [],
        reveal_labels=_labels(graph, sorted(biggest)) if len(biggest) >= 3 else [],
    )


def check_chaos(graph: KnowledgeGraph, payload: dict[str, Any]) -> MissionResult:
    answer = str(payload.get("node_id") or "")
    actual = str(payload.get("actual_node_id") or "")
    if not actual:
        return MissionResult(False, "Start a chaos run first.")
    if answer == actual:
        return MissionResult(
            True,
            "Diagnosed. You traced the blast radius back to its origin without being told.",
            reveal=[actual],
            reveal_labels=_labels(graph, [actual]),
            score=200,
        )
    return MissionResult(
        False,
        "Not the origin. Follow the shockwave inwards: the origin is the only node at "
        "distance 0.",
        reveal=[actual],
        reveal_labels=_labels(graph, [actual]),
    )


# --------------------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------------------

MISSIONS: list[Mission] = [
    Mission(
        id="hidden-dependency",
        title="Hidden Dependency",
        tagline="Something depends on the customer without ever saying so.",
        brief="One service identifies the shopper by a name that never mentions customers. "
        "Find that field. It is the reason a 'safe' rename in one service takes down another.",
        difficulty="gentle",
        estimated_seconds=60,
        answer_kind="node",
        hints=[
            "Open Ask and type: which concepts have conflicting definitions?",
            "Dashed edges are suggestions, not facts — follow one.",
            "It lives in the service that moves money.",
        ],
        where="Galaxy or Ask",
        points=100,
        check=check_hidden_dependency,
        teaches="Aliases are invisible in a specification and lethal in a refactor.",
    ),
    Mission(
        id="stop-the-data-leak",
        title="Stop the Data Leak",
        tagline="One endpoint hands out personal data to anyone who asks.",
        brief="Exactly one operation returns personal data with no authentication at all. "
        "Find it before someone else does.",
        difficulty="gentle",
        estimated_seconds=45,
        answer_kind="node",
        hints=[
            "Filter the galaxy to operations with no security scheme.",
            "Then check which of those return a schema flagged as carrying personal data.",
            "Its path says it is public.",
        ],
        where="Overview → Top risks, or the Galaxy filters",
        points=100,
        check=check_data_leak,
        teaches="'Public' in a path is a naming convention; `security: []` is the actual control.",
    ),
    Mission(
        id="survive-the-rename",
        title="Survive the Rename",
        tagline="customer_id just became party_id. Keep checkout alive.",
        brief="Apply the rename in Break Lab, watch what breaks, then repair it so every "
        "journey validates again — without simply undoing the change.",
        difficulty="tricky",
        estimated_seconds=120,
        answer_kind="scenario",
        hints=[
            "Break Lab → Rename a field → customer_id → party_id.",
            "Read the affected journeys panel before you reach for a repair.",
            "The alias mapping repair keeps existing consumers working; reverting does not "
            "count as surviving.",
        ],
        where="Break Lab",
        points=150,
        check=check_survive_rename,
        teaches="A breaking change is survivable if you publish a mapping before you publish "
        "the rename.",
    ),
    Mission(
        id="untangle-the-twins",
        title="Untangle the Twins",
        tagline="Three names, one shopper.",
        brief="customer_id, cust_no and party_key are the same person. Select all three and "
        "accept them as one concept.",
        difficulty="tricky",
        estimated_seconds=90,
        answer_kind="nodes",
        hints=[
            "Ask: what depends on customer_id?",
            "Each alias lives in a different service.",
            "Accepting the cluster changes every impact calculation afterwards.",
        ],
        where="Ask, then the inspector",
        points=120,
        check=check_untangle_twins,
        teaches="Accepting an inference is a decision — it gets logged, and it changes the model.",
    ),
    Mission(
        id="chaos-mode",
        title="Chaos Mode",
        tagline="Something broke. We are not telling you what.",
        brief="A safe, random breaking change has been applied to a scenario. Diagnose the "
        "origin from the impact alone, then check your answer.",
        difficulty="hard",
        estimated_seconds=150,
        answer_kind="node",
        hints=[
            "Sort the impact table by status, then by distance.",
            "Only one node is at distance 0.",
            "Broken journeys name the step that fails first.",
        ],
        where="Break Lab → Chaos",
        points=200,
        check=check_chaos,
        teaches="Reading a blast radius backwards is the skill that shortens an incident.",
    ),
]

MISSION_INDEX: dict[str, Mission] = {m.id: m for m in MISSIONS}


def list_missions() -> list[dict[str, Any]]:
    return [m.to_dict() for m in MISSIONS]


def evaluate(mission_id: str, graph: KnowledgeGraph, payload: dict[str, Any]) -> MissionResult:
    mission = MISSION_INDEX.get(mission_id)
    if mission is None:
        return MissionResult(False, f"No mission called '{mission_id}'.")
    return mission.check(graph, payload)


def chaos_candidates(graph: KnowledgeGraph, *, limit: int = 12) -> list[dict[str, Any]]:
    """Fields that are safe and interesting to break: required, used by more than one thing.

    Returned as a deterministic, ranked list. The caller picks an index — we do not use a
    random number generator here so a chaos run is reproducible from its scenario record.
    """
    index = graph.node_index()
    scored: list[tuple[int, str]] = []
    for node in graph.nodes_of(NodeType.FIELD):
        if not node.attrs.get("required"):
            continue
        schemas = [
            e.source for e in graph.edges
            if e.type is EdgeType.CONTAINS and e.target == node.id
        ]
        if not schemas:
            continue
        consumers = sum(
            1
            for e in graph.edges
            if e.target in schemas and e.type in (EdgeType.RETURNS, EdgeType.USES_REQUEST)
        )
        if consumers >= 2:
            scored.append((consumers, node.id))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [
        {
            "node_id": node_id,
            "label": index[node_id].label,
            "service": index[node_id].attrs.get("service"),
            "consumers": consumers,
        }
        for consumers, node_id in scored[:limit]
    ]
