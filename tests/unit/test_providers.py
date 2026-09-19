"""Provider response validation, ID whitelisting, sanitisation and the Model Arena."""

from __future__ import annotations

import pytest
from api_galaxy.contracts.graph import EdgeType
from api_galaxy.contracts.providers import (
    EnrichmentRequest,
    EnrichmentResult,
    GraphQuestionRequest,
    ProviderKind,
)
from api_galaxy.providers import (
    ComparisonService,
    DeterministicProvider,
    build_context,
    context_for_question,
    extract_json,
    filter_references,
    sanitize,
    sanitize_text,
    validate_against,
)
from api_galaxy.providers.base import SchemaViolation, StructuredCall, clean_rationale
from api_galaxy.providers.cache import CacheKey, ResultCache
from api_galaxy.providers.comparison import ArenaRun, PricingBook
from api_galaxy.providers.kimi import ConsentRequired, ConsentStore, KimiProvider
from api_galaxy.providers.ollama import _parse_answer, _parse_enrichment
from api_galaxy.providers.prompts import ANSWER_SCHEMA, ENRICHMENT_SCHEMA

# --------------------------------------------------------------------------------------
# JSON extraction and validation
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        '{"a": 1}',
        'Sure! Here is the JSON:\n```json\n{"a": 1}\n```',
        'Here you go: {"a": 1} — hope that helps.',
        '```\n{"a": 1}\n```',
    ],
)
def test_json_survives_the_wrappers_small_models_add(raw):
    assert extract_json(raw) == {"a": 1}


def test_unparseable_output_raises_with_a_reason():
    with pytest.raises(ValueError, match="not valid JSON"):
        extract_json("I am afraid I cannot do that.")


def test_schema_validation_catches_shape_errors():
    schema = {
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {"type": "array", "items": {"type": "object",
                                                 "required": ["name"],
                                                 "properties": {"name": {"type": "string"}}}},
            "score": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }
    validate_against(schema, {"items": [{"name": "ok"}], "score": 0.5})

    with pytest.raises(SchemaViolation, match="missing required key 'items'"):
        validate_against(schema, {})
    with pytest.raises(SchemaViolation, match=r"expected a string"):
        validate_against(schema, {"items": [{"name": 3}]})
    with pytest.raises(SchemaViolation, match="above the maximum"):
        validate_against(schema, {"items": [], "score": 4})


async def test_structured_call_retries_with_feedback_then_gives_up():
    attempts: list[str | None] = []

    async def always_bad(feedback):
        attempts.append(feedback)
        return "not json at all", {}

    call = StructuredCall(ProviderKind.OLLAMA, {"type": "object"})
    with pytest.raises(Exception, match="did not return valid structured output"):
        await call.run(always_bad)
    assert len(attempts) == 3, "one attempt plus two bounded retries"
    assert attempts[0] is None
    assert "could not be used" in (attempts[1] or "")


async def test_structured_call_accepts_a_late_success():
    responses = iter(["garbage", '{"ok": true}'])

    async def sometimes(feedback):  # noqa: ARG001
        return next(responses), {"input_tokens": 10, "output_tokens": 4}

    call = StructuredCall(ProviderKind.OLLAMA, {"type": "object"})
    assert await call.run(sometimes) == {"ok": True}
    assert call.retries == 1
    assert call.input_tokens == 10


# --------------------------------------------------------------------------------------
# Reference whitelisting — the anti-hallucination guarantee
# --------------------------------------------------------------------------------------


def test_invented_ids_are_dropped_and_counted():
    dropped: list[str] = []
    kept = filter_references(["real:1", "made:up", "real:2", "made:up"], {"real:1", "real:2"},
                             dropped)
    assert kept == ["real:1", "real:2"]
    assert dropped == ["made:up"]


def test_enrichment_parsing_discards_unknown_node_ids(novacart):
    context = build_context(novacart.graph)
    request = EnrichmentRequest(project_id="p", context=context)
    payload = {
        "entities": [{"name": "Customer", "represented_by": ["schema:customer-api:Customer",
                                                             "schema:ghost-api:Ghost"]}],
        "domains": [],
        "journeys": [],
        "aliases": [{"canonical_name": "customer",
                     "member_ids": ["field:customer-api:Customer.customer_id", "nope"]}],
        "relations": [{"source_id": "op:nowhere", "target_id": "op:nowhere-else"}],
    }
    call = StructuredCall(ProviderKind.OLLAMA, ENRICHMENT_SCHEMA)
    result = _parse_enrichment(payload, request, ProviderKind.OLLAMA, "test-model", call)

    assert result.entities[0].represented_by == ["schema:customer-api:Customer"]
    assert "schema:ghost-api:Ghost" in result.dropped_references
    assert result.relations == [], "a relation between two invented nodes cannot survive"
    assert result.warnings, "the user must be told references were discarded"


