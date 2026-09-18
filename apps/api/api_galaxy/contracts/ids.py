"""Stable, deterministic identifiers for every graph object.

IDs are content-derived, not random, so that:

* re-parsing the same specification yields byte-identical graphs (reproducibility),
* a scenario graph can be diffed against its base graph by ID,
* an exported report can be regenerated and compared, and
* an LLM can only reference nodes that actually exist (we whitelist by ID).

The format is ``<prefix>:<parts joined by ':'>``. Prefixes are short and readable so
that provenance and model citations remain human-auditable.
"""

from __future__ import annotations

import hashlib
import re

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_MULTI_DASH = re.compile(r"-{2,}")


def slugify(value: str, *, max_length: int = 64) -> str:
    """Lowercase, dash-separated, ASCII-safe slug. Stable for a given input."""
    lowered = value.strip().lower()
    slug = _SLUG_STRIP.sub("-", lowered)
    slug = _MULTI_DASH.sub("-", slug).strip("-")
    if not slug:
        slug = "x" + _digest(value, 8)
    if len(slug) > max_length:
        slug = f"{slug[: max_length - 9]}-{_digest(value, 8)}"
    return slug


def _digest(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def fingerprint(payload: bytes | str) -> str:
    """Specification / context fingerprint used for caching and report disclosure."""
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    return "sha256:" + hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------------------
# Node IDs
# --------------------------------------------------------------------------------------


def estate_id(project_slug: str) -> str:
    return f"estate:{project_slug}"


def service_id(service: str) -> str:
    return f"svc:{slugify(service)}"


def server_id(service: str, index: int) -> str:
    return f"server:{slugify(service)}:{index}"


def path_id(service: str, path: str) -> str:
    return f"ep:{slugify(service)}:{path}"


def operation_id(service: str, method: str, path: str) -> str:
    return f"op:{slugify(service)}:{method.lower()}:{path}"


def schema_id(service: str, schema_name: str) -> str:
    return f"schema:{slugify(service)}:{schema_name}"


def field_id(service: str, schema_name: str, dotted_path: str) -> str:
    return f"field:{slugify(service)}:{schema_name}.{dotted_path}"


def security_scheme_id(service: str, scheme_name: str) -> str:
    return f"sec:{slugify(service)}:{scheme_name}"


def domain_id(name: str) -> str:
    return f"domain:{slugify(name)}"


def entity_id(name: str) -> str:
    return f"entity:{slugify(name)}"


def capability_id(name: str) -> str:
    return f"cap:{slugify(name)}"


def journey_id(name: str) -> str:
    return f"journey:{slugify(name)}"


def journey_step_id(journey: str, order: int) -> str:
    base = journey if journey.startswith("journey:") else journey_id(journey)
    return f"jstep:{base.split(':', 1)[1]}:{order}"


def risk_id(rule_id: str, *locators: str) -> str:
    return f"risk:{rule_id}:{_digest('|'.join(locators), 10)}"


def evidence_id(source_file: str, pointer: str) -> str:
    return f"ev:{_digest(f'{source_file}#{pointer}', 12)}"


def scenario_id(raw: str) -> str:
    return f"scn:{slugify(raw)}"


def change_id(scenario: str, index: int) -> str:
    return f"chg:{scenario.split(':', 1)[-1]}:{index}"


def repair_id(scenario: str, index: int) -> str:
    return f"rep:{scenario.split(':', 1)[-1]}:{index}"


# --------------------------------------------------------------------------------------
# Edge IDs
# --------------------------------------------------------------------------------------


def edge_id(edge_type: str, source: str, target: str) -> str:
    """Edges are identified by (type, source, target) so re-parsing is idempotent."""
    return f"e:{_digest(f'{edge_type}|{source}|{target}', 16)}"


def json_pointer(*segments: str) -> str:
    """Build an RFC 6901 JSON Pointer from raw segments."""
    escaped = [seg.replace("~", "~0").replace("/", "~1") for seg in segments]
    return "/" + "/".join(escaped)
