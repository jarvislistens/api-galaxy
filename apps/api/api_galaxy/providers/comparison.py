"""The Model Arena.

Two providers get the *same* sanitized context, the *same* prompt template version and
the *same* response schema, and the results are normalised through the same parser. That
is the only way a comparison means anything.

What we compare, and why:

* structured-output validity and retries — does it follow instructions at all?
* entities / domains / aliases / relations found — recall of the semantic layer
* agreement, disagreement and outright conflict on relationships
* hallucinated references — IDs it invented; the single most important honesty metric
* latency, tokens and estimated cost — what it costs you to get that

Pricing is user-editable and stamped with who last changed it. We ship example numbers
and label them as examples; nothing in the product treats a price as a permanent truth.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from api_galaxy.contracts.providers import (
    ArenaComparison,
    ArenaRelation,
    EnrichmentRequest,
    EnrichmentResult,
    ProviderKind,
    ProviderRunMetrics,
    TaskKind,
)


@dataclass
class ProviderPricing:
    """USD per 1M tokens. Example values only — the user owns these numbers."""

    input_per_million: float
    output_per_million: float
    note: str = "Example value shipped with the app. Edit it in Settings."
    updated_by: str = "app"
    updated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )

    def cost(self, input_tokens: int | None, output_tokens: int | None) -> float | None:
        if input_tokens is None and output_tokens is None:
            return None
        return round(
            (input_tokens or 0) / 1_000_000 * self.input_per_million
            + (output_tokens or 0) / 1_000_000 * self.output_per_million,
            6,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_per_million": self.input_per_million,
            "output_per_million": self.output_per_million,
            "note": self.note,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at,
        }


DEFAULT_PRICING: dict[str, ProviderPricing] = {
    ProviderKind.DETERMINISTIC.value: ProviderPricing(
        0.0, 0.0, note="Runs locally with no model. Always free."
    ),
    ProviderKind.OLLAMA.value: ProviderPricing(
        0.0, 0.0, note="Runs on your own machine. No per-token cost — you pay in watts."
    ),
    ProviderKind.KIMI.value: ProviderPricing(
        0.60,
        2.50,
        note="EXAMPLE PRICING, not a quote. Check the provider's current price list and "
        "update this in Settings.",
    ),
}


class PricingBook:
    def __init__(self, pricing: dict[str, ProviderPricing] | None = None) -> None:
        self._pricing = dict(pricing or DEFAULT_PRICING)

    def get(self, provider: ProviderKind | str) -> ProviderPricing:
        key = provider.value if isinstance(provider, ProviderKind) else str(provider)
        return self._pricing.get(key, ProviderPricing(0.0, 0.0, note="No pricing configured."))

    def set(self, provider: str, *, input_per_million: float, output_per_million: float,
            note: str = "") -> ProviderPricing:
        updated = ProviderPricing(
            input_per_million=max(0.0, float(input_per_million)),
            output_per_million=max(0.0, float(output_per_million)),
            note=note or "Set by you.",
            updated_by="local-user",
        )
        self._pricing[provider] = updated
        return updated

    def to_dict(self) -> dict[str, Any]:
        return {name: pricing.to_dict() for name, pricing in sorted(self._pricing.items())}


# --------------------------------------------------------------------------------------


@dataclass
class ArenaRun:
    provider: ProviderKind
    result: EnrichmentResult | None
    error: str = ""
    elapsed_ms: float = 0.0


class ComparisonService:
    def __init__(self, pricing: PricingBook | None = None) -> None:
        self.pricing = pricing or PricingBook()

    async def run(
        self,
        providers: list[Any],
        request: EnrichmentRequest,
    ) -> ArenaComparison:
        """Run the same enrichment task on each provider concurrently."""
        runs = await asyncio.gather(
            *(self._run_one(provider, request) for provider in providers),
            return_exceptions=False,
        )
        return self.compare(runs, project_id=request.project_id)

    async def _run_one(self, provider: Any, request: EnrichmentRequest) -> ArenaRun:
        started = time.perf_counter()
        try:
            result = await provider.enrich(request)
            return ArenaRun(
                provider=provider.kind,
                result=result,
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:  # noqa: BLE001 - one provider failing must not kill the arena
            return ArenaRun(
                provider=getattr(provider, "kind", ProviderKind.DETERMINISTIC),
                result=None,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )

    # ---------------------------------------------------------------- comparison

    def compare(self, runs: list[ArenaRun], *, project_id: str) -> ArenaComparison:
        comparison = ArenaComparison(project_id=project_id, task=TaskKind.ENRICH)

        for run in runs:
            pricing = self.pricing.get(run.provider)
            result = run.result
            comparison.metrics.append(
                ProviderRunMetrics(
                    provider=run.provider,
                    model=result.model if result else "",
                    ok=result is not None,
                    error=run.error,
                    latency_ms=round(result.latency_ms if result else run.elapsed_ms, 1),
                    input_tokens=result.input_tokens if result else None,
                    output_tokens=result.output_tokens if result else None,
                    estimated_cost_usd=pricing.cost(
                        result.input_tokens if result else None,
                        result.output_tokens if result else None,
                    ),
                    valid_structured_output=bool(result and result.valid_json),
                    retries=result.retries if result else 0,
                    entities=len(result.entities) if result else 0,
                    relations=len(result.relations) if result else 0,
                    aliases=len(result.aliases) if result else 0,
                    domains=len(result.domains) if result else 0,
                    risks=len(result.risks) if result else 0,
                    hallucinated_references=len(result.dropped_references) if result else 0,
                    rationale=result.rationale if result else "",
                )
            )

        ok_runs = [r for r in runs if r.result is not None]
        if len(ok_runs) < 2:
            comparison.notes.append(
                "Fewer than two providers returned a result, so there is nothing to compare. "
                "The metrics table above still shows what happened to each."
            )
            if ok_runs:
                only = ok_runs[0]
                comparison.only_a = _relations_of(only)
            return comparison

        a, b = ok_runs[0], ok_runs[1]
        relations_a = {(_key(r)): r for r in a.result.relations}
        relations_b = {(_key(r)): r for r in b.result.relations}

        for key in sorted(set(relations_a) | set(relations_b)):
            in_a = relations_a.get(key)
            in_b = relations_b.get(key)
            pair = key.split("||")
            entry = ArenaRelation(
                source_id=pair[0],
                target_id=pair[1],
                relation=in_a.relation if in_a else (in_b.relation if in_b else ""),
            )
            if in_a and in_b:
                entry.providers = [a.provider, b.provider]
                entry.confidences = {
                    a.provider.value: in_a.confidence,
                    b.provider.value: in_b.confidence,
                }
                entry.rationales = {
                    a.provider.value: in_a.rationale,
                    b.provider.value: in_b.rationale,
                }
                if in_a.relation != in_b.relation:
                    entry.verdict = "conflict"
                    comparison.conflicts.append(entry)
                else:
                    entry.verdict = "consensus"
                    comparison.consensus.append(entry)
            elif in_a:
                entry.providers = [a.provider]
                entry.confidences = {a.provider.value: in_a.confidence}
                entry.rationales = {a.provider.value: in_a.rationale}
                entry.verdict = f"{a.provider.value}_only"
                comparison.only_a.append(entry)
            elif in_b:
                entry.providers = [b.provider]
                entry.confidences = {b.provider.value: in_b.confidence}
                entry.rationales = {b.provider.value: in_b.rationale}
                entry.verdict = f"{b.provider.value}_only"
                comparison.only_b.append(entry)

        comparison.alias_agreement = _set_agreement(
            {frozenset(x.member_ids) for x in a.result.aliases},
            {frozenset(x.member_ids) for x in b.result.aliases},
            a.provider,
            b.provider,
        )
        comparison.domain_agreement = _set_agreement(
            {x.name.strip().lower() for x in a.result.domains},
            {x.name.strip().lower() for x in b.result.domains},
            a.provider,
            b.provider,
        )

        comparison.notes.append(
            f"{len(comparison.consensus)} relationship(s) agreed, "
            f"{len(comparison.conflicts)} in direct conflict, "
            f"{len(comparison.only_a)} only from {a.provider.value}, "
            f"{len(comparison.only_b)} only from {b.provider.value}."
        )
        hallucinations = {
            m.provider.value: m.hallucinated_references for m in comparison.metrics if m.ok
        }
        if any(hallucinations.values()):
            comparison.notes.append(
                "Invented references (discarded before reaching the graph): "
                + ", ".join(f"{name} {count}" for name, count in sorted(hallucinations.items()))
                + "."
            )
        return comparison


def _key(relation: Any) -> str:
    return f"{relation.source_id}||{relation.target_id}"


def _relations_of(run: ArenaRun) -> list[ArenaRelation]:
    if run.result is None:
        return []
    return [
        ArenaRelation(
            source_id=r.source_id,
            target_id=r.target_id,
            relation=r.relation,
            providers=[run.provider],
            confidences={run.provider.value: r.confidence},
            rationales={run.provider.value: r.rationale},
            verdict=f"{run.provider.value}_only",
        )
        for r in run.result.relations
    ]


def _set_agreement(a: set, b: set, provider_a: ProviderKind, provider_b: ProviderKind) -> dict[str, Any]:
    both = a & b
    union = a | b
    return {
        "agreed": len(both),
        "only_" + provider_a.value: len(a - b),
        "only_" + provider_b.value: len(b - a),
        "jaccard": round(len(both) / len(union), 3) if union else 0.0,
    }
