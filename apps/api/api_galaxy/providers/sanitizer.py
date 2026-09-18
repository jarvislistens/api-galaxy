"""Sanitisation and consent for anything that might leave this machine.

Nothing reaches an external provider without passing through :func:`sanitize`, and the
user sees a preview of exactly what would be sent and what was removed before the first
request of a project. The redaction list is deliberately broad: a specification is not
supposed to contain credentials, but real ones routinely do — in ``example`` values, in
server URLs, in description prose pasted from a wiki.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

MAX_EXTERNAL_PAYLOAD_BYTES = 256 * 1024


@dataclass(frozen=True)
class RedactionRule:
    name: str
    pattern: re.Pattern[str]
    placeholder: str
    why: str


def _rule(name: str, pattern: str, placeholder: str, why: str, flags: int = re.IGNORECASE) -> RedactionRule:
    return RedactionRule(name, re.compile(pattern, flags), placeholder, why)


# Order matters: the most specific patterns run first so a bearer token is not first
# mangled by the generic "long random string" rule.
REDACTION_RULES: tuple[RedactionRule, ...] = (
    _rule("private_key",
          r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
          "[REDACTED_PRIVATE_KEY]", "Private keys must never leave the machine."),
    _rule("jwt", r"\bey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
          "[REDACTED_JWT]", "Looks like a JSON Web Token."),
    # `Authorization: Bearer <token>` has the scheme name between the colon and the
    # secret, so the optional `bearer` group is what lets the value itself match.
    _rule("bearer",
          r"\b(?:bearer|token|authorization)\b\s*[:=]?\s*(?:bearer\s+)?[\"']?[A-Za-z0-9._\-]{16,}",
          "[REDACTED_BEARER]", "Looks like an authorization header value."),
    _rule("api_key_assignment",
          r"\b(?:api[_-]?key|apikey|secret|client[_-]?secret|access[_-]?token|refresh[_-]?token|"
          r"password|passwd|pwd)\b\s*[:=]\s*[\"']?[^\s\"',}]{6,}",
          "[REDACTED_SECRET]", "Looks like a credential assignment."),
    _rule("aws_key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", "[REDACTED_AWS_KEY]",
          "Matches the AWS access key ID format.", 0),
    _rule("slack_token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b", "[REDACTED_TOKEN]",
          "Matches a Slack token."),
    _rule("github_token", r"\bgh[pousr]_[A-Za-z0-9]{20,}\b", "[REDACTED_TOKEN]",
          "Matches a GitHub token.", 0),
    _rule("openai_key", r"\bsk-[A-Za-z0-9_-]{20,}\b", "[REDACTED_TOKEN]",
          "Matches an API key prefix.", 0),
    _rule("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
          "[REDACTED_EMAIL]", "Email addresses are personal data."),
    # Card before phone, deliberately. A 16-digit card number also satisfies the phone
    # pattern, and whichever rule runs first consumes it — so the more specific and more
    # sensitive classification has to go first.
    _rule("card", r"(?<![\d\-])(?:\d[ \-]?){12,18}\d(?![\d\-])", "[REDACTED_CARD]",
          "Looks like a payment card number.", 0),
    # Two guards worth the noise:
    #  * the trailing `(?!\d)` rather than `(?![\w.])` — a number at the end of a sentence
    #    is followed by a full stop, and excluding '.' missed every number written in prose;
    #  * the leading date lookahead — `2026-09-19` otherwise matches, and silently
    #    redacting every date out of a specification's descriptions makes the context we
    #    send a model worse for no privacy gain.
    _rule("phone", r"(?<![\w+])(?!\d{4}-\d{2}-\d{2})\+?\d[\d\s().-]{7,16}\d(?!\d)",
          "[REDACTED_PHONE]", "Looks like a telephone number.", 0),
    _rule("cookie", r"\b(?:set-)?cookie\s*[:=]\s*[^\s;]{8,}", "[REDACTED_COOKIE]",
          "Cookies carry session identity."),
    _rule("private_host",
          r"\bhttps?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|"
          r"(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
          r"192\.168\.\d{1,3}\.\d{1,3}|"
          r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"
          r"[A-Za-z0-9.-]+\.(?:local|internal|intranet|corp|lan))(?::\d+)?[^\s\"']*",
          "[REDACTED_INTERNAL_URL]", "Internal URLs describe your network."),
    _rule("env_var", r"\b(?:[A-Z][A-Z0-9_]{3,})=(?!\s)[^\s\"';]{4,}",
          "[REDACTED_ENV]", "Looks like an environment variable assignment.", 0),
)

# Keys whose *value* is dropped wholesale rather than pattern-matched.
SENSITIVE_KEYS = frozenset(
    {
        "example", "examples", "default", "enum", "x-internal", "x-secret",
        "password", "secret", "token", "apikey", "api_key", "authorization",
        "cookie", "credentials", "servers",
    }
)


@dataclass
class SanitizationReport:
    """What was removed, in language the consent dialog can show verbatim."""

    removed: dict[str, int] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    dropped_keys: list[str] = field(default_factory=list)
    truncated: bool = False
    original_bytes: int = 0
    sanitized_bytes: int = 0

    @property
    def total_redactions(self) -> int:
        return sum(self.removed.values())

    def summary(self) -> str:
        if not self.total_redactions and not self.dropped_keys:
            return "Nothing matched a redaction rule."
        parts: list[str] = []
        for name, count in sorted(self.removed.items()):
            parts.append(f"{count}× {name.replace('_', ' ')}")
        if self.dropped_keys:
            unique = sorted(set(self.dropped_keys))
            parts.append(
                f"{len(self.dropped_keys)} example/default value(s) dropped "
                f"({', '.join(unique[:4])})"
            )
        return "Removed " + ", ".join(parts) + "."

    def to_dict(self) -> dict[str, Any]:
        return {
            "removed": self.removed,
            "reasons": self.reasons,
            "dropped_keys": sorted(set(self.dropped_keys)),
            "truncated": self.truncated,
            "original_bytes": self.original_bytes,
            "sanitized_bytes": self.sanitized_bytes,
            "total_redactions": self.total_redactions,
            "summary": self.summary(),
        }


def sanitize_text(value: str, report: SanitizationReport | None = None) -> str:
    """Apply every redaction rule to a string, counting what fired."""
    report = report if report is not None else SanitizationReport()
    out = value
    for rule in REDACTION_RULES:
        out, count = rule.pattern.subn(rule.placeholder, out)
        if count:
            report.removed[rule.name] = report.removed.get(rule.name, 0) + count
            report.reasons[rule.name] = rule.why
    return out


def sanitize(payload: Any, *, drop_examples: bool = True) -> tuple[Any, SanitizationReport]:
    """Recursively sanitize a JSON-ish payload.

    Returns the cleaned payload and a report. The payload is also size-capped: a model
    does not need a megabyte of context, and a smaller payload is a smaller disclosure.
    """
    report = SanitizationReport()
    report.original_bytes = _approx_size(payload)
    cleaned = _walk(payload, report, drop_examples=drop_examples, depth=0)
    report.sanitized_bytes = _approx_size(cleaned)
    if report.sanitized_bytes > MAX_EXTERNAL_PAYLOAD_BYTES:
        cleaned = _truncate(cleaned)
        report.truncated = True
        report.sanitized_bytes = _approx_size(cleaned)
    return cleaned, report


def _walk(node: Any, report: SanitizationReport, *, drop_examples: bool, depth: int) -> Any:
    if depth > 24:
        return "[TRUNCATED_DEPTH]"
    if isinstance(node, str):
        return sanitize_text(node, report)
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            lowered = str(key).lower().replace("-", "_")
            if drop_examples and lowered in SENSITIVE_KEYS:
                report.dropped_keys.append(str(key))
                continue
            out[str(key)] = _walk(value, report, drop_examples=drop_examples, depth=depth + 1)
        return out
    if isinstance(node, list):
        return [_walk(item, report, drop_examples=drop_examples, depth=depth + 1) for item in node]
    return node


def _approx_size(payload: Any) -> int:
    import json

    try:
        return len(json.dumps(payload, default=str).encode("utf-8"))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return len(str(payload).encode("utf-8"))


def _truncate(payload: Any) -> Any:
    """Shrink the biggest lists until the payload fits, keeping the shape intact."""
    if isinstance(payload, dict):
        out = dict(payload)
        for key, value in sorted(
            out.items(), key=lambda kv: _approx_size(kv[1]), reverse=True
        ):
            if _approx_size(out) <= MAX_EXTERNAL_PAYLOAD_BYTES:
                break
            if isinstance(value, list) and len(value) > 3:
                keep = max(3, len(value) // 2)
                out[key] = [*value[:keep], f"[TRUNCATED {len(value) - keep} more]"]
            elif isinstance(value, (dict, list)):
                out[key] = _truncate(value)
        return out
    if isinstance(payload, list) and len(payload) > 3:
        keep = max(3, len(payload) // 2)
        return [*payload[:keep], f"[TRUNCATED {len(payload) - keep} more]"]
    return payload


def payload_fingerprint(payload: Any) -> str:
    import json

    data = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass
class ExternalRequestPreview:
    """Everything the consent dialog needs — and nothing the user has to trust us about."""

    provider: str
    model: str
    endpoint: str
    payload: Any
    report: SanitizationReport
    fingerprint: str
    estimated_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "endpoint": self.endpoint,
            "payload_preview": self.payload,
            "sanitization": self.report.to_dict(),
            "fingerprint": self.fingerprint,
            "estimated_bytes": self.estimated_bytes,
            "warning": (
                "This will send the content shown above to a third-party service over the "
                "internet. Everything else stays on this machine."
            ),
        }


def build_preview(
    payload: Any, *, provider: str, model: str, endpoint: str
) -> ExternalRequestPreview:
    cleaned, report = sanitize(payload)
    return ExternalRequestPreview(
        provider=provider,
        model=model,
        endpoint=endpoint,
        payload=cleaned,
        report=report,
        fingerprint=payload_fingerprint(cleaned),
        estimated_bytes=report.sanitized_bytes,
    )
