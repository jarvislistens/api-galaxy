"""Graph construction, provenance, risk rules, aliases, journeys and impact."""

from __future__ import annotations

import pytest
from api_galaxy.analysis import (
    apply_changes,
    compute_impact,
    detect_alias_clusters,
    propose_deterministic_repairs,
    validate_all,
    validate_journey,
)
from api_galaxy.analysis.pii import DEFAULT_DICTIONARY
from api_galaxy.contracts.graph import Acceptance, EdgeType, NodeType, SourceKind
from api_galaxy.contracts.scenario import Change, ChangeKind, ImpactStatus, RepairStatus, Scenario
from api_galaxy.graph.engine import NetworkXGraphRepository, QueryLimits, diff_graphs

CUSTOMER_ID = "field:customer-api:Customer.customer_id"


# --------------------------------------------------------------------------------------
# Graph and provenance
# --------------------------------------------------------------------------------------


def test_every_node_and_edge_carries_provenance(novacart):
    """The rule the whole product rests on: nothing enters the graph anonymously."""
    for node in novacart.graph.nodes:
        assert node.provenance.explanation, f"{node.id} has no explanation"
        assert node.provenance.source_kind is not None
    for edge in novacart.graph.edges:
        assert edge.provenance.explanation, f"{edge.id} has no explanation"


def test_specification_nodes_cite_a_file_and_pointer(novacart):
    operations = novacart.graph.nodes_of(NodeType.API_OPERATION)
    assert operations
    for node in operations:
        assert node.provenance.source_kind is SourceKind.SPECIFICATION
        assert node.provenance.source_file
        assert node.provenance.source_pointer
        assert node.evidence, f"{node.id} has no evidence"


def test_facts_and_inferences_are_never_merged(novacart):
    """An alias edge is a suggestion; it must not be recorded as observed."""
    alias_edges = novacart.graph.edges_of(EdgeType.ALIAS_OF)
    assert alias_edges
    assert all(edge.acceptance is Acceptance.PROPOSED for edge in alias_edges)
    assert all(edge.stroke in ("dashed", "dotted") for edge in alias_edges)

    # Specification-sourced structure is solid. Note that CONTAINS is also used by the
    # bundled analysis to group operations under a capability — that is an inference and
    # is correctly dashed, so the assertion is scoped by source kind rather than by type.
    structural = [
        e for e in novacart.graph.edges_of(EdgeType.CONTAINS)
        if e.provenance.source_kind is SourceKind.SPECIFICATION
    ]
    assert structural
    assert all(edge.stroke == "solid" for edge in structural)
    assert all(edge.acceptance is Acceptance.OBSERVED for edge in structural)


def test_ids_are_stable_across_reruns():
    from api_galaxy.pipeline import analyse_manifest
    from tests.conftest import NOVACART_MANIFEST

    first = analyse_manifest(NOVACART_MANIFEST, project_id="stable-a")
    second = analyse_manifest(NOVACART_MANIFEST, project_id="stable-b")
    assert {n.id for n in first.graph.nodes} == {n.id for n in second.graph.nodes}
    assert {e.id for e in first.graph.edges} == {e.id for e in second.graph.edges}
    assert first.fingerprint == second.fingerprint


def test_expected_counts_for_the_sample_estate(novacart):
    stats = novacart.graph.stats()
    assert stats.services == 7
    assert stats.operations == 32
    assert stats.domains == 7
    assert stats.journeys == 6
    # Tolerances, not exact equality: these move when the sample gains a field.
    assert 25 <= stats.schemas <= 40
    assert 150 <= stats.fields <= 220
    assert stats.observed_edges > stats.inferred_edges > 0


# --------------------------------------------------------------------------------------
# Traversal
# --------------------------------------------------------------------------------------


def test_traversal_respects_its_limits(novacart):
    repo = NetworkXGraphRepository(novacart.graph)
    result = repo.neighbors(CUSTOMER_ID, depth=6, limits=QueryLimits(max_depth=6, max_nodes=10))
    assert len(result.nodes) <= 10
    assert result.truncated is True
    assert result.truncation_reason


