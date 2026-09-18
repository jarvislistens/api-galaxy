"""Configurable dictionaries for spotting potentially sensitive data.

This is explicitly a *heuristic*. It matches on names and formats, which is how every
practical scanner works and is also why every finding it produces is labelled
"heuristic" in the UI. Users can extend the dictionaries in Settings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Token → (category, severity weight). Matching is on word-ish boundaries within a
# snake_case / camelCase / kebab-case identifier, not naive substring containment, so
# `identity` does not match `id` and `company` does not match `pan`.
DIRECT_IDENTIFIERS: dict[str, str] = {
    "email": "contact",
    "e_mail": "contact",
    "phone": "contact",
    "mobile": "contact",
    "msisdn": "contact",
    "telephone": "contact",
    "full_name": "name",
    "fullname": "name",
    "first_name": "name",
    "last_name": "name",
    "surname": "name",
    "given_name": "name",
    "family_name": "name",
    "date_of_birth": "sensitive",
    "dob": "sensitive",
    "birthdate": "sensitive",
    "ssn": "government-id",
    "national_id": "government-id",
    "passport": "government-id",
    "tax_id": "government-id",
    "pan": "government-id",
    "aadhaar": "government-id",
    "driver_license": "government-id",
    "card_number": "financial",
    "cardnumber": "financial",
    "pan_number": "financial",
    "card_last4": "financial",
    "cvv": "financial",
    "iban": "financial",
    "account_number": "financial",
    "routing_number": "financial",
    "password": "credential",
    "secret": "credential",
    "api_key": "credential",
    "access_token": "credential",
    "refresh_token": "credential",
    "private_key": "credential",
    "session_id": "credential",
    "latitude": "location",
    "longitude": "location",
    "geo": "location",
    "ip_address": "location",
    "health": "special-category",
    "medical": "special-category",
    "ethnicity": "special-category",
    "religion": "special-category",
}

QUASI_IDENTIFIERS: dict[str, str] = {
    "address": "location",
    "street": "location",
    "postal_code": "location",
    "postcode": "location",
    "zip": "location",
    "city": "location",
    "gender": "demographic",
    "age": "demographic",
    "nationality": "demographic",
    "loyalty_tier": "behavioural",
    "segment": "behavioural",
}

SENSITIVE_FORMATS: dict[str, str] = {
    "email": "contact",
    "password": "credential",
    "date": "sensitive-if-birthdate",
}

_SPLIT = re.compile(r"[^a-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


@dataclass
class PiiMatch:
    token: str
    category: str
    strength: str  # "direct" | "quasi" | "format" | "declared"
    reason: str


@dataclass
class PiiDictionary:
    direct: dict[str, str] = field(default_factory=lambda: dict(DIRECT_IDENTIFIERS))
    quasi: dict[str, str] = field(default_factory=lambda: dict(QUASI_IDENTIFIERS))
    formats: dict[str, str] = field(default_factory=lambda: dict(SENSITIVE_FORMATS))

    def tokens(self, identifier: str) -> list[str]:
        """Split `dateOfBirth`, `date_of_birth` and `date-of-birth` the same way."""
        spaced = _CAMEL.sub("_", identifier)
        parts = [p for p in _SPLIT.split(spaced.lower()) if p]
        joined = "_".join(parts)
        candidates = {joined, *parts}
        # multi-word dictionary keys such as "date_of_birth" and "card_last4"
        for size in (2, 3):
            for index in range(len(parts) - size + 1):
                candidates.add("_".join(parts[index : index + size]))
        return sorted(candidates)

    def classify(
        self,
        name: str,
        *,
        fmt: str | None = None,
        declared_sensitive: bool = False,
        description: str = "",
    ) -> list[PiiMatch]:
        matches: list[PiiMatch] = []
        if declared_sensitive:
            matches.append(
                PiiMatch(
                    token=name,
                    category="declared",
                    strength="declared",
                    reason="The specification marks this field as sensitive.",
                )
            )
        seen_tokens: set[str] = set()
        for token in self.tokens(name):
            if token in seen_tokens:
                continue
            if token in self.direct:
                seen_tokens.add(token)
                matches.append(
                    PiiMatch(
                        token=token,
                        category=self.direct[token],
                        strength="direct",
                        reason=f"The field name contains '{token}', a direct identifier.",
                    )
                )
            elif token in self.quasi:
                seen_tokens.add(token)
                matches.append(
                    PiiMatch(
                        token=token,
                        category=self.quasi[token],
                        strength="quasi",
                        reason=f"The field name contains '{token}', a quasi-identifier.",
                    )
                )
        if fmt and fmt in self.formats and fmt != "date":
            matches.append(
                PiiMatch(
                    token=fmt,
                    category=self.formats[fmt],
                    strength="format",
                    reason=f"The field declares format '{fmt}'.",
                )
            )
        return matches

    def is_sensitive(self, name: str, *, fmt: str | None = None, declared: bool = False) -> bool:
        return any(
            m.strength in ("direct", "declared", "format")
            for m in self.classify(name, fmt=fmt, declared_sensitive=declared)
        )


DEFAULT_DICTIONARY = PiiDictionary()
