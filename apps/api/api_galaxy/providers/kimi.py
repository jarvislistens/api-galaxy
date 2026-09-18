"""Kimi adapter — the optional external provider.

Everything about this class is built around one rule: **nothing leaves the machine
without the user having seen it and agreed.** The adapter therefore refuses to send
anything unless it is handed an explicit consent token, and the payload it sends has
already been through :mod:`api_galaxy.providers.sanitizer`.

The API is OpenAI-compatible, so the transport is a plain ``/chat/completions`` call.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from api_galaxy.contracts.providers import (
    EnrichmentRequest,
    EnrichmentResult,
    GraphAnswer,
    GraphQuestionRequest,
    ProviderHealth,
    ProviderKind,
    ProviderStatus,
    RepairProposal,
    RepairRequest,
)
from api_galaxy.providers.base import ProviderError, StructuredCall
from api_galaxy.providers.ollama import _parse_answer, _parse_enrichment, _parse_repairs
from api_galaxy.providers.prompts import (
    ANSWER_SCHEMA,
    ENRICHMENT_SCHEMA,
    REPAIR_SCHEMA,
    answer_prompt,
    enrichment_prompt,
    repair_prompt,
)
from api_galaxy.providers.sanitizer import sanitize_text

DEFAULT_BASE_URL = "https://api.moonshot.ai/v1"
DEFAULT_MODEL = "kimi-k2-0905-preview"
DEFAULT_TIMEOUT = 120.0

SYSTEM_PROMPT = (
    "You are an API analysis assistant. You always reply with a single valid JSON object "
    "and nothing else. You never invent identifiers that were not given to you."
)


class ConsentRequired(PermissionError):
    """Raised when an external call is attempted without recorded consent."""

    def __init__(self, project_id: str) -> None:
        super().__init__(
            "Sending data to Kimi needs explicit consent for this project. "
            "Open the request preview and approve it first."
        )
        self.project_id = project_id


class KimiProvider:
    kind = ProviderKind.KIMI

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        enabled: bool = True,
        consent: ConsentStore | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.enabled = enabled
        self.consent = consent

    # ------------------------------------------------------------------- health

    async def health(self) -> ProviderHealth:
        if not self.enabled:
            return ProviderHealth(
                kind=self.kind,
                status=ProviderStatus.DISABLED,
                model=self.model,
                base_url=self.base_url,
                external=True,
                detail="External providers are switched off globally.",
                setup_hint="Enable external providers in Settings → Privacy.",
            )
        if not self.api_key:
            return ProviderHealth(
                kind=self.kind,
                status=ProviderStatus.NOT_CONFIGURED,
                model=self.model,
                base_url=self.base_url,
                external=True,
                detail="No API key is configured.",
                setup_hint="Add a Kimi API key in Settings → Providers. It is stored in "
                "your OS keychain when available, and only in memory otherwise.",
            )
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.HTTPError as exc:
            return ProviderHealth(
                kind=self.kind,
                status=ProviderStatus.UNREACHABLE,
                model=self.model,
                base_url=self.base_url,
                external=True,
                detail=f"Could not reach {self.base_url}: {type(exc).__name__}.",
                setup_hint="Check your network and the base URL.",
            )
        if response.status_code in (401, 403):
            return ProviderHealth(
                kind=self.kind,
                status=ProviderStatus.NOT_CONFIGURED,
                model=self.model,
                base_url=self.base_url,
                external=True,
                detail="The API key was rejected.",
                setup_hint="Check the key in Settings → Providers.",
            )
        if response.status_code >= 400:
            return ProviderHealth(
                kind=self.kind,
                status=ProviderStatus.ERROR,
                model=self.model,
                base_url=self.base_url,
                external=True,
                detail=f"The endpoint returned HTTP {response.status_code}.",
            )
        models: list[str] = []
        try:
            models = [str(m.get("id")) for m in response.json().get("data", []) if m.get("id")]
        except ValueError:
            pass
        return ProviderHealth(
            kind=self.kind,
            status=ProviderStatus.READY,
            model=self.model,
            base_url=self.base_url,
            external=True,
            detail="Ready. Every request still requires per-project consent.",
            available_models=models,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    # ------------------------------------------------------------------ transport

    def _require_consent(self, project_id: str) -> None:
        if not self.enabled:
            raise ProviderError(self.kind, "External providers are disabled in Settings.")
        if not self.api_key:
            raise ProviderError(
                self.kind,
                "No Kimi API key is configured.",
                hint="Add one in Settings → Providers.",
            )
        if self.consent is not None and not self.consent.has_consent(project_id):
            raise ConsentRequired(project_id)

    async def _chat(self, prompt: str, feedback: str | None) -> tuple[str, dict[str, Any]]:
        # The prompt is redacted one final time at the wire, independently of whatever the
        # caller did. Defence in depth: a new call site cannot accidentally leak.
        content = prompt if feedback is None else f"{prompt}\n\nCORRECTION: {feedback}"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": sanitize_text(content)},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(self.kind, f"Kimi did not respond within {self.timeout:.0f}s.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(self.kind, f"Kimi request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text[:300]
            raise ProviderError(
                self.kind,
                f"Kimi returned HTTP {response.status_code}.",
                hint=detail,
            )
        payload = response.json()
        choices = payload.get("choices") or []
        text = ""
        if choices and isinstance(choices[0], dict):
            text = str((choices[0].get("message") or {}).get("content") or "")
        usage = payload.get("usage") or {}
        return text, {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
        }

    # -------------------------------------------------------------------- tasks

    async def enrich(self, request: EnrichmentRequest) -> EnrichmentResult:
        self._require_consent(request.project_id)
        prompt = enrichment_prompt(request.context, max_items=request.max_items)
        call = StructuredCall(self.kind, ENRICHMENT_SCHEMA)
        payload = await call.run(lambda feedback: self._chat(prompt, feedback))
        return _parse_enrichment(payload, request, self.kind, self.model, call)

    async def answer(self, request: GraphQuestionRequest) -> GraphAnswer:
        self._require_consent(request.project_id)
        prompt = answer_prompt(request.context, request.question)
        call = StructuredCall(self.kind, ANSWER_SCHEMA)
        payload = await call.run(lambda feedback: self._chat(prompt, feedback))
        return _parse_answer(payload, request, self.kind, self.model, call)

    async def propose_repairs(self, request: RepairRequest) -> RepairProposal:
        self._require_consent(request.project_id)
        prompt = repair_prompt(
            request.context,
            request.change_summaries,
            request.broken_node_ids,
            request.broken_journeys,
        )
        call = StructuredCall(self.kind, REPAIR_SCHEMA)
        payload = await call.run(lambda feedback: self._chat(prompt, feedback))
        return _parse_repairs(payload, request, self.kind, self.model, call)


class ConsentStore:
    """Per-project consent for external calls, with an optional 'remember' flag.

    Consent is deliberately *per project*: agreeing to send NovaCart's public sample
    specification says nothing about agreeing to send your employer's internal one.
    """

    def __init__(self) -> None:
        self._granted: dict[str, dict[str, Any]] = {}

    def has_consent(self, project_id: str) -> bool:
        return bool(self._granted.get(project_id, {}).get("granted"))

    def grant(self, project_id: str, *, remember: bool, fingerprint: str = "") -> None:
        self._granted[project_id] = {
            "granted": True,
            "remember": remember,
            "fingerprint": fingerprint,
            "at": time.time(),
        }

    def revoke(self, project_id: str) -> None:
        self._granted.pop(project_id, None)

    def clear(self) -> None:
        self._granted.clear()

    def state(self, project_id: str) -> dict[str, Any]:
        record = self._granted.get(project_id)
        return {
            "granted": bool(record and record.get("granted")),
            "remembered": bool(record and record.get("remember")),
        }