def test_shortest_path_between_two_services(novacart):
    repo = NetworkXGraphRepository(novacart.graph)
    path = repo.shortest_path("svc:cart-api", "svc:payment-api")
    assert path and path[0] == "svc:cart-api" and path[-1] == "svc:payment-api"


def test_dependents_returns_a_chain_starting_at_the_target(novacart):
    repo = NetworkXGraphRepository(novacart.graph)
    dependents = repo.dependents(CUSTOMER_ID, limits=QueryLimits(max_depth=3))
    assert dependents
    for node_id, distance, chain in dependents:
        assert chain[0] == CUSTOMER_ID
        assert chain[-1] == node_id
        assert len(chain) == distance + 1


def test_cycle_detection_finds_the_deliberate_service_loop(novacart):
    titles = [r.title for r in novacart.risks if r.rule_id == "circular-dependency"]
    joined = " ".join(titles)
    assert "inventory-api" in joined and "order-api" in joined


# --------------------------------------------------------------------------------------
# Risk rules — one assertion per deliberate defect in the sample estate
# --------------------------------------------------------------------------------------


def _rule(novacart, rule_id):
    return [r for r in novacart.risks if r.rule_id == rule_id]


def test_defect_1_alias_ambiguity(novacart):
    findings = _rule(novacart, "alias-ambiguity")
    assert findings, "the three customer identifiers should be flagged"
    described = " ".join(f.description for f in findings)
    assert "customer_id" in described and "cust_no" in described and "party_key" in described


def test_defect_2_unauthenticated_sensitive_endpoint(novacart):
    findings = _rule(novacart, "unsecured-operation")
    assert any("/public/customers" in f.description for f in findings)
    assert any(f.severity.value == "high" for f in findings)


def test_defect_4_inconsistent_error_envelopes(novacart):
    findings = _rule(novacart, "inconsistent-error-model")
    assert findings and "ProblemResponse" in findings[0].description


def test_defect_5_type_change_across_a_boundary(novacart):
    findings = _rule(novacart, "type-change-across-boundary")
    amount = [f for f in findings if "amount" in f.title]
    assert amount, "total_amount (number) vs amount (string) should be flagged"
    assert "string(decimal)" in amount[0].description
    assert "number(double)" in amount[0].description


def test_defect_6_deprecated_operation_still_in_a_chain(novacart):
    findings = _rule(novacart, "deprecated-in-use")
    assert findings and "checkout" in " ".join(f.description for f in findings)


def test_defect_8_divergent_pagination(novacart):
    findings = _rule(novacart, "inconsistent-pagination")
    assert findings
    described = findings[0].description
    assert "page-size" in described and "limit-offset" in described and "cursor" in described


def test_orphaned_schema_is_found(novacart):
    assert any("LegacyPromoCode" in f.title for f in _rule(novacart, "orphaned-schema"))


def test_heuristic_rules_are_labelled_as_such(novacart):
    for risk in novacart.risks:
        if risk.rule_id in ("pii-in-schema", "alias-ambiguity", "inconsistent-pagination",
                            "type-change-across-boundary"):
            assert risk.heuristic is True, f"{risk.rule_id} must admit it is a judgement"
        if risk.rule_id in ("orphaned-schema", "inconsistent-error-model", "deprecated-in-use"):
            assert risk.heuristic is False


def test_no_broken_refs_or_duplicate_ids_in_the_sample(novacart):
    assert not _rule(novacart, "broken-ref")
    assert not _rule(novacart, "duplicate-operation-id")


# --------------------------------------------------------------------------------------
# PII dictionary
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("email", True),
        ("date_of_birth", True),
        ("dateOfBirth", True),
        ("card_last4", True),
        ("full_name", True),
        ("product_id", False),
        ("identity_provider", False),   # must not match on the bare token "id"
        ("company_name", False),        # "name" alone is not a direct identifier
    ],
)
def test_pii_dictionary_matches_on_word_boundaries(name, expected):
    assert DEFAULT_DICTIONARY.is_sensitive(name) is expected


# --------------------------------------------------------------------------------------
# Aliases
# --------------------------------------------------------------------------------------


