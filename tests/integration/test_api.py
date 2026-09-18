"""End-to-end API tests over the real application, with a throwaway data directory.

These run the same code path the browser does — import, graph, ask, break, repair,
replay, arena, export — so a route that drifts from its module is caught here rather
than in a demo.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NOVACART = REPO_ROOT / "samples" / "novacart"


@pytest.fixture(scope="module")
def client():
    """A TestClient bound to a fresh data directory, so tests never see real projects."""
    with tempfile.TemporaryDirectory(prefix="api-galaxy-test-") as directory:
        os.environ["API_GALAXY_DATA_DIR"] = directory
        from api_galaxy.app.settings import get_settings
        from api_galaxy.app.state import reset_state

        get_settings.cache_clear()
        reset_state()

        from fastapi.testclient import TestClient
        from api_galaxy.app.main import create_app

        with TestClient(create_app()) as test_client:
            yield test_client

        get_settings.cache_clear()
        reset_state()
        os.environ.pop("API_GALAXY_DATA_DIR", None)


@pytest.fixture(scope="module")
def demo(client) -> str:
    response = client.post("/api/v1/projects/demo")
    assert response.status_code == 201, response.text
    return response.json()["project_id"]


def ok(response, *, expect: int | None = None):
    if expect is not None:
        assert response.status_code == expect, response.text
    else:
        assert response.status_code < 400, response.text
    return response.json()


# --------------------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------------------


def test_health_and_meta(client):
    health = ok(client.get("/api/v1/health"))
    assert health["status"] == "ok" and health["version"]
    meta = ok(client.get("/api/v1/meta"))
    assert meta["app"] == "API Galaxy" and meta["rules"]


def test_demo_import_produces_the_expected_estate(client, demo):
    project = ok(client.get(f"/api/v1/projects/{demo}"))
    assert project["is_demo"] is True
    assert project["enrichment_label"] == "Bundled Demo Analysis"
    assert project["stats"]["services"] == 7
    assert project["stats"]["operations"] == 32
    assert len(project["services"]) == 7
    assert project["coverage"]["parsed_cleanly"] is True


def test_demo_import_is_idempotent(client, demo):
    again = ok(client.post("/api/v1/projects/demo"))
    assert again["project_id"] == demo and again["created"] is False


def test_valid_spec_validates_with_a_preview(client):
    content = (NOVACART / "cart-api.yaml").read_text(encoding="utf-8")
    result = ok(client.post("/api/v1/specs/validate",
                            json={"content": content, "filename": "cart-api.yaml"}))
    assert result["valid"] is True
    assert result["kind"] == "openapi"
    assert result["counts"]["operations"] == 5
    assert result["preview"]["operations"]


def test_invalid_spec_is_rejected_with_a_line_number(client):
    result = ok(client.post("/api/v1/specs/validate",
                            json={"content": "openapi: 3.0.0\npaths: [", "filename": "x.yaml"}))
    assert result["valid"] is False
    assert result["error"]["line"] is not None
    assert result["error"]["hint"]


def test_a_non_openapi_document_is_named_as_such(client):
    result = ok(client.post("/api/v1/specs/validate",
                            json={"content": '{"hello": "world"}', "filename": "x.json"}))
    assert result["valid"] is False
    assert "not an OpenAPI document" in result["error"]["message"]


def test_importing_a_pasted_spec_runs_a_job_to_completion(client):
    content = (NOVACART / "catalog-api.yaml").read_text(encoding="utf-8")
    started = ok(
        client.post(
            "/api/v1/projects/import",
            json={"name": "Catalog only",
                  "documents": [{"content": content, "filename": "catalog-api.yaml"}]},
        ),
        expect=202,
    )
    # The TestClient runs the event loop, so the job finishes before the next request.
    job = ok(client.get(f"/api/v1/jobs/{started['job_id']}"))
    assert job["status"] in ("succeeded", "running", "queued")
    for _ in range(40):
        job = ok(client.get(f"/api/v1/jobs/{started['job_id']}"))
        if job["status"] == "succeeded":
            break
    assert job["status"] == "succeeded", job
    assert job["result"]["stats"]["operations"] == 4

    project = ok(client.get(f"/api/v1/projects/{started['project_id']}"))
    assert project["name"] == "Catalog only"
    ok(client.delete(f"/api/v1/projects/{started['project_id']}"))


def test_unknown_project_is_a_problem_document(client):
    response = client.get("/api/v1/projects/does-not-exist")
    assert response.status_code == 404
    problem = response.json()
    assert problem["title"] == "Not found"
    assert problem["correlation_id"]
    assert problem["type"].endswith("/not-found")


# --------------------------------------------------------------------------------------
# Overview and graph
# --------------------------------------------------------------------------------------


def test_overview_answers_the_four_questions(client, demo):
    overview = ok(client.get(f"/api/v1/projects/{demo}/overview"))
    assert len(overview["domains"]) == 7
    assert [d["name"] for d in overview["domains"]][0] == "Customer"
    assert len(overview["journeys"]) == 6
    assert overview["top_risks"]
    assert overview["counts"]["observed_relationships"] > 0
    assert overview["counts"]["inferred_relationships"] > 0
    assert len(overview["derivation"]) == 4, "the 'how was this derived?' control needs content"
    assert overview["enrichment"]["is_bundled"] is True


def test_semantic_zoom_reduces_the_graph(client, demo):
    level1 = ok(client.get(f"/api/v1/projects/{demo}/graph?level=1"))
    level4 = ok(client.get(f"/api/v1/projects/{demo}/graph?level=4&max_nodes=5000"))
    assert len(level1["nodes"]) < len(level4["nodes"])
    assert {n["type"] for n in level1["nodes"]} <= {"Estate", "Domain", "Capability"}


def test_graph_edges_carry_their_stroke_and_fact_flag(client, demo):
    payload = ok(client.get(f"/api/v1/projects/{demo}/graph?level=4&max_nodes=5000"))
    strokes = {e["stroke"] for e in payload["edges"]}
    assert "solid" in strokes and "dashed" in strokes
    for edge in payload["edges"]:
        assert "is_fact" in edge


def test_hiding_inferences_removes_only_inferences(client, demo):
    with_inferred = ok(client.get(f"/api/v1/projects/{demo}/graph?level=4&max_nodes=5000"))
    without = ok(
        client.get(f"/api/v1/projects/{demo}/graph?level=4&max_nodes=5000&include_inferred=false")
    )
    assert len(without["edges"]) < len(with_inferred["edges"])
    assert all(e["stroke"] == "solid" for e in without["edges"])


def test_node_detail_carries_evidence_and_aliases(client, demo):
    node_id = "field:customer-api:Customer.customer_id"
    detail = ok(client.get(f"/api/v1/projects/{demo}/graph/node/{node_id}"))
    assert detail["node"]["id"] == node_id
    assert detail["evidence"], "every specification node must cite its source"
    assert detail["evidence"][0]["pointer"]
    labels = {a["name"] for a in detail["aliases"]}
    assert {"cust_no", "party_key"} <= labels
    assert detail["dependents"]

    # One entry per related node, never one per edge.
    assert len(detail["aliases"]) == len({a["id"] for a in detail["aliases"]})


def test_accepting_an_inference_records_a_decision(client, demo):
    node_id = "field:customer-api:Customer.customer_id"
    detail = ok(client.get(f"/api/v1/projects/{demo}/graph/node/{node_id}"))
    alias = next(a for a in detail["aliases"] if a["acceptance"] == "proposed")

    result = ok(client.post(
        f"/api/v1/projects/{demo}/graph/edges/{alias['edge_id']}/decision",
        json={"action": "accept", "note": "checked against the order service"},
    ))
    assert result["edge"]["acceptance"] == "accepted"
    assert result["edge"]["stroke"] == "dotted", "an accepted inference reads as a user edit"
    assert result["decision"]["action"] == "accept"

    decisions = ok(client.get(f"/api/v1/projects/{demo}/decisions"))
    assert any(d["id"] == result["decision"]["id"] for d in decisions["decisions"])
    assert "append-only" in decisions["note"]


def test_a_specification_fact_cannot_be_accepted(client, demo):
    payload = ok(client.get(f"/api/v1/projects/{demo}/graph?level=4&max_nodes=5000"))
    fact = next(e for e in payload["edges"] if e["stroke"] == "solid")
    response = client.post(
        f"/api/v1/projects/{demo}/graph/edges/{fact['id']}/decision", json={"action": "accept"}
    )
    assert response.status_code == 422
    assert "specification fact" in response.json()["detail"]


def test_search_and_path(client, demo):
    hits = ok(client.get(f"/api/v1/projects/{demo}/graph/search?q=customer_id"))
    assert hits["results"]
    path = ok(client.get(
        f"/api/v1/projects/{demo}/graph/path?from=svc:cart-api&to=svc:payment-api"
    ))
    assert path["found"] is True and path["paths"][0]["labels"]


def test_legend_never_relies_on_colour_alone(client, demo):
    legend = ok(client.get(f"/api/v1/projects/{demo}/graph/legend"))
    assert {e["stroke"] for e in legend["edges"]} == {"solid", "dashed", "dotted"}
    assert all(state["icon"] for state in legend["states"])
    assert "colour alone" in legend["note"]


# --------------------------------------------------------------------------------------
# Journeys and Ask
# --------------------------------------------------------------------------------------


def test_journeys_validate_and_play_back(client, demo):
    journeys = ok(client.get(f"/api/v1/projects/{demo}/journeys"))["journeys"]
    assert len(journeys) == 6
    assert all(j["validation"]["ok"] for j in journeys)

    place_order = next(j for j in journeys if j["name"] == "Place Order")
    playback = ok(client.get(f"/api/v1/projects/{demo}/journeys/{place_order['id']}/playback"))
    assert len(playback["frames"]) == len(place_order["steps"])
    first = playback["frames"][0]
    assert first["narration"] and first["highlight_nodes"] and first["evidence"]
    # The trail accumulates, which is what makes the traversal read as a path.
    assert len(playback["frames"][-1]["trail"]) >= len(first["trail"])


def test_ask_is_grounded_and_separates_fact_from_inference(client, demo):
    answer = ok(client.post(f"/api/v1/projects/{demo}/ask",
                            json={"question": "How does checkout work?"}))
    assert "Place Order" in answer["answer"]
    assert answer["grounded"] is True
    assert answer["path"] and answer["path_labels"]
    assert answer["evidence"]
    assert answer["fact_vs_inference"]["facts"] >= 1
    assert not answer["dropped_references"]


def test_ask_only_ever_cites_nodes_that_exist(client, demo):
    graph = ok(client.get(f"/api/v1/projects/{demo}/graph?level=4&max_nodes=5000"))
    existing = {n["id"] for n in graph["nodes"]}
    for question in ["How does checkout work?", "What depends on customer_id?",
                     "Which endpoints touch customer data?"]:
        answer = ok(client.post(f"/api/v1/projects/{demo}/ask", json={"question": question}))
        assert set(answer["highlighted_node_ids"]) <= existing
        assert {e["node_id"] for e in answer["evidence"]} <= existing


def test_ask_results_are_cached_by_question(client, demo):
    body = {"question": "Which concepts have conflicting definitions?"}
    first = ok(client.post(f"/api/v1/projects/{demo}/ask", json=body))
    second = ok(client.post(f"/api/v1/projects/{demo}/ask", json=body))
    assert first["cached"] is False and second["cached"] is True


# --------------------------------------------------------------------------------------
# Break Lab: the full break → impact → repair → replay loop
# --------------------------------------------------------------------------------------


def test_break_and_repair_restores_the_journeys(client, demo):
    scenario = ok(client.post(f"/api/v1/projects/{demo}/scenarios",
                              json={"name": "Rename customer_id"}), expect=201)["scenario"]
    scenario_id = scenario["id"]

    impact = ok(client.post(
        f"/api/v1/projects/{demo}/scenarios/{scenario_id}/changes",
        json={"kind": "rename_field",
              "target_id": "field:customer-api:Customer.customer_id",
              "params": {"new_name": "party_id"}},
    ))
    assert impact["impact"]["counts"]["broken"] >= 1
    assert impact["impact"]["counts"]["journeys_broken"] >= 1
    assert impact["impact"]["assumptions"] and impact["impact"]["limitations"]

    broken_before = {j["journey_name"] for j in impact["all_journeys"] if not j["ok"]}
    assert "Place Order" in broken_before

    # Every shockwave row explains itself and points back at the origin.
    for item in impact["shockwave"]:
        assert item["reason"]
        if item["distance"] > 0:
            assert item["chain"][0] == "field:customer-api:Customer.customer_id"
            assert len(item["chain"]) == item["distance"] + 1

    repairs = ok(client.post(f"/api/v1/projects/{demo}/scenarios/{scenario_id}/repairs/propose",
                             json={"provider": "deterministic"}))["repairs"]
    assert repairs and all(r["deterministic"] for r in repairs)
    revert = next(r for r in repairs if r["kind"] == "restore_field_name")

    applied = ok(client.post(
        f"/api/v1/projects/{demo}/scenarios/{scenario_id}/repairs/{revert['id']}/decision",
        json={"action": "apply"},
    ))
    assert applied["all_valid"] is True
    assert "Place Order" in applied["journeys_restored"]

    summary = ok(client.get(f"/api/v1/projects/{demo}/scenarios/{scenario_id}/change-summary"))
    assert "## Changes" in summary["markdown"]
    assert summary["migration_steps"]

    comparison = ok(client.get(f"/api/v1/projects/{demo}/scenarios/{scenario_id}/compare"))
    assert comparison["before"]["journeys_ok"] == 6

    ok(client.delete(f"/api/v1/projects/{demo}/scenarios/{scenario_id}"))


def test_the_base_project_is_untouched_by_a_scenario(client, demo):
    before = ok(client.get(f"/api/v1/projects/{demo}"))["stats"]
    scenario = ok(client.post(f"/api/v1/projects/{demo}/scenarios",
                              json={"name": "Destructive"}), expect=201)["scenario"]
    ok(client.post(
        f"/api/v1/projects/{demo}/scenarios/{scenario['id']}/changes",
        json={"kind": "remove_field", "target_id": "field:customer-api:Customer.email"},
    ))
    after = ok(client.get(f"/api/v1/projects/{demo}"))["stats"]
    assert after["nodes"] == before["nodes"]
    assert all(j["validation"]["ok"] for j in ok(client.get(f"/api/v1/projects/{demo}/journeys"))["journeys"])
    ok(client.delete(f"/api/v1/projects/{demo}/scenarios/{scenario['id']}"))


def test_a_change_is_rejected_when_the_target_is_the_wrong_type(client, demo):
    scenario = ok(client.post(f"/api/v1/projects/{demo}/scenarios",
                              json={"name": "Wrong target"}), expect=201)["scenario"]
    response = client.post(
        f"/api/v1/projects/{demo}/scenarios/{scenario['id']}/changes",
        json={"kind": "rename_field", "target_id": "svc:cart-api", "params": {"new_name": "x"}},
    )
    assert response.status_code == 422
    assert "applies to Field" in response.json()["detail"]
    ok(client.delete(f"/api/v1/projects/{demo}/scenarios/{scenario['id']}"))


def test_chaos_hides_the_origin_but_still_shows_the_blast_radius(client, demo):
    chaos = ok(client.post(f"/api/v1/projects/{demo}/scenarios/chaos", json={"seed": 3}))
    assert chaos["shockwave"], "there must be something to diagnose"
    assert all(item["distance"] > 0 for item in chaos["shockwave"])
    assert all(not item["chain"] for item in chaos["shockwave"])
    assert chaos["scenario"]["changes"][0]["target_id"] == "hidden"
    assert chaos["hidden_origin_token"]
    assert chaos["candidates"]


# --------------------------------------------------------------------------------------
# Providers, privacy, arena
# --------------------------------------------------------------------------------------


def test_provider_health_lists_every_provider(client):
    payload = ok(client.get("/api/v1/providers/health"))
    kinds = {p["kind"] for p in payload["providers"]}
    assert kinds == {"deterministic", "ollama", "kimi"}
    deterministic = next(p for p in payload["providers"] if p["kind"] == "deterministic")
    assert deterministic["ready"] is True
    assert len(payload["modes"]) == 4


def test_external_preview_shows_what_would_be_sent(client, demo):
    preview = ok(client.get(f"/api/v1/projects/{demo}/external-preview"))
    assert preview["sanitization"]["summary"]
    assert preview["consent"]["granted"] is False
    assert "third-party" in preview["warning"]
    payload = str(preview["payload_preview"])
    assert "novacart.example" not in payload or "[REDACTED" in payload


def test_consent_is_required_recorded_and_revocable(client, demo):
    assert ok(client.get(f"/api/v1/projects/{demo}/external-preview"))["consent"]["granted"] is False
    granted = ok(client.post(f"/api/v1/projects/{demo}/consent",
                             json={"granted": True, "remember": True}))
    assert granted["consent"]["granted"] is True
    revoked = ok(client.post(f"/api/v1/projects/{demo}/consent", json={"granted": False}))
    assert revoked["consent"]["granted"] is False


def test_disabling_external_providers_clears_consent(client, demo):
    ok(client.post(f"/api/v1/projects/{demo}/consent", json={"granted": True}))
    ok(client.put("/api/v1/providers/config", json={"external_providers_enabled": False}))
    state = ok(client.get(f"/api/v1/projects/{demo}/external-preview"))
    assert state["consent"]["granted"] is False
    assert state["external_providers_enabled"] is False
    # Restore for later tests.
    ok(client.put("/api/v1/providers/config", json={"external_providers_enabled": True}))


def test_arena_runs_and_records_a_decision(client, demo):
    arena = ok(client.post(f"/api/v1/projects/{demo}/arena",
                           json={"providers": ["deterministic", "deterministic"]}))
    assert len(arena["metrics"]) == 2
    assert arena["consensus"]
    assert arena["consensus"][0]["source_label"]
    assert arena["pricing_disclaimer"]
    assert arena["prompt_template_version"]

    decision = ok(client.post(f"/api/v1/projects/{demo}/arena/decision",
                              json={"action": "merge", "subject": "customer alias",
                                    "payload": {"canonical": "customer"}}))
    assert decision["decision"]["action"] == "merge"
    assert decision["decision"]["payload_fingerprint"].startswith("sha256:")


def test_arena_needs_two_providers(client, demo):
    response = client.post(f"/api/v1/projects/{demo}/arena", json={"providers": ["deterministic"]})
    assert response.status_code == 422


def test_pricing_is_editable_and_labelled_as_examples(client):
    pricing = ok(client.get("/api/v1/providers/pricing"))
    assert "not a quote" in pricing["disclaimer"]
    updated = ok(client.put("/api/v1/providers/pricing",
                            json={"provider": "kimi", "input_per_million": 1.25,
                                  "output_per_million": 5.0, "note": "checked today"}))
    assert updated["pricing"]["kimi"]["input_per_million"] == 1.25
    assert updated["pricing"]["kimi"]["updated_by"] == "local-user"


# --------------------------------------------------------------------------------------
# Missions
# --------------------------------------------------------------------------------------


def test_missions_are_graded_against_the_real_graph(client, demo):
    missions = ok(client.get("/api/v1/missions"))["missions"]
    assert {m["id"] for m in missions} == {
        "hidden-dependency", "stop-the-data-leak", "survive-the-rename",
        "untangle-the-twins", "chaos-mode",
    }

    correct = ok(client.post(
        f"/api/v1/projects/{demo}/missions/stop-the-data-leak/check",
        json={"node_id": "op:customer-api:get:/public/customers/{customerId}/summary"},
    ))
    assert correct["correct"] is True and correct["score"] > 0 and correct["teaches"]

    wrong = ok(client.post(f"/api/v1/projects/{demo}/missions/stop-the-data-leak/check",
                           json={"node_id": "op:customer-api:post:/customers"}))
    assert wrong["correct"] is False and wrong["score"] == 0

    hinted = ok(client.post(
        f"/api/v1/projects/{demo}/missions/hidden-dependency/check",
        json={"node_id": "field:payment-api:Payment.party_key", "hints_used": 2},
    ))
    assert hinted["correct"] is True
    assert hinted["score"] < hinted["max_score"], "hints must cost something"


def test_untangle_the_twins_needs_all_three_names(client, demo):
    members = [
        "field:customer-api:Customer.customer_id",
        "field:order-api:Order.cust_no",
        "field:payment-api:Payment.party_key",
    ]
    assert ok(client.post(f"/api/v1/projects/{demo}/missions/untangle-the-twins/check",
                          json={"node_ids": members}))["correct"] is True
    assert ok(client.post(f"/api/v1/projects/{demo}/missions/untangle-the-twins/check",
                          json={"node_ids": members[:2]}))["correct"] is False


# --------------------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------------------


def test_every_available_format_renders_through_the_api(client, demo):
    formats = ok(client.get("/api/v1/exports/formats"))["formats"]
    assert len(formats) >= 8
    produced = []
    for spec in formats:
        if not spec["available"]:
            continue
        created = ok(client.post(f"/api/v1/projects/{demo}/exports",
                                 json={"format": spec["id"]}), expect=201)
        record = created["export"]
        assert record["size_bytes"] > 0, f"{spec['id']} produced an empty file"
        assert record["filename"].endswith(spec["extension"])
        produced.append(spec["id"])

        download = client.get(created["download_url"])
        assert download.status_code == 200
        assert len(download.content) == record["size_bytes"]

    assert {"html", "markdown", "svg", "mermaid", "jsonld", "graphml", "csv"} <= set(produced)


def test_the_html_report_is_self_contained(client, demo):
    created = ok(client.post(f"/api/v1/projects/{demo}/exports", json={"format": "html"}),
                 expect=201)
    assert created["interactive"] is True
    document = client.get(created["download_url"]).text
    assert "<script src=" not in document
    assert '<link rel="stylesheet"' not in document
    assert "api-galaxy-data" in document


def test_scoping_an_export_to_a_journey_shrinks_it(client, demo):
    whole = ok(client.post(f"/api/v1/projects/{demo}/exports", json={"format": "svg"}),
               expect=201)["export"]
    scoped = ok(client.post(f"/api/v1/projects/{demo}/exports",
                            json={"format": "svg", "journey_id": "journey:place-order"}),
                expect=201)["export"]
    assert scoped["size_bytes"] < whole["size_bytes"]
    assert scoped["scope"] == "journey:place-order"


def test_unknown_format_is_refused_with_the_list(client, demo):
    response = client.post(f"/api/v1/projects/{demo}/exports", json={"format": "powerpoint"})
    assert response.status_code == 422
    assert "not a known export format" in response.json()["detail"]


def test_export_history_is_listed(client, demo):
    exports = ok(client.get(f"/api/v1/projects/{demo}/exports"))["exports"]
    assert exports and all(e["download_url"] for e in exports)
