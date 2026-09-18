"""Unit tests for the export layer.

The assertions here are mostly about *safety* and *honesty* rather than about content:
that a hostile node label cannot become a spreadsheet formula or a script tag, that a
diagram is valid XML, that provenance survives every serialisation, and that a scoped
export really is a subset. Those are the properties that would fail silently in
production, so they are the ones worth pinning down.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

import networkx as nx
import pytest
from api_galaxy.contracts.graph import (
    Acceptance,
    GraphNode,
    NodeType,
    Provenance,
    SourceKind,
)
from api_galaxy.exports import diagrams, machine
from api_galaxy.exports.bundle import LEGEND, ReportBundle, build_bundle, scope_bundle
from api_galaxy.exports.html_report import external_references, to_html
from api_galaxy.exports.markdown import to_markdown
from api_galaxy.exports.support import truncate

FORMULA_LABEL = "=cmd|' /c calc'!A0"
SCRIPT_LABEL = "<script>alert(1)</script>"


def _hostile_node(node_id: str, label: str) -> GraphNode:
    """A service, because services appear in every section of every format."""
    return GraphNode(
        id=node_id,
        type=NodeType.SERVICE,
        label=label,
        project_id="test-novacart",
        description=f"Injected by a test: {label}",
        acceptance=Acceptance.OBSERVED,
        provenance=Provenance(
            source_kind=SourceKind.SPECIFICATION,
            explanation=f"Hostile label fixture: {label}",
        ),
    )


@pytest.fixture(scope="module")
def hostile_bundle(novacart) -> ReportBundle:
    """A bundle carrying labels that would break a spreadsheet or a browser."""
    project = novacart
    graph = project.graph.clone()
    graph.add_node(_hostile_node("svc:test-formula", FORMULA_LABEL))
    graph.add_node(_hostile_node("svc:test-script", SCRIPT_LABEL))
    return build_bundle(project, graph=graph)


# --------------------------------------------------------------------------------------
# Bundle
# --------------------------------------------------------------------------------------


def test_bundle_carries_the_full_disclosure(novacart_bundle: ReportBundle) -> None:
    keys = {key for key, _ in novacart_bundle.disclosure_rows()}
    assert keys >= {
        "Project",
        "Generated",
        "Specification fingerprint",
        "API Galaxy version",
        "Active scenario",
        "Semantic analysis by",
    }
    assert novacart_bundle.spec_fingerprint.startswith("sha256:")
    assert novacart_bundle.app_version
    assert novacart_bundle.legend == list(LEGEND)
    assert novacart_bundle.methodology
    assert any("not a production prediction" in item or "cannot" in item
               for item in novacart_bundle.limitations)


def test_methodology_states_the_impact_caveat(novacart_bundle: ReportBundle) -> None:
    text = " ".join(note.body for note in novacart_bundle.methodology).lower()
    assert "not a production forecast" in text or "not a prediction" in text
    assert "provenance" in text


def test_scope_bundle_by_journey_is_a_strict_subset(novacart_bundle: ReportBundle) -> None:
    journey = novacart_bundle.journeys[0]
    scoped = scope_bundle(novacart_bundle, journey_id=journey.id)

    assert scoped.stats.nodes < novacart_bundle.stats.nodes
    assert scoped.graph.node_ids() < novacart_bundle.graph.node_ids()

    referenced = {nid for step in journey.steps for nid in step.node_ids}
    referenced &= novacart_bundle.graph.node_ids()
    assert referenced <= scoped.graph.node_ids()

    assert [j.id for j in scoped.journeys] == [journey.id]
    assert scoped.scope_label.startswith("Journey:")
    # Edges must not dangle out of the scope.
    ids = scoped.graph.node_ids()
    assert all(e.source in ids and e.target in ids for e in scoped.graph.edges)


def test_scope_bundle_by_domain_keeps_the_domain(novacart_bundle: ReportBundle) -> None:
    domain = novacart_bundle.nodes_of(NodeType.DOMAIN)[0]
    scoped = scope_bundle(novacart_bundle, domain_id=domain.id)
    assert domain.id in scoped.graph.node_ids()
    assert scoped.stats.nodes < novacart_bundle.stats.nodes
    assert scoped.scope_label == f"Domain: {domain.label}"


def test_scope_bundle_by_node_ids(novacart_bundle: ReportBundle) -> None:
    wanted = [n.id for n in novacart_bundle.nodes_of(NodeType.SERVICE)][:3]
    scoped = scope_bundle(novacart_bundle, node_ids=wanted)
    assert scoped.graph.node_ids() == set(wanted)
    assert scoped.scope_label == "Current view"


def test_scope_bundle_rejects_unknown_ids(novacart_bundle: ReportBundle) -> None:
    with pytest.raises(KeyError):
        scope_bundle(novacart_bundle, journey_id="journey:does-not-exist")


# --------------------------------------------------------------------------------------
# Layout and SVG
# --------------------------------------------------------------------------------------


def test_layout_is_deterministic(novacart_bundle: ReportBundle) -> None:
    nodes, edges, _ = diagrams.select(novacart_bundle)
    assert diagrams.layout(nodes, edges) == diagrams.layout(nodes, edges)


def test_layout_respects_type_layers(novacart_bundle: ReportBundle) -> None:
    nodes, edges, _ = diagrams.select(novacart_bundle)
    positions = diagrams.layout(nodes, edges)
    by_type = {}
    for node in nodes:
        if node.id in positions:
            by_type.setdefault(node.type, set()).add(positions[node.id][0])
    if NodeType.DOMAIN in by_type and NodeType.SERVICE in by_type:
        assert max(by_type[NodeType.DOMAIN]) < min(by_type[NodeType.SERVICE])
    if NodeType.SCHEMA in by_type and NodeType.FIELD in by_type:
        assert max(by_type[NodeType.SCHEMA]) < min(by_type[NodeType.FIELD])


def test_svg_is_valid_xml_with_a_legend(novacart_bundle: ReportBundle) -> None:
    svg = diagrams.render_svg(novacart_bundle, title="Estate map")
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")

    assert "How to read this diagram" in svg
    for entry in LEGEND[:4]:
        assert entry.label in svg
    # The fact-vs-inference encoding must be in the geometry, not only the colour.
    assert 'stroke-dasharray="6 4"' in svg
    assert "<marker" in svg
    assert "<style>" in svg


def test_svg_escapes_hostile_labels(hostile_bundle: ReportBundle) -> None:
    svg = diagrams.render_svg(
        hostile_bundle, scope=["svc:test-script", "svc:test-formula"]
    )
    ET.fromstring(svg)
    assert SCRIPT_LABEL not in svg
    assert "&lt;script&gt;" in svg


def test_svg_for_embedding_declares_no_namespace_url(novacart_bundle: ReportBundle) -> None:
    standalone = diagrams.render_svg(novacart_bundle)
    embedded = diagrams.render_svg(novacart_bundle, interactive=True)
    assert "http://www.w3.org/2000/svg" in standalone
    assert "http://" not in embedded
    assert 'class="ag-viewport"' in embedded
    assert "data-node-id=" in embedded
    ET.fromstring(embedded)


def test_print_svg_is_light_and_attribute_styled(novacart_bundle: ReportBundle) -> None:
    svg = diagrams.render_print_svg(novacart_bundle, title="Structure", max_nodes=24)
    ET.fromstring(svg)
    assert "<style>" not in svg  # the PDF engine only understands presentation attributes
    assert 'fill="#FFFFFF"' in svg


# --------------------------------------------------------------------------------------
# Mermaid
# --------------------------------------------------------------------------------------

_QUOTED = re.compile(r'"([^"]*)"')


def test_mermaid_flowchart_labels_are_safe(novacart_bundle: ReportBundle) -> None:
    text = diagrams.render_mermaid(novacart_bundle)
    assert text.startswith("flowchart LR")
    assert "subgraph" in text
    assert " -.-> " in text or " .-> " in text  # inference edges are dotted
    assert " --> " in text or "-->|" in text

    for line in text.splitlines():
        if line.strip().startswith("%%"):
            continue
        for label in _QUOTED.findall(line):
            assert "\n" not in label
            assert '"' not in label
            assert "[" not in label and "]" not in label


def test_mermaid_escapes_hostile_labels(hostile_bundle: ReportBundle) -> None:
    text = diagrams.render_mermaid(
        hostile_bundle, scope=["svc:test-script", "svc:test-formula"]
    )
    assert SCRIPT_LABEL not in text
    for label in _QUOTED.findall(text):
        assert '"' not in label


def test_journey_mermaid_is_a_sequence_diagram(novacart_bundle: ReportBundle) -> None:
    journey = novacart_bundle.journeys[0]
    text = diagrams.render_journey_mermaid(journey)
    assert text.startswith("sequenceDiagram")
    assert "participant " in text
    assert "Note over " in text
    for line in text.splitlines():
        assert "\n" not in line
    assert text.count("participant ") >= 2


# --------------------------------------------------------------------------------------
# JSON-LD
# --------------------------------------------------------------------------------------


def test_jsonld_round_trips_with_unique_ids(novacart_bundle: ReportBundle) -> None:
    document = json.loads(json.dumps(machine.to_jsonld(novacart_bundle)))
    assert document["@context"]["@vocab"] == machine.NAMESPACE

    ids = [item["@id"] for item in document["@graph"]]
    assert len(ids) == len(set(ids)), "every @id in @graph must be unique"
    assert all(isinstance(i, str) and i for i in ids)


def test_jsonld_preserves_provenance(novacart_bundle: ReportBundle) -> None:
    document = machine.to_jsonld(novacart_bundle)
    by_id = {item["@id"]: item for item in document["@graph"]}

    node = novacart_bundle.graph.nodes[0]
    serialised = by_id[f"urn:api-galaxy:node:{node.id}"]
    provenance = serialised["provenance"]
    assert provenance["sourceKind"] == node.provenance.source_kind.value
    assert provenance["explanation"] == node.provenance.explanation
    assert provenance["isFact"] == node.provenance.is_fact
    assert set(provenance) >= {
        "sourceKind",
        "confidence",
        "provider",
        "model",
        "promptTemplateVersion",
        "explanation",
    }
    assert "acceptance" in serialised

    inferred = next(
        item
        for item in document["@graph"]
        if item.get("provenance", {}).get("sourceKind")
        in ("bundled_analysis", "ai_inference", "deterministic_rule")
    )
    assert inferred["provenance"]["isFact"] in (True, False)


# --------------------------------------------------------------------------------------
# GraphML
# --------------------------------------------------------------------------------------


def test_graphml_parses_and_round_trips_through_networkx(novacart_bundle: ReportBundle) -> None:
    text = machine.to_graphml(novacart_bundle)
    ET.fromstring(text)

    graph = nx.parse_graphml(text)
    assert graph.number_of_nodes() == len(novacart_bundle.graph.nodes)
    assert graph.number_of_edges() == len(novacart_bundle.graph.edges)

    node = novacart_bundle.graph.nodes[0]
    attrs = graph.nodes[node.id]
    assert attrs["label"] == node.label
    assert attrs["type"] == node.type.value
    assert attrs["sourceKind"] == node.provenance.source_kind.value
    assert attrs["acceptance"] == node.acceptance.value


def test_graphml_declares_every_key_it_uses(novacart_bundle: ReportBundle) -> None:
    root = ET.fromstring(machine.to_graphml(novacart_bundle))
    namespace = "{http://graphml.graphdrawing.org/xmlns}"
    declared = {key.get("id") for key in root.findall(f"{namespace}key")}
    used = {data.get("key") for data in root.iter(f"{namespace}data")}
    assert used <= declared
    names = {key.get("attr.name") for key in root.findall(f"{namespace}key")}
    assert {"label", "type", "sourceKind", "acceptance", "confidence", "service", "domain"} <= names


# --------------------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------------------


def test_csv_bundle_has_every_sheet(novacart_bundle: ReportBundle) -> None:
    sheets = machine.to_csv_bundle(novacart_bundle)
    assert set(sheets) == {
        "metadata.csv",
        "nodes.csv",
        "edges.csv",
        "risks.csv",
        "journeys.csv",
        "decisions.csv",
    }
    assert novacart_bundle.spec_fingerprint in sheets["metadata.csv"]
    assert novacart_bundle.app_version in sheets["metadata.csv"]


def test_csv_neutralises_formula_injection(hostile_bundle: ReportBundle) -> None:
    nodes_csv = machine.to_csv_bundle(hostile_bundle)["nodes.csv"]
    assert "'" + FORMULA_LABEL in nodes_csv
    # No cell may begin a formula: check the raw label never appears at a field start.
    for line in nodes_csv.splitlines():
        for cell in line.split(","):
            assert not cell.startswith("=")
            assert not cell.startswith('"=')


@pytest.mark.parametrize(
    "raw",
    ["=1+1", "+1", "-1", "@SUM(A1)", "\tinjected", "\rinjected"],
)
def test_sanitise_cell_prefixes_dangerous_values(raw: str) -> None:
    assert machine.sanitise_cell(raw).startswith("'")


def test_sanitise_cell_leaves_ordinary_text_alone() -> None:
    assert machine.sanitise_cell("GET /customers/{customerId}") == "GET /customers/{customerId}"
    assert machine.sanitise_cell(None) == ""
    assert machine.sanitise_cell(True) == "true"


# --------------------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------------------


def test_markdown_states_provenance_up_front(novacart_bundle: ReportBundle) -> None:
    text = to_markdown(novacart_bundle)
    assert novacart_bundle.spec_fingerprint in text
    assert f"| API Galaxy version | {novacart_bundle.app_version} |" in text
    assert "Fact vs inference legend" in text
    for entry in LEGEND:
        assert entry.label in text
    assert "## Methodology" in text
    assert "## Limitations" in text
    assert "```mermaid" in text
    assert "Heuristic" in text and "Deterministic" in text


def test_markdown_escapes_table_breaking_characters(hostile_bundle: ReportBundle) -> None:
    text = to_markdown(hostile_bundle, include_diagrams=False)
    assert SCRIPT_LABEL not in text
    assert "&lt;script&gt;" in text


# --------------------------------------------------------------------------------------
# HTML report
# --------------------------------------------------------------------------------------


def test_html_makes_no_external_requests(novacart_bundle: ReportBundle) -> None:
    document = to_html(novacart_bundle)
    assert external_references(document) == []
    assert "<script src" not in document
    assert '<link rel="stylesheet"' not in document
    assert "//cdn" not in document
    assert "@import" not in document
    # Any http(s) text that remains is escaped page content — a server URL the imported
    # specification declared — never an attribute the browser would resolve.
    for match in re.finditer(r"https?://", document):
        preceding = document[max(0, match.start() - 12) : match.start()]
        assert not re.search(r"""(src|href|action|data|poster)\s*=\s*["']?$""", preceding)


