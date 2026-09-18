"""Ask mode.

The rule this module exists to enforce: a model never answers from memory. We retrieve a
bounded slice of the graph, hand it over with an explicit ID whitelist, validate the
response, discard every reference that does not exist, and then stitch the surviving IDs
into a path the graph can actually light up. An answer with no surviving citation is
returned with ``grounded: false`` and the UI says so.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api_galaxy.app.errors import NotFoundError, ProviderUnavailableError
from api_galaxy.app.state import get_state
from api_galaxy.contracts.graph import EdgeType, NodeType
from api_galaxy.contracts.providers import GraphQuestionRequest, ProviderKind
from api_galaxy.graph.engine import NetworkXGraphRepository
from api_galaxy.providers.base import ProviderError
from api_galaxy.providers.cache import CacheKey
from api_galaxy.providers.context import context_for_question
from api_galaxy.providers.kimi import ConsentRequired
from api_galaxy.providers.prompts import PROMPT_TEMPLATE_VERSION

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["ask"])

STARTERS = [
    "How does checkout work?",
    "Which endpoints touch customer data?",
    "Where is payment information used?",
    "What depends on customer_id?",
    "Which concepts have conflicting definitions?",
]


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    provider: str = ProviderKind.DETERMINISTIC.value
    scenario_id: str | None = None
    refresh: bool = False


@router.get("/ask/starters")
async def starters(project_id: str) -> dict[str, Any]:  # noqa: ARG001
    return {"starters": STARTERS}


@router.post("/ask")
async def ask(project_id: str, payload: AskRequest) -> dict[str, Any]:
    state = get_state()
    live = state.get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")

    graph = live.graph
    if payload.scenario_id:
        from api_galaxy.analysis.impact import apply_changes

        scenario = live.scenarios.get(payload.scenario_id)
        if scenario is None:
            raise NotFoundError(f"No scenario with id '{payload.scenario_id}'.")
        graph = apply_changes(live.graph, scenario)

    try:
        kind = ProviderKind(payload.provider)
    except ValueError as exc:
        raise ProviderUnavailableError(f"'{payload.provider}' is not a known provider.") from exc

    context = context_for_question(graph, payload.question)
    started = time.perf_counter()

    cache_key = CacheKey(
        spec_fingerprint=graph.spec_fingerprint,
        context_fingerprint=f"q:{payload.question.strip().lower()}|s:{payload.scenario_id or ''}",
        provider=kind.value,
        model=_model_for(state, kind),
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        task="answer",
    )
    if not payload.refresh:
        cached = state.cache.get(cache_key)
        if cached is not None:
            return {**cached, "cached": True}

    provider = state.provider(kind, graph)
    request = GraphQuestionRequest(
        project_id=project_id,
        question=payload.question,
        context=context,
        scenario_id=payload.scenario_id,
    )
    try:
        answer = await provider.answer(request)
    except ConsentRequired as exc:
        from api_galaxy.app.errors import ConsentMissingError

        raise ConsentMissingError(str(exc), project_id=project_id) from exc
    except ProviderError as exc:
        raise ProviderUnavailableError(exc.message, hint=exc.hint) from exc

    index = graph.node_index()
    highlighted = [node_id for node_id in answer.highlighted_node_ids if node_id in index]
    repo = NetworkXGraphRepository(graph)
    path = [node_id for node_id in answer.path if node_id in index]
    if not path and len(highlighted) > 1:
        path = repo.evidence_path(highlighted[:6])

    edge_ids = [
        e.id
        for e in graph.edges
        if e.source in set(highlighted) and e.target in set(highlighted)
    ]

    evidence = []
    for item in answer.evidence:
        node = index.get(item.node_id)
        if node is None:
            continue
        evidence.append(
            {
                "node_id": item.node_id,
                "label": node.label,
                "type": node.type.value,
                "why": item.why,
                "is_fact": node.is_fact,
                "source": [e.locator for e in node.evidence[:2]],
                "service": node.attrs.get("service"),
            }
        )

    fact_count = sum(1 for e in evidence if e["is_fact"])
    payload_out = {
        "question": payload.question,
        "provider": kind.value,
        "model": answer.model,
        "answer": answer.answer,
        "technical_explanation": answer.technical_explanation,
        "highlighted_node_ids": highlighted,
        "highlighted_edge_ids": edge_ids,
        "path": path,
        "path_labels": [index[n].label for n in path if n in index],
        "evidence": evidence,
        "inference_note": answer.inference_note,
        "fact_vs_inference": {
            "facts": fact_count,
            "inferences": len(evidence) - fact_count,
        },
        "confidence": answer.confidence,
        "coverage": answer.coverage,
        "grounded": answer.grounded and bool(highlighted),
        "dropped_references": answer.dropped_references,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "input_tokens": answer.input_tokens,
        "output_tokens": answer.output_tokens,
        "scenario_id": payload.scenario_id,
        "cached": False,
    }
    if not payload_out["grounded"]:
        payload_out["warning"] = (
            "This answer cites nothing that exists in the graph, so treat it as unverified. "
            "Try rephrasing, or switch to the local deterministic provider."
        )
    if answer.dropped_references:
        payload_out["warning"] = (
            f"{len(answer.dropped_references)} reference(s) the model produced do not exist "
            "and were discarded before this answer was shown."
        )

    state.cache.put(cache_key, payload_out)
    return payload_out


@router.get("/ask/context-preview")
async def context_preview(project_id: str, question: str) -> dict[str, Any]:
    """What would be sent for this question. Backs the 'show me what you send' control."""
    live = get_state().get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    context = context_for_question(live.graph, question)
    return {
        "chunk_label": context.chunk_label,
        "services": len(context.services),
        "operations": len(context.operations),
        "schemas": len(context.schemas),
        "allowed_ids": len(context.allowed_node_ids),
        "sample_ids": context.allowed_node_ids[:20],
    }


def _model_for(state, kind: ProviderKind) -> str:
    values = state.provider_settings()
    if kind is ProviderKind.OLLAMA:
        return str(values["ollama_model"])
    if kind is ProviderKind.KIMI:
        return str(values["kimi_model"])
    return "deterministic-v1"


@router.get("/concepts")
async def concepts(project_id: str) -> dict[str, Any]:
    """Business entities and capabilities — the non-technical view of the estate."""
    live = get_state().get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    graph = live.graph
    index = graph.node_index()

    def represented(node_id: str) -> list[dict[str, str]]:
        return [
            {"id": e.source, "label": index[e.source].label, "type": index[e.source].type.value}
            for e in graph.edges
            if e.type is EdgeType.REPRESENTS and e.target == node_id and e.source in index
        ]

    return {
        "entities": [
            {
                **node.model_dump(mode="json"),
                "represented_by": represented(node.id),
            }
            for node in graph.nodes_of(NodeType.BUSINESS_ENTITY)
        ],
        "capabilities": [
            {
                **node.model_dump(mode="json"),
                "operations": [
                    {"id": e.target, "label": index[e.target].label}
                    for e in graph.edges
                    if e.type is EdgeType.CONTAINS and e.source == node.id and e.target in index
                    and index[e.target].type is NodeType.API_OPERATION
                ],
            }
            for node in graph.nodes_of(NodeType.CAPABILITY)
        ],
        "alias_clusters": [c.model_dump(mode="json") for c in live.analysed.alias_clusters],
    }
