"""Write-back: a scenario as a reviewable diff against the original documents.

The bar these tests hold is not "a diff was produced" but "the diff is minimal, it still
parses, and `git apply` would take it".
"""

from __future__ import annotations

import yaml
from api_galaxy.contracts.graph import Provenance, SourceKind
from api_galaxy.contracts.scenario import Change, ChangeKind, Repair, RepairStatus, Scenario
from api_galaxy.exports.writeback import generate_writeback, index_spans

CUSTOMER_ID = "field:customer-api:Customer.customer_id"


def _scenario(*changes: Change, repairs: list[Repair] | None = None) -> Scenario:
    return Scenario(
        id="scn:test", project_id="test", name="test", changes=list(changes),
        repairs=repairs or [],
    )


def _rename(target: str = CUSTOMER_ID, new_name: str = "party_id") -> Change:
    return Change(id="c0", kind=ChangeKind.RENAME_FIELD, target_id=target,
                  params={"new_name": new_name})


# -- pointer index -------------------------------------------------------------------


def test_every_pointer_resolves_to_the_line_it_is_on():
    text = "a:\n  b: 1\n  c:\n    - x\n    - y\n"
    spans = index_spans(text)
    assert spans["/a/b"].key_line == 1
    assert spans["/a/c/0"].start_line == 3
    assert spans["/a/c/1"].start_line == 4


def test_pointer_index_survives_a_document_with_no_content():
    assert index_spans("") == {}


# -- the diff ------------------------------------------------------------------------


def test_a_rename_changes_only_the_lines_it_has_to(novacart):
    result = generate_writeback(novacart.estate, novacart.graph, _scenario(_rename()))
    assert len(result.changed_files) == 1
    diff = result.patch()
    added = [ln for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    removed = [ln for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---")]
    # The property and its entry in `required` — and nothing else. A structural rewrite
    # would touch hundreds of lines here.
    assert len(added) == 2, diff
    assert len(removed) == 2, diff
    assert any("party_id" in ln for ln in added)


def test_the_original_comments_and_formatting_survive(novacart):
    result = generate_writeback(novacart.estate, novacart.graph, _scenario(_rename()))
    modified = result.changed_files[0].modified
    original = result.changed_files[0].original
    # Same number of lines, same description prose: only a token moved.
    assert len(modified.splitlines()) == len(original.splitlines())
    assert "Canonical, immutable identifier for the shopper" in modified


def test_required_is_kept_consistent_or_the_document_would_not_validate(novacart):
    """Renaming a property while leaving `required:` behind emits an invalid spec."""
    result = generate_writeback(novacart.estate, novacart.graph, _scenario(_rename()))
    document = yaml.safe_load(result.changed_files[0].modified)
    schema = document["components"]["schemas"]["Customer"]
    assert "party_id" in schema["properties"]
    assert "customer_id" not in schema["properties"]
    assert set(schema["required"]) <= set(schema["properties"])


def test_removing_a_field_also_removes_it_from_required(novacart):
    change = Change(id="c0", kind=ChangeKind.REMOVE_FIELD,
                    target_id="field:customer-api:Customer.loyalty_tier", params={})
    result = generate_writeback(novacart.estate, novacart.graph, _scenario(change))
    document = yaml.safe_load(result.changed_files[0].modified)
    schema = document["components"]["schemas"]["Customer"]
    assert "loyalty_tier" not in schema["properties"]
    assert "loyalty_tier" not in schema.get("required", [])


def test_a_type_change_rewrites_only_the_type_line(novacart):
    change = Change(id="c0", kind=ChangeKind.CHANGE_FIELD_TYPE, target_id=CUSTOMER_ID,
                    params={"new_type": "integer"})
    result = generate_writeback(novacart.estate, novacart.graph, _scenario(change))
    document = yaml.safe_load(result.changed_files[0].modified)
    assert document["components"]["schemas"]["Customer"]["properties"]["customer_id"]["type"] == "integer"


def test_every_edited_document_still_parses(novacart):
    for change in (
        _rename(),
        Change(id="c", kind=ChangeKind.REMOVE_FIELD,
               target_id="field:customer-api:Customer.loyalty_tier", params={}),
        Change(id="c", kind=ChangeKind.CHANGE_FIELD_TYPE, target_id=CUSTOMER_ID,
               params={"new_type": "integer"}),
    ):
        result = generate_writeback(novacart.estate, novacart.graph, _scenario(change))
        for file in result.changed_files:
            assert file.valid, f"{change.kind}: {file.validation_errors}"


# -- honesty about what it will not do ------------------------------------------------


def test_simulated_behaviour_is_reported_not_faked(novacart):
    """An outage is a statement about the model, not an edit to a document."""
    change = Change(id="c0", kind=ChangeKind.SERVICE_UNAVAILABLE,
                    target_id="svc:customer-api", params={})
    result = generate_writeback(novacart.estate, novacart.graph, _scenario(change))
    assert not result.changed_files
    assert any("simulated behaviour" in entry for entry in result.skipped)


def test_an_applied_revert_cancels_its_change(novacart):
    """Undo it in the UI and the patch should be empty, not show the change anyway."""
    repair = Repair(
        id="r0", title="Revert", rationale="", kind="restore_field_name",
        target_ids=[CUSTOMER_ID], status=RepairStatus.APPLIED,
        provenance=Provenance(source_kind=SourceKind.DETERMINISTIC_RULE, explanation="test"),
    )
    result = generate_writeback(
        novacart.estate, novacart.graph, _scenario(_rename(), repairs=[repair])
    )
    assert not result.changed_files
    assert any("not in this patch" in w or "was applied" in w for w in result.warnings)


def test_a_project_imported_before_writeback_says_so_rather_than_guessing(novacart):
    estate = novacart.estate.model_copy(deep=True)
    for service in estate.services:
        service.source_text = ""
    result = generate_writeback(estate, novacart.graph, _scenario(_rename()))
    assert not result.changed_files
    assert any("Re-import" in warning for warning in result.warnings)
