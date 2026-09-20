"""The normalized representation of an API estate.

This sits between the raw OpenAPI document and the graph. It is *stable*: field order is
deterministic, every element knows its JSON Pointer, and nothing here is inferred — if a
value is present, the specification said so.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from api_galaxy.contracts.ids import slugify

NORMALIZED_SCHEMA_VERSION = "1.0"


class DiagnosticLevel(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Diagnostic(BaseModel):
    level: DiagnosticLevel
    code: str
    message: str
    file: str = ""
    pointer: str = ""
    hint: str = ""


class NormField(BaseModel):
    name: str
    dotted_path: str
    schema_name: str
    service: str
    type: str | None = None
    format: str | None = None
    description: str = ""
    required: bool = False
    nullable: bool = False
    deprecated: bool = False
    read_only: bool = False
    write_only: bool = False
    enum: list[Any] = Field(default_factory=list)
    default: Any = None
    example: Any = None
    ref_target: str | None = Field(default=None, description="Schema name this field refs.")
    array_item_type: str | None = None
    sensitive_hint: bool = Field(
        default=False, description="Explicitly flagged by x-api-galaxy-sensitive."
    )
    pointer: str = ""

    @property
    def type_signature(self) -> str:
        base = self.type or (f"$ref:{self.ref_target}" if self.ref_target else "any")
        if self.type == "array" and self.array_item_type:
            base = f"array<{self.array_item_type}>"
        return f"{base}({self.format})" if self.format else base


class NormSchema(BaseModel):
    name: str
    service: str
    title: str = ""
    description: str = ""
    type: str = "object"
    pointer: str = ""
    deprecated: bool = False
    required: list[str] = Field(default_factory=list)
    fields: list[NormField] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list, description="Other schema names used.")
    composition: dict[str, list[str]] = Field(
        default_factory=dict, description="allOf/oneOf/anyOf → referenced schema names."
    )
    discriminator: str | None = None
    example: Any = None
    recursive: bool = False

    def field_by_path(self, dotted_path: str) -> NormField | None:
        for f in self.fields:
            if f.dotted_path == dotted_path:
                return f
        return None


class NormParameter(BaseModel):
    name: str
    location: str  # query | path | header | cookie
    required: bool = False
    description: str = ""
    type: str | None = None
    format: str | None = None
    schema_ref: str | None = None
    deprecated: bool = False
    pointer: str = ""


class NormResponse(BaseModel):
    status: str
    description: str = ""
    content_type: str | None = None
    schema_ref: str | None = None
    is_array: bool = False
    pointer: str = ""
    has_example: bool = False


class NormRequestBody(BaseModel):
    required: bool = False
    description: str = ""
    content_type: str | None = None
    schema_ref: str | None = None
    is_array: bool = False
    pointer: str = ""


class NormDependency(BaseModel):
    """An EXPLICIT cross-service dependency declared via ``x-api-galaxy-depends-on``."""

    service: str
    operation_id: str
    reason: str = ""


class NormOperation(BaseModel):
    operation_id: str
    method: str
    path: str
    service: str
    summary: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    deprecated: bool = False
    parameters: list[NormParameter] = Field(default_factory=list)
    request_body: NormRequestBody | None = None
    responses: list[NormResponse] = Field(default_factory=list)
    security: list[str] = Field(default_factory=list, description="Security scheme names.")
    security_declared: bool = Field(
        default=False, description="True if the operation set its own `security` (incl. [])."
    )
    depends_on: list[NormDependency] = Field(default_factory=list)
    pointer: str = ""
    kind: str = Field(default="path", description="path | webhook | callback")

    @property
    def is_public(self) -> bool:
        return not self.security

    @property
    def signature(self) -> str:
        return f"{self.method.upper()} {self.path}"

    @property
    def pagination_style(self) -> str | None:
        names = {p.name.lower() for p in self.parameters if p.location == "query"}
        if {"page", "size"} <= names or {"page", "per_page"} <= names:
            return "page-size"
        if {"limit", "offset"} <= names:
            return "limit-offset"
        if names & {"cursor", "after", "next_token", "page_token"}:
            return "cursor"
        return None


class NormServer(BaseModel):
    url: str
    description: str = ""
    pointer: str = ""


class NormSecurityScheme(BaseModel):
    name: str
    type: str
    scheme: str | None = None
    bearer_format: str | None = None
    location: str | None = None
    param_name: str | None = None
    description: str = ""
    pointer: str = ""

    @property
    def strength(self) -> str:
        if self.type == "oauth2" or (self.type == "http" and (self.scheme or "").lower() == "bearer"):
            return "strong"
        if self.type == "apiKey":
            return "weak"
        if self.type == "http" and (self.scheme or "").lower() == "basic":
            return "weak"
        return "unknown"


class NormalizedService(BaseModel):
    name: str
    slug: str
    title: str
    version: str = ""
    description: str = ""
    openapi_version: str = ""
    domain: str | None = None
    source_file: str = ""
    source_text: str = Field(
        default="",
        description="The document exactly as imported. Kept verbatim so write-back can "
        "produce a minimal diff against what the author actually wrote, comments and "
        "formatting included, rather than against a re-serialisation of the parse.",
    )
    servers: list[NormServer] = Field(default_factory=list)
    operations: list[NormOperation] = Field(default_factory=list)
    schemas: list[NormSchema] = Field(default_factory=list)
    security_schemes: list[NormSecurityScheme] = Field(default_factory=list)
    global_security: list[str] = Field(default_factory=list)
    tags: list[dict[str, str]] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    def schema_by_name(self, name: str) -> NormSchema | None:
        for s in self.schemas:
            if s.name == name:
                return s
        return None

    def operation_by_id(self, operation_id: str) -> NormOperation | None:
        for op in self.operations:
            if op.operation_id == operation_id:
                return op
        return None

    @property
    def paths(self) -> list[str]:
        seen: dict[str, None] = {}
        for op in self.operations:
            seen.setdefault(op.path, None)
        return list(seen)


class NormalizedEstate(BaseModel):
    schema_version: str = NORMALIZED_SCHEMA_VERSION
    name: str
    description: str = ""
    services: list[NormalizedService] = Field(default_factory=list)
    fingerprint: str = ""
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    def service_by_slug(self, slug: str) -> NormalizedService | None:
        for svc in self.services:
            if svc.slug == slug:
                return svc
        return None

    def service_by_name(self, name: str) -> NormalizedService | None:
        target = slugify(name)
        return self.service_by_slug(target)

    def find_operation(self, service_hint: str, operation_id: str) -> NormOperation | None:
        svc = self.service_by_name(service_hint)
        if svc:
            op = svc.operation_by_id(operation_id)
            if op:
                return op
        for candidate in self.services:
            op = candidate.operation_by_id(operation_id)
            if op:
                return op
        return None

    @property
    def all_operations(self) -> list[NormOperation]:
        return [op for svc in self.services for op in svc.operations]

    @property
    def all_schemas(self) -> list[NormSchema]:
        return [s for svc in self.services for s in svc.schemas]

    @property
    def all_fields(self) -> list[NormField]:
        return [f for s in self.all_schemas for f in s.fields]

    def coverage(self) -> dict[str, Any]:
        errors = [d for d in self.diagnostics if d.level is DiagnosticLevel.ERROR]
        warnings = [d for d in self.diagnostics if d.level is DiagnosticLevel.WARNING]
        described_ops = sum(1 for op in self.all_operations if op.description or op.summary)
        total_ops = len(self.all_operations) or 1
        return {
            "services": len(self.services),
            "operations": len(self.all_operations),
            "schemas": len(self.all_schemas),
            "fields": len(self.all_fields),
            "errors": len(errors),
            "warnings": len(warnings),
            "described_operation_ratio": round(described_ops / total_ops, 3),
            "parsed_cleanly": not errors,
        }
