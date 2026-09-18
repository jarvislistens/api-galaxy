"""Safe loading of OpenAPI documents from text, files, manifests and Postman collections.

Everything here is defensive: YAML is loaded with ``yaml.safe_load`` only, inputs are
size-capped, and parse failures are reported with the exact line/column when the
underlying library gives us one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

MAX_SPEC_BYTES = 12 * 1024 * 1024  # 12 MB — large enough for real estates, small enough to be safe
MAX_MANIFEST_SERVICES = 64


class SpecLoadError(ValueError):
    """Raised when a document cannot be read as JSON or YAML.

    Carries ``line``/``column``/``field_path`` when available so the import screen can
    point at the exact place that failed.
    """

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
        field_path: str | None = None,
        hint: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.field_path = field_path
        self.hint = hint

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "field_path": self.field_path,
            "hint": self.hint,
        }


@dataclass
class LoadedDocument:
    """A parsed document plus where it came from."""

    data: dict[str, Any]
    source_file: str
    text: str
    format: str  # "json" | "yaml"
    warnings: list[str] = field(default_factory=list)


def detect_format(text: str, filename: str | None = None) -> str:
    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix == ".json":
            return "json"
        if suffix in (".yaml", ".yml"):
            return "yaml"
    stripped = text.lstrip()
    return "json" if stripped.startswith(("{", "[")) else "yaml"


def load_spec_text(text: str, *, source_file: str = "spec.yaml") -> LoadedDocument:
    """Parse ``text`` as JSON or YAML with friendly, located errors."""
    if not text or not text.strip():
        raise SpecLoadError("The file is empty.", hint="Paste or upload an OpenAPI document.")

    encoded_size = len(text.encode("utf-8"))
    if encoded_size > MAX_SPEC_BYTES:
        raise SpecLoadError(
            f"Document is {encoded_size // 1024 // 1024} MB, which exceeds the "
            f"{MAX_SPEC_BYTES // 1024 // 1024} MB limit.",
            hint="Split the estate into per-service files and use an import manifest.",
        )

    fmt = detect_format(text, source_file)
    data: Any
    if fmt == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SpecLoadError(
                f"Invalid JSON: {exc.msg}.",
                line=exc.lineno,
                column=exc.colno,
                hint="Check for a trailing comma or an unquoted key.",
            ) from exc
    else:
        try:
            data = yaml.safe_load(text)
        except yaml.MarkedYAMLError as exc:
            mark = exc.problem_mark
            raise SpecLoadError(
                f"Invalid YAML: {exc.problem or exc.context or 'could not be parsed'}.",
                line=(mark.line + 1) if mark else None,
                column=(mark.column + 1) if mark else None,
                hint="YAML is indentation sensitive — check the highlighted line.",
            ) from exc
        except yaml.YAMLError as exc:  # pragma: no cover - defensive
            raise SpecLoadError(f"Invalid YAML: {exc}.") from exc

    if data is None:
        raise SpecLoadError("The document parsed to nothing.", hint="Is the file only comments?")
    if not isinstance(data, dict):
        raise SpecLoadError(
            f"Expected an object at the top level, found {type(data).__name__}.",
            field_path="$",
            hint="An OpenAPI document must be a mapping with an 'openapi' key.",
        )
    return LoadedDocument(data=data, source_file=source_file, text=text, format=fmt)


def load_spec_file(path: str | Path) -> LoadedDocument:
    p = Path(path)
    if not p.is_file():
        raise SpecLoadError(f"No such file: {p}")
    if p.stat().st_size > MAX_SPEC_BYTES:
        raise SpecLoadError(f"{p.name} exceeds the {MAX_SPEC_BYTES // 1024 // 1024} MB limit.")
    return load_spec_text(p.read_text(encoding="utf-8"), source_file=p.name)


def looks_like_openapi(data: dict[str, Any]) -> bool:
    return "openapi" in data or "swagger" in data


def looks_like_postman(data: dict[str, Any]) -> bool:
    info = data.get("info")
    return isinstance(info, dict) and "schema" in info and "postman" in str(info.get("schema", ""))


def looks_like_manifest(data: dict[str, Any]) -> bool:
    return data.get("kind") == "EstateManifest"


@dataclass
class ManifestService:
    name: str
    file: str
    domain: str | None = None


@dataclass
class EstateManifest:
    name: str
    description: str
    services: list[ManifestService]


def load_estate_manifest(path: str | Path) -> EstateManifest:
    """Read a multi-file import manifest and validate every referenced file exists.

    Paths inside the manifest are resolved *relative to the manifest* and are rejected if
    they escape its directory — a manifest must not be able to read arbitrary files.
    """
    manifest_path = Path(path).resolve()
    doc = load_spec_file(manifest_path)
    data = doc.data
    if not looks_like_manifest(data):
        raise SpecLoadError(
            "Not an estate manifest.",
            field_path="kind",
            hint="Expected 'kind: EstateManifest'.",
        )

    root = manifest_path.parent
    meta = data.get("metadata") or {}
    spec = data.get("spec") or {}
    raw_services = spec.get("services") or []
    if not isinstance(raw_services, list) or not raw_services:
        raise SpecLoadError("Manifest lists no services.", field_path="spec.services")
    if len(raw_services) > MAX_MANIFEST_SERVICES:
        raise SpecLoadError(
            f"Manifest lists {len(raw_services)} services; the limit is {MAX_MANIFEST_SERVICES}."
        )

    services: list[ManifestService] = []
    for index, entry in enumerate(raw_services):
        if not isinstance(entry, dict) or "file" not in entry:
            raise SpecLoadError(
                "Each service needs a 'file'.", field_path=f"spec.services[{index}]"
            )
        candidate = (root / str(entry["file"])).resolve()
        if root not in candidate.parents and candidate.parent != root:
            raise SpecLoadError(
                f"Service file '{entry['file']}' resolves outside the manifest directory.",
                field_path=f"spec.services[{index}].file",
                hint="Manifest paths must stay next to the manifest.",
            )
        if not candidate.is_file():
            raise SpecLoadError(
                f"Service file '{entry['file']}' does not exist.",
                field_path=f"spec.services[{index}].file",
            )
        services.append(
            ManifestService(
                name=str(entry.get("name") or candidate.stem),
                file=str(candidate),
                domain=entry.get("domain"),
            )
        )

    return EstateManifest(
        name=str(meta.get("name") or manifest_path.stem),
        description=str(meta.get("description") or ""),
        services=services,
    )


# --------------------------------------------------------------------------------------
# Postman → OpenAPI (beta path)
# --------------------------------------------------------------------------------------


def postman_to_openapi(data: dict[str, Any], *, title_fallback: str = "Imported") -> dict[str, Any]:
    """Convert a Postman v2.x collection into a minimal but valid OpenAPI 3.0 document.

    This is deliberately shallow: Postman has no schema language, so we recover paths,
    methods, names, descriptions and folder-as-tag structure, and nothing more. The
    import screen labels this path *beta* for exactly that reason.
    """
    info = data.get("info") or {}
    title = str(info.get("name") or title_fallback)
    paths: dict[str, Any] = {}
    servers: set[str] = set()

    def walk(items: list[Any], trail: list[str]) -> None:
        for item in items or []:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("item"), list):
                walk(item["item"], [*trail, str(item.get("name") or "")])
                continue
            request = item.get("request")
            if not isinstance(request, dict):
                continue
            method = str(request.get("method") or "GET").lower()
            url = request.get("url")
            raw = ""
            segments: list[str] = []
            if isinstance(url, dict):
                raw = str(url.get("raw") or "")
                segments = [str(s) for s in (url.get("path") or [])]
                host = url.get("host")
                if isinstance(host, list) and host:
                    servers.add(".".join(str(h) for h in host))
                elif isinstance(host, str):
                    servers.add(host)
            elif isinstance(url, str):
                raw = url
            if segments:
                path = "/" + "/".join(segments)
            elif raw:
                stripped = raw.split("?")[0]
                for prefix in ("{{baseUrl}}", "{{base_url}}"):
                    stripped = stripped.replace(prefix, "")
                path = stripped if stripped.startswith("/") else "/" + stripped
            else:
                continue
            # Postman writes :param; OpenAPI wants {param}
            path = "/".join(
                "{" + seg[1:] + "}" if seg.startswith(":") else seg for seg in path.split("/")
            )
            name = str(item.get("name") or f"{method} {path}")
            operation: dict[str, Any] = {
                "operationId": _camel(name),
                "summary": name,
                "description": str(
                    (request.get("description") or item.get("description") or "")
                    if isinstance(request.get("description"), str)
                    else ""
                ),
                "tags": [t for t in trail if t] or ["Imported"],
                "responses": {"200": {"description": "Successful response"}},
            }
            params = [
                {
                    "name": seg.strip("{}"),
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
                for seg in path.split("/")
                if seg.startswith("{") and seg.endswith("}")
            ]
            if params:
                operation["parameters"] = params
            paths.setdefault(path, {})[method] = operation

    walk(data.get("item") or [], [])

    return {
        "openapi": "3.0.3",
        "info": {
            "title": title,
            "version": "1.0.0",
            "description": str(info.get("description") or "Imported from a Postman collection."),
        },
        "servers": [{"url": f"https://{s}"} for s in sorted(servers)] or [{"url": "/"}],
        "paths": paths,
        "components": {"schemas": {}},
        "x-api-galaxy-import": "postman",
    }


def _camel(value: str) -> str:
    parts = [p for p in "".join(c if c.isalnum() else " " for c in value).split() if p]
    if not parts:
        return "operation"
    return parts[0].lower() + "".join(p[:1].upper() + p[1:] for p in parts[1:])
