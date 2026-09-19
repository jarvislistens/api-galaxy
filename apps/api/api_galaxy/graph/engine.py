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

from api_galaxy.contracts.graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    NodeType,
    Standing,
)

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
    def dependents(self, node_id: str, *, limits: QueryLimits) -> list[DependencyPath]: ...
    def shortest_path(self, source: str, target: str) -> list[str]: ...
    def cycles(self, *, limit: int = 25) -> list[list[str]]: ...


# Edge types that carry a *contract*: crossing one means the thing at the far end
# consumes a shape it cannot keep working without. Breaking a contract breaks consumers.
CONTRACT_EDGES: frozenset[EdgeType] = frozenset(
    {
        EdgeType.CONTAINS,
        EdgeType.EXPOSES,
        EdgeType.USES_REQUEST,
        EdgeType.RETURNS,
        EdgeType.REFERENCES,
        EdgeType.DEPENDS_ON,
        EdgeType.CALLS_OR_PRECEDES,
        EdgeType.PART_OF_JOURNEY,
    }
)

# Edge types that carry *meaning* rather than a contract. `Order.cust_no` being an alias
# of `Customer.customer_id` does not mean renaming one stops the other from parsing — it
# means the concept moved. Real, worth surfacing, but never "broken".
SEMANTIC_EDGES: frozenset[EdgeType] = frozenset(
    {
        EdgeType.ALIAS_OF,
        EdgeType.REPRESENTS,
    }
)

# Everything a change can propagate along. The walk runs against edge direction, from the
# thing that would break back to what it depends on.
DEPENDENCY_EDGES: frozenset[EdgeType] = CONTRACT_EDGES | SEMANTIC_EDGES


@dataclass(frozen=True)
class Hop:
    """One step of a dependency walk: what kind of link it was, and how well attested."""

    edge_type: EdgeType
    standing: Standing

    @property
    def is_contract(self) -> bool:
        return self.edge_type in CONTRACT_EDGES

    @property
    def weight(self) -> int:
        """Lower is stronger. Used to pick the best of several links between two nodes."""
        if self.standing is not Standing.STATED:
            return 3 if not self.is_contract else 2
        return 0 if self.is_contract else 1


@dataclass(frozen=True)
class DependencyPath:
    """A node reached by the dependency walk, with the route taken to reach it."""

    node_id: str
    distance: int
    chain: list[str]
    hops: list[Hop]

    @property
    def all_contract(self) -> bool:
        return all(hop.is_contract for hop in self.hops)

    @property
    def all_stated(self) -> bool:
        return all(hop.standing is Standing.STATED for hop in self.hops)

    def weakest_hop(self) -> Hop | None:
        """The hop that limits how strong a claim this path can support."""
        return max(self.hops, key=lambda hop: hop.weight, default=None)


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
    ) -> list[DependencyPath]:
        """Who is affected if ``node_id`` changes, and *by what kind of relationship*.

        Walks incoming dependency edges transitively. The edge types and standings
        crossed are returned alongside the chain, because "two hops away" and "two hops
        away, the second of which was a suggested alias" are completely different
        statements and only the caller can weigh them. Returning just the node IDs is
        what let the impact scorer call an alias hop a broken contract.
        """
        limits = (limits or QueryLimits(max_depth=6, max_nodes=DEFAULT_MAX_NODES)).clamp()
        if node_id not in self._nx:
            return []
        allowed = {e.value for e in DEPENDENCY_EDGES}
        start = DependencyPath(node_id=node_id, distance=0, chain=[node_id], hops=[])
        seen: dict[str, DependencyPath] = {node_id: start}
        queue: list[str] = [node_id]
        out: list[DependencyPath] = []

        while queue:
            current = queue.pop(0)
            path = seen[current]
            if path.distance >= limits.max_depth:
                continue
            for predecessor in self._nx.predecessors(current):
                if predecessor in seen:
                    continue
                data = self._nx.get_edge_data(predecessor, current, default={})
                hop = self._strongest_hop(
                    [key for key, d in data.items() if d.get("type") in allowed]
                )
                if hop is None:
                    continue
                if len(seen) >= limits.max_nodes:
                    return out
                extended = DependencyPath(
                    node_id=predecessor,
                    distance=path.distance + 1,
                    chain=[*path.chain, predecessor],
                    hops=[*path.hops, hop],
                )
                seen[predecessor] = extended
                out.append(extended)
                queue.append(predecessor)
        return out

    def _strongest_hop(self, edge_ids: list[str]) -> Hop | None:
        """Pick the hop that carries the most weight when two nodes are linked twice.

        A field and its schema can be joined by both CONTAINS (stated) and ALIAS_OF
        (suggested). The relationship between them is the stronger of the two, so a
        suggested edge must not weaken a contract that also exists.
        """
        best: Hop | None = None
        for edge_id in edge_ids:
            edge = self._edge_index.get(edge_id)
            if edge is None:
                continue
            candidate = Hop(edge_type=edge.type, standing=edge.standing)
            if best is None or candidate.weight < best.weight:
                best = candidate
        return best

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
            nodes = [n for n in nodes if n.standing.is_stated]

        truncated = False
        reason = ""
        if len(nodes) > limits.max_nodes:
            nodes = nodes[: limits.max_nodes]
            truncated = True
            reason = f"showing the first {limits.max_nodes} of the matching nodes"
        keep = {n.id for n in nodes}
        edges = [e for e in self.document.edges if e.source in keep and e.target in keep]
        if not include_inferred:
            edges = [e for e in edges if e.standing.is_stated]
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
