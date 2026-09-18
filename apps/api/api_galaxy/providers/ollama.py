"""Ollama adapter — the default, local, private provider.

Two hard-won details are baked in here:

* ``think: false``. Reasoning-tuned models (qwen3 and friends) put their output in a
  separate ``thinking`` field and leave ``response`` empty, so the caller sees nothing and
  silently falls back. We disable thinking and, belt-and-braces, read ``thinking`` if
  ``response`` comes back empty anyway.
* ``format: "json"``. Ollama can constrain decoding to valid JSON, which removes most of
  the retry loop's work for small models.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from api_galaxy.contracts.providers import (
    AnswerEvidence,
    EnrichmentRequest,
    EnrichmentResult,
    GraphAnswer,
    GraphQuestionRequest,
    InferredAlias,
    InferredCapability,
    InferredDomain,
    InferredEntity,
    InferredJourney,
    InferredRelation,
    InferredRisk,
    ProposedRepair,
    ProviderHealth,
    ProviderKind,
    ProviderStatus,
    RepairProposal,
    RepairRequest,
)
from api_galaxy.providers.base import (
    ProviderError,
    StructuredCall,
    clamp_confidence,
    clean_rationale,
    filter_references,
)
from api_galaxy.providers.prompts import (
    ALLOWED_REPAIR_KINDS,
    ANSWER_SCHEMA,
    ENRICHMENT_SCHEMA,
    PROMPT_TEMPLATE_VERSION,
    REPAIR_SCHEMA,
    answer_prompt,
    enrichment_prompt,
    repair_prompt,
)

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:4b"
DEFAULT_TIMEOUT = 180.0


class OllamaProvider:
    kind = ProviderKind.OLLAMA

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        temperature: float = 0.1,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature

    # ------------------------------------------------------------------- health

    async def health(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
        except httpx.ConnectError:
            return ProviderHealth(
                kind=self.kind,
                status=ProviderStatus.UNREACHABLE,
                model=self.model,
                base_url=self.base_url,
                detail=f"Nothing is listening on {self.base_url}.",
                setup_hint="Install Ollama from ollama.com, then run `ollama serve`. "
                f"Pull the model with `ollama pull {self.model}`.",
            )
        except Exception as exc:  # noqa: BLE001 - surface anything as actionable status
            return ProviderHealth(
                kind=self.kind,
                status=ProviderStatus.ERROR,
                model=self.model,
                base_url=self.base_url,
                detail=f"{type(exc).__name__}: {exc}",
                setup_hint="Check that Ollama is running and reachable.",
            )

        available = [str(m.get("name")) for m in payload.get("models", []) if m.get("name")]
        latency = (time.perf_counter() - started) * 1000
        if self.model not in available:
            return ProviderHealth(
                kind=self.kind,
                status=ProviderStatus.NOT_CONFIGURED,
                model=self.model,
                base_url=self.base_url,
                detail=f"Ollama is running but '{self.model}' is not pulled.",
                setup_hint=f"Run `ollama pull {self.model}`."
                + (f" Available now: {', '.join(available[:6])}." if available else ""),
                available_models=available,
                latency_ms=latency,
            )
        return ProviderHealth(
            kind=self.kind,
            status=ProviderStatus.READY,
            model=self.model,
            base_url=self.base_url,
            detail=f"Ready. {len(available)} model(s) installed locally.",
            available_models=available,
            latency_ms=latency,
        )

    # ------------------------------------------------------------------ transport

    async def _generate(self, prompt: str, feedback: str | None) -> tuple[str, dict[str, Any]]:
        body = {
            "model": self.model,
            "prompt": prompt if feedback is None else f"{prompt}\n\nCORRECTION: {feedback}",
            "stream": False,
            "format": "json",
            # See the module docstring: leaving thinking on returns an empty `response`.
            "think": False,
            "options": {"temperature": self.temperature, "num_ctx": 8192},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=body)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderError(
                self.kind,
                f"Ollama did not respond within {self.timeout:.0f}s.",
                hint="Try a smaller model, or raise the timeout in Settings.",
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(self.kind, f"Ollama request failed: {exc}") from exc

        text = str(payload.get("response") or "")
        if not text.strip():
            text = str(payload.get("thinking") or "")
        usage = {
            "input_tokens": payload.get("prompt_eval_count"),
            "output_tokens": payload.get("eval_count"),
        }
        return text, usage

    # -------------------------------------------------------------------- tasks

    async def enrich(self, request: EnrichmentRequest) -> EnrichmentResult:
        prompt = enrichment_prompt(request.context, max_items=request.max_items)
        call = StructuredCall(self.kind, ENRICHMENT_SCHEMA)
        payload = await call.run(lambda feedback: self._generate(prompt, feedback))
        return _parse_enrichment(payload, request, self.kind, self.model, call)

    async def answer(self, request: GraphQuestionRequest) -> GraphAnswer:
        prompt = answer_prompt(request.context, request.question)
        call = StructuredCall(self.kind, ANSWER_SCHEMA)
        payload = await call.run(lambda feedback: self._generate(prompt, feedback))
        return _parse_answer(payload, request, self.kind, self.model, call)

    async def propose_repairs(self, request: RepairRequest) -> RepairProposal:
        prompt = repair_prompt(
            request.context,
            request.change_summaries,
            request.broken_node_ids,
            request.broken_journeys,
        )
        call = StructuredCall(self.kind, REPAIR_SCHEMA)
        payload = await call.run(lambda feedback: self._generate(prompt, feedback))
        return _parse_repairs(payload, request, self.kind, self.model, call)


# --------------------------------------------------------------------------------------
# Shared response parsing — used by Ollama and Kimi so both are normalised identically,
# which is what makes the Model Arena a fair comparison.
# --------------------------------------------------------------------------------------


def _parse_enrichment(
    payload: dict[str, Any],
    request: EnrichmentRequest,
    kind: ProviderKind,
    model: str,
    call: StructuredCall,
) -> EnrichmentResult:
    allowed = set(request.context.allowed_node_ids)
    dropped: list[str] = []
    limit = request.max_items

    result = EnrichmentResult(
        provider=kind,
        model=model,
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        latency_ms=call.latency_ms,
        input_tokens=call.input_tokens,
        output_tokens=call.output_tokens,
        retries=call.retries,
        warnings=list(call.warnings),
        rationale=clean_rationale(payload.get("rationale")),
    )

    for raw in (payload.get("entities") or [])[:limit]:
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        result.entities.append(
            InferredEntity(
                name=name[:120],
                description=clean_rationale(raw.get("description"), max_length=400),
                represented_by=filter_references(raw.get("represented_by") or [], allowed, dropped),
                confidence=clamp_confidence(raw.get("confidence")),
            )
        )

    for raw in (payload.get("domains") or [])[:limit]:
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        result.domains.append(
            InferredDomain(
                name=name[:120],
                description=clean_rationale(raw.get("description"), max_length=400),
                service_ids=filter_references(raw.get("service_ids") or [], allowed, dropped),
                confidence=clamp_confidence(raw.get("confidence")),
            )
        )

    for raw in (payload.get("capabilities") or [])[:limit]:
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        result.capabilities.append(
            InferredCapability(
                name=name[:120],
                description=clean_rationale(raw.get("description"), max_length=400),
                operation_ids=filter_references(raw.get("operation_ids") or [], allowed, dropped),
                confidence=clamp_confidence(raw.get("confidence")),
            )
        )

    for raw in (payload.get("journeys") or [])[:limit]:
        name = str(raw.get("name") or "").strip()
        operation_ids = filter_references(raw.get("operation_ids") or [], allowed, dropped)
        if not name or not operation_ids:
            continue
        result.journeys.append(
            InferredJourney(
                name=name[:120],
                description=clean_rationale(raw.get("description"), max_length=400),
                operation_ids=operation_ids,
                narrations=[clean_rationale(n, max_length=240) for n in (raw.get("narrations") or [])],
                confidence=clamp_confidence(raw.get("confidence")),
            )
        )

    for raw in (payload.get("aliases") or [])[:limit]:
        members = filter_references(raw.get("member_ids") or [], allowed, dropped)
        if len(members) < 2:
            continue
        result.aliases.append(
            InferredAlias(
                canonical_name=str(raw.get("canonical_name") or "concept")[:80],
                member_ids=members,
                rationale=clean_rationale(raw.get("rationale"), max_length=300),
                confidence=clamp_confidence(raw.get("confidence")),
            )
        )

    for raw in (payload.get("relations") or [])[:limit]:
        source = filter_references([raw.get("source_id")], allowed, dropped)
        target = filter_references([raw.get("target_id")], allowed, dropped)
        if not source or not target or source[0] == target[0]:
            continue
        result.relations.append(
            InferredRelation(
                source_id=source[0],
                target_id=target[0],
                relation=str(raw.get("relation") or "DEPENDS_ON").upper()[:40],
                rationale=clean_rationale(raw.get("rationale"), max_length=300),
                confidence=clamp_confidence(raw.get("confidence")),
            )
        )

    for raw in (payload.get("risks") or [])[:limit]:
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        severity = str(raw.get("severity") or "medium").lower()
        result.risks.append(
            InferredRisk(
                title=title[:160],
                description=clean_rationale(raw.get("description"), max_length=400),
                severity=severity if severity in ("high", "medium", "low", "info") else "medium",
                node_ids=filter_references(raw.get("node_ids") or [], allowed, dropped),
                confidence=clamp_confidence(raw.get("confidence")),
            )
        )

    result.dropped_references = dropped
    if dropped:
        result.warnings.append(
            f"{len(dropped)} reference(s) pointed at nodes that do not exist and were discarded."
        )
    return result


def _parse_answer(
    payload: dict[str, Any],
    request: GraphQuestionRequest,
    kind: ProviderKind,
    model: str,
    call: StructuredCall,
) -> GraphAnswer:
    allowed = set(request.context.allowed_node_ids)
    dropped: list[str] = []
    highlighted = filter_references(payload.get("highlighted_node_ids") or [], allowed, dropped, limit=120)
    path = filter_references(payload.get("path") or [], allowed, dropped, limit=40)

    evidence: list[AnswerEvidence] = []
    for raw in payload.get("evidence") or []:
        if not isinstance(raw, dict):
            continue
        node_ids = filter_references([raw.get("node_id")], allowed, dropped)
        if not node_ids:
            continue
        evidence.append(
            AnswerEvidence(
                node_id=node_ids[0],
                why=clean_rationale(raw.get("why"), max_length=240),
            )
        )

    answer_text = clean_rationale(payload.get("answer"), max_length=1200)
    return GraphAnswer(
        provider=kind,
        model=model,
        answer=answer_text or "The model returned no answer.",
        technical_explanation=clean_rationale(payload.get("technical_explanation"), max_length=2000),
        highlighted_node_ids=highlighted,
        path=path,
        evidence=evidence,
        inference_note=clean_rationale(payload.get("inference_note"), max_length=400),
        confidence=clamp_confidence(payload.get("confidence")),
        coverage=round(len(highlighted) / max(1, len(allowed)), 3),
        dropped_references=dropped,
        latency_ms=call.latency_ms,
        input_tokens=call.input_tokens,
        output_tokens=call.output_tokens,
        # An answer with no surviving citation is not grounded, however fluent it reads.
        grounded=bool(highlighted or not answer_text),
    )


def _parse_repairs(
    payload: dict[str, Any],
    request: RepairRequest,
    kind: ProviderKind,
    model: str,
    call: StructuredCall,
) -> RepairProposal:
    allowed = set(request.context.allowed_node_ids) | set(request.broken_node_ids)
    dropped: list[str] = []
    repairs: list[ProposedRepair] = []
    for raw in (payload.get("repairs") or [])[:8]:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        repair_kind = str(raw.get("kind") or "semantic_mapping")
        if repair_kind not in ALLOWED_REPAIR_KINDS:
            repair_kind = "semantic_mapping"
        repairs.append(
            ProposedRepair(
                title=title[:160],
                rationale=clean_rationale(raw.get("rationale"), max_length=600),
                kind=repair_kind,
                target_ids=filter_references(raw.get("target_ids") or [], allowed, dropped, limit=12),
                confidence=clamp_confidence(raw.get("confidence")),
                migration_steps=[
                    clean_rationale(step, max_length=240)
                    for step in (raw.get("migration_steps") or [])[:8]
                ],
            )
        )
    return RepairProposal(
        provider=kind,
        model=model,
        repairs=repairs,
        latency_ms=call.latency_ms,
        input_tokens=call.input_tokens,
        output_tokens=call.output_tokens,
        dropped_references=dropped,
    )