def test_html_embeds_a_neutralised_json_block(novacart_bundle: ReportBundle) -> None:
    document = to_html(novacart_bundle)
    opening = '<script type="application/json" id="api-galaxy-data">'
    assert opening in document

    block = document.split(opening, 1)[1].split("</script>", 1)[0]
    assert "<" not in block and ">" not in block
    payload = json.loads(block)
    assert payload["project"]["fingerprint"] == novacart_bundle.spec_fingerprint
    assert len(payload["nodeOrder"]) == len(novacart_bundle.graph.nodes)
    sample = payload["nodes"][novacart_bundle.graph.nodes[0].id]
    assert {"sourceKind", "explanation", "provenanceGroup", "evidence"} <= set(sample)


def test_html_escapes_a_script_tag_in_a_node_label(hostile_bundle: ReportBundle) -> None:
    document = to_html(hostile_bundle)
    assert SCRIPT_LABEL not in document
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document

    opening = '<script type="application/json" id="api-galaxy-data">'
    block = document.split(opening, 1)[1].split("</script>", 1)[0]
    assert "\\u003cscript\\u003e" in block
    assert json.loads(block)["nodes"]["svc:test-script"]["label"] == SCRIPT_LABEL


def test_html_is_accessible_and_printable(novacart_bundle: ReportBundle) -> None:
    document = to_html(novacart_bundle)
    assert 'role="tablist"' in document and 'role="tabpanel"' in document
    assert "aria-label=" in document and "aria-live=" in document
    assert "@media print" in document
    assert "prefers-reduced-motion" in document
    assert 'class="ag-skip"' in document
    # The screen-reader / no-JavaScript fallback lists everything.
    assert f"Nodes ({len(novacart_bundle.graph.nodes)})" in document
    assert f"Relationships ({len(novacart_bundle.graph.edges)})" in document


