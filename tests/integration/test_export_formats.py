"""Integration tests: every advertised format actually renders the NovaCart estate.

The registry promises the UI that a format marked ``available`` will work. These tests
hold it to that — including the two formats whose availability depends on optional
packages, which are skipped (never silently passed) when those packages are missing.
"""

from __future__ import annotations

import io
import struct
import xml.etree.ElementTree as ET
import zipfile

import pytest
from api_galaxy.analysis.impact import (
    apply_changes,
    compute_impact,
    propose_deterministic_repairs,
)
from api_galaxy.contracts.graph import NodeType
from api_galaxy.contracts.ids import change_id, scenario_id
from api_galaxy.contracts.scenario import Change, ChangeKind, Scenario
from api_galaxy.exports import EXPORT_FORMATS, ExportUnavailable, format_by_id, render
from api_galaxy.exports.bundle import ReportBundle, build_bundle, scope_bundle
from api_galaxy.exports.diagrams import render_png, render_svg
from api_galaxy.exports.pdf import to_pdf, to_pdf_html
from api_galaxy.exports.support import probe_cairosvg, probe_weasyprint

AVAILABLE = [fmt.id for fmt in EXPORT_FORMATS if fmt.available]


@pytest.fixture(scope="module")
def scenario_bundle(novacart) -> ReportBundle:
    """A bundle with a real Break Lab scenario applied, to exercise the impact path."""
    field = next(
        node
        for node in novacart.graph.nodes
        if node.type is NodeType.FIELD and node.attrs.get("name") == "customer_id"
    )
    sid = scenario_id("rename-customer-id")
    scenario = Scenario(
        id=sid,
        project_id=novacart.project_id,
        name="Rename customer_id to shopper_ref",
        description="What breaks if the customer identifier is renamed?",
        changes=[
            Change(
                id=change_id(sid, 0),
                kind=ChangeKind.RENAME_FIELD,
                target_id=field.id,
                params={"new_name": "shopper_ref"},
            )
        ],
    )
    scenario_graph = apply_changes(novacart.graph, scenario)
    impact = compute_impact(novacart.graph, scenario_graph, scenario, novacart.journeys)
    scenario.repairs = propose_deterministic_repairs(novacart.graph, scenario, impact)
    return build_bundle(
        novacart,
        scenario=scenario,
        impact=impact,
        graph=scenario_graph,
        provider_disclosure="Bundled Demo Analysis",
    )


# --------------------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------------------


def test_registry_is_well_formed() -> None:
    ids = [fmt.id for fmt in EXPORT_FORMATS]
    assert len(ids) == len(set(ids))
    for fmt in EXPORT_FORMATS:
        assert fmt.label and fmt.description
        assert fmt.extension.startswith(".")
        assert "/" in fmt.media_type
        assert fmt.available is not bool(fmt.unavailable_reason)
    assert {"html", "pdf", "markdown", "svg", "png", "mermaid", "jsonld", "graphml", "csv"} <= set(
        ids
    )
    assert format_by_id("html").interactive is True
    assert format_by_id("pdf").interactive is False


def test_unknown_format_is_rejected(novacart_bundle: ReportBundle) -> None:
    with pytest.raises(KeyError):
        render(novacart_bundle, "powerpoint")


@pytest.mark.parametrize("format_id", AVAILABLE)
def test_available_format_renders_non_empty_output(
    novacart_bundle: ReportBundle, format_id: str
) -> None:
    payload, filename, media_type = render(novacart_bundle, format_id)
    fmt = format_by_id(format_id)
    assert isinstance(payload, bytes)
    assert len(payload) > 512, f"{format_id} produced a suspiciously small artifact"
    assert filename.endswith(fmt.extension)
    assert media_type == fmt.media_type
    assert novacart_bundle.slug in filename


@pytest.mark.parametrize("format_id", AVAILABLE)
def test_available_format_renders_a_scoped_bundle(
    novacart_bundle: ReportBundle, format_id: str
) -> None:
    scoped = scope_bundle(novacart_bundle, journey_id=novacart_bundle.journeys[0].id)
    payload, _, _ = render(scoped, format_id)
    assert len(payload) > 256


@pytest.mark.parametrize("format_id", AVAILABLE)
def test_available_format_renders_a_scenario_bundle(
    scenario_bundle: ReportBundle, format_id: str
) -> None:
    payload, _, _ = render(scenario_bundle, format_id)
    assert len(payload) > 512


# --------------------------------------------------------------------------------------
# Format-specific contracts
# --------------------------------------------------------------------------------------


