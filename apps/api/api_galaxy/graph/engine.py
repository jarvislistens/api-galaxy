"""Graph algorithms behind a repository interface.

The interface exists so the NetworkX implementation can be swapped for Kùzu or Neo4j
later without touching callers. Every traversal is bounded — by depth, by node count and
by edge count — because an unbounded query on a large estate is a denial-of-service on
your own laptop.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

import networkx as nx

from api_galaxy.contracts.graph import EdgeType, GraphEdge, GraphNode, KnowledgeGraph, NodeType

DEFAULT_MAX_DEPTH = 4
DEFAULT_MAX_NODES = 600
DEFAULT_MAX_EDGES = 2000
HARD_MAX_DEPTH = 12
HARD_MAX_NODES = 5000


class QueryLimitExceeded(RuntimeError):
    def __init__(self, what: str, limit: int) -> None:
        super().__init__(f"Query stopped: {what} exceeded the limit of {limit}.")
        self.what = what
        self.limit = limit


@dataclass(frozen=True)
class QueryLimits:
    max_depth: int = DEFAULT_MAX_DEPTH
    max_nodes: int = DEFAULT_MAX_NODES
    max_edges: int = DEFAULT_MAX_EDGES

    def clamp(self) -> QueryLimits:
        return QueryLimits(
            max_depth=max(1, min(self.max_depth, HARD_MAX_DEPTH)),
            max_nodes=max(1, min(self.max_nodes, HARD_MAX_NODES)),
            max_edges=max(1, min(self.max_edges, HARD_MAX_NODES * 4)),
        )


@dataclass
class Subgraph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool = False
    truncation_reason: str = ""

    def node_ids(self) -> list[str]:
        return [n.id for n in self.nodes]


class GraphRepository(Protocol):
    """The seam between API Galaxy and whatever stores the graph."""

    def all_nodes(self) -> list[GraphNode]: ...
    def all_edges(self) -> list[GraphEdge]: ...
    def node(self, node_id: str) -> GraphNode | None: ...
    def neighbors(self, node_id: str, *, depth: int, limits: QueryLimits) -> Subgraph: ...
    def dependents(self, node_id: str, *, limits: QueryLimits) -> list[tuple[str, int, list[str]]]: ...
    def shortest_path(self, source: str, target: str) -> list[str]: ...
    def cycles(self, *, limit: int = 25) -> list[list[str]]: ...


# Edge types that mean "a change here can propagate to there", used for impact analysis.
# The direction is *from the thing that would break* back to *what it depends on*, so the
# impact walk runs along reversed edges.
DEPENDENCY_EDGES: frozenset[EdgeType] = frozenset(
    {
        EdgeType.CONTAINS,
        EdgeType.EXPOSES,
        EdgeType.USES_REQUEST,
        EdgeType.RETURNS,
        EdgeType.REFERENCES,
        EdgeType.DEPENDS_ON,
        EdgeType.CALLS_OR_PRECEDES,
        EdgeType.PART_OF_JOURNEY,
        EdgeType.ALIAS_OF,
        EdgeType.REPRESENTS,
    }
)


class NetworkXGraphRepository:
    """MVP implementation. Rebuilds a DiGraph from the document on construction."""

    def __init__(self, graph: KnowledgeGraph) -> None:
        self.document = graph
        self._nx = nx.MultiDiGraph()
        for node in graph.nodes:
            self._nx.add_node(node.id, type=node.type.value)
        for edge in graph.edges:
            if edge.source in self._nx and edge.target in self._nx:
                self._nx.add_edge(edge.source, edge.target, key=edge.id, type=edge.type.value)
        self._node_index = graph.node_index()
        self._edge_index = graph.edge_index()

    # -- basics --------------------------------------------------------------------

    @property
    def nx_graph(self) -> nx.MultiDiGraph:
        return self._nx

    def all_nodes(self) -> list[GraphNode]:
        return list(self.document.nodes)

    def all_edges(self) -> list[GraphEdge]:
        return list(self.document.edges)

    def node(self, node_id: str) -> GraphNode | None:
        return self._node_index.get(node_id)

    def edge(self, edge_id: str) -> GraphEdge | None:
        return self._edge_index.get(edge_id)

    def edges_between(self, a: str, b: str) -> list[GraphEdge]:
        return [e for e in self.document.edges if e.source == a and e.target == b]

    def incident_edges(self, node_ids: Iterable[str]) -> list[GraphEdge]:
        wanted = set(node_ids)
        return [e for e in self.document.edges if e.source in wanted and e.target in wanted]

    # -- traversal -----------------------------------------------------------------

    def neighbors(
        self,
        node_id: str,
        *,
        depth: int = 1,
        limits: QueryLimits | None = None,
        node_types: set[NodeType] | None = None,
        edge_types: set[EdgeType] | None = None,
        undirected: bool = True,
    ) -> Subgraph:
        """Breadth-first neighborhood expansion with hard caps."""
        limits = (limits or QueryLimits(max_depth=depth)).clamp()
        depth = min(depth, limits.max_depth)
        if node_id not in self._nx:
            return Subgraph(nodes=[], edges=[])

        allowed_edge_values = {e.value for e in edge_types} if edge_types else None
        visited: dict[str, int] = {node_id: 0}
        frontier = [node_id]
        truncated = False
        reason = ""

        for level in range(depth):
            next_frontier: list[str] = []
            for current in frontier:
                adjacency: list[str] = list(self._nx.successors(current))
                if undirected:
                    adjacency += list(self._nx.predecessors(current))
                for neighbor in adjacency:
                    if neighbor in visited:
                        continue
                    if allowed_edge_values is not None:
                        connecting = list(self._nx.get_edge_data(current, neighbor, default={}).values()) + list(
                            self._nx.get_edge_data(neighbor, current, default={}).values()
                        )
                        if not any(d.get("type") in allowed_edge_values for d in connecting):
                            continue
                    if len(visited) >= limits.max_nodes:
                        truncated = True
                        reason = f"stopped at {limits.max_nodes} nodes"
                        break
                    visited[neighbor] = level + 1
                    next_frontier.append(neighbor)
                if truncated:
                    break
            if truncated:
                break
            frontier = next_frontier
            if not frontier:
                break

        nodes = [self._node_index[n] for n in visited if n in self._node_index]
        if node_types:
            keep = {n.id for n in nodes if n.type in node_types or n.id == node_id}
            nodes = [n for n in nodes if n.id in keep]
        keep_ids = {n.id for n in nodes}
        edges = [e for e in self.document.edges if e.source in keep_ids and e.target in keep_ids]
        if allowed_edge_values is not None:
            edges = [e for e in edges if e.type.value in allowed_edge_values]
        if len(edges) > limits.max_edges:
            edges = edges[: limits.max_edges]
            truncated = True
            reason = reason or f"stopped at {limits.max_edges} edges"
        return Subgraph(nodes=nodes, edges=edges, truncated=truncated, truncation_reason=reason)

    def dependents(
        self, node_id: str, *, limits: QueryLimits | None = None
    ) -> list[tuple[str, int, list[str]]]:
        """Who breaks if ``node_id`` changes.

        Walks *incoming* dependency edges transitively and returns
        ``(node_id, distance, chain)`` where ``chain`` starts at the changed node.
        """
        limits = (limits or QueryLimits(max_depth=6, max_nodes=DEFAULT_MAX_NODES)).clamp()
        if node_id not in self._nx:
            return []
        allowed = {e.value for e in DEPENDENCY_EDGES}
        seen: dict[str, tuple[int, list[str]]] = {node_id: (0, [node_id])}
        queue: list[str] = [node_id]
        out: list[tuple[str, int, list[str]]] = []

        while queue:
            current = queue.pop(0)
            distance, chain = seen[current]
            if distance >= limits.max_depth:
                continue
            for predecessor in self._nx.predecessors(current):
                if predecessor in seen:
                    continue
                data = self._nx.get_edge_data(predecessor, current, default={})
                if not any(d.get("type") in allowed for d in data.values()):
                    continue
                if len(seen) >= limits.max_nodes:
                    return out
                new_chain = [*chain, predecessor]
                seen[predecessor] = (distance + 1, new_chain)
                out.append((predecessor, distance + 1, new_chain))
                queue.append(predecessor)
        return out

    def transitive_dependencies(
        self, node_id: str, *, limits: QueryLimits | None = None
    ) -> list[tuple[str, int]]:
        """What ``node_id`` itself relies on (the opposite direction of ``dependents``)."""
        limits = (limits or QueryLimits(max_depth=6)).clamp()
        if node_id not in self._nx:
            return []
        allowed = {e.value for e in DEPENDENCY_EDGES}
        seen = {node_id: 0}
        queue = [node_id]
        out: list[tuple[str, int]] = []
        while queue:
            current = queue.pop(0)
            distance = seen[current]
            if distance >= limits.max_depth:
                continue
            for successor in self._nx.successors(current):
                if successor in seen:
                    continue
                data = self._nx.get_edge_data(current, successor, default={})
                if not any(d.get("type") in allowed for d in data.values()):
                    continue
                if len(seen) >= limits.max_nodes:
                    return out
                seen[successor] = distance + 1
                out.append((successor, distance + 1))
                queue.append(successor)
        return out

    # -- paths ---------------------------------------------------------------------

    def shortest_path(self, source: str, target: str) -> list[str]:
        if source not in self._nx or target not in self._nx:
            return []
        undirected = self._nx.to_undirected(as_view=False)
        try:
            return list(nx.shortest_path(undirected, source, target))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def k_shortest_paths(self, source: str, target: str, k: int = 3) -> list[list[str]]:
        """Alternative evidence paths. Useful when two services both reach a schema."""
        if source not in self._nx or target not in self._nx or source == target:
            return []
        undirected = nx.Graph(self._nx.to_undirected(as_view=False))
        try:
            generator = nx.shortest_simple_paths(undirected, source, target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
        paths: list[list[str]] = []
        for path in generator:
            paths.append(list(path))
            if len(paths) >= max(1, min(k, 8)):
                break
        return paths

    def evidence_path(self, node_ids: list[str]) -> list[str]:
        """Stitch a readable path through a set of highlighted nodes."""
        ordered = [n for n in node_ids if n in self._nx]
        if len(ordered) < 2:
            return ordered
        path: list[str] = [ordered[0]]
        for nxt in ordered[1:]:
            leg = self.shortest_path(path[-1], nxt)
            if not leg:
                path.append(nxt)
                continue
            path.extend(leg[1:])
        deduped: list[str] = []
        for node in path:
            if not deduped or deduped[-1] != node:
                deduped.append(node)
        return deduped

    # -- structure -----------------------------------------------------------------

    def cycles(self, *, limit: int = 25, edge_types: set[EdgeType] | None = None) -> list[list[str]]:
        """Simple cycles over dependency-ish edges only.

        Restricting the edge set matters: CONTAINS edges make trivially uninteresting
        cycles, while a genuine service↔service DEPENDS_ON loop is a real finding.
        """
        types = edge_types or {EdgeType.DEPENDS_ON, EdgeType.CALLS_OR_PRECEDES, EdgeType.REFERENCES}
        values = {t.value for t in types}
        projected = nx.DiGraph()
        projected.add_nodes_from(self._nx.nodes)
        for source, target, data in self._nx.edges(data=True):
            if data.get("type") in values:
                projected.add_edge(source, target)
        found: list[list[str]] = []
        for cycle in nx.simple_cycles(projected):
            if len(cycle) < 2:
                continue
            found.append(list(cycle))
            if len(found) >= limit:
                break
        return found

    def connected_components(self) -> list[list[str]]:
        undirected = self._nx.to_undirected(as_view=False)
        return [sorted(component) for component in nx.connected_components(undirected)]

    def orphans(self, node_type: NodeType) -> list[str]:
        """Nodes of ``node_type`` that nothing points at except their own container."""
        out: list[str] = []
        for node in self.document.nodes:
            if node.type is not node_type:
                continue
            incoming = [
                e
                for e in self.document.edges
                if e.target == node.id and e.type is not EdgeType.CONTAINS
            ]
            if not incoming:
                out.append(node.id)
        return out

    # -- filtering -----------------------------------------------------------------

    def filter(
        self,
        *,
        node_types: set[NodeType] | None = None,
        domains: set[str] | None = None,
        services: set[str] | None = None,
        search: str | None = None,
        include_inferred: bool = True,
        limits: QueryLimits | None = None,
    ) -> Subgraph:
        limits = (limits or QueryLimits(max_nodes=DEFAULT_MAX_NODES)).clamp()
        nodes = list(self.document.nodes)
        if node_types:
            nodes = [n for n in nodes if n.type in node_types]
        if services:
            nodes = [
                n
                for n in nodes
                if n.attrs.get("service") in services
                or n.id in services
                or n.type in (NodeType.DOMAIN, NodeType.ESTATE)
            ]
        if domains:
            in_domain = {
                e.source
                for e in self.document.edges
                if e.type is EdgeType.BELONGS_TO_DOMAIN and e.target in domains
            }
            nodes = [n for n in nodes if n.id in in_domain or n.id in domains]
        if search:
            needle = search.lower()
            nodes = [
                n
                for n in nodes
                if needle in n.label.lower()
                or needle in n.description.lower()
                or needle in n.id.lower()
            ]
        if not include_inferred:
            nodes = [n for n in nodes if n.is_fact]

        truncated = False
        reason = ""
        if len(nodes) > limits.max_nodes:
            nodes = nodes[: limits.max_nodes]
            truncated = True
            reason = f"showing the first {limits.max_nodes} of the matching nodes"
        keep = {n.id for n in nodes}
        edges = [e for e in self.document.edges if e.source in keep and e.target in keep]
        if not include_inferred:
            edges = [e for e in edges if e.is_fact]
        return Subgraph(nodes=nodes, edges=edges, truncated=truncated, truncation_reason=reason)

    def search(self, needle: str, *, limit: int = 30) -> list[GraphNode]:
        lowered = needle.lower().strip()
        if not lowered:
            return []
        scored: list[tuple[int, GraphNode]] = []
        for node in self.document.nodes:
            label = node.label.lower()
            if lowered == label:
                score = 0
            elif label.startswith(lowered):
                score = 1
            elif lowered in label:
                score = 2
            elif lowered in node.id.lower():
                score = 3
            elif lowered in node.description.lower():
                score = 4
            else:
                continue
            scored.append((score, node))
        scored.sort(key=lambda pair: (pair[0], pair[1].label))
        return [node for _, node in scored[:limit]]


# --------------------------------------------------------------------------------------
# Diffing
# --------------------------------------------------------------------------------------


@dataclass
class GraphDiff:
    added_nodes: list[str]
    removed_nodes: list[str]
    changed_nodes: list[str]
    added_edges: list[str]
    removed_edges: list[str]

    @property
    def is_empty(self) -> bool:
        return not (
            self.added_nodes
            or self.removed_nodes
            or self.changed_nodes
            or self.added_edges
            or self.removed_edges
        )


def diff_graphs(base: KnowledgeGraph, other: KnowledgeGraph) -> GraphDiff:
    base_nodes = base.node_index()
    other_nodes = other.node_index()
    base_edges = set(base.edge_index())
    other_edges = set(other.edge_index())

    changed: list[str] = []
    for node_id, node in other_nodes.items():
        original = base_nodes.get(node_id)
        if original is None:
            continue
        if original.label != node.label or original.attrs != node.attrs:
            changed.append(node_id)

    return GraphDiff(
        added_nodes=sorted(set(other_nodes) - set(base_nodes)),
        removed_nodes=sorted(set(base_nodes) - set(other_nodes)),
        changed_nodes=sorted(changed),
        added_edges=sorted(other_edges - base_edges),
        removed_edges=sorted(base_edges - other_edges),
    )
