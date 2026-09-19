"""Building bounded graph context for a model.

We never hand a model the whole project. Context is chunked — by domain, by journey, or
by relevance to a question — and every chunk carries the explicit list of node IDs the
model is permitted to cite. This is what makes reference whitelisting possible downstream.
"""

from __future__ import annotations

from api_galaxy.contracts.graph import EdgeType, KnowledgeGraph, NodeType
from api_galaxy.contracts.providers import ContextOperation, ContextSchema, GraphContext

MAX_OPERATIONS_PER_CHUNK = 40
MAX_SCHEMAS_PER_CHUNK = 30
MAX_FIELDS_PER_SCHEMA = 14


def build_context(
    graph: KnowledgeGraph,
    *,
    chunk_label: str = "estate",
    node_ids: set[str] | None = None,
    max_operations: int = MAX_OPERATIONS_PER_CHUNK,
    max_schemas: int = MAX_SCHEMAS_PER_CHUNK,
) -> GraphContext:
    index = graph.node_index()
    wanted = node_ids

    services = [
        {
            "id": node.id,
            "name": node.label,
            "description": node.description[:300],
            "slug": str(node.attrs.get("slug", "")),
        }
        for node in graph.nodes_of(NodeType.SERVICE)
        if wanted is None or node.id in wanted
    ]

    operations: list[ContextOperation] = []
    for node in graph.nodes_of(NodeType.API_OPERATION):
        if wanted is not None and node.id not in wanted:
            continue
        request_schema = next(
            (e.target for e in graph.edges if e.source == node.id and e.type is EdgeType.USES_REQUEST),
            None,
        )
        responses = [
            e.target for e in graph.edges if e.source == node.id and e.type is EdgeType.RETURNS
        ]
        operations.append(
            ContextOperation(
                id=node.id,
                service=str(node.attrs.get("service", "")),
                method=str(node.attrs.get("method", "")),
                path=str(node.attrs.get("path", "")),
                summary=str(node.attrs.get("summary", ""))[:200],
                description=node.description[:400],
                tags=list(node.tags),
                request_schema=request_schema,
                response_schemas=sorted(set(responses))[:4],
                deprecated=bool(node.attrs.get("deprecated")),
                secured=bool(node.attrs.get("security")),
            )
        )
        if len(operations) >= max_operations:
            break

    schemas: list[ContextSchema] = []
    for node in graph.nodes_of(NodeType.SCHEMA):
        if wanted is not None and node.id not in wanted:
            continue
        fields = [
            {
                "name": str(index[e.target].attrs.get("name", index[e.target].label)),
                "type": str(index[e.target].attrs.get("type_signature", "")),
                "description": index[e.target].description[:120],
            }
            for e in graph.edges
            if e.source == node.id
            and e.type is EdgeType.CONTAINS
            and e.target in index
            and index[e.target].type is NodeType.FIELD
        ][:MAX_FIELDS_PER_SCHEMA]
        schemas.append(
            ContextSchema(
                id=node.id,
                service=str(node.attrs.get("service", "")),
                name=node.label,
                description=node.description[:300],
                fields=fields,
            )
        )
        if len(schemas) >= max_schemas:
            break

    # Domains follow the same scope as everything else. Listing all of them regardless
    # meant a request narrowed to one domain still handed out seven domain IDs as
    # citable, so a scoped run was never really scoped.
    domains = [n for n in graph.nodes_of(NodeType.DOMAIN) if wanted is None or n.id in wanted]

    allowed = (
        [s["id"] for s in services]
        + [o.id for o in operations]
        + [s.id for s in schemas]
        + [n.id for n in domains]
        + [
            f["id"]
            for s in schemas
            for f in _field_ids(graph, index, s.id)
        ]
    )

    return GraphContext(
        project_name=graph.project_name,
        chunk_label=chunk_label,
        services=services,
        operations=operations,
        schemas=schemas,
        existing_domains=[n.label for n in domains],
        allowed_node_ids=sorted(set(allowed)),
    )


def _field_ids(graph: KnowledgeGraph, index, schema_id: str) -> list[dict[str, str]]:
    return [
        {"id": e.target}
        for e in graph.edges
        if e.source == schema_id
        and e.type is EdgeType.CONTAINS
        and e.target in index
        and index[e.target].type is NodeType.FIELD
    ][:MAX_FIELDS_PER_SCHEMA]


def chunk_by_domain(graph: KnowledgeGraph) -> list[GraphContext]:
    """One context per business domain, so a small model sees a tractable slice."""
    contexts: list[GraphContext] = []
    for domain in graph.nodes_of(NodeType.DOMAIN):
        members = {
            e.source for e in graph.edges
            if e.type is EdgeType.BELONGS_TO_DOMAIN and e.target == domain.id
        }
        expanded = set(members)
        for edge in graph.edges:
            if edge.source in members and edge.type in (
                EdgeType.USES_REQUEST,
                EdgeType.RETURNS,
                EdgeType.EXPOSES,
                EdgeType.CONTAINS,
            ):
                expanded.add(edge.target)
        for edge in graph.edges:
            if edge.source in expanded and edge.type is EdgeType.CONTAINS:
                expanded.add(edge.target)
        if not expanded:
            continue
        contexts.append(
            build_context(graph, chunk_label=f"domain: {domain.label}", node_ids=expanded)
        )
    return contexts or [build_context(graph)]


def context_for_question(graph: KnowledgeGraph, question: str, *, budget: int = 45) -> GraphContext:
    """Retrieve the slice of the graph most likely to contain the answer.

    Deliberately simple lexical retrieval over labels, descriptions and IDs, then a
    one-hop expansion so the model sees each hit in context rather than in isolation.
    """
    terms = [t for t in _terms(question) if len(t) > 2]
    if not terms:
        return build_context(graph, chunk_label="question")

    index = graph.node_index()
    scored: list[tuple[int, str]] = []
    for node in graph.nodes:
        haystack = f"{node.label} {node.description} {node.id}".lower()
        score = sum(3 if term in node.label.lower() else 1 for term in terms if term in haystack)
        if score:
            scored.append((score, node.id))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))

    selected = {node_id for _, node_id in scored[:budget]}
    for edge in graph.edges:
        if len(selected) > budget * 4:
            break
        if edge.source in selected:
            selected.add(edge.target)
        elif edge.target in selected:
            selected.add(edge.source)

    # Always include the structural spine so the model can place what it found.
    for node in graph.nodes:
        if node.type in (NodeType.SERVICE, NodeType.DOMAIN):
            selected.add(node.id)

    selected = {node_id for node_id in selected if node_id in index}
    return build_context(
        graph, chunk_label=f"question: {question[:60]}", node_ids=selected, max_operations=45
    )


def _terms(text: str) -> list[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    stop = {
        "the", "a", "an", "of", "is", "are", "what", "which", "where", "how", "does", "do",
        "and", "or", "to", "in", "on", "for", "with", "that", "this", "it", "me", "show",
        "tell", "can", "i", "my", "we", "work", "works", "used", "use", "uses", "touch",
        "touches", "depends", "depend", "there", "any", "all",
    }
    return [t for t in cleaned.split() if t not in stop]
