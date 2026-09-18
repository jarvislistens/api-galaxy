"""The export registry: what can be produced, and honestly whether it can be right now.

Availability is probed at import time rather than guessed, because the alternative is a
UI that offers a PDF button which throws when pressed. Optional dependencies (cairosvg
for PNG, weasyprint for PDF) each need system libraries that may or may not be present,
so :data:`EXPORT_FORMATS` carries both ``available`` and the exact ``unavailable_reason``
the user would need to fix it.

Every exporter is a pure function of a :class:`~api_galaxy.exports.bundle.ReportBundle`,
so :func:`render` is a dispatch table and nothing more.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from api_galaxy.exports.bundle import (
    LEGEND,
    METHODOLOGY,
    LegendEntry,
    MethodologyNote,
    ReportBundle,
    build_bundle,
    legend_for,
    scope_bundle,
)
from api_galaxy.exports.diagrams import (
    layout,
    render_journey_mermaid,
    render_mermaid,
    render_png,
    render_print_svg,
    render_svg,
)
from api_galaxy.exports.html_report import external_references, to_html
from api_galaxy.exports.machine import to_csv_bundle, to_graphml, to_jsonld
from api_galaxy.exports.markdown import to_markdown
from api_galaxy.exports.pdf import to_pdf, to_pdf_html
from api_galaxy.exports.support import ExportUnavailable, probe_cairosvg, probe_weasyprint

__all__ = [
    "EXPORT_FORMATS",
    "ExportFormat",
    "ExportUnavailable",
    "LEGEND",
    "METHODOLOGY",
    "LegendEntry",
    "MethodologyNote",
    "ReportBundle",
    "build_bundle",
    "external_references",
    "format_by_id",
    "layout",
    "legend_for",
    "render",
    "render_journey_mermaid",
    "render_mermaid",
    "render_png",
    "render_print_svg",
    "render_svg",
    "scope_bundle",
    "to_csv_bundle",
    "to_graphml",
    "to_html",
    "to_jsonld",
    "to_markdown",
    "to_pdf",
    "to_pdf_html",
]


class ExportFormat(BaseModel):
    id: str
    label: str
    extension: str
    media_type: str
    description: str
    interactive: bool = False
    available: bool = True
    unavailable_reason: str = ""


# Probed once, at import, so the API can serve the catalogue without touching the
# optional packages on every request.
_PNG_REASON = probe_cairosvg()
_PDF_REASON = probe_weasyprint()


EXPORT_FORMATS: list[ExportFormat] = [
    ExportFormat(
        id="html",
        label="Interactive report",
        extension=".html",
        media_type="text/html; charset=utf-8",
        description="One self-contained file: searchable map with pan and zoom, a node "
        "inspector showing provenance and evidence, a journey player, and every report "
        "section. Makes no network requests.",
        interactive=True,
    ),
    ExportFormat(
        id="pdf",
        label="PDF report",
        extension=".pdf",
        media_type="application/pdf",
        description="A paginated static document with a cover page, contents, per-domain "
        "diagrams and print-safe colours. Not interactive.",
        available=not _PDF_REASON,
        unavailable_reason=_PDF_REASON,
    ),
    ExportFormat(
        id="print_html",
        label="Print-ready HTML",
        extension=".print.html",
        media_type="text/html; charset=utf-8",
        description="The PDF's source document. Open it and use your browser's Print to "
        "PDF — page breaks, page numbers and contents all work.",
    ),
    ExportFormat(
        id="markdown",
        label="Markdown report",
        extension=".md",
        media_type="text/markdown; charset=utf-8",
        description="A technical report for a repository or Confluence page, with Mermaid "
        "diagrams that render inline.",
    ),
    ExportFormat(
        id="svg",
        label="Diagram (SVG)",
        extension=".svg",
        media_type="image/svg+xml",
        description="Vector estate map with an embedded legend. Scales to any size and "
        "stays readable in print.",
    ),
    ExportFormat(
        id="png",
        label="Diagram (PNG)",
        extension=".png",
        media_type="image/png",
        description="Raster estate map at 1×, 2× or 3× for slides and documents.",
        available=not _PNG_REASON,
        unavailable_reason=_PNG_REASON,
    ),
    ExportFormat(
        id="mermaid",
        label="Mermaid diagram",
        extension=".mmd",
        media_type="text/vnd.mermaid",
        description="A flowchart in Mermaid source, editable in a pull request and "
        "rendered natively by GitHub, GitLab and Confluence.",
    ),
    ExportFormat(
        id="jsonld",
        label="Knowledge graph (JSON-LD)",
        extension=".jsonld",
        media_type="application/ld+json",
        description="Linked data with a declared vocabulary. Provenance, confidence and "
        "evidence are preserved on every node and relationship.",
    ),
    ExportFormat(
        id="graphml",
        label="Knowledge graph (GraphML)",
        extension=".graphml",
        media_type="application/xml",
        description="Opens directly in Gephi, yEd, Cytoscape and NetworkX.",
    ),
    ExportFormat(
        id="csv",
        label="Spreadsheets (CSV bundle)",
        extension=".zip",
        media_type="application/zip",
        description="Nodes, relationships, findings, journeys, decisions and the report "
        "metadata as six CSV files. Cells are neutralised against formula injection.",
    ),
]

_FORMATS_BY_ID = {fmt.id: fmt for fmt in EXPORT_FORMATS}


def format_by_id(format_id: str) -> ExportFormat:
    try:
        return _FORMATS_BY_ID[format_id]
    except KeyError:
        raise KeyError(
            f"Unknown export format '{format_id}'. Known formats: "
            + ", ".join(sorted(_FORMATS_BY_ID))
        ) from None


# --------------------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------------------


def _render_html(bundle: ReportBundle, **opts: Any) -> bytes:
    return to_html(bundle, **opts).encode("utf-8")


def _render_print_html(bundle: ReportBundle, **_: Any) -> bytes:
    return to_pdf_html(bundle).encode("utf-8")


def _render_pdf(bundle: ReportBundle, **_: Any) -> bytes:
    return to_pdf(bundle)


def _render_markdown(bundle: ReportBundle, **opts: Any) -> bytes:
    return to_markdown(bundle, **opts).encode("utf-8")


def _render_svg(bundle: ReportBundle, **opts: Any) -> bytes:
    return render_svg(bundle, **opts).encode("utf-8")


def _render_png(bundle: ReportBundle, *, scale: int = 2, **opts: Any) -> bytes:
    return render_png(render_svg(bundle, **opts), scale=scale)


def _render_mermaid(bundle: ReportBundle, **opts: Any) -> bytes:
    return render_mermaid(bundle, **opts).encode("utf-8")


def _render_jsonld(bundle: ReportBundle, *, indent: int = 2, **_: Any) -> bytes:
    import json

    return json.dumps(to_jsonld(bundle), indent=indent, ensure_ascii=False).encode("utf-8")


def _render_graphml(bundle: ReportBundle, **_: Any) -> bytes:
    return to_graphml(bundle).encode("utf-8")


def _render_csv(bundle: ReportBundle, **_: Any) -> bytes:
    """Six CSVs in one archive — a browser download has to be a single file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in to_csv_bundle(bundle).items():
            archive.writestr(name, content)
    return buffer.getvalue()


_RENDERERS: dict[str, Callable[..., bytes]] = {
    "html": _render_html,
    "pdf": _render_pdf,
    "print_html": _render_print_html,
    "markdown": _render_markdown,
    "svg": _render_svg,
    "png": _render_png,
    "mermaid": _render_mermaid,
    "jsonld": _render_jsonld,
    "graphml": _render_graphml,
    "csv": _render_csv,
}


def render(bundle: ReportBundle, format_id: str, **opts: Any) -> tuple[bytes, str, str]:
    """Produce ``(payload, filename, media_type)`` for one format.

    Raises :class:`ExportUnavailable` when the format needs a dependency this
    installation does not have — never a partial or substituted artifact.
    """
    fmt = format_by_id(format_id)
    if not fmt.available:
        raise ExportUnavailable(fmt.unavailable_reason, format_id=format_id)
    payload = _RENDERERS[format_id](bundle, **opts)
    return payload, bundle.filename_stem + fmt.extension, fmt.media_type