def test_alias_detection_produces_one_clean_customer_cluster(novacart):
    clusters = novacart.alias_clusters
    assert len(clusters) == 1, "over-merging is the failure mode this guards"
    cluster = clusters[0]
    names = {label.rsplit(".", 1)[-1] for label in cluster.member_labels}
    assert names == {"customer_id", "cust_no", "party_key"}
    assert 0.6 <= cluster.confidence <= 0.95
    assert cluster.accepted is None, "an alias is never auto-accepted"


def test_anchored_identifiers_are_not_dragged_into_other_concepts(novacart):
    """`cart_id` has a `Cart` schema, so prose mentioning a customer must not move it."""
    members = {m for c in novacart.alias_clusters for m in c.member_labels}
    assert not any(label.endswith(".cart_id") for label in members)
    assert not any(label.endswith(".order_id") for label in members)


def test_alias_detection_is_empty_when_nothing_is_ambiguous():
    from api_galaxy.parsing import parse_estate

    estate = parse_estate(
        [
            (
                """
openapi: 3.0.3
info: {title: Solo, version: "1"}
paths: {}
components:
  schemas:
    Order:
      type: object
      properties:
        order_id: {type: string, description: Identifier of the order.}
""",
                "solo-api",
                None,
            )
        ],
        name="solo",
    )
    assert detect_alias_clusters(estate) == []


# --------------------------------------------------------------------------------------
# Journeys
# --------------------------------------------------------------------------------------


def test_bundled_journeys_are_curated_and_labelled(novacart):
    names = [j.name for j in novacart.journeys]
    assert names == [
        "Register Customer",
        "Search and Add Product to Cart",
        "Place Order",
        "Complete Payment",
        "Reserve Inventory",
        "Create Shipment and Track Delivery",
    ]
    assert all(j.provenance.source_kind is SourceKind.BUNDLED_ANALYSIS for j in novacart.journeys)
    assert all(j.provenance.provider == "Bundled Demo Analysis" for j in novacart.journeys)


def test_place_order_crosses_the_checkout_services(novacart):
    journey = next(j for j in novacart.journeys if j.name == "Place Order")
    index = novacart.graph.node_index()
    services = {index[s.operation_id].attrs["service"] for s in journey.steps if s.operation_id}
    assert {"cart-api", "order-api", "inventory-api", "payment-api"} <= services


def test_every_journey_validates_against_the_untouched_graph(novacart):
    for validation in validate_all(novacart.journeys, novacart.graph):
        assert validation.ok, f"{validation.journey_name}: {validation.summary}"


def test_every_journey_step_cites_evidence(novacart):
    for journey in novacart.journeys:
        for step in journey.steps:
            assert step.narration, f"{journey.name} step {step.order} has no narration"
            assert step.evidence, f"{journey.name} step {step.order} cites nothing"


# --------------------------------------------------------------------------------------
# Break Lab
# --------------------------------------------------------------------------------------


def _rename_scenario(target: str = CUSTOMER_ID, new_name: str = "party_id") -> Scenario:
    return Scenario(
        id="scn:test",
        project_id="test-novacart",
        name="Rename",
        changes=[
            Change(
                id="chg:0",
                kind=ChangeKind.RENAME_FIELD,
                target_id=target,
                params={"new_name": new_name},
                label=f"Rename to {new_name}",
            )
        ],
    )


def test_a_scenario_never_mutates_the_base_graph(novacart):
    before_nodes = len(novacart.graph.nodes)
    before_label = novacart.graph.get(CUSTOMER_ID).label
    scenario_graph = apply_changes(novacart.graph, _rename_scenario())
    assert len(novacart.graph.nodes) == before_nodes
    assert novacart.graph.get(CUSTOMER_ID).label == before_label
    assert scenario_graph.get(CUSTOMER_ID).attrs["name"] == "party_id"
    assert scenario_graph.scenario_id == "scn:test"


