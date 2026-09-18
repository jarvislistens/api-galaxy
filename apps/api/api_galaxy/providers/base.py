"""The provider seam, plus the machinery that makes model output safe to trust.

Three rules are enforced here for every provider, so no individual adapter can forget:

1. **Strict JSON, validated.** Each task declares a versioned JSON Schema; the response
   is parsed and validated, and on failure we retry a small bounded number of times with
   the validation error fed back. After that we give up and return an empty result rather
   than a guess.
2. **ID whitelisting.** A model may only reference node IDs that were in the context we
   gave it. Anything else is dropped and counted as a hallucinated reference, which the
   Model Arena then scores.
3. **No hidden reasoning, no executable output.** We store a short rationale string and
   nothing else. We never accept Cypher, SQL, shell, JavaScript or Python for execution.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Protocol

from api_galaxy.contracts.providers import (
    EnrichmentRequest,
    EnrichmentResult,
    GraphAnswer,
    GraphQuestionRequest,
    ProviderHealth,
    ProviderKind,
    RepairProposal,
    RepairRequest,
)

MAX_VALIDATION_RETRIES = 2
DEFAULT_TIMEOUT_SECONDS = 120.0


class SemanticProvider(Protocol):
    """Every semantic capability API Galaxy can ask a model for."""

    kind: ProviderKind

    async def health(self) -> ProviderHealth: ...

    async def enrich(self, request: EnrichmentRequest) -> EnrichmentResult: ...

    async def answer(self, request: GraphQuestionRequest) -> GraphAnswer: ...

    async def propose_repairs(self, request: RepairRequest) -> RepairProposal: ...


class ProviderError(RuntimeError):
    def __init__(self, provider: ProviderKind, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.provider = provider
        self.message = message
        self.hint = hint


# --------------------------------------------------------------------------------------
# JSON extraction and validation
# --------------------------------------------------------------------------------------

_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def extract_json(text: str) -> Any:
    """Pull a JSON document out of a model response.

    Small local models wrap JSON in prose or code fences more often than not, so we try,
    in order: the whole string, any fenced block, then the outermost balanced ``{}``/``[]``
    span. If none of that yields JSON we raise and let the retry loop say why.
    """
    candidates: list[str] = []
    stripped = text.strip()
    if stripped:
        candidates.append(stripped)
    candidates.extend(match.group(1).strip() for match in _FENCE.finditer(text))
    span = _balanced_span(text)
    if span:
        candidates.append(span)

    last_error = "no JSON found"
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = f"{exc.msg} at line {exc.lineno} column {exc.colno}"
    raise ValueError(f"Response was not valid JSON ({last_error}).")


def _balanced_span(text: str) -> str | None:
    starts = [i for i, ch in enumerate(text) if ch in "{["]
    if not starts:
        return None
    start = starts[0]
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


class SchemaViolation(ValueError):
    pass


def validate_against(schema: dict[str, Any], payload: Any, *, path: str = "$") -> None:
    """A small, dependency-free structural validator.

    We only need the subset of JSON Schema our own task schemas use, and pulling in a
    full validator for that would be a dependency we then have to keep current.
    """
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(payload, dict):
            raise SchemaViolation(f"{path}: expected an object, got {_name(payload)}")
        for key in schema.get("required", []):
            if key not in payload:
                raise SchemaViolation(f"{path}: missing required key '{key}'")
        properties = schema.get("properties", {})
        for key, value in payload.items():
            if key in properties:
                validate_against(properties[key], value, path=f"{path}.{key}")
    elif expected == "array":
        if not isinstance(payload, list):
            raise SchemaViolation(f"{path}: expected an array, got {_name(payload)}")
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(payload):
                validate_against(items, item, path=f"{path}[{index}]")
    elif expected == "string":
        if not isinstance(payload, str):
            raise SchemaViolation(f"{path}: expected a string, got {_name(payload)}")
    elif expected == "number":
        if isinstance(payload, bool) or not isinstance(payload, (int, float)):
            raise SchemaViolation(f"{path}: expected a number, got {_name(payload)}")
        _check_range(schema, payload, path)
    elif expected == "integer":
        if isinstance(payload, bool) or not isinstance(payload, int):
            raise SchemaViolation(f"{path}: expected an integer, got {_name(payload)}")
        _check_range(schema, payload, path)
    elif expected == "boolean":
        if not isinstance(payload, bool):
            raise SchemaViolation(f"{path}: expected a boolean, got {_name(payload)}")


def _check_range(schema: dict[str, Any], value: float, path: str) -> None:
    if "minimum" in schema and value < schema["minimum"]:
        raise SchemaViolation(f"{path}: {value} is below the minimum of {schema['minimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        raise SchemaViolation(f"{path}: {value} is above the maximum of {schema['maximum']}")


def _name(value: Any) -> str:
    return {dict: "an object", list: "an array", str: "a string", bool: "a boolean"}.get(
        type(value), type(value).__name__
    )


# --------------------------------------------------------------------------------------
# Reference whitelisting
# --------------------------------------------------------------------------------------


def filter_references(
    ids: list[Any], allowed: set[str], dropped: list[str], *, limit: int = 64
) -> list[str]:
    """Keep only IDs the model was actually shown. Everything else is recorded as invented."""
    kept: list[str] = []
    for raw in ids or []:
        value = str(raw).strip()
        if not value:
            continue
        if value in allowed:
            if value not in kept:
                kept.append(value)
        elif value not in dropped:
            dropped.append(value)
        if len(kept) >= limit:
            break
    return kept


def clamp_confidence(value: Any, default: float = 0.5) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def clean_rationale(text: Any, *, max_length: int = 600) -> str:
    """Store a short, user-facing justification only.

    Reasoning-tuned models emit long internal monologues. We never surface or persist
    those: we drop anything inside think-style tags and cap what remains.
    """
    value = str(text or "")
    value = re.sub(r"<(think|thinking|reasoning)>[\s\S]*?</\1>", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:max_length]


# --------------------------------------------------------------------------------------
# Retry loop shared by the real providers
# --------------------------------------------------------------------------------------


class StructuredCall:
    """Runs a prompt → JSON → validate loop with bounded, feedback-driven retries."""

    def __init__(self, provider: ProviderKind, schema: dict[str, Any]) -> None:
        self.provider = provider
        self.schema = schema
        self.retries = 0
        self.warnings: list[str] = []
        self.latency_ms = 0.0
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None

    async def run(self, send) -> Any:
        """``send(feedback: str | None) -> tuple[str, dict]`` returns (text, usage)."""
        feedback: str | None = None
        started = time.perf_counter()
        last_error = ""
        for attempt in range(MAX_VALIDATION_RETRIES + 1):
            self.retries = attempt
            text, usage = await send(feedback)
            self.input_tokens = usage.get("input_tokens", self.input_tokens)
            self.output_tokens = usage.get("output_tokens", self.output_tokens)
            try:
                payload = extract_json(text)
                validate_against(self.schema, payload)
            except (ValueError, SchemaViolation) as exc:
                last_error = str(exc)
                feedback = (
                    "Your previous response could not be used: "
                    f"{last_error}. Reply with ONLY the JSON object, no prose, no code fence."
                )
                self.warnings.append(f"attempt {attempt + 1}: {last_error}")
                continue
            self.latency_ms = (time.perf_counter() - started) * 1000
            return payload
        self.latency_ms = (time.perf_counter() - started) * 1000
        raise ProviderError(
            self.provider,
            f"The model did not return valid structured output after "
            f"{MAX_VALIDATION_RETRIES + 1} attempts. Last error: {last_error}",
            hint="Try a larger model, or use the deterministic provider.",
        )
