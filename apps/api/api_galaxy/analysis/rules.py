"""Deterministic risk rules.

Each rule is a pure function of the normalized estate (plus, where useful, the built
graph). Rules that *prove* something are marked ``heuristic=False``; rules that make a
judgement call — PII by field name, "these two identifiers look like the same thing" —
are marked ``heuristic=True`` and the UI says so out loud.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

from api_galaxy.contracts.analysis import Risk, RiskCategory, RiskSeverity
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
    edge_id,
    evidence_id,
    field_id,
    operation_id,
    risk_id,
    schema_id,
    service_id,
)
from api_galaxy.analysis.pii import DEFAULT_DICTIONARY, PiiDictionary
from api_galaxy.parsing.normalize import DiagnosticLevel, NormalizedEstate, NormalizedService

WRITE_METHODS = {"post", "put", "patch", "delete"}
ERROR_STATUS = re.compile(r"^[45]\d\d$|^[45]XX$", re.IGNORECASE)
SNAKE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
CAMEL = re.compile(r"^[a-z][a-zA-Z0-9]*$")


@dataclass
class RuleContext:
    estate: NormalizedEstate
    graph: KnowledgeGraph
    dictionary: PiiDictionary


def _prov(rule_id: str, explanation: str, *, heuristic: bool = False) -> Provenance:
    return Provenance(
        source_kind=SourceKind.DETERMINISTIC_RULE,
        rule_id=rule_id,
        explanation=explanation,
        confidence=0.6 if heuristic else 1.0,
    )


def _ev(service: NormalizedService, pointer: str, label: str) -> Evidence:
    return Evidence(
        id=evidence_id(service.source_file, pointer),
        source_file=service.source_file,
        pointer=pointer,
        label=label,
    )


# --------------------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------------------


def rule_broken_refs(ctx: RuleContext) -> list[Risk]:
    out: list[Risk] = []
    for diagnostic in ctx.estate.diagnostics:
        if diagnostic.code != "broken-ref":
            continue
        out.append(
            Risk(
                id=risk_id("broken-ref", diagnostic.file, diagnostic.pointer),
                rule_id="broken-ref",
                severity=RiskSeverity.HIGH,
                category=RiskCategory.STRUCTURE,
                title="Unresolvable $ref",
                description=diagnostic.message,
                recommendation="Fix the pointer or add the missing component; tooling "
                "downstream of this specification will fail on it.",
                provenance=_prov("broken-ref", "The reference could not be resolved."),
                evidence=[
                    Evidence(
                        id=evidence_id(diagnostic.file, diagnostic.pointer),
                        source_file=diagnostic.file,
                        pointer=diagnostic.pointer,
                        label="Broken reference",
                    )
                ],
            )
        )
    return out


def rule_duplicate_operation_ids(ctx: RuleContext) -> list[Risk]:
    out: list[Risk] = []
    for diagnostic in ctx.estate.diagnostics:
        if diagnostic.code != "duplicate-operation-id":
            continue
        out.append(
            Risk(
                id=risk_id("duplicate-operation-id", diagnostic.file, diagnostic.pointer),
                rule_id="duplicate-operation-id",
                severity=RiskSeverity.MEDIUM,
                category=RiskCategory.STRUCTURE,
                title="Duplicate operationId",
                description=diagnostic.message,
                recommendation="operationIds must be unique; generated clients will "
                "collide or silently drop one of the operations.",
                provenance=_prov("duplicate-operation-id", "Two operations share an ID."),
                evidence=[
                    Evidence(
                        id=evidence_id(diagnostic.file, diagnostic.pointer),
                        source_file=diagnostic.file,
                        pointer=diagnostic.pointer,
                        label="Duplicate operationId",
                    )
                ],
            )
        )
    return out


def rule_unsecured_operations(ctx: RuleContext) -> list[Risk]:
    """Write operations, and read operations over sensitive data, with no security."""
    out: list[Risk] = []
    for service in ctx.estate.services:
        for op in service.operations:
            if op.security:
                continue
            sensitive = _sensitive_fields_reachable(ctx, service, op)
            is_write = op.method in WRITE_METHODS
            if not is_write and not sensitive:
                continue
            severity = RiskSeverity.HIGH if sensitive else RiskSeverity.MEDIUM
            oid = operation_id(service.name, op.method, op.path)
            if sensitive:
                title = "Sensitive data exposed without authentication"
                description = (
                    f"{op.signature} declares no security requirement and its response "
                    f"includes {_humanise(sorted(sensitive))}."
                )
                recommendation = (
                    "Require a security scheme, or remove the sensitive fields from this "
                    "response shape."
                )
            else:
                title = "Unauthenticated write operation"
                description = (
                    f"{op.signature} changes state but declares no security requirement."
                )
                recommendation = "Apply a security scheme to this operation."
            out.append(
                Risk(
                    id=risk_id("unsecured-operation", service.source_file, op.pointer),
                    rule_id="unsecured-operation",
                    severity=severity,
                    category=RiskCategory.SECURITY,
                    title=title,
                    description=description,
                    recommendation=recommendation,
                    heuristic=bool(sensitive) and not _has_declared_sensitive(ctx, service, op),
                    node_ids=[oid],
                    provenance=_prov(
                        "unsecured-operation",
                        "The operation's effective security requirement is empty.",
                    ),
                    evidence=[_ev(service, op.pointer, op.signature)],
                )
            )
    return out


def rule_pii_exposure(ctx: RuleContext) -> list[Risk]:
    """Schemas carrying potentially personal data, so reviewers know where to look."""
    out: list[Risk] = []
    for service in ctx.estate.services:
        for schema in service.schemas:
            hits: list[tuple[str, str, str]] = []
            for fld in schema.fields:
                matches = ctx.dictionary.classify(
                    fld.name, fmt=fld.format, declared_sensitive=fld.sensitive_hint
                )
                strong = [m for m in matches if m.strength in ("direct", "declared", "format")]
                if strong:
                    hits.append((fld.dotted_path, strong[0].category, strong[0].reason))
            if not hits:
                continue
            categories = sorted({c for _, c, _ in hits})
            out.append(
                Risk(
                    id=risk_id("pii-in-schema", service.source_file, schema.pointer),
                    rule_id="pii-in-schema",
                    severity=RiskSeverity.MEDIUM
                    if "credential" not in categories and "government-id" not in categories
                    else RiskSeverity.HIGH,
                    category=RiskCategory.PRIVACY,
                    title=f"{schema.name} carries personal data",
                    description=(
                        f"{len(hits)} field(s) in {service.name}.{schema.name} look like personal "
                        f"data ({', '.join(categories)}): "
                        + ", ".join(path for path, _, _ in hits[:6])
                        + ("…" if len(hits) > 6 else "")
                    ),
                    recommendation="Confirm the classification, then check every operation "
                    "that returns this schema is authenticated and audited.",
                    heuristic=True,
                    node_ids=[schema_id(service.name, schema.name)]
                    + [field_id(service.name, schema.name, path) for path, _, _ in hits[:20]],
                    provenance=_prov(
                        "pii-in-schema",
                        "Field names and formats were matched against the PII dictionary.",
                        heuristic=True,
                    ),
                    evidence=[_ev(service, schema.pointer, schema.name)],
                )
            )
    return out


def rule_orphaned_schemas(ctx: RuleContext) -> list[Risk]:
    out: list[Risk] = []
    for service in ctx.estate.services:
        used: set[str] = set()
        for op in service.operations:
            if op.request_body and op.request_body.schema_ref:
                used.add(op.request_body.schema_ref)
            for response in op.responses:
                if response.schema_ref:
                    used.add(response.schema_ref)
            for param in op.parameters:
                if param.schema_ref:
                    used.add(param.schema_ref)
        for schema in service.schemas:
            for referenced in schema.references:
                if referenced != schema.name:
                    used.add(referenced)
        for schema in service.schemas:
            if schema.name in used:
                continue
            out.append(
                Risk(
                    id=risk_id("orphaned-schema", service.source_file, schema.pointer),
                    rule_id="orphaned-schema",
                    severity=RiskSeverity.LOW,
                    category=RiskCategory.STRUCTURE,
                    title=f"Schema '{schema.name}' is never used",
                    description=(
                        f"{service.name} declares {schema.name} but no operation or other "
                        "schema references it."
                    ),
                    recommendation="Remove it, or wire it up — unused schemas mislead "
                    "consumers and bloat generated clients.",
                    node_ids=[schema_id(service.name, schema.name)],
                    provenance=_prov("orphaned-schema", "No inbound reference was found."),
                    evidence=[_ev(service, schema.pointer, schema.name)],
                )
            )
    return out


def rule_circular_dependencies(ctx: RuleContext) -> list[Risk]:
    """Cycles at two levels: operation→operation, and (more usefully) service→service.

    Estates rarely have a literal operation loop. What they do have is order-api calling
    inventory-api while inventory-api calls back into order-api — a real coupling problem
    that is invisible unless you collapse operations onto the service that owns them.
    """
    import networkx as nx

    index = ctx.graph.node_index()
    out: list[Risk] = []

    # --- service-level projection -------------------------------------------------
    service_graph = nx.DiGraph()
    edge_witnesses: dict[tuple[str, str], list[str]] = defaultdict(list)
    for edge in ctx.graph.edges:
        if edge.type is not EdgeType.DEPENDS_ON:
            continue
        source = index.get(edge.source)
        target = index.get(edge.target)
        if source is None or target is None:
            continue
        src_service = str(source.attrs.get("service") or "")
        dst_service = str(target.attrs.get("service") or "")
        if not src_service or not dst_service or src_service == dst_service:
            continue
        service_graph.add_edge(src_service, dst_service)
        edge_witnesses[(src_service, dst_service)].append(f"{source.label} → {target.label}")

    seen: set[str] = set()
    for cycle in nx.simple_cycles(service_graph):
        if len(cycle) < 2:
            continue
        signature = "|".join(sorted(cycle))
        if signature in seen:
            continue
        seen.add(signature)
        legs: list[str] = []
        witnesses: list[str] = []
        for position, service in enumerate(cycle):
            nxt = cycle[(position + 1) % len(cycle)]
            legs.append(f"{service} → {nxt}")
            witnesses.extend(edge_witnesses.get((service, nxt), [])[:2])
        out.append(
            Risk(
                id=risk_id("circular-dependency", *sorted(cycle)),
                rule_id="circular-dependency",
                severity=RiskSeverity.MEDIUM,
                category=RiskCategory.STRUCTURE,
                title=f"Circular dependency between {' and '.join(sorted(cycle))}",
                description=(
                    "These services depend on each other in a loop: "
                    + ", ".join(legs)
                    + ". Declared by: "
                    + "; ".join(witnesses[:4])
                    + "."
                ),
                recommendation="The specification is still valid, but a cycle makes "
                "deployment ordering, local testing and failure isolation harder. An event "
                "or a saga usually breaks it.",
                node_ids=[service_id(name) for name in sorted(cycle)],
                provenance=_prov(
                    "circular-dependency",
                    "Declared dependency edges were collapsed onto their owning services, "
                    "and a directed cycle was found.",
                ),
            )
        )

    # --- operation-level cycles ---------------------------------------------------
    from api_galaxy.graph.engine import NetworkXGraphRepository

    repo = NetworkXGraphRepository(ctx.graph)
    for cycle in repo.cycles(
        limit=10, edge_types={EdgeType.DEPENDS_ON, EdgeType.CALLS_OR_PRECEDES}
    ):
        labels = [index[n].label for n in cycle if n in index]
        if len(labels) < 2:
            continue
        signature = "op|" + "|".join(sorted(cycle))
        if signature in seen:
            continue
        seen.add(signature)
        out.append(
            Risk(
                id=risk_id("circular-dependency", *cycle),
                rule_id="circular-dependency",
                severity=RiskSeverity.MEDIUM,
                category=RiskCategory.STRUCTURE,
                title="Circular dependency between operations",
                description="These operations depend on each other in a loop: "
                + " → ".join([*labels, labels[0]])
                + ".",
                recommendation="Break the loop, or document which side is authoritative.",
                node_ids=list(cycle),
                provenance=_prov(
                    "circular-dependency",
                    "A directed cycle was found over declared dependency edges.",
                ),
            )
        )
    return out


def rule_schema_cycles(ctx: RuleContext) -> list[Risk]:
    out: list[Risk] = []
    for service in ctx.estate.services:
        for schema in service.schemas:
            if not schema.recursive:
                continue
            out.append(
                Risk(
                    id=risk_id("recursive-schema", service.source_file, schema.pointer),
                    rule_id="recursive-schema",
                    severity=RiskSeverity.INFO,
                    category=RiskCategory.STRUCTURE,
                    title=f"{schema.name} is recursive",
                    description=f"{schema.name} references itself. This parses, but some "
                    "code generators and validators handle it poorly.",
                    recommendation="Confirm your client generator supports recursion, and "
                    "bound the depth at the API edge.",
                    node_ids=[schema_id(service.name, schema.name)],
                    provenance=_prov("recursive-schema", "The schema references itself."),
                    evidence=[_ev(service, schema.pointer, schema.name)],
                )
            )
    return out


def rule_deprecated_still_used(ctx: RuleContext) -> list[Risk]:
    """Deprecated operations that other operations still declare a dependency on."""
    depended_on: set[tuple[str, str]] = set()
    for service in ctx.estate.services:
        for op in service.operations:
            for dep in op.depends_on:
                depended_on.add((dep.service, dep.operation_id))
    out: list[Risk] = []
    for service in ctx.estate.services:
        for op in service.operations:
            if not op.deprecated:
                continue
            referenced = any(
                op.operation_id == dep_op
                for dep_svc, dep_op in depended_on
            ) or bool(op.depends_on)
            out.append(
                Risk(
                    id=risk_id("deprecated-in-use", service.source_file, op.pointer),
                    rule_id="deprecated-in-use",
                    severity=RiskSeverity.MEDIUM if referenced else RiskSeverity.LOW,
                    category=RiskCategory.COMPATIBILITY,
                    title=f"Deprecated operation {'still participates in a flow' if referenced else 'is published'}",
                    description=(
                        f"{op.signature} ({op.operation_id}) is marked deprecated"
                        + (
                            " yet it is still part of a declared dependency chain."
                            if referenced
                            else "."
                        )
                    ),
                    recommendation="Publish the replacement, move consumers across, then "
                    "remove it on a announced date.",
                    node_ids=[operation_id(service.name, op.method, op.path)],
                    provenance=_prov("deprecated-in-use", "The operation sets deprecated: true."),
                    evidence=[_ev(service, op.pointer, op.signature)],
                )
            )
    return out


def rule_inconsistent_error_models(ctx: RuleContext) -> list[Risk]:
    envelopes: dict[str, list[str]] = defaultdict(list)
    for service in ctx.estate.services:
        names: set[str] = set()
        for op in service.operations:
            for response in op.responses:
                if ERROR_STATUS.match(response.status) and response.schema_ref:
                    names.add(response.schema_ref)
        for name in names:
            envelopes[name].append(service.name)
    if len(envelopes) < 2:
        return []
    described = "; ".join(
        f"'{name}' in {', '.join(sorted(services))}" for name, services in sorted(envelopes.items())
    )
    return [
        Risk(
            id=risk_id("inconsistent-error-model", *sorted(envelopes)),
            rule_id="inconsistent-error-model",
            severity=RiskSeverity.MEDIUM,
            category=RiskCategory.CONSISTENCY,
            title="Services return different error envelopes",
            description=f"{len(envelopes)} different error shapes are in use across the "
            f"estate: {described}.",
            recommendation="Standardise on one error envelope (RFC 9457 problem details "
            "is a good default) so clients need one error handler, not many.",
            node_ids=[
                schema_id(svc, name) for name, services in envelopes.items() for svc in services
            ],
            provenance=_prov(
                "inconsistent-error-model",
                "Error responses across services resolve to different schemas.",
            ),
        )
    ]


def rule_inconsistent_pagination(ctx: RuleContext) -> list[Risk]:
    styles: dict[str, list[str]] = defaultdict(list)
    for service in ctx.estate.services:
        for op in service.operations:
            style = op.pagination_style
            if style:
                styles[style].append(f"{service.name} {op.signature}")
    if len(styles) < 2:
        return []
    return [
        Risk(
            id=risk_id("inconsistent-pagination", *sorted(styles)),
            rule_id="inconsistent-pagination",
            severity=RiskSeverity.LOW,
            category=RiskCategory.CONSISTENCY,
            title="Pagination conventions differ across the estate",
            description="; ".join(
                f"{style}: {', '.join(sorted(examples)[:3])}"
                + ("…" if len(examples) > 3 else "")
                for style, examples in sorted(styles.items())
            ),
            recommendation="Pick one convention. Mixed pagination is the most common cause "
            "of subtly broken list endpoints in generated clients.",
            heuristic=True,
            provenance=_prov(
                "inconsistent-pagination",
                "Query parameter names were matched against known pagination styles.",
                heuristic=True,
            ),
        )
    ]


# Qualifiers that describe *which* amount/date/count a field holds without changing the
# underlying concept, so `total_amount` and `amount` should be compared with each other.
VALUE_QUALIFIERS = (
    "total_", "sub_", "subtotal_", "net_", "gross_", "unit_", "base_", "final_",
    "original_", "discounted_", "paid_", "authorized_", "captured_", "refunded_",
)


ERROR_ENVELOPE_HINTS = ("error", "problem", "fault", "failure")


def _is_error_envelope(schema_name: str) -> bool:
    lowered = schema_name.lower()
    return any(hint in lowered for hint in ERROR_ENVELOPE_HINTS)


def _base_type(signature: str) -> str:
    """'array<OrderLine>' → 'array'; 'string(decimal)' → 'string'."""
    return signature.split("(")[0].split("<")[0]


def _concept_key(name: str) -> str:
    lowered = name.lower()
    for qualifier in VALUE_QUALIFIERS:
        if lowered.startswith(qualifier) and len(lowered) > len(qualifier):
            return lowered[len(qualifier) :]
    if lowered == "subtotal":
        return "total"
    return lowered


def rule_type_change_across_boundary(ctx: RuleContext) -> list[Risk]:
    """The same business concept typed differently in two services.

    Matching is on the *concept*, not the literal field name: ``Order.total_amount`` and
    ``Payment.amount`` are the same money value crossing a service boundary, and the fact
    that one is a JSON number and the other a decimal string is exactly the kind of bug
    this rule exists to surface.
    """
    by_concept: dict[str, set[tuple[str, str, str, str, str]]] = defaultdict(set)
    for service in ctx.estate.services:
        for schema in service.schemas:
            # Error envelopes reuse generic words (`status`, `type`, `detail`) with
            # transport meanings. Comparing their `status` to a domain `status` produces
            # a confident, entirely useless finding, so they sit this rule out.
            if _is_error_envelope(schema.name):
                continue
            for fld in schema.fields:
                if "." in fld.dotted_path:
                    continue
                by_concept[_concept_key(fld.name)].add(
                    (service.name, schema.name, fld.name, fld.type_signature, fld.pointer)
                )
    out: list[Risk] = []
    for concept, entries in sorted(by_concept.items()):
        services = {e[0] for e in entries}
        signatures = {e[3] for e in entries}
        base_types = {_base_type(sig) for sig in signatures}
        if len(services) < 2 or len(signatures) < 2:
            continue
        if len(base_types) == 1 and any("(" not in sig for sig in signatures):
            # Same underlying type, and at least one side simply declares no format —
            # `array<object>` vs `array<OrderLine>` is a documentation gap, not a
            # boundary conversion bug. The orphaned/undocumented-schema rules cover it.
            continue
        described = ", ".join(
            f"{svc}.{schema}.{name} is {sig}" for svc, schema, name, sig, _ in sorted(entries)
        )
        # A differing base type (number vs string) is materially worse than a differing
        # format on the same base type.
        severity = RiskSeverity.HIGH if len(base_types) > 1 else RiskSeverity.MEDIUM
        out.append(
            Risk(
                id=risk_id("type-change-across-boundary", concept, *sorted(signatures)),
                rule_id="type-change-across-boundary",
                severity=severity,
                category=RiskCategory.COMPATIBILITY,
                title=f"'{concept}' has different types in different services",
                description=f"{described}. A value crossing this boundary needs an explicit "
                "conversion, and rounding or precision bugs hide here.",
                recommendation="Agree one representation, or document the conversion "
                "explicitly at the boundary.",
                heuristic=True,
                node_ids=[
                    field_id(svc, schema, name) for svc, schema, name, _, _ in sorted(entries)
                ],
                provenance=_prov(
                    "type-change-across-boundary",
                    "Fields naming the same concept resolve to different declared types.",
                    heuristic=True,
                ),
            )
        )
    return out


def rule_naming_inconsistency(ctx: RuleContext) -> list[Risk]:
    snake = 0
    camel = 0
    other = 0
    examples: dict[str, list[str]] = {"snake_case": [], "camelCase": [], "other": []}
    for service in ctx.estate.services:
        for schema in service.schemas:
            for fld in schema.fields:
                if "." in fld.dotted_path:
                    continue
                if "_" in fld.name and SNAKE.match(fld.name):
                    snake += 1
                    if len(examples["snake_case"]) < 3:
                        examples["snake_case"].append(f"{schema.name}.{fld.name}")
                elif CAMEL.match(fld.name) and any(c.isupper() for c in fld.name):
                    camel += 1
                    if len(examples["camelCase"]) < 3:
                        examples["camelCase"].append(f"{schema.name}.{fld.name}")
                elif not SNAKE.match(fld.name) and not CAMEL.match(fld.name):
                    other += 1
                    if len(examples["other"]) < 3:
                        examples["other"].append(f"{schema.name}.{fld.name}")
    styles = {k: v for k, v in {"snake_case": snake, "camelCase": camel, "other": other}.items() if v}
    if len(styles) < 2:
        return []
    return [
        Risk(
            id=risk_id("naming-inconsistency", *sorted(styles)),
            rule_id="naming-inconsistency",
            severity=RiskSeverity.LOW,
            category=RiskCategory.CONSISTENCY,
            title="Field naming styles are mixed",
            description="; ".join(
                f"{style}: {count} field(s)" + (f" e.g. {', '.join(examples[style])}" if examples[style] else "")
                for style, count in sorted(styles.items())
            ),
            recommendation="Pick one casing convention across the estate.",
            heuristic=True,
            provenance=_prov(
                "naming-inconsistency", "Top-level field names were classified by casing.",
                heuristic=True,
            ),
        )
    ]


def rule_missing_error_responses(ctx: RuleContext) -> list[Risk]:
    offenders: list[tuple[str, str, str]] = []
    for service in ctx.estate.services:
        for op in service.operations:
            if op.kind != "path":
                continue
            if not any(ERROR_STATUS.match(r.status) for r in op.responses):
                offenders.append((service.name, op.signature, op.pointer))
    if not offenders:
        return []
    return [
        Risk(
            id=risk_id("missing-error-response", *[o[1] for o in offenders[:8]]),
            rule_id="missing-error-response",
            severity=RiskSeverity.LOW,
            category=RiskCategory.CONSISTENCY,
            title=f"{len(offenders)} operation(s) document no failure response",
            description="These operations declare only success responses: "
            + ", ".join(f"{svc} {sig}" for svc, sig, _ in offenders[:6])
            + ("…" if len(offenders) > 6 else ""),
            recommendation="Document at least the 4xx your clients will actually hit.",
            provenance=_prov(
                "missing-error-response", "No 4xx/5xx response was declared."
            ),
        )
    ]


def rule_missing_examples(ctx: RuleContext) -> list[Risk]:
    missing = [
        (service.name, op.signature)
        for service in ctx.estate.services
        for op in service.operations
        if op.kind == "path"
        and not any(r.has_example for r in op.responses if r.status.startswith("2"))
    ]
    if not missing:
        return []
    total = len(ctx.estate.all_operations) or 1
    return [
        Risk(
            id=risk_id("missing-response-example", str(len(missing))),
            rule_id="missing-response-example",
            severity=RiskSeverity.INFO,
            category=RiskCategory.CONSISTENCY,
            title=f"{len(missing)} of {total} operations have no success example",
            description="Examples are what make an API learnable and what mock servers "
            "use. Missing: "
            + ", ".join(f"{svc} {sig}" for svc, sig in missing[:6])
            + ("…" if len(missing) > 6 else ""),
            recommendation="Add one realistic example per success response.",
            provenance=_prov(
                "missing-response-example", "No example was declared on any 2xx response."
            ),
        )
    ]


def rule_weak_security_schemes(ctx: RuleContext) -> list[Risk]:
    out: list[Risk] = []
    for service in ctx.estate.services:
        for scheme in service.security_schemes:
            if scheme.strength != "weak":
                continue
            used_by_write = any(
                scheme.name in op.security and op.method in WRITE_METHODS
                for op in service.operations
            )
            if not used_by_write:
                continue
            out.append(
                Risk(
                    id=risk_id("weak-security-scheme", service.source_file, scheme.pointer),
                    rule_id="weak-security-scheme",
                    severity=RiskSeverity.MEDIUM,
                    category=RiskCategory.SECURITY,
                    title=f"Write operations protected only by {scheme.name}",
                    description=f"{service.name} protects state-changing operations with a "
                    f"{scheme.type} scheme, which carries no expiry, audience or scope.",
                    recommendation="Use OAuth2 or a signed bearer token for write paths.",
                    heuristic=True,
                    node_ids=[service_id(service.name)],
                    provenance=_prov(
                        "weak-security-scheme",
                        "The scheme type offers no scoping or expiry.",
                        heuristic=True,
                    ),
                    evidence=[_ev(service, scheme.pointer, scheme.name)],
                )
            )
    return out


ALL_RULES: list[Callable[[RuleContext], list[Risk]]] = [
    rule_broken_refs,
    rule_duplicate_operation_ids,
    rule_unsecured_operations,
    rule_pii_exposure,
    rule_orphaned_schemas,
    rule_circular_dependencies,
    rule_schema_cycles,
    rule_deprecated_still_used,
    rule_inconsistent_error_models,
    rule_inconsistent_pagination,
    rule_type_change_across_boundary,
    rule_naming_inconsistency,
    rule_missing_error_responses,
    rule_missing_examples,
    rule_weak_security_schemes,
]

RULE_CATALOG: list[dict[str, str]] = [
    {"id": "broken-ref", "what": "A $ref that points at nothing.", "kind": "deterministic"},
    {"id": "duplicate-operation-id", "what": "Two operations sharing an operationId.",
     "kind": "deterministic"},
    {"id": "unsecured-operation", "what": "State-changing or sensitive operations with no "
     "security requirement.", "kind": "deterministic"},
    {"id": "pii-in-schema", "what": "Schemas carrying probable personal data.",
     "kind": "heuristic"},
    {"id": "orphaned-schema", "what": "A schema nothing references.", "kind": "deterministic"},
    {"id": "circular-dependency", "what": "A dependency loop between operations/services.",
     "kind": "deterministic"},
    {"id": "recursive-schema", "what": "A schema that references itself.",
     "kind": "deterministic"},
    {"id": "deprecated-in-use", "what": "A deprecated operation still in a dependency chain.",
     "kind": "deterministic"},
    {"id": "inconsistent-error-model", "what": "More than one error envelope in the estate.",
     "kind": "deterministic"},
    {"id": "inconsistent-pagination", "what": "Mixed pagination conventions.",
     "kind": "heuristic"},
    {"id": "type-change-across-boundary", "what": "One field name, several declared types.",
     "kind": "heuristic"},
    {"id": "naming-inconsistency", "what": "Mixed field-name casing.", "kind": "heuristic"},
    {"id": "missing-error-response", "what": "Operations documenting no failure case.",
     "kind": "deterministic"},
    {"id": "missing-response-example", "what": "Success responses without examples.",
     "kind": "deterministic"},
    {"id": "weak-security-scheme", "what": "Writes protected only by an API key or basic auth.",
     "kind": "heuristic"},
    {"id": "alias-ambiguity", "what": "Several identifiers that appear to mean the same thing.",
     "kind": "heuristic"},
]


# --------------------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------------------


def run_rules(
    estate: NormalizedEstate,
    graph: KnowledgeGraph,
    *,
    dictionary: PiiDictionary | None = None,
) -> list[Risk]:
    ctx = RuleContext(estate=estate, graph=graph, dictionary=dictionary or DEFAULT_DICTIONARY)
    risks: list[Risk] = []
    for rule in ALL_RULES:
        try:
            risks.extend(rule(ctx))
        except Exception as exc:  # pragma: no cover - a broken rule must not kill the import
            risks.append(
                Risk(
                    id=risk_id("rule-error", rule.__name__),
                    rule_id="rule-error",
                    severity=RiskSeverity.INFO,
                    category=RiskCategory.STRUCTURE,
                    title=f"Rule '{rule.__name__}' failed to run",
                    description=f"{type(exc).__name__}: {exc}",
                    provenance=_prov("rule-error", "A rule raised an exception."),
                )
            )
    risks.sort(key=lambda r: (r.severity.rank, r.rule_id, r.id))
    return risks


def attach_risks_to_graph(graph: KnowledgeGraph, risks: list[Risk]) -> None:
    """Materialise risks as graph nodes so they are navigable and exportable."""
    for risk in risks:
        graph.add_node(
            GraphNode(
                id=risk.id,
                type=NodeType.RISK,
                label=risk.title,
                project_id=graph.project_id,
                description=risk.description,
                acceptance=Acceptance.OBSERVED,
                provenance=risk.provenance,
                attrs={
                    "rule_id": risk.rule_id,
                    "severity": risk.severity.value,
                    "category": risk.category.value,
                    "heuristic": risk.heuristic,
                    "recommendation": risk.recommendation,
                },
                evidence=risk.evidence,
            )
        )
        for node_id in risk.node_ids:
            if graph.get(node_id) is None:
                continue
            graph.add_edge(
                GraphEdge(
                    id=edge_id(EdgeType.AFFECTS.value, risk.id, node_id),
                    type=EdgeType.AFFECTS,
                    source=risk.id,
                    target=node_id,
                    label="affects",
                    provenance=risk.provenance,
                    attrs={"severity": risk.severity.value},
                )
            )


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def _sensitive_fields_reachable(ctx: RuleContext, service, op) -> set[str]:
    """Sensitive field names present in any schema the operation returns."""
    names: set[str] = set()
    for response in op.responses:
        if not response.schema_ref or not response.status.startswith("2"):
            continue
        for schema_name in _schema_closure(service, response.schema_ref):
            schema = service.schema_by_name(schema_name)
            if schema is None:
                continue
            for fld in schema.fields:
                if ctx.dictionary.is_sensitive(
                    fld.name, fmt=fld.format, declared=fld.sensitive_hint
                ):
                    names.add(fld.name)
    return names


def _has_declared_sensitive(ctx: RuleContext, service, op) -> bool:
    for response in op.responses:
        if not response.schema_ref:
            continue
        for schema_name in _schema_closure(service, response.schema_ref):
            schema = service.schema_by_name(schema_name)
            if schema and any(f.sensitive_hint for f in schema.fields):
                return True
    return False


def _schema_closure(service, root: str, *, max_depth: int = 3) -> set[str]:
    """The schema plus the schemas it embeds, bounded so recursion terminates."""
    seen = {root}
    frontier = [(root, 0)]
    while frontier:
        name, depth = frontier.pop()
        if depth >= max_depth:
            continue
        schema = service.schema_by_name(name)
        if schema is None:
            continue
        for referenced in schema.references:
            if referenced not in seen:
                seen.add(referenced)
                frontier.append((referenced, depth + 1))
    return seen


def _humanise(names: list[str]) -> str:
    if len(names) == 1:
        return f"'{names[0]}'"
    if len(names) == 2:
        return f"'{names[0]}' and '{names[1]}'"
    return ", ".join(f"'{n}'" for n in names[:-1]) + f" and '{names[-1]}'"
