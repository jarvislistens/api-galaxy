"""Export creation, listing and download.

The export layer is a pure function of a :class:`ReportBundle`, so this router's only
jobs are to build the bundle at the requested scope, run the renderer, and hand back a
file. Availability is probed at import time: a format whose optional dependency is not
installed reports ``available: false`` with the reason, and the UI greys it out instead
of failing on click.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api_galaxy.app.errors import NotFoundError, ValidationFailure
from api_galaxy.app.state import get_state

router = APIRouter(prefix="/api/v1", tags=["exports"])


class ExportRequest(BaseModel):
    format: str
    scenario_id: str | None = None
    journey_id: str | None = None
    domain_id: str | None = None
    node_ids: list[str] = Field(default_factory=list, max_length=2000)
    scale: int = Field(default=2, ge=1, le=3)
    title: str = ""


def _exports_module():
    try:
        from api_galaxy import exports
    except ImportError as exc:  # pragma: no cover - only if the package is broken
        raise NotFoundError(
            "The export layer is not available in this build.", hint=str(exc)
        ) from exc
    return exports


def _decision_records(rows: list[dict[str, Any]]) -> list[Any]:
    """Turn stored decision rows into the contract model the report bundle expects.

    The database keeps `provider` as a plain string and writes "" when a decision had no
    provider (a human edit, say), which is not a valid `ProviderKind` — so it maps to None.
    """
    from api_galaxy.contracts.providers import DecisionRecord, ProviderKind

    records: list[Any] = []
    for row in rows:
        raw_provider = str(row.get("provider") or "")
        try:
            provider = ProviderKind(raw_provider) if raw_provider else None
        except ValueError:
            provider = None
        records.append(
            DecisionRecord(
                id=str(row.get("id", "")),
                project_id=str(row.get("project_id", "")),
                timestamp=str(row.get("timestamp") or ""),
                provider=provider,
                model=str(row.get("model") or ""),
                prompt_template_version=str(row.get("prompt_template_version") or ""),
                task=str(row.get("task") or ""),
                action=str(row.get("action") or ""),
                subject=str(row.get("subject") or ""),
                accepted_payload=row.get("accepted_payload") or {},
                editor=str(row.get("editor") or "local-user"),
                source_references=list(row.get("source_references") or []),
                payload_fingerprint=str(row.get("payload_fingerprint") or ""),
            )
        )
    return records


@router.get("/exports/formats")
async def formats() -> dict[str, Any]:
    exports = _exports_module()
    return {
        "formats": exports.EXPORT_FORMATS,
        "note": "The interactive HTML report is the flagship export: it opens locally with "
        "no backend, no API key and no internet access. The PDF is a static document.",
    }


@router.post("/projects/{project_id}/exports", status_code=201)
async def create_export(project_id: str, payload: ExportRequest) -> dict[str, Any]:
    exports = _exports_module()
    state = get_state()
    live = state.get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")

    catalogue = {f.id: f for f in exports.EXPORT_FORMATS}
    spec = catalogue.get(payload.format)
    if spec is None:
        raise ValidationFailure(
            f"'{payload.format}' is not a known export format. "
            f"Available: {', '.join(sorted(catalogue))}."
        )
    if not spec.available:
        raise ValidationFailure(
            f"{spec.label} is not available in this installation: "
            f"{spec.unavailable_reason or 'a dependency is missing'}."
        )

    scenario = live.scenarios.get(payload.scenario_id) if payload.scenario_id else None
    if payload.scenario_id and scenario is None:
        raise NotFoundError(f"No scenario with id '{payload.scenario_id}'.")

    impact = None
    scenario_graph = None
    if scenario is not None:
        from api_galaxy.analysis.impact import apply_changes, compute_impact

        scenario_graph = apply_changes(live.graph, scenario)
        impact = compute_impact(live.graph, scenario_graph, scenario, live.analysed.journeys)

    bundle = exports.build_bundle(
        live.analysed,
        scenario=scenario,
        impact=impact,
        # A scenario export must show the scenario's graph, while the risks, journeys and
        # disclosure still come from the base analysis.
        graph=scenario_graph,
        decisions=_decision_records(state.storage.list_decisions(project_id)),
        provider_disclosure=live.analysed.enrichment_label,
    )
    if payload.journey_id or payload.domain_id or payload.node_ids:
        bundle = exports.scope_bundle(
            bundle,
            node_ids=set(payload.node_ids) or None,
            journey_id=payload.journey_id,
            domain_id=payload.domain_id,
        )

    # Only pass options the chosen renderer actually understands. The renderers forward
    # their kwargs to the underlying `to_*` function, so an irrelevant one (a `scale` on a
    # Markdown export) is a TypeError rather than something harmlessly ignored.
    options: dict[str, Any] = {}
    if payload.format == "png":
        options["scale"] = payload.scale
    if payload.title and payload.format in ("svg", "png", "mermaid"):
        options["title"] = payload.title

    try:
        data, filename, media_type = exports.render(bundle, payload.format, **options)
    except exports.ExportUnavailable as exc:
        raise ValidationFailure(str(exc)) from exc

    path = state.storage.write_export(project_id, filename, data)
    scope = (
        payload.journey_id
        or payload.domain_id
        or (f"{len(payload.node_ids)} selected nodes" if payload.node_ids else "project")
    )
    record = state.storage.record_export(
        id=f"exp:{uuid.uuid4().hex[:12]}",
        project_id=project_id,
        format=payload.format,
        filename=filename,
        media_type=media_type,
        size_bytes=len(data),
        scope=str(scope)[:120],
        path=str(path),
    )
    return {
        "export": record,
        "download_url": f"/api/v1/exports/{record['id']}/download",
        "interactive": spec.interactive,
    }


@router.get("/projects/{project_id}/exports")
async def list_exports(project_id: str) -> dict[str, Any]:
    state = get_state()
    if state.get(project_id) is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    records = state.storage.list_exports(project_id)
    return {
        "exports": [
            {**r, "download_url": f"/api/v1/exports/{r['id']}/download"} for r in records
        ]
    }


@router.get("/exports/{export_id}/download")
async def download_export(export_id: str) -> FileResponse:
    state = get_state()
    record = state.storage.get_export(export_id)
    if record is None:
        raise NotFoundError(f"No export with id '{export_id}'.")
    from pathlib import Path

    path = Path(record.path)
    # The stored path is always inside the exports directory; re-check before serving it
    # so a tampered database row cannot turn into an arbitrary file read.
    exports_root = state.settings.exports_dir.resolve()
    if not path.is_file() or exports_root not in path.resolve().parents:
        raise NotFoundError("The export file is no longer on disk.")
    return FileResponse(
        path,
        media_type=record.media_type,
        filename=record.filename,
        headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
    )
