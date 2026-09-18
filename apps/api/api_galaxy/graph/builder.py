"""Turn a :class:`NormalizedEstate` into a :class:`KnowledgeGraph`.

Everything this module writes carries ``SourceKind.SPECIFICATION`` — these are the
facts. Domains come from the ``x-api-galaxy-domain`` extension or from tags, which is
still specification-derived; anything an LLM proposes is added later, separately, and is
never allowed to overwrite what is built here.
"""

from __future__ import annotations

from typing import Iterable

from api_galaxy.contracts.graph import (
    Acceptance,
    EdgeType,
    Evidence,
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    NodeType,
    Provenance,
    SourceKind,
)
from api_galaxy.contracts.ids import (
    domain_id,
    edge_id,
    estate_id,
    evidence_id,
    field_id,
    operation_id,
    path_id,
    schema_id,
    security_scheme_id,
    server_id,
    service_id,
    slugify,
)
from api_galaxy.parsing.normalize import (
    NormalizedEstate,
    NormalizedService,
    NormField,
    NormOperation,
    NormSchema,
)


def _evidence(service: NormalizedService, pointer: str, label: str, excerpt: str = "") -> Evidence:
    return Evidence(
        id=evidence_id(service.source_file, pointer),
        source_file=service.source_file or f"{service.slug}.yaml",
        pointer=pointer,
        label=label,
        excerpt=excerpt[:280],
    )


def _spec_provenance(
    service: NormalizedService, pointer: str, explanation: str
) -> Provenance:
    return Provenance(
        source_kind=SourceKind.SPECIFICATION,
        explanation=explanation,
        source_file=service.source_file or f"{service.slug}.yaml",
        source_pointer=pointer,
    )


