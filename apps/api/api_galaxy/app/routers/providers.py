"""Provider health and configuration, external-request consent, pricing, and Model Arena."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api_galaxy import PROMPT_TEMPLATE_VERSION
from api_galaxy.app.errors import NotFoundError, ProviderUnavailableError, ValidationFailure
from api_galaxy.app.state import get_state
from api_galaxy.contracts.providers import EnrichmentRequest, ProviderKind
from api_galaxy.providers.base import ProviderError
from api_galaxy.providers.context import build_context
from api_galaxy.providers.prompts import enrichment_prompt
from api_galaxy.providers.sanitizer import build_preview

router = APIRouter(prefix="/api/v1", tags=["providers"])


@router.get("/providers/health")
async def providers_health() -> dict[str, Any]:
    """Health-check every provider concurrently so Settings loads in one round trip."""
    state = get_state()
    providers = [
        state.deterministic_provider(),
        state.ollama_provider(),
        state.kimi_provider(),
    ]
    results = await asyncio.gather(*(p.health() for p in providers), return_exceptions=True)
    payload = []
    for provider, result in zip(providers, results, strict=True):
        if isinstance(result, Exception):
            payload.append(
                {
                    "kind": provider.kind.value,
                    "status": "error",
                    "detail": f"{type(result).__name__}: {result}",
                    "external": provider.kind is ProviderKind.KIMI,
                    "ready": False,
                }
            )
        else:
            payload.append({**result.model_dump(mode="json"), "ready": result.ready})
    return {
        "providers": payload,
        "settings": state.provider_settings(),
        "kimi_key_configured": bool(state.kimi_key()),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "modes": [
            {
                "id": "local",
                "label": "Local & Private",
                "detail": "Ollama on this machine. Nothing leaves your laptop.",
                "provider": ProviderKind.OLLAMA.value,
            },
            {
                "id": "external",
                "label": "Kimi API",
                "detail": "Optional external analysis. Requires per-project consent.",
                "provider": ProviderKind.KIMI.value,
            },
            {
                "id": "arena",
                "label": "Compare Both",
                "detail": "Model Arena — same task, same schema, side-by-side.",
                "provider": "arena",
            },
            {
                "id": "deterministic",
                "label": "No model",
                "detail": "Graph-derived answers. Always available, always reproducible.",
                "provider": ProviderKind.DETERMINISTIC.value,
            },
        ],
    }


class ProviderConfig(BaseModel):
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    ollama_timeout: float | None = Field(default=None, ge=5, le=900)
    kimi_base_url: str | None = None
    kimi_model: str | None = None
    kimi_timeout: float | None = Field(default=None, ge=5, le=600)
    external_providers_enabled: bool | None = None


@router.put("/providers/config")
async def update_config(payload: ProviderConfig) -> dict[str, Any]:
    state = get_state()
    values = state.save_provider_settings(payload.model_dump(exclude_none=True))
    if payload.external_providers_enabled is False:
        # Turning the master switch off also drops every recorded consent, so switching it
        # back on cannot silently resume sending data.
        state.consent.clear()
    return {"settings": values}


class KimiKeyPayload(BaseModel):
    api_key: str = ""


@router.post("/providers/kimi/key")
async def set_kimi_key(payload: KimiKeyPayload) -> dict[str, Any]:
    state = get_state()
    return state.set_kimi_key(payload.api_key.strip() or None)


@router.post("/providers/{provider}/test")
async def test_provider(provider: str) -> dict[str, Any]:
    state = get_state()
    try:
        kind = ProviderKind(provider)
    except ValueError as exc:
        raise NotFoundError(f"'{provider}' is not a known provider.") from exc
    health = await state.provider(kind).health()
    return {**health.model_dump(mode="json"), "ready": health.ready}


# --------------------------------------------------------------------------------------
# Pricing
# --------------------------------------------------------------------------------------


class PricingUpdate(BaseModel):
    provider: str
    input_per_million: float = Field(ge=0, le=10_000)
    output_per_million: float = Field(ge=0, le=10_000)
    note: str = ""


@router.get("/providers/pricing")
async def get_pricing() -> dict[str, Any]:
    state = get_state()
    return {
        "pricing": state.pricing.to_dict(),
        "disclaimer": "These are example figures shipped with the app, not a quote. Check "
        "your provider's current price list and edit them here. API Galaxy never treats a "
        "price as permanent truth.",
    }


@router.put("/providers/pricing")
async def update_pricing(payload: PricingUpdate) -> dict[str, Any]:
    state = get_state()
    state.pricing.set(
        payload.provider,
        input_per_million=payload.input_per_million,
        output_per_million=payload.output_per_million,
        note=payload.note,
    )
    state.save_pricing()
    return {"pricing": state.pricing.to_dict()}


# --------------------------------------------------------------------------------------
# Consent and the external-request preview
# --------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/external-preview")
async def external_preview(project_id: str, task: str = "enrich") -> dict[str, Any]:
    """Exactly what would be sent to the external provider, and what was stripped out."""
    state = get_state()
    live = state.get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    values = state.provider_settings()
    context = build_context(live.graph, chunk_label=f"{task} preview")
    prompt = enrichment_prompt(context)
    preview = build_preview(
        {"prompt": prompt, "context": context.model_dump(mode="json")},
        provider="kimi",
        model=str(values["kimi_model"]),
        endpoint=f"{values['kimi_base_url']}/chat/completions",
    )
    return {
        **preview.to_dict(),
        "consent": state.consent.state(project_id),
        "external_providers_enabled": values["external_providers_enabled"],
    }


class ConsentPayload(BaseModel):
    granted: bool
    remember: bool = False
    fingerprint: str = ""


@router.post("/projects/{project_id}/consent")
async def set_consent(project_id: str, payload: ConsentPayload) -> dict[str, Any]:
    state = get_state()
    if state.get(project_id) is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    if payload.granted:
        if not state.provider_settings()["external_providers_enabled"]:
            raise ValidationFailure(
                "External providers are switched off globally. Enable them in Settings first."
            )
        state.consent.grant(project_id, remember=payload.remember, fingerprint=payload.fingerprint)
    else:
        state.consent.revoke(project_id)
    return {"consent": state.consent.state(project_id), "project_id": project_id}


# --------------------------------------------------------------------------------------
# Model Arena
# --------------------------------------------------------------------------------------


class ArenaRequest(BaseModel):
    providers: list[str] = Field(default_factory=lambda: ["deterministic", "ollama"])
    domain_id: str | None = None
    max_items: int = Field(default=16, ge=4, le=40)


@router.post("/projects/{project_id}/arena")
async def run_arena(project_id: str, payload: ArenaRequest) -> dict[str, Any]:
    """Run the same enrichment task on two or more providers and normalise the results."""
    state = get_state()
    live = state.get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    if len(payload.providers) < 2:
        raise ValidationFailure("The arena needs at least two providers to compare.")

    kinds: list[ProviderKind] = []
    for name in payload.providers:
        try:
            kinds.append(ProviderKind(name))
        except ValueError as exc:
            raise ProviderUnavailableError(f"'{name}' is not a known provider.") from exc

    node_ids = None
    if payload.domain_id:
        from api_galaxy.contracts.graph import EdgeType

        members = {
            e.source
            for e in live.graph.edges
            if e.type is EdgeType.BELONGS_TO_DOMAIN and e.target == payload.domain_id
        }
        expanded = set(members)
        for edge in live.graph.edges:
            if edge.source in members:
                expanded.add(edge.target)
        node_ids = expanded or None

    context = build_context(
        live.graph,
        chunk_label=payload.domain_id or "estate",
        node_ids=node_ids,
    )
    request = EnrichmentRequest(
        project_id=project_id, context=context, max_items=payload.max_items
    )
    providers = [state.provider(kind, live.graph) for kind in kinds]

    try:
        comparison = await state.comparison.run(providers, request)
    except ProviderError as exc:
        raise ProviderUnavailableError(exc.message, hint=exc.hint) from exc

    index = live.graph.node_index()

    def decorate(items):
        return [
            {
                **item.model_dump(mode="json"),
                "source_label": index[item.source_id].label if item.source_id in index else item.source_id,
                "target_label": index[item.target_id].label if item.target_id in index else item.target_id,
            }
            for item in items
        ]

    return {
        **comparison.model_dump(mode="json"),
        "consensus": decorate(comparison.consensus),
        "only_a": decorate(comparison.only_a),
        "only_b": decorate(comparison.only_b),
        "conflicts": decorate(comparison.conflicts),
        "pricing_disclaimer": "Cost is estimated from your editable pricing table, not billed.",
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
    }


class ArenaDecision(BaseModel):
    action: str = Field(description="accept_ollama | accept_kimi | merge | reject_both | edit")
    subject: str
    payload: dict[str, Any] = Field(default_factory=dict)
    provider: str = ""
    model: str = ""
    source_references: list[str] = Field(default_factory=list)


@router.post("/projects/{project_id}/arena/decision")
async def record_arena_decision(project_id: str, payload: ArenaDecision) -> dict[str, Any]:
    """Write an immutable decision-log entry. There is no update or delete path for these."""
    state = get_state()
    if state.get(project_id) is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    allowed = {"accept_ollama", "accept_kimi", "accept_deterministic", "merge", "reject_both", "edit"}
    if payload.action not in allowed:
        raise ValidationFailure(f"action must be one of: {', '.join(sorted(allowed))}.")

    from api_galaxy.providers.sanitizer import payload_fingerprint

    record = state.storage.record_decision(
        project_id=project_id,
        provider=payload.provider,
        model=payload.model,
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        task="arena",
        action=payload.action,
        subject=payload.subject,
        accepted_payload=payload.payload,
        payload_fingerprint=payload_fingerprint(payload.payload),
        source_references=payload.source_references,
    )
    return {"decision": record}


@router.get("/projects/{project_id}/decisions")
async def list_decisions(project_id: str, limit: int = 200) -> dict[str, Any]:
    state = get_state()
    if state.get(project_id) is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    return {
        "decisions": state.storage.list_decisions(project_id, limit=limit),
        "note": "This log is append-only. Entries are never edited or removed.",
    }


# --------------------------------------------------------------------------------------
# Cache and data controls
# --------------------------------------------------------------------------------------


@router.get("/cache")
async def cache_stats() -> dict[str, Any]:
    return {"cache": get_state().cache.stats()}


@router.delete("/cache")
async def clear_cache() -> dict[str, Any]:
    return {"cleared": get_state().cache.clear()}


@router.delete("/data")
async def clear_everything() -> dict[str, Any]:
    """Settings → 'Clear all local data'. Removes projects, exports, decisions and caches."""
    state = get_state()
    counts = state.storage.clear_all()
    state.cache.clear()
    state.consent.clear()
    credentials = state.set_kimi_key(None)
    for project_id in list(getattr(state, "_projects", {})):
        state.forget(project_id)
    return {
        "cleared": counts,
        "credentials_cleared": not credentials["configured"],
        "note": "Projects, exports, decisions, caches, consent and the stored API key are gone.",
    }