def test_csv_archive_contains_six_sheets(novacart_bundle: ReportBundle) -> None:
    payload, _, _ = render(novacart_bundle, "csv")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == {
            "metadata.csv",
            "nodes.csv",
            "edges.csv",
            "risks.csv",
            "journeys.csv",
            "decisions.csv",
        }
        assert archive.read("nodes.csv").decode("utf-8").startswith("id,type,label")


def test_svg_export_is_standalone_xml(novacart_bundle: ReportBundle) -> None:
    payload, _, _ = render(novacart_bundle, "svg")
    root = ET.fromstring(payload.decode("utf-8"))
    assert root.tag == "{http://www.w3.org/2000/svg}svg"


def test_scenario_report_declares_the_scenario(scenario_bundle: ReportBundle) -> None:
    assert scenario_bundle.active_scenario == "Rename customer_id to shopper_ref"
    assert scenario_bundle.impact is not None
    assert scenario_bundle.repairs

    markdown = render(scenario_bundle, "markdown")[0].decode("utf-8")
    assert "## Scenario impact" in markdown
    assert "not a prediction about production" in markdown
    assert "Rename customer_id to shopper_ref" in markdown

    html = render(scenario_bundle, "html")[0].decode("utf-8")
    assert "hypothetical estate" in html


# --------------------------------------------------------------------------------------
# Optional dependencies
# --------------------------------------------------------------------------------------


@pytest.mark.skipif(bool(probe_cairosvg()), reason=probe_cairosvg() or "cairosvg available")
@pytest.mark.parametrize("scale", [1, 2, 3])
def test_png_renders_at_every_supported_scale(novacart_bundle: ReportBundle, scale: int) -> None:
    svg = render_svg(novacart_bundle, width=800, height=600, max_nodes=40)
    png = render_png(svg, scale=scale)

    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert png[12:16] == b"IHDR"
    width, height = struct.unpack(">II", png[16:24])
    assert width > 100 and height > 100
    if scale > 1:
        base = struct.unpack(">II", render_png(svg, scale=1)[16:24])
        assert width == pytest.approx(base[0] * scale, abs=scale)


def test_png_scale_must_be_supported(novacart_bundle: ReportBundle) -> None:
    svg = render_svg(novacart_bundle, max_nodes=10)
    with pytest.raises(ValueError):
        render_png(svg, scale=7)


@pytest.mark.skipif(bool(probe_cairosvg()), reason="cairosvg is not installed")
def test_png_export_goes_through_the_registry(novacart_bundle: ReportBundle) -> None:
    payload, filename, media_type = render(novacart_bundle, "png", scale=1, max_nodes=30)
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    assert filename.endswith(".png")
    assert media_type == "image/png"


def test_print_html_is_always_available(novacart_bundle: ReportBundle) -> None:
    """The documented fallback must not itself depend on an optional package."""
    assert format_by_id("print_html").available is True
    document = to_pdf_html(novacart_bundle)
    assert document.startswith("<!doctype html>")
    assert "@page" in document and "counter(page)" in document
    assert "target-counter(attr(href), page)" in document
    assert "break-before: page" in document
    assert "<script" not in document  # the print document is static
    assert novacart_bundle.spec_fingerprint in document


@pytest.mark.skipif(bool(probe_weasyprint()), reason="weasyprint is not installed")
def test_pdf_has_a_cover_contents_and_several_pages(novacart_bundle: ReportBundle) -> None:
    payload = to_pdf(novacart_bundle)
    assert payload[:5] == b"%PDF-"

    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(io.BytesIO(payload))
    assert len(reader.pages) > 1

    cover = reader.pages[0].extract_text()
    assert novacart_bundle.project_name in cover
    assert "API estate report" in cover

    contents = reader.pages[1].extract_text()
    assert "Contents" in contents
    assert "Executive summary" in contents

    body = "\n".join(page.extract_text() for page in reader.pages[2:])
    assert "Methodology" in body
    assert "Limitations" in body


@pytest.mark.skipif(not probe_weasyprint(), reason="weasyprint is installed, so PDF works")
def test_pdf_fails_honestly_without_weasyprint(novacart_bundle: ReportBundle) -> None:
    with pytest.raises(ExportUnavailable) as raised:
        to_pdf(novacart_bundle)
    assert "weasyprint" in str(raised.value).lower()
    assert "print" in str(raised.value).lower()


def test_unavailable_formats_report_their_reason() -> None:
    for fmt in EXPORT_FORMATS:
        if fmt.available:
            continue
        assert fmt.unavailable_reason
        assert "pip install" in fmt.unavailable_reason or "brew install" in fmt.unavailable_reason