class GraphBuilder:
    def __init__(self, estate: NormalizedEstate, *, project_id: str, project_name: str) -> None:
        self.estate = estate
        self.project_id = project_id
        self.project_name = project_name
        self.graph = KnowledgeGraph(
            project_id=project_id,
            project_name=project_name,
            spec_fingerprint=estate.fingerprint,
        )
        # operationId → node id, for resolving x-api-galaxy-depends-on across services.
        self._op_lookup: dict[str, str] = {}
        self._op_lookup_qualified: dict[tuple[str, str], str] = {}

    # -- public --------------------------------------------------------------------

    def build(self) -> KnowledgeGraph:
        self._add_estate()
        for service in self.estate.services:
            self._add_service(service)
        self._link_explicit_dependencies()
        self._link_schema_references()
        self.graph.diagnostics = [d.model_dump(mode="json") for d in self.estate.diagnostics]
        return self.graph

    # -- nodes ---------------------------------------------------------------------

    def _add_estate(self) -> None:
        eid = estate_id(slugify(self.project_name))
        self.graph.add_node(
            GraphNode(
                id=eid,
                type=NodeType.ESTATE,
                label=self.estate.name or self.project_name,
                project_id=self.project_id,
                description=self.estate.description,
                provenance=Provenance(
                    source_kind=SourceKind.SPECIFICATION,
                    explanation="The set of specifications you imported.",
                ),
                attrs={"services": len(self.estate.services)},
            )
        )
        self.estate_node_id = eid

    def _domain_node(self, name: str, service: NormalizedService) -> str:
        did = domain_id(name)
        self.graph.add_node(
            GraphNode(
                id=did,
                type=NodeType.DOMAIN,
                label=name,
                project_id=self.project_id,
                description=f"Business area grouping the services that own {name.lower()} data.",
                provenance=_spec_provenance(
                    service,
                    "/x-api-galaxy-domain",
                    f"Declared by the specification as the '{name}' business domain.",
                ),
            )
        )
        self._edge(
            EdgeType.CONTAINS,
            self.estate_node_id,
            did,
            service,
            "/",
            f"The estate contains the {name} domain.",
        )
        return did

    def _add_service(self, service: NormalizedService) -> None:
        sid = service_id(service.name)
        self.graph.add_node(
            GraphNode(
                id=sid,
                type=NodeType.SERVICE,
                label=service.title or service.name,
                project_id=self.project_id,
                description=service.description,
                provenance=_spec_provenance(
                    service, "/info", f"Declared by {service.source_file}."
                ),
                attrs={
                    "slug": service.slug,
                    "version": service.version,
                    "openapi": service.openapi_version,
                    "source_file": service.source_file,
                    "operations": len(service.operations),
                    "schemas": len(service.schemas),
                    "base_url": service.servers[0].url if service.servers else None,
                },
                evidence=[_evidence(service, "/info", "Service metadata", service.title)],
            )
        )
        self._edge(
            EdgeType.CONTAINS, self.estate_node_id, sid, service, "/info", "Part of the estate."
        )

        domain_name = service.domain or _domain_from_tags(service) or service.title or service.name
        did = self._domain_node(domain_name, service)
        self._edge(
            EdgeType.BELONGS_TO_DOMAIN,
            sid,
            did,
            service,
            "/x-api-galaxy-domain" if service.domain else "/tags",
            f"{service.title or service.name} is part of the {domain_name} domain.",
        )

        for index, server in enumerate(service.servers):
            srv_id = server_id(service.name, index)
            self.graph.add_node(
                GraphNode(
                    id=srv_id,
                    type=NodeType.SERVER,
                    label=server.url,
                    project_id=self.project_id,
                    description=server.description,
                    provenance=_spec_provenance(
                        service, server.pointer, "Server URL declared in the specification."
                    ),
                    attrs={"url": server.url},
                )
            )
            self._edge(EdgeType.CONTAINS, sid, srv_id, service, server.pointer, "Declared server.")

        for scheme in service.security_schemes:
            sec_id = security_scheme_id(service.name, scheme.name)
            self.graph.add_node(
                GraphNode(
                    id=sec_id,
                    type=NodeType.SECURITY_SCHEME,
                    label=scheme.name,
                    project_id=self.project_id,
                    description=scheme.description
                    or f"{scheme.type} security scheme declared by {service.name}.",
                    provenance=_spec_provenance(
                        service, scheme.pointer, f"Security scheme '{scheme.name}'."
                    ),
                    attrs={
                        "type": scheme.type,
                        "scheme": scheme.scheme,
                        "in": scheme.location,
                        "param": scheme.param_name,
                        "strength": scheme.strength,
                    },
                    evidence=[_evidence(service, scheme.pointer, f"securitySchemes.{scheme.name}")],
                )
            )
            self._edge(EdgeType.CONTAINS, sid, sec_id, service, scheme.pointer, "Declared scheme.")

        for schema in service.schemas:
            self._add_schema(service, sid, schema)

        seen_paths: set[str] = set()
        for op in service.operations:
            ep_id = path_id(service.name, op.path)
            if op.path not in seen_paths:
                seen_paths.add(op.path)
                self.graph.add_node(
                    GraphNode(
                        id=ep_id,
                        type=NodeType.ENDPOINT,
                        label=op.path,
                        project_id=self.project_id,
                        description=f"HTTP endpoint exposed by {service.title or service.name}.",
                        provenance=_spec_provenance(
                            service, f"/paths/{op.path}", "Path declared in the specification."
                        ),
                        attrs={"path": op.path, "kind": op.kind},
                    )
                )
                self._edge(
                    EdgeType.EXPOSES, sid, ep_id, service, op.pointer, f"Exposes {op.path}."
                )
            self._add_operation(service, sid, ep_id, did, op)

    def _add_schema(self, service: NormalizedService, sid: str, schema: NormSchema) -> None:
        scid = schema_id(service.name, schema.name)
        self.graph.add_node(
            GraphNode(
                id=scid,
                type=NodeType.SCHEMA,
                label=schema.name,
                project_id=self.project_id,
                description=schema.description,
                provenance=_spec_provenance(
                    service, schema.pointer, f"Schema '{schema.name}' declared in components."
                ),
                attrs={
                    "service": service.slug,
                    "type": schema.type,
                    "deprecated": schema.deprecated,
                    "recursive": schema.recursive,
                    "required": schema.required,
                    "field_count": len(schema.fields),
                    "composition": schema.composition,
                    "discriminator": schema.discriminator,
                },
                evidence=[
                    _evidence(service, schema.pointer, f"components.schemas.{schema.name}",
                              schema.description)
                ],
            )
        )
        self._edge(EdgeType.CONTAINS, sid, scid, service, schema.pointer, "Declared schema.")

        for field in schema.fields:
            self._add_field(service, scid, schema, field)

    def _add_field(
        self, service: NormalizedService, scid: str, schema: NormSchema, field: NormField
    ) -> None:
        fid = field_id(service.name, schema.name, field.dotted_path)
        self.graph.add_node(
            GraphNode(
                id=fid,
                type=NodeType.FIELD,
                label=field.dotted_path,
                project_id=self.project_id,
                description=field.description,
                provenance=_spec_provenance(
                    service,
                    field.pointer,
                    f"Property '{field.dotted_path}' of {schema.name}.",
                ),
                attrs={
                    "service": service.slug,
                    "schema": schema.name,
                    "name": field.name,
                    "type": field.type,
                    "format": field.format,
                    "type_signature": field.type_signature,
                    "required": field.required,
                    "nullable": field.nullable,
                    "deprecated": field.deprecated,
                    "enum": field.enum,
                    "ref_target": field.ref_target,
                    "array_item_type": field.array_item_type,
                    "sensitive_hint": field.sensitive_hint,
                },
                evidence=[_evidence(service, field.pointer, field.dotted_path, field.description)],
            )
        )
        self._edge(EdgeType.CONTAINS, scid, fid, service, field.pointer, "Declared property.")
        if field.ref_target:
            target = schema_id(service.name, field.ref_target)
            self._edge(
                EdgeType.REFERENCES,
                fid,
                target,
                service,
                field.pointer,
                f"'{field.dotted_path}' is typed as {field.ref_target}.",
            )

    def _add_operation(
        self,
        service: NormalizedService,
        sid: str,
        ep_id: str,
        did: str,
        op: NormOperation,
    ) -> None:
        oid = operation_id(service.name, op.method, op.path)
        self._op_lookup.setdefault(op.operation_id, oid)
        self._op_lookup_qualified[(service.slug, op.operation_id)] = oid
        self.graph.add_node(
            GraphNode(
                id=oid,
                type=NodeType.API_OPERATION,
                label=f"{op.method.upper()} {op.path}",
                project_id=self.project_id,
                description=op.description or op.summary,
                provenance=_spec_provenance(
                    service, op.pointer, f"Operation '{op.operation_id}'."
                ),
                tags=op.tags,
                attrs={
                    "service": service.slug,
                    "operation_id": op.operation_id,
                    "method": op.method.upper(),
                    "path": op.path,
                    "summary": op.summary,
                    "deprecated": op.deprecated,
                    "security": op.security,
                    "security_declared": op.security_declared,
                    "public": op.is_public,
                    "pagination": op.pagination_style,
                    "kind": op.kind,
                    "parameters": [
                        {
                            "name": p.name,
                            "in": p.location,
                            "required": p.required,
                            "type": p.type,
                            "description": p.description,
                        }
                        for p in op.parameters
                    ],
                    "responses": [
                        {
                            "status": r.status,
                            "schema": r.schema_ref,
                            "array": r.is_array,
                            "description": r.description,
                            "example": r.has_example,
                        }
                        for r in op.responses
                    ],
                    "request_schema": op.request_body.schema_ref if op.request_body else None,
                },
                evidence=[_evidence(service, op.pointer, op.signature, op.summary or op.description)],
            )
        )
        self._edge(EdgeType.EXPOSES, ep_id, oid, service, op.pointer, f"{op.method.upper()} handler.")
        self._edge(
            EdgeType.BELONGS_TO_DOMAIN,
            oid,
            did,
            service,
            op.pointer,
            "Inherits the domain of the service that exposes it.",
        )

        for scheme_name in op.security:
            self._edge(
                EdgeType.REQUIRES_SECURITY,
                oid,
                security_scheme_id(service.name, scheme_name),
                service,
                f"{op.pointer}/security",
                f"Requires the '{scheme_name}' security scheme.",
            )

        if op.request_body and op.request_body.schema_ref:
            self._edge(
                EdgeType.USES_REQUEST,
                oid,
                schema_id(service.name, op.request_body.schema_ref),
                service,
                op.request_body.pointer,
                f"Accepts a {op.request_body.schema_ref} request body.",
            )
        for response in op.responses:
            if response.schema_ref:
                self._edge(
                    EdgeType.RETURNS,
                    oid,
                    schema_id(service.name, response.schema_ref),
                    service,
                    response.pointer,
                    f"Returns {response.schema_ref} on {response.status}.",
                    attrs={"status": response.status, "array": response.is_array},
                )
        for param in op.parameters:
            if param.schema_ref:
                self._edge(
                    EdgeType.REFERENCES,
                    oid,
                    schema_id(service.name, param.schema_ref),
                    service,
                    param.pointer,
                    f"Parameter '{param.name}' is typed as {param.schema_ref}.",
                )

    # -- cross-cutting links -------------------------------------------------------

    def _link_schema_references(self) -> None:
        """Schema→schema REFERENCES edges, derived from the fields' resolved refs."""
        for service in self.estate.services:
            for schema in service.schemas:
                src = schema_id(service.name, schema.name)
                for referenced in schema.references:
                    target = schema_id(service.name, referenced)
                    if self.graph.get(target) is None:
                        continue
                    self._edge(
                        EdgeType.REFERENCES,
                        src,
                        target,
                        service,
                        schema.pointer,
                        f"{schema.name} embeds or references {referenced}."
                        + (" This is a self-reference." if referenced == schema.name else ""),
                        attrs={"self_reference": referenced == schema.name},
                    )

    def _link_explicit_dependencies(self) -> None:
        """Wire the ``x-api-galaxy-depends-on`` extension into DEPENDS_ON edges.

        These are *explicit* facts: the specification author said so. Unresolvable
        targets become diagnostics rather than silently-dropped edges.
        """
        for service in self.estate.services:
            for op in service.operations:
                if not op.depends_on:
                    continue
                source = operation_id(service.name, op.method, op.path)
                for dep in op.depends_on:
                    target_svc = slugify(dep.service)
                    target = self._op_lookup_qualified.get((target_svc, dep.operation_id))
                    if target is None:
                        target = self._op_lookup.get(dep.operation_id)
                    if target is None:
                        self.estate.diagnostics.append(
                            _unresolved_dependency(service, op, dep.service, dep.operation_id)
                        )
                        continue
                    self._edge(
                        EdgeType.DEPENDS_ON,
                        source,
                        target,
                        service,
                        f"{op.pointer}/x-api-galaxy-depends-on",
                        dep.reason
                        or f"{op.operation_id} explicitly depends on {dep.operation_id}.",
                        attrs={"explicit": True, "target_service": target_svc},
                    )
                    self._edge(
                        EdgeType.CALLS_OR_PRECEDES,
                        source,
                        target,
                        service,
                        f"{op.pointer}/x-api-galaxy-depends-on",
                        f"{op.operation_id} calls or precedes {dep.operation_id}.",
                        attrs={"explicit": True},
                    )

    # -- helper --------------------------------------------------------------------

    def _edge(
        self,
        edge_type: EdgeType,
        source: str,
        target: str,
        service: NormalizedService,
        pointer: str,
        explanation: str,
        attrs: dict | None = None,
    ) -> GraphEdge | None:
        if self.graph.get(source) is None or self.graph.get(target) is None:
            return None
        return self.graph.add_edge(
            GraphEdge(
                id=edge_id(edge_type.value, source, target),
                type=edge_type,
                source=source,
                target=target,
                label=edge_type.value.replace("_", " ").lower(),
                acceptance=Acceptance.OBSERVED,
                provenance=_spec_provenance(service, pointer, explanation),
                attrs=attrs or {},
                evidence=[_evidence(service, pointer, explanation)],
            )
        )


def _domain_from_tags(service: NormalizedService) -> str | None:
    counts: dict[str, int] = {}
    for op in service.operations:
        for tag in op.tags:
            counts[tag] = counts.get(tag, 0) + 1
    if not counts:
        return None
    return max(sorted(counts), key=lambda t: counts[t])


def _unresolved_dependency(service, op, dep_service: str, dep_op: str):
    from api_galaxy.parsing.normalize import Diagnostic, DiagnosticLevel

    return Diagnostic(
        level=DiagnosticLevel.WARNING,
        code="unresolved-dependency",
        message=(
            f"'{op.operation_id}' declares a dependency on '{dep_op}' in '{dep_service}', "
            "but no such operation was imported."
        ),
        file=service.source_file,
        pointer=f"{op.pointer}/x-api-galaxy-depends-on",
        hint="Import that service too, or correct the operationId.",
    )


def build_graph(
    estate: NormalizedEstate, *, project_id: str, project_name: str
) -> KnowledgeGraph:
    return GraphBuilder(estate, project_id=project_id, project_name=project_name).build()


def iter_operation_nodes(graph: KnowledgeGraph) -> Iterable[GraphNode]:
    return (n for n in graph.nodes if n.type is NodeType.API_OPERATION)
