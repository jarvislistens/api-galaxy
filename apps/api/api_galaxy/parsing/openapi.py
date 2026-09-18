"""The OpenAPI 3.0 / 3.1 parser.

Nothing in this module guesses. Every value written into the normalized estate came
literally from the document, and every element records the JSON Pointer it came from so
the UI can always answer "how do you know that?".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api_galaxy.contracts.ids import fingerprint, slugify
from api_galaxy.parsing.loader import (
    LoadedDocument,
    load_spec_file,
    load_spec_text,
    looks_like_postman,
    postman_to_openapi,
)
from api_galaxy.parsing.normalize import (
    Diagnostic,
    DiagnosticLevel,
    NormalizedEstate,
    NormalizedService,
    NormDependency,
    NormField,
    NormOperation,
    NormParameter,
    NormRequestBody,
    NormResponse,
    NormSchema,
    NormSecurityScheme,
    NormServer,
)
from api_galaxy.parsing.refs import RefResolver, escape_pointer_segment

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
MAX_FIELD_DEPTH = 6
MAX_FIELDS_PER_SCHEMA = 400

EXT_DEPENDS_ON = "x-api-galaxy-depends-on"
EXT_DOMAIN = "x-api-galaxy-domain"
EXT_SENSITIVE = "x-api-galaxy-sensitive"


def _ptr(*segments: str) -> str:
    return "/" + "/".join(escape_pointer_segment(s) for s in segments)


class OpenAPIParser:
    """Parses one OpenAPI document into one :class:`NormalizedService`."""

    def __init__(
        self,
        document: LoadedDocument,
        *,
        service_name: str | None = None,
        domain: str | None = None,
        allow_remote_refs: bool = False,
    ) -> None:
        self.doc = document
        self.data = document.data
        self.source_file = document.source_file
        self.diagnostics: list[Diagnostic] = []
        self.resolver = RefResolver(
            self.data, source_file=self.source_file, allow_remote=allow_remote_refs
        )
        info = self.data.get("info") or {}
        self.title = str(info.get("title") or Path(self.source_file).stem)
        self.service_name = service_name or Path(self.source_file).stem or slugify(self.title)
        self.domain_override = domain

    # -- diagnostics ---------------------------------------------------------------

    def _diag(
        self,
        level: DiagnosticLevel,
        code: str,
        message: str,
        pointer: str = "",
        hint: str = "",
    ) -> None:
        self.diagnostics.append(
            Diagnostic(
                level=level,
                code=code,
                message=message,
                file=self.source_file,
                pointer=pointer,
                hint=hint,
            )
        )

    # -- entry point ---------------------------------------------------------------

    def parse(self) -> NormalizedService:
        version = self._check_version()
        info = self.data.get("info") or {}

        service = NormalizedService(
            name=self.service_name,
            slug=slugify(self.service_name),
            title=self.title,
            version=str(info.get("version") or ""),
            description=str(info.get("description") or ""),
            openapi_version=version,
            domain=self.domain_override or self._as_str(self.data.get(EXT_DOMAIN)),
            source_file=self.source_file,
            servers=self._parse_servers(),
            security_schemes=self._parse_security_schemes(),
            tags=self._parse_tags(),
        )
        service.global_security = self._parse_security(self.data.get("security"), "/security")[0]
        service.schemas = self._parse_schemas()
        service.operations = self._parse_operations(service)

        self._check_duplicate_operation_ids(service)
        self._record_broken_refs()
        service.diagnostics = list(self.diagnostics)
        return service

    # -- version -------------------------------------------------------------------

    def _check_version(self) -> str:
        if "swagger" in self.data:
            self._diag(
                DiagnosticLevel.ERROR,
                "unsupported-version",
                f"Swagger {self.data.get('swagger')} is not supported.",
                "/swagger",
                hint="Convert to OpenAPI 3.0 or 3.1 first (for example with swagger2openapi).",
            )
            return str(self.data.get("swagger"))
        raw = self.data.get("openapi")
        if not isinstance(raw, str):
            self._diag(
                DiagnosticLevel.ERROR,
                "missing-openapi-version",
                "The document has no top-level 'openapi' version string.",
                "/openapi",
                hint="Add e.g. `openapi: 3.0.3`.",
            )
            return ""
        if not raw.startswith(("3.0", "3.1")):
            self._diag(
                DiagnosticLevel.WARNING,
                "unknown-openapi-version",
                f"OpenAPI {raw} is outside the tested 3.0/3.1 range; parsing best-effort.",
                "/openapi",
            )
        if not isinstance(self.data.get("info"), dict):
            self._diag(
                DiagnosticLevel.ERROR, "missing-info", "The document has no 'info' object.", "/info"
            )
        if not isinstance(self.data.get("paths"), dict) and not isinstance(
            self.data.get("webhooks"), dict
        ):
            self._diag(
                DiagnosticLevel.ERROR,
                "missing-paths",
                "The document declares neither 'paths' nor 'webhooks'.",
                "/paths",
            )
        return raw

    # -- simple sections -----------------------------------------------------------

    @staticmethod
    def _as_str(value: Any) -> str | None:
        return str(value) if isinstance(value, str) and value.strip() else None

    def _parse_servers(self) -> list[NormServer]:
        servers = self.data.get("servers")
        if not isinstance(servers, list):
            return []
        out: list[NormServer] = []
        for index, entry in enumerate(servers):
            if not isinstance(entry, dict) or "url" not in entry:
                continue
            out.append(
                NormServer(
                    url=str(entry["url"]),
                    description=str(entry.get("description") or ""),
                    pointer=_ptr("servers", str(index)),
                )
            )
        return out

    def _parse_tags(self) -> list[dict[str, str]]:
        tags = self.data.get("tags")
        if not isinstance(tags, list):
            return []
        return [
            {"name": str(t.get("name", "")), "description": str(t.get("description") or "")}
            for t in tags
            if isinstance(t, dict) and t.get("name")
        ]

    def _parse_security_schemes(self) -> list[NormSecurityScheme]:
        components = self.data.get("components")
        if not isinstance(components, dict):
            return []
        schemes = components.get("securitySchemes")
        if not isinstance(schemes, dict):
            return []
        out: list[NormSecurityScheme] = []
        for name, raw in sorted(schemes.items()):
            value, _ = self.resolver.deref(raw)
            if not isinstance(value, dict):
                continue
            out.append(
                NormSecurityScheme(
                    name=str(name),
                    type=str(value.get("type") or "unknown"),
                    scheme=self._as_str(value.get("scheme")),
                    bearer_format=self._as_str(value.get("bearerFormat")),
                    location=self._as_str(value.get("in")),
                    param_name=self._as_str(value.get("name")),
                    description=str(value.get("description") or ""),
                    pointer=_ptr("components", "securitySchemes", str(name)),
                )
            )
        return out

    def _parse_security(self, raw: Any, pointer: str) -> tuple[list[str], bool]:
        """Return (scheme names, was_declared). An empty list with declared=True means
        the operation deliberately opted out of authentication."""
        if raw is None:
            return [], False
        if not isinstance(raw, list):
            self._diag(
                DiagnosticLevel.WARNING,
                "invalid-security",
                "'security' must be an array of requirement objects.",
                pointer,
            )
            return [], False
        names: list[str] = []
        for entry in raw:
            if isinstance(entry, dict):
                for key in entry:
                    if key not in names:
                        names.append(str(key))
        return names, True

    # -- schemas -------------------------------------------------------------------

    def _parse_schemas(self) -> list[NormSchema]:
        components = self.data.get("components")
        raw_schemas = components.get("schemas") if isinstance(components, dict) else None
        if not isinstance(raw_schemas, dict):
            return []
        out: list[NormSchema] = []
        for name, raw in sorted(raw_schemas.items()):
            pointer = _ptr("components", "schemas", str(name))
            value, _ = self.resolver.deref(raw, pointer_hint=pointer)
            if not isinstance(value, dict):
                self._diag(
                    DiagnosticLevel.WARNING,
                    "unreadable-schema",
                    f"Schema '{name}' could not be read.",
                    pointer,
                )
                continue
            out.append(self._normalize_schema(str(name), value, pointer))
        return out

    def _normalize_schema(self, name: str, raw: dict[str, Any], pointer: str) -> NormSchema:
        declared_type = _type_of(raw)
        schema = NormSchema(
            name=name,
            service=self.service_name,
            title=str(raw.get("title") or ""),
            description=str(raw.get("description") or ""),
            type=declared_type or ("object" if "properties" in raw else "any"),
            pointer=pointer,
            deprecated=bool(raw.get("deprecated")),
            required=[str(r) for r in raw.get("required", []) if isinstance(r, str)],
            example=raw.get("example"),
            discriminator=(raw.get("discriminator") or {}).get("propertyName")
            if isinstance(raw.get("discriminator"), dict)
            else None,
        )

        references: list[str] = []
        composition: dict[str, list[str]] = {}
        for keyword in ("allOf", "oneOf", "anyOf"):
            entries = raw.get(keyword)
            if not isinstance(entries, list):
                continue
            named: list[str] = []
            for index, entry in enumerate(entries):
                if self.resolver.is_ref(entry):
                    _, resolved = self.resolver.deref(
                        entry, pointer_hint=f"{pointer}/{keyword}/{index}"
                    )
                    if resolved and resolved.component_name:
                        named.append(resolved.component_name)
                        references.append(resolved.component_name)
                elif isinstance(entry, dict) and keyword == "allOf":
                    # Inline allOf members contribute their properties to this schema.
                    self._collect_fields(
                        schema,
                        entry,
                        prefix="",
                        pointer=f"{pointer}/{keyword}/{index}",
                        depth=0,
                        required=set(entry.get("required", []) or []),
                        references=references,
                        seen={name},
                    )
            if named:
                composition[keyword] = named
        schema.composition = composition

        self._collect_fields(
            schema,
            raw,
            prefix="",
            pointer=pointer,
            depth=0,
            required=set(schema.required),
            references=references,
            seen={name},
        )

        # Stable, de-duplicated reference list. Self-references are kept: a recursive
        # schema is a real fact the cycle detector and the graph legend both surface.
        schema.references = sorted({r for r in references if r})
        schema.recursive = name in references
        return schema

    def _collect_fields(
        self,
        schema: NormSchema,
        raw: dict[str, Any],
        *,
        prefix: str,
        pointer: str,
        depth: int,
        required: set[str],
        references: list[str],
        seen: set[str],
    ) -> None:
        """Flatten ``raw``'s properties into ``schema.fields`` using dotted paths.

        Recursion is bounded twice over: by ``MAX_FIELD_DEPTH`` and by ``seen``, which
        holds the schema names already on the current branch. A self-referencing schema
        therefore produces one field with ``ref_target`` set and stops — no infinite loop.
        """
        if depth > MAX_FIELD_DEPTH or len(schema.fields) >= MAX_FIELDS_PER_SCHEMA:
            return
        properties = raw.get("properties")
        if not isinstance(properties, dict):
            return

        for prop_name, prop_raw in properties.items():
            if len(schema.fields) >= MAX_FIELDS_PER_SCHEMA:
                self._diag(
                    DiagnosticLevel.WARNING,
                    "schema-too-wide",
                    f"Schema '{schema.name}' has more than {MAX_FIELDS_PER_SCHEMA} fields; "
                    "the remainder was not expanded.",
                    schema.pointer,
                )
                return
            dotted = f"{prefix}{prop_name}"
            prop_pointer = f"{pointer}/properties/{escape_pointer_segment(str(prop_name))}"
            value = prop_raw
            ref_target: str | None = None
            cyclic = False

            if self.resolver.is_ref(prop_raw):
                ref = prop_raw["$ref"]
                resolved_value, resolved = self.resolver.deref(prop_raw, pointer_hint=prop_pointer)
                if resolved is not None:
                    ref_target = resolved.component_name
                    cyclic = resolved.cyclic
                    if ref_target:
                        references.append(ref_target)
                if resolved_value is None:
                    value = {}
                else:
                    value = resolved_value
                if ref_target and ref_target in seen:
                    cyclic = True
                if ref is not None and not isinstance(value, dict):
                    value = {}

            if not isinstance(value, dict):
                value = {}

            array_item_type: str | None = None
            if _type_of(value) == "array":
                items = value.get("items")
                if self.resolver.is_ref(items):
                    _, item_resolved = self.resolver.deref(
                        items, pointer_hint=f"{prop_pointer}/items"
                    )
                    if item_resolved and item_resolved.component_name:
                        array_item_type = item_resolved.component_name
                        references.append(item_resolved.component_name)
                        ref_target = ref_target or item_resolved.component_name
                        if item_resolved.component_name in seen:
                            cyclic = True
                elif isinstance(items, dict):
                    array_item_type = _type_of(items) or "object"

            # allOf on a property merges in the referenced schema names too.
            for keyword in ("allOf", "oneOf", "anyOf"):
                entries = value.get(keyword)
                if isinstance(entries, list):
                    for index, entry in enumerate(entries):
                        if self.resolver.is_ref(entry):
                            _, r = self.resolver.deref(
                                entry, pointer_hint=f"{prop_pointer}/{keyword}/{index}"
                            )
                            if r and r.component_name:
                                references.append(r.component_name)
                                ref_target = ref_target or r.component_name

            field = NormField(
                name=str(prop_name),
                dotted_path=dotted,
                schema_name=schema.name,
                service=self.service_name,
                type=_type_of(value),
                format=self._as_str(value.get("format")),
                description=str(value.get("description") or ""),
                required=str(prop_name) in required,
                nullable=_is_nullable(value),
                deprecated=bool(value.get("deprecated")),
                read_only=bool(value.get("readOnly")),
                write_only=bool(value.get("writeOnly")),
                enum=list(value.get("enum") or []),
                default=value.get("default"),
                example=value.get("example"),
                ref_target=ref_target,
                array_item_type=array_item_type,
                sensitive_hint=bool(value.get(EXT_SENSITIVE)),
                pointer=prop_pointer,
            )
            schema.fields.append(field)

            # Descend into inline objects only. A $ref to a named schema becomes an edge
            # between schemas instead — flattening it would duplicate the whole subtree.
            if ref_target is None and not cyclic and isinstance(value.get("properties"), dict):
                self._collect_fields(
                    schema,
                    value,
                    prefix=f"{dotted}.",
                    pointer=prop_pointer,
                    depth=depth + 1,
                    required=set(value.get("required", []) or []),
                    references=references,
                    seen=seen,
                )

    # -- operations ----------------------------------------------------------------

    def _parse_operations(self, service: NormalizedService) -> list[NormOperation]:
        operations: list[NormOperation] = []
        paths = self.data.get("paths")
        if isinstance(paths, dict):
            for path, path_item in paths.items():
                operations.extend(
                    self._parse_path_item(
                        service, str(path), path_item, _ptr("paths", str(path)), kind="path"
                    )
                )
        webhooks = self.data.get("webhooks")
        if isinstance(webhooks, dict):
            for name, path_item in webhooks.items():
                operations.extend(
                    self._parse_path_item(
                        service,
                        f"webhook:{name}",
                        path_item,
                        _ptr("webhooks", str(name)),
                        kind="webhook",
                    )
                )
        return operations

    def _parse_path_item(
        self,
        service: NormalizedService,
        path: str,
        raw_item: Any,
        pointer: str,
        *,
        kind: str,
    ) -> list[NormOperation]:
        item, _ = self.resolver.deref(raw_item, pointer_hint=pointer)
        if not isinstance(item, dict):
            self._diag(
                DiagnosticLevel.WARNING, "unreadable-path", f"Path '{path}' could not be read.", pointer
            )
            return []

        shared_params = self._parse_parameters(item.get("parameters"), f"{pointer}/parameters")
        out: list[NormOperation] = []
        for method in HTTP_METHODS:
            raw_op = item.get(method)
            if not isinstance(raw_op, dict):
                continue
            op_pointer = f"{pointer}/{method}"
            security, declared = self._parse_security(
                raw_op.get("security"), f"{op_pointer}/security"
            )
            if not declared:
                security = list(service.global_security)

            params = list(shared_params)
            own = self._parse_parameters(raw_op.get("parameters"), f"{op_pointer}/parameters")
            by_key = {(p.name, p.location): p for p in params}
            for p in own:
                by_key[(p.name, p.location)] = p
            params = list(by_key.values())

            operation = NormOperation(
                operation_id=str(
                    raw_op.get("operationId") or _synthetic_operation_id(method, path)
                ),
                method=method,
                path=path,
                service=self.service_name,
                summary=str(raw_op.get("summary") or ""),
                description=str(raw_op.get("description") or ""),
                tags=[str(t) for t in raw_op.get("tags", []) if isinstance(t, str)],
                deprecated=bool(raw_op.get("deprecated")),
                parameters=params,
                request_body=self._parse_request_body(
                    raw_op.get("requestBody"), f"{op_pointer}/requestBody"
                ),
                responses=self._parse_responses(raw_op.get("responses"), f"{op_pointer}/responses"),
                security=security,
                security_declared=declared,
                depends_on=self._parse_dependencies(raw_op.get(EXT_DEPENDS_ON), op_pointer),
                pointer=op_pointer,
                kind=kind,
            )
            if not raw_op.get("operationId"):
                self._diag(
                    DiagnosticLevel.INFO,
                    "synthetic-operation-id",
                    f"{method.upper()} {path} has no operationId; "
                    f"'{operation.operation_id}' was derived from the method and path.",
                    op_pointer,
                    hint="Add an explicit operationId so references stay stable.",
                )
            if not operation.responses:
                self._diag(
                    DiagnosticLevel.WARNING,
                    "no-responses",
                    f"{method.upper()} {path} declares no responses.",
                    op_pointer,
                )
            out.append(operation)

            # Callbacks are parsed one level deep so their operations appear in the graph.
            callbacks = raw_op.get("callbacks")
            if isinstance(callbacks, dict):
                for cb_name, cb_raw in callbacks.items():
                    cb_value, _ = self.resolver.deref(
                        cb_raw, pointer_hint=f"{op_pointer}/callbacks/{cb_name}"
                    )
                    if not isinstance(cb_value, dict):
                        continue
                    for expression, cb_item in cb_value.items():
                        out.extend(
                            self._parse_path_item(
                                service,
                                f"callback:{operation.operation_id}:{expression}",
                                cb_item,
                                f"{op_pointer}/callbacks/{escape_pointer_segment(str(cb_name))}"
                                f"/{escape_pointer_segment(str(expression))}",
                                kind="callback",
                            )
                        )
        return out

    def _parse_parameters(self, raw: Any, pointer: str) -> list[NormParameter]:
        if not isinstance(raw, list):
            return []
        out: list[NormParameter] = []
        for index, entry in enumerate(raw):
            entry_pointer = f"{pointer}/{index}"
            value, _ = self.resolver.deref(entry, pointer_hint=entry_pointer)
            if not isinstance(value, dict) or "name" not in value:
                continue
            schema_raw = value.get("schema")
            schema_ref = None
            ptype = None
            pformat = None
            if self.resolver.is_ref(schema_raw):
                _, resolved = self.resolver.deref(
                    schema_raw, pointer_hint=f"{entry_pointer}/schema"
                )
                schema_ref = resolved.component_name if resolved else None
            elif isinstance(schema_raw, dict):
                ptype = _type_of(schema_raw)
                pformat = self._as_str(schema_raw.get("format"))
            out.append(
                NormParameter(
                    name=str(value["name"]),
                    location=str(value.get("in") or "query"),
                    required=bool(value.get("required")),
                    description=str(value.get("description") or ""),
                    type=ptype,
                    format=pformat,
                    schema_ref=schema_ref,
                    deprecated=bool(value.get("deprecated")),
                    pointer=entry_pointer,
                )
            )
        return out

    def _content_ref(self, content: Any, pointer: str) -> tuple[str | None, str | None, bool, bool]:
        """Return (content_type, schema_name, is_array, has_example)."""
        if not isinstance(content, dict) or not content:
            return None, None, False, False
        # Prefer JSON, otherwise take the first declared media type deterministically.
        media_type = next(
            (mt for mt in content if "json" in str(mt).lower()), sorted(content)[0]
        )
        media = content.get(media_type)
        if not isinstance(media, dict):
            return str(media_type), None, False, False
        has_example = bool(media.get("example") or media.get("examples"))
        schema_raw = media.get("schema")
        media_pointer = f"{pointer}/content/{escape_pointer_segment(str(media_type))}/schema"
        if self.resolver.is_ref(schema_raw):
            _, resolved = self.resolver.deref(schema_raw, pointer_hint=media_pointer)
            name = resolved.component_name if resolved else None
            return str(media_type), name, False, has_example
        if isinstance(schema_raw, dict):
            if _type_of(schema_raw) == "array":
                items = schema_raw.get("items")
                if self.resolver.is_ref(items):
                    _, resolved = self.resolver.deref(items, pointer_hint=f"{media_pointer}/items")
                    return (
                        str(media_type),
                        resolved.component_name if resolved else None,
                        True,
                        has_example,
                    )
                return str(media_type), None, True, has_example
            has_example = has_example or bool(schema_raw.get("example"))
        return str(media_type), None, False, has_example

    def _parse_request_body(self, raw: Any, pointer: str) -> NormRequestBody | None:
        if raw is None:
            return None
        value, _ = self.resolver.deref(raw, pointer_hint=pointer)
        if not isinstance(value, dict):
            return None
        content_type, schema_ref, is_array, _ = self._content_ref(value.get("content"), pointer)
        return NormRequestBody(
            required=bool(value.get("required")),
            description=str(value.get("description") or ""),
            content_type=content_type,
            schema_ref=schema_ref,
            is_array=is_array,
            pointer=pointer,
        )

    def _parse_responses(self, raw: Any, pointer: str) -> list[NormResponse]:
        if not isinstance(raw, dict):
            return []
        out: list[NormResponse] = []
        for status, entry in sorted(raw.items(), key=lambda kv: str(kv[0])):
            status_pointer = f"{pointer}/{escape_pointer_segment(str(status))}"
            value, _ = self.resolver.deref(entry, pointer_hint=status_pointer)
            if not isinstance(value, dict):
                continue
            content_type, schema_ref, is_array, has_example = self._content_ref(
                value.get("content"), status_pointer
            )
            out.append(
                NormResponse(
                    status=str(status),
                    description=str(value.get("description") or ""),
                    content_type=content_type,
                    schema_ref=schema_ref,
                    is_array=is_array,
                    pointer=status_pointer,
                    has_example=has_example,
                )
            )
        return out

    def _parse_dependencies(self, raw: Any, pointer: str) -> list[NormDependency]:
        if raw is None:
            return []
        if not isinstance(raw, list):
            self._diag(
                DiagnosticLevel.WARNING,
                "invalid-depends-on",
                f"'{EXT_DEPENDS_ON}' must be an array.",
                pointer,
            )
            return []
        out: list[NormDependency] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            service = entry.get("service")
            operation = entry.get("operationId")
            if not service or not operation:
                self._diag(
                    DiagnosticLevel.WARNING,
                    "incomplete-depends-on",
                    f"'{EXT_DEPENDS_ON}' entries need both 'service' and 'operationId'.",
                    pointer,
                )
                continue
            out.append(
                NormDependency(
                    service=str(service),
                    operation_id=str(operation),
                    reason=str(entry.get("reason") or ""),
                )
            )
        return out

    # -- post-checks ---------------------------------------------------------------

    def _check_duplicate_operation_ids(self, service: NormalizedService) -> None:
        seen: dict[str, str] = {}
        for op in service.operations:
            if op.operation_id in seen:
                self._diag(
                    DiagnosticLevel.ERROR,
                    "duplicate-operation-id",
                    f"operationId '{op.operation_id}' is used by both "
                    f"{seen[op.operation_id]} and {op.signature}.",
                    op.pointer,
                    hint="operationIds must be unique within a document.",
                )
            else:
                seen[op.operation_id] = op.signature

    def _record_broken_refs(self) -> None:
        for broken in self.resolver.broken:
            self._diag(
                DiagnosticLevel.ERROR,
                "broken-ref",
                f"$ref '{broken['ref']}' could not be resolved ({broken['reason']}).",
                broken.get("at", ""),
                hint="Check the component exists and the pointer is spelled correctly.",
            )


def _type_of(schema: dict[str, Any]) -> str | None:
    """OpenAPI 3.1 allows ``type: [string, "null"]``; collapse it to the non-null type."""
    raw = schema.get("type")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        non_null = [t for t in raw if t != "null"]
        if non_null:
            return str(non_null[0])
        return "null"
    if "properties" in schema:
        return "object"
    if "items" in schema:
        return "array"
    return None


def _is_nullable(schema: dict[str, Any]) -> bool:
    if schema.get("nullable") is True:  # 3.0 style
        return True
    raw = schema.get("type")
    return isinstance(raw, list) and "null" in raw  # 3.1 style


def _synthetic_operation_id(method: str, path: str) -> str:
    parts = [p for p in path.replace("{", "by-").replace("}", "").split("/") if p]
    tail = "-".join(parts) or "root"
    return slugify(f"{method}-{tail}").replace("-", "_")


# --------------------------------------------------------------------------------------
# Convenience entry points
# --------------------------------------------------------------------------------------


def parse_service(
    text_or_path: str,
    *,
    source_file: str | None = None,
    service_name: str | None = None,
    domain: str | None = None,
    is_path: bool = False,
) -> NormalizedService:
    document = (
        load_spec_file(text_or_path)
        if is_path
        else load_spec_text(text_or_path, source_file=source_file or "spec.yaml")
    )
    if looks_like_postman(document.data):
        document.data = postman_to_openapi(
            document.data, title_fallback=service_name or "Imported collection"
        )
    return OpenAPIParser(document, service_name=service_name, domain=domain).parse()


def parse_estate(
    sources: list[tuple[str, str, str | None]],
    *,
    name: str = "API estate",
    description: str = "",
    from_paths: bool = False,
) -> NormalizedEstate:
    """Parse many documents into one estate.

    ``sources`` is a list of ``(content_or_path, service_name, domain)`` triples.
    """
    estate = NormalizedEstate(name=name, description=description)
    payload_parts: list[str] = []
    for content, service_name, domain in sources:
        if from_paths:
            document = load_spec_file(content)
        else:
            document = load_spec_text(content, source_file=f"{service_name}.yaml")
        payload_parts.append(document.text)
        if looks_like_postman(document.data):
            document.data = postman_to_openapi(document.data, title_fallback=service_name)
        service = OpenAPIParser(document, service_name=service_name, domain=domain).parse()
        estate.services.append(service)
        estate.diagnostics.extend(service.diagnostics)
    estate.fingerprint = fingerprint("\n".join(payload_parts))
    return estate