def test_html_runtime_hooks_all_exist_in_the_rendered_page(
    novacart_bundle: ReportBundle,
) -> None:
    """The runtime has no build step, so a renamed id fails silently at run time.

    Every element id and class ``report.js`` looks up is extracted from the source and
    checked against the rendered document, which turns "the journey player quietly did
    nothing" into a failing test.
    """
    from api_galaxy.exports.html_report import runtime_dir

    script = (runtime_dir() / "report.js").read_text(encoding="utf-8")
    document = to_html(novacart_bundle)

    pairs = re.findall(
        r"""getElementById\(["']([\w-]+)["']\)|\$\(\s*["']#([\w-]+)["']""", script
    )
    for element_id in sorted({first or second for first, second in pairs}):
        assert f'id="{element_id}"' in document, f"report.js queries #{element_id}, page has none"

    for class_name in sorted(set(re.findall(r"""\$\$?\(\s*["']\.([\w-]+)["']""", script))):
        assert class_name in document, f"report.js queries .{class_name}, page has none"

    for attribute in ("data-node-id", "data-node-type", "data-source", "data-target"):
        assert attribute in document


def test_html_runtime_never_builds_dom_from_data_with_innerhtml() -> None:
    from api_galaxy.exports.html_report import runtime_dir

    source = (runtime_dir() / "report.js").read_text(encoding="utf-8")
    # The rules these assertions enforce are also written down in the file's header, so
    # comments are stripped before looking for the constructs themselves.
    script = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    script = re.sub(r"^\s*//.*$", "", script, flags=re.MULTILINE)
    assert "innerHTML" not in script
    assert "insertAdjacentHTML" not in script
    assert "document.write" not in script
    assert "fetch(" not in script
    assert "XMLHttpRequest" not in script


# --------------------------------------------------------------------------------------
# Support
# --------------------------------------------------------------------------------------


def test_truncate_collapses_whitespace_and_marks_the_cut() -> None:
    assert truncate("a  b\nc", 40) == "a b c"
    assert truncate("x" * 50, 10).endswith("…")
    assert len(truncate("x" * 50, 10)) == 10