def test_an_answer_that_cites_nothing_real_is_marked_ungrounded(novacart):
    context = context_for_question(novacart.graph, "how does checkout work")
    request = GraphQuestionRequest(project_id="p", question="how does checkout work",
                                   context=context)
    call = StructuredCall(ProviderKind.OLLAMA, ANSWER_SCHEMA)
    result = _parse_answer(
        {"answer": "It works beautifully.", "highlighted_node_ids": ["op:imaginary"]},
        request, ProviderKind.OLLAMA, "test-model", call,
    )
    assert result.grounded is False
    assert result.highlighted_node_ids == []
    assert result.dropped_references == ["op:imaginary"]


def test_hidden_reasoning_is_never_stored():
    assert clean_rationale("<think>secret chain of thought</think>Because X.") == "Because X."
    assert "secret" not in clean_rationale("<thinking>secret</thinking> visible")


# --------------------------------------------------------------------------------------
# Sanitisation
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,placeholder",
    [
        ("contact ops@novacart.example now", "[REDACTED_EMAIL]"),
        ("call +1 415 555 0134.", "[REDACTED_PHONE]"),
        ("api_key=sk-abcdef1234567890abcd", "[REDACTED_SECRET]"),
        ("Authorization: Bearer abcdefghijklmnop1234", "[REDACTED_BEARER]"),
        ("see http://10.0.0.5:8080/internal", "[REDACTED_INTERNAL_URL]"),
        ("AKIAIOSFODNN7EXAMPLE", "[REDACTED_AWS_KEY]"),
        ("card 4111 1111 1111 1111", "[REDACTED_CARD]"),
    ],
)
def test_every_redaction_rule_fires(raw, placeholder):
    assert placeholder in sanitize_text(raw)


def test_secrets_never_survive_sanitisation():
    payload = {
        "description": "Ping ops@novacart.example with token=sk-abcdef1234567890abcd",
        "servers": [{"url": "https://api.novacart.example"}],
        "example": {"customer_id": "cus_123"},
        "nested": {"password": "hunter2"},
    }
    cleaned, report = sanitize(payload)
    text = str(cleaned)
    assert "ops@novacart.example" not in text
    assert "sk-abcdef1234567890abcd" not in text
    assert "servers" not in cleaned, "server declarations describe your network"
    assert "example" not in cleaned
    assert report.total_redactions >= 1
    assert "Removed" in report.summary()


def test_sanitisation_report_is_specific_enough_to_show_a_user():
    _, report = sanitize({"a": "mail me at x@y.example"})
    assert report.removed.get("email") == 1
    assert "personal data" in report.reasons["email"].lower()


# --------------------------------------------------------------------------------------
# Consent
# --------------------------------------------------------------------------------------


async def test_kimi_refuses_to_send_without_consent(novacart):
    provider = KimiProvider(api_key="test-key", consent=ConsentStore())
    request = EnrichmentRequest(project_id="p", context=build_context(novacart.graph))
    with pytest.raises(ConsentRequired):
        await provider.enrich(request)


async def test_kimi_consent_is_per_project(novacart):
    store = ConsentStore()
    store.grant("project-a", remember=False)
    provider = KimiProvider(api_key="test-key", consent=store)

    assert store.has_consent("project-a") is True
    assert store.has_consent("project-b") is False
    request = EnrichmentRequest(project_id="project-b", context=build_context(novacart.graph))
    with pytest.raises(ConsentRequired):
        await provider.enrich(request)


async def test_disabled_external_providers_report_it_rather_than_failing_obscurely():
    health = await KimiProvider(api_key="k", enabled=False).health()
    assert health.status.value == "disabled"
    assert health.ready is False
    assert "Settings" in health.setup_hint


async def test_missing_key_is_a_configuration_state_not_an_error():
    health = await KimiProvider(api_key=None).health()
    assert health.status.value == "not_configured"
    assert "keychain" in health.setup_hint


# --------------------------------------------------------------------------------------
# Deterministic provider — the zero-setup guarantee
# --------------------------------------------------------------------------------------


async def test_deterministic_provider_is_always_ready():
    health = await DeterministicProvider().health()
    assert health.ready is True and health.external is False