def test_rename_impact_classifies_and_explains(novacart):
    scenario = _rename_scenario()
    scenario_graph = apply_changes(novacart.graph, scenario)
    impact = compute_impact(novacart.graph, scenario_graph, scenario, novacart.journeys)

    origin = next(i for i in impact.items if i.node_id == CUSTOMER_ID)
    assert origin.status is ImpactStatus.BROKEN and origin.distance == 0

    assert impact.counts["broken"] >= 1
    assert impact.counts["journeys_broken"] >= 1
    assert impact.assumptions and impact.limitations
    for item in impact.items:
        assert item.reason, f"{item.node_id} has no explanation"
        if item.distance > 0:
            assert item.chain[0] == CUSTOMER_ID


def test_rename_breaks_exactly_the_journeys_that_use_the_field(novacart):
    scenario = _rename_scenario()
    scenario_graph = apply_changes(novacart.graph, scenario)
    broken = {v.journey_name for v in validate_all(novacart.journeys, scenario_graph) if not v.ok}
    assert "Place Order" in broken
    assert "Search and Add Product to Cart" not in broken


def test_repair_restores_validation_and_says_why(novacart):
    scenario = _rename_scenario()
    scenario_graph = apply_changes(novacart.graph, scenario)
    impact = compute_impact(novacart.graph, scenario_graph, scenario, novacart.journeys)

    repairs = propose_deterministic_repairs(novacart.graph, scenario, impact)
    kinds = {r.kind for r in repairs}
    assert "add_alias_mapping" in kinds and "restore_field_name" in kinds
    assert all(r.deterministic for r in repairs)
    assert all(r.migration_steps for r in repairs)

    scenario.repairs = repairs
    for repair in scenario.repairs:
        if repair.kind == "restore_field_name":
            repair.status = RepairStatus.APPLIED

    repaired = apply_changes(novacart.graph, scenario)
    assert all(v.ok for v in validate_all(novacart.journeys, repaired))


def test_service_outage_degrades_rather_than_renaming_anything(novacart):
    scenario = Scenario(
        id="scn:outage",
        project_id="test-novacart",
        name="Payment outage",
        changes=[
            Change(id="chg:0", kind=ChangeKind.SERVICE_UNAVAILABLE, target_id="svc:payment-api",
                   params={}, label="Payment is down")
        ],
    )
    scenario_graph = apply_changes(novacart.graph, scenario)
    operations = [
        n for n in scenario_graph.nodes
        if n.type is NodeType.API_OPERATION and n.attrs.get("service") == "payment-api"
    ]
    assert operations and all(n.attrs.get("unavailable") for n in operations)
    broken = {v.journey_name for v in validate_all(novacart.journeys, scenario_graph) if not v.ok}
    assert "Complete Payment" in broken


def test_remove_field_drops_the_node_and_its_edges(novacart):
    scenario = Scenario(
        id="scn:remove",
        project_id="test-novacart",
        name="Remove",
        changes=[Change(id="chg:0", kind=ChangeKind.REMOVE_FIELD, target_id=CUSTOMER_ID)],
    )
    scenario_graph = apply_changes(novacart.graph, scenario)
    assert scenario_graph.get(CUSTOMER_ID) is None
    assert not [e for e in scenario_graph.edges
                if CUSTOMER_ID in (e.source, e.target)]


def test_diff_reports_what_actually_changed(novacart):
    scenario_graph = apply_changes(novacart.graph, _rename_scenario())
    diff = diff_graphs(novacart.graph, scenario_graph)
    assert CUSTOMER_ID in diff.changed_nodes
    assert not diff.removed_nodes and not diff.added_nodes


def test_undoing_every_change_returns_the_original_graph(novacart):
    scenario = _rename_scenario()
    scenario.changes = []
    restored = apply_changes(novacart.graph, scenario)
    assert restored.get(CUSTOMER_ID).label == novacart.graph.get(CUSTOMER_ID).label
    assert all(v.ok for v in validate_all(novacart.journeys, restored))


def test_journey_validation_names_the_broken_step(novacart):
    scenario_graph = apply_changes(novacart.graph, _rename_scenario())
    journey = next(j for j in novacart.journeys if j.name == "Place Order")
    validation = validate_journey(journey, scenario_graph)
    assert not validation.ok
    reasons = [r for step in validation.steps for r in step.reasons]
    assert any("renamed" in r for r in reasons)
    assert validation.summary.endswith("are broken.")
