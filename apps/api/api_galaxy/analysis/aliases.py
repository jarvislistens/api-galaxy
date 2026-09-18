"""Deterministic alias detection.

Finding that ``customer_id``, ``cust_no`` and ``party_key`` are the same concept is a
semantic judgement, so this is a heuristic and is labelled as one everywhere it surfaces.
But it does not need a language model.

The rule that makes this work without over-merging
---------------------------------------------------
Naive pairwise similarity plus transitive closure collapses an entire e-commerce estate
into one blob: ``Cart.customer_id``'s description mentions "cart", ``Order.cart_id``'s
mentions "order", and within three hops every identifier is an alias of every other.

So we anchor first:

* An identifier whose **stem matches a declared schema name** (``customer_id`` → there is
  a ``Customer`` schema; ``cart_id`` → there is a ``Cart``) is a *self-explaining* concept.
  It keeps its own identity and is never pulled into another concept by prose.
* An identifier whose stem matches **nothing** in the estate (``cust_no`` → no ``Cust``
  schema; ``party_key`` → no ``Party``) is *unexplained*, and only those get resolved —
  by abbreviation (``cust`` is a prefix of ``customer``) or by their own description
  naming the concept ("Stable identifier of the **customer** who placed the order").

Merging therefore flows one way, from unexplained names toward anchored ones, which is
both accurate on real estates and easy for a reviewer to check in a single click.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field

from api_galaxy.analysis.pii import _CAMEL, _SPLIT
from api_galaxy.contracts.analysis import AliasCluster
from api_galaxy.contracts.graph import Provenance, SourceKind
from api_galaxy.contracts.ids import field_id, slugify
from api_galaxy.parsing.normalize import NormalizedEstate

IDENTIFIER_SUFFIXES = (
    "_id",
    "_ids",
    "_no",
    "_num",
    "_number",
    "_key",
    "_ref",
    "_reference",
    "_code",
    "_uuid",
    "_guid",
    "_identifier",
)
MIN_ABBREVIATION_LENGTH = 3
STOPWORDS = {
    "the", "a", "an", "of", "for", "this", "that", "which", "who", "and", "or", "to",
    "is", "was", "in", "on", "by", "with", "from", "it", "its", "has", "have", "be",
    "unique", "stable", "identifier", "id", "reference", "value", "field", "used",
    "owns", "owned", "placed", "belongs", "same", "as", "at", "no", "not",
}


def _tokens(value: str) -> list[str]:
    spaced = _CAMEL.sub("_", value)
    return [t for t in _SPLIT.split(spaced.lower()) if t]


def _stem(name: str) -> str:
    lowered = "_".join(_tokens(name))
    for suffix in IDENTIFIER_SUFFIXES:
        if lowered.endswith(suffix) and len(lowered) > len(suffix):
            return lowered[: -len(suffix)]
    return lowered


def looks_like_identifier(name: str) -> bool:
    lowered = "_".join(_tokens(name))
    if lowered in ("id", "uuid", "guid"):
        return True
    return any(lowered.endswith(suffix) for suffix in IDENTIFIER_SUFFIXES)


@dataclass
class _Candidate:
    node_id: str
    label: str
    service: str
    schema: str
    name: str
    stem: str
    description: str
    words: list[str] = dc_field(default_factory=list)
    anchored: bool = False


def _schema_vocabulary(estate: NormalizedEstate) -> set[str]:
    """Every token that appears in a declared schema name, plus the names themselves.

    ``CartItem`` contributes ``cartitem``, ``cart`` and ``item``; this is what decides
    whether an identifier stem is self-explaining.
    """
    vocabulary: set[str] = set()
    for service in estate.services:
        for schema in service.schemas:
            tokens = _tokens(schema.name)
            vocabulary.add("".join(tokens))
            vocabulary.add("_".join(tokens))
            vocabulary.update(tokens)
    return vocabulary


def detect_alias_clusters(
    estate: NormalizedEstate, *, min_confidence: float = 0.65
) -> list[AliasCluster]:
    vocabulary = _schema_vocabulary(estate)
    candidates: list[_Candidate] = []
    for service in estate.services:
        for schema in service.schemas:
            for fld in schema.fields:
                if "." in fld.dotted_path or not looks_like_identifier(fld.name):
                    continue
                stem = _stem(fld.name)
                if not stem or stem in ("", "id", "uuid", "guid"):
                    continue
                stem_tokens = stem.split("_")
                candidates.append(
                    _Candidate(
                        node_id=field_id(service.name, schema.name, fld.dotted_path),
                        label=f"{service.name}.{schema.name}.{fld.name}",
                        service=service.slug,
                        schema=schema.name,
                        name=fld.name,
                        stem=stem,
                        description=fld.description,
                        words=[w for w in _tokens(fld.description) if w not in STOPWORDS],
                        anchored=any(token in vocabulary for token in stem_tokens),
                    )
                )

    if not candidates:
        return []

    anchored_stems = {c.stem for c in candidates if c.anchored}

    # Each stem starts as its own concept; unexplained stems may be redirected once.
    resolution: dict[str, str] = {c.stem: c.stem for c in candidates}
    reasons: dict[str, tuple[str, float]] = {}

    # Identifiers already present in the same schema. A schema almost never carries two
    # identifiers for the same concept, so `Payment.order_id` rules `order` out as the
    # meaning of its sibling `Payment.party_key` — which is what pins party_key to
    # `customer` even though its description mentions the order too.
    claimed_by_schema: dict[tuple[str, str], set[str]] = {}
    for candidate in candidates:
        if candidate.anchored:
            claimed_by_schema.setdefault((candidate.service, candidate.schema), set()).add(
                candidate.stem
            )

    for candidate in candidates:
        if candidate.anchored or resolution[candidate.stem] != candidate.stem:
            continue
        claimed = claimed_by_schema.get((candidate.service, candidate.schema), set())
        target, reason, score = _resolve(candidate, anchored_stems, claimed)
        if target and score >= min_confidence:
            resolution[candidate.stem] = target
            reasons[candidate.stem] = (reason, score)

    groups: dict[str, list[_Candidate]] = {}
    for candidate in candidates:
        groups.setdefault(resolution[candidate.stem], []).append(candidate)

    clusters: list[AliasCluster] = []
    for concept, members in sorted(groups.items()):
        names = sorted({m.name for m in members})
        services = sorted({m.service for m in members})
        if len(names) < 2:
            continue  # the same name in several services is not an *alias* problem
        scores = [score for stem, (_, score) in reasons.items()
                  if any(m.stem == stem for m in members)]
        confidence = round(min(0.95, sum(scores) / len(scores)), 2) if scores else 0.9
        explanations = [reason for stem, (reason, _) in sorted(reasons.items())
                        if any(m.stem == stem for m in members)]
        clusters.append(
            AliasCluster(
                id=f"alias:{slugify(concept)}",
                canonical_name=concept.replace("_", " "),
                members=sorted(m.node_id for m in members),
                member_labels=sorted(m.label for m in members),
                confidence=confidence,
                rationale=(
                    f"{len(names)} different names across {len(services)} service(s) appear to "
                    f"identify the same '{concept.replace('_', ' ')}'. "
                    + " ".join(explanations[:3])
                ).strip(),
                accepted=None,
                provenance=Provenance(
                    source_kind=SourceKind.DETERMINISTIC_RULE,
                    rule_id="alias-detection",
                    explanation="Unexplained identifier stems were resolved to the schema "
                    "concepts named by their abbreviation or their own description. "
                    "This is a suggestion, not a fact.",
                    confidence=confidence,
                ),
            )
        )
    clusters.sort(key=lambda c: (-c.confidence, c.canonical_name))
    return clusters


def _resolve(
    candidate: _Candidate, anchored_stems: set[str], claimed: set[str]
) -> tuple[str | None, str, float]:
    """Map an unexplained identifier onto an anchored concept, or leave it alone.

    ``claimed`` holds the concepts already covered by sibling identifiers in the same
    schema; those are never candidate meanings.
    """
    available = anchored_stems - claimed - {candidate.stem}

    # 1. Abbreviation: 'cust' is a prefix of 'customer'.
    prefixes = sorted(
        (stem for stem in available if stem.startswith(candidate.stem)),
        key=len,
    )
    if prefixes and len(candidate.stem) >= MIN_ABBREVIATION_LENGTH:
        target = prefixes[0]
        return target, f"'{candidate.name}' reads as an abbreviation of '{target}'.", 0.78

    # 2. The field's own description names an anchored concept that is still unclaimed.
    for word in candidate.words:
        if word in available:
            return (
                word,
                f"The description of '{candidate.name}' says it identifies the {word}, "
                f"and no other identifier in {candidate.schema} covers that concept.",
                0.72,
            )
    return None, "", 0.0