@pytest.mark.parametrize(
    "question,expected",
    [
        ("How does checkout work?", "Place Order"),
        ("Show me the shipping flow", "Create Shipment"),
    ],
)
async def test_deterministic_answers_find_the_right_journey(novacart, question, expected):
    provider = DeterministicProvider(novacart.graph)
    answer = await provider.answer(
        GraphQuestionRequest(project_id="p", question=question,
                             context=context_for_question(novacart.graph, question))
    )
    assert expected in answer.answer
    assert answer.highlighted_node_ids and answer.path


async def test_deterministic_dependency_answer_surfaces_the_aliases(novacart):
    provider = DeterministicProvider(novacart.graph)
    question = "What depends on customer_id?"
    answer = await provider.answer(
        GraphQuestionRequest(project_id="p", question=question,
                             context=context_for_question(novacart.graph, question))
    )
    assert "cust_no" in answer.answer and "party_key" in answer.answer
    assert "not statements in the specification" in answer.inference_note


async def test_deterministic_pii_answer_names_the_unauthenticated_endpoint(novacart):
    provider = DeterministicProvider(novacart.graph)
    question = "Which endpoints touch customer data?"
    answer = await provider.answer(
        GraphQuestionRequest(project_id="p", question=question,
                             context=context_for_question(novacart.graph, question))
    )
    assert "no authentication" in answer.answer
    assert "/public/customers" in answer.answer


async def test_deterministic_answers_only_ever_cite_real_nodes(novacart):
    provider = DeterministicProvider(novacart.graph)
    ids = novacart.graph.node_ids()
    for question in ["How does checkout work?", "What depends on customer_id?",
                     "Which concepts have conflicting definitions?", "What looks risky?"]:
        answer = await provider.answer(
            GraphQuestionRequest(project_id="p", question=question,
                                 context=context_for_question(novacart.graph, question))
        )
        assert set(answer.highlighted_node_ids) <= ids
        assert {e.node_id for e in answer.evidence} <= ids


# --------------------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------------------


def test_context_is_bounded_and_carries_a_whitelist(novacart):
    context = build_context(novacart.graph, max_operations=10, max_schemas=8)
    assert len(context.operations) <= 10
    assert len(context.schemas) <= 8
    assert context.allowed_node_ids
    assert set(context.allowed_node_ids) <= novacart.graph.node_ids()


def test_question_context_retrieves_the_relevant_slice(novacart):
    context = context_for_question(novacart.graph, "payment authorization")
    ids = " ".join(context.allowed_node_ids)
    assert "payment-api" in ids
    assert len(context.allowed_node_ids) < len(novacart.graph.nodes)


# --------------------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------------------


def test_cache_key_changes_when_any_part_of_provenance_changes():
    base = dict(spec_fingerprint="sha256:a", context_fingerprint="c", provider="ollama",
                model="qwen3:4b", prompt_template_version="1", task="answer")
    original = CacheKey(**base).digest()
    for field in base:
        altered = {**base, field: base[field] + "-changed"}
        assert CacheKey(**altered).digest() != original, f"{field} must affect the cache key"


def test_cache_hit_and_miss_accounting():
    cache = ResultCache()
    key = CacheKey("f", "c", "ollama", "m", "1", "answer")
    assert cache.get(key) is None
    cache.put(key, {"answer": "x"})
    assert cache.get(key) == {"answer": "x"}
    stats = cache.stats()
    assert stats["hits"] == 1 and stats["misses"] == 1 and stats["entries"] == 1


# --------------------------------------------------------------------------------------
# Model Arena
# --------------------------------------------------------------------------------------


def _result(provider: ProviderKind, relations, *, dropped=0, tokens=(100, 50)) -> EnrichmentResult:
    from api_galaxy.contracts.providers import InferredRelation

    return EnrichmentResult(
        provider=provider,
        model=f"{provider.value}-model",
        relations=[InferredRelation(source_id=s, target_id=t, relation=r, confidence=c)
                   for s, t, r, c in relations],
        dropped_references=["ghost"] * dropped,
        input_tokens=tokens[0],
        output_tokens=tokens[1],
    )


def test_arena_separates_consensus_conflict_and_exclusives():
    service = ComparisonService(PricingBook())
    a = ArenaRun(ProviderKind.OLLAMA,
                 _result(ProviderKind.OLLAMA,
                         [("x", "y", "DEPENDS_ON", 0.8), ("p", "q", "ALIAS_OF", 0.6),
                          ("only", "a", "DEPENDS_ON", 0.5)]))
    b = ArenaRun(ProviderKind.KIMI,
                 _result(ProviderKind.KIMI,
                         [("x", "y", "DEPENDS_ON", 0.9), ("p", "q", "DEPENDS_ON", 0.7),
                          ("only", "b", "DEPENDS_ON", 0.5)], dropped=2))

    comparison = service.compare([a, b], project_id="p")
    assert [r.source_id for r in comparison.consensus] == ["x"]
    assert [r.source_id for r in comparison.conflicts] == ["p"]
    assert [r.target_id for r in comparison.only_a] == ["a"]
    assert [r.target_id for r in comparison.only_b] == ["b"]

    conflict = comparison.conflicts[0]
    assert conflict.rationales.keys() == {"ollama", "kimi"}

    kimi_metrics = next(m for m in comparison.metrics if m.provider is ProviderKind.KIMI)
    assert kimi_metrics.hallucinated_references == 2
    assert any("Invented references" in note for note in comparison.notes)


def test_arena_is_honest_when_only_one_provider_answered():
    service = ComparisonService(PricingBook())
    ok = ArenaRun(ProviderKind.OLLAMA, _result(ProviderKind.OLLAMA, [("x", "y", "DEPENDS_ON", 1)]))
    failed = ArenaRun(ProviderKind.KIMI, None, error="ConnectError: unreachable")

    comparison = service.compare([ok, failed], project_id="p")
    assert any("nothing to compare" in note for note in comparison.notes)
    metrics = next(m for m in comparison.metrics if m.provider is ProviderKind.KIMI)
    assert metrics.ok is False and "unreachable" in metrics.error


def test_pricing_is_editable_and_stamped():
    book = PricingBook()
    shipped = book.get(ProviderKind.KIMI)
    assert "EXAMPLE" in shipped.note.upper()
    assert shipped.updated_by == "app"

    updated = book.set("kimi", input_per_million=1.0, output_per_million=3.0)
    assert updated.updated_by == "local-user"
    assert book.get("kimi").cost(1_000_000, 1_000_000) == 4.0


def test_local_providers_cost_nothing():
    book = PricingBook()
    assert book.get(ProviderKind.OLLAMA).cost(10_000_000, 10_000_000) == 0.0
    assert book.get(ProviderKind.DETERMINISTIC).cost(None, None) is None


async def test_arena_runs_both_providers_and_survives_one_failing(novacart):
    class Exploding:
        kind = ProviderKind.KIMI

        async def enrich(self, request):  # noqa: ARG002
            raise RuntimeError("boom")

    service = ComparisonService(PricingBook())
    comparison = await service.run(
        [DeterministicProvider(novacart.graph), Exploding()],
        EnrichmentRequest(project_id="p", context=build_context(novacart.graph)),
    )
    assert len(comparison.metrics) == 2
    assert [m.ok for m in comparison.metrics] == [True, False]
    assert "boom" in comparison.metrics[1].error


async def test_a_scoped_arena_run_is_actually_scoped(novacart):
    """Both sides of a comparison must see the same slice.

    The deterministic provider reads the graph directly rather than a prompt, so unlike a
    model it *can* answer beyond its context — and it did, reporting all seven domains
    and every DEPENDS_ON edge in the estate while its opponent had been handed one
    domain. Every scoped comparison was quietly rigged in its favour.
    """
    graph = novacart.graph
    customer_nodes = {
        edge.source
        for edge in graph.edges
        if edge.type is EdgeType.BELONGS_TO_DOMAIN and edge.target == "domain:customer"
    } | {"domain:customer"}
    # Pull in what those nodes own, the way the arena route builds its scope.
    for edge in graph.edges:
        if edge.source in customer_nodes:
            customer_nodes.add(edge.target)

    scoped = build_context(graph, node_ids=customer_nodes, chunk_label="domain: Customer")

    # The context must not hand out IDs from outside the slice.
    assert "domain:customer" in scoped.allowed_node_ids
    assert "domain:payment" not in scoped.allowed_node_ids
    assert scoped.existing_domains == ["Customer"]

    scoped_result = await DeterministicProvider(graph).enrich(
        EnrichmentRequest(project_id="p", context=scoped)
    )
    whole = await DeterministicProvider(graph).enrich(
        EnrichmentRequest(project_id="p", context=build_context(graph))
    )

    assert [d.name for d in scoped_result.domains] == ["Customer"]
    assert len(whole.domains) > len(scoped_result.domains)
    # Nothing it reports may reference a node the opponent never saw.
    allowed = set(scoped.allowed_node_ids)
    for relation in scoped_result.relations:
        assert relation.source_id in allowed and relation.target_id in allowed
    for alias in scoped_result.aliases:
        assert set(alias.member_ids) <= allowed
    for journey in scoped_result.journeys:
        assert set(journey.operation_ids) <= allowed
