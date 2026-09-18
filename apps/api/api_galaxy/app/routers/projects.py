"""Project lifecycle: validate, import, inspect, delete — plus the job stream."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api_galaxy import __version__
from api_galaxy.analysis.rules import RULE_CATALOG
from api_galaxy.app.errors import LimitExceededError, NotFoundError, ValidationFailure
from api_galaxy.app.state import AppState, get_state
from api_galaxy.contracts.analysis import EstateOverview
from api_galaxy.contracts.graph import EdgeType, NodeType
from api_galaxy.contracts.ids import slugify
from api_galaxy.parsing.loader import (
    SpecLoadError,
    detect_format,
    load_spec_text,
    looks_like_manifest,
    looks_like_openapi,
    looks_like_postman,
)
from api_galaxy.parsing.normalize import DiagnosticLevel
from api_galaxy.parsing.openapi import parse_estate
from api_galaxy.pipeline import analyse, analyse_manifest

router = APIRouter(prefix="/api/v1", tags=["projects"])

DEMO_PROJECT_ID = "demo-novacart"


# --------------------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------------------


class SpecPayload(BaseModel):
    content: str = Field(min_length=1)
    filename: str = "spec.yaml"


class ImportRequest(BaseModel):
    name: str = Field(default="", max_length=120)
    documents: list[SpecPayload] = Field(default_factory=list, max_length=32)


class ValidateResponse(BaseModel):
    valid: bool
    kind: str
    format: str
    title: str = ""
    version: str = ""
    counts: dict[str, int] = Field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None


# --------------------------------------------------------------------------------------
# Validation and preview
# --------------------------------------------------------------------------------------


@router.post("/specs/validate", response_model=ValidateResponse)
async def validate_spec(payload: SpecPayload) -> ValidateResponse:
    """Parse a document without importing it, so the drop zone can fail fast and precisely."""
    state = get_state()
    if len(payload.content.encode("utf-8")) > state.settings.max_upload_bytes:
        raise LimitExceededError(
            f"That document is larger than the "
            f"{state.settings.max_upload_bytes // 1024 // 1024} MB limit."
        )
    try:
        document = load_spec_text(payload.content, source_file=payload.filename)
    except SpecLoadError as exc:
        return ValidateResponse(
            valid=False,
            kind="unknown",
            format=detect_format(payload.content, payload.filename),
            error=exc.to_dict(),
        )

    data = document.data
    if looks_like_manifest(data):
        return ValidateResponse(
            valid=True, kind="manifest", format=document.format,
            title=str((data.get("metadata") or {}).get("name") or ""),
        )
    kind = "postman" if looks_like_postman(data) else "openapi"
    if kind == "openapi" and not looks_like_openapi(data):
        return ValidateResponse(
            valid=False,
            kind="unknown",
            format=document.format,
            error={
                "message": "This is valid "
                + document.format.upper()
                + ", but it is not an OpenAPI document or a Postman collection.",
                "field_path": "openapi",
                "hint": "An OpenAPI document has a top-level `openapi: 3.x.x` key.",
            },
        )

    try:
        estate = parse_estate(
            [(payload.content, _service_name(payload.filename), None)],
            name=_service_name(payload.filename),
        )
    except SpecLoadError as exc:
        return ValidateResponse(valid=False, kind=kind, format=document.format,
                                error=exc.to_dict())

    service = estate.services[0]
    errors = [d for d in estate.diagnostics if d.level is DiagnosticLevel.ERROR]
    return ValidateResponse(
        valid=not errors,
        kind=kind,
        format=document.format,
        title=service.title,
        version=service.version,
        counts={
            "operations": len(service.operations),
            "schemas": len(service.schemas),
            "fields": sum(len(s.fields) for s in service.schemas),
            "security_schemes": len(service.security_schemes),
        },
        diagnostics=[d.model_dump(mode="json") for d in estate.diagnostics[:40]],
        preview={
            "service": service.name,
            "operations": [
                {"id": op.operation_id, "method": op.method.upper(), "path": op.path,
                 "summary": op.summary, "deprecated": op.deprecated}
                for op in service.operations[:20]
            ],
            "schemas": [s.name for s in service.schemas[:30]],
        },
    )


# --------------------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------------------


@router.post("/projects/demo", status_code=201)
async def create_demo_project() -> dict[str, Any]:
    """Load the bundled NovaCart estate. Idempotent: re-calling reuses the same project."""
    state = get_state()
    existing = state.get(DEMO_PROJECT_ID)
    if existing is not None:
        return {
            "project_id": DEMO_PROJECT_ID,
            "created": False,
            "stats": existing.graph.stats().model_dump(),
        }

    manifest = state.settings.resolve_samples_dir() / "novacart" / "novacart-manifest.yaml"
    if not manifest.is_file():
        raise NotFoundError(
            f"The bundled sample estate is missing (expected {manifest}).",
            hint="Re-clone the repository or set API_GALAXY_SAMPLES_DIR.",
        )
    project = analyse_manifest(manifest, project_id=DEMO_PROJECT_ID)
    live = state.register(project, is_demo=True, source_kind="demo")
    return {
        "project_id": DEMO_PROJECT_ID,
        "created": True,
        "stats": live.graph.stats().model_dump(),
        "enrichment": project.enrichment_label,
    }


@router.post("/projects/import", status_code=202)
async def import_project(payload: ImportRequest) -> dict[str, Any]:
    """Import one or more pasted documents. Runs as a job so the UI can show stages."""
    state = get_state()
    if not payload.documents:
        raise ValidationFailure("No documents were supplied.")
    if state.project_count() >= state.settings.max_projects:
        raise LimitExceededError(
            f"You already have {state.settings.max_projects} projects. Delete one first."
        )
    total = sum(len(d.content.encode("utf-8")) for d in payload.documents)
    if total > state.settings.max_upload_bytes:
        raise LimitExceededError("The documents exceed the upload limit in total.")

    name = payload.name or _service_name(payload.documents[0].filename)
    project_id = f"proj-{slugify(name)}-{uuid.uuid4().hex[:6]}"
    sources = [(d.content, _service_name(d.filename), None) for d in payload.documents]

    job = state.jobs.start(
        "import",
        _import_body(state, project_id, name, sources),
        project_id=project_id,
    )
    return {"job_id": job.id, "project_id": project_id}


@router.post("/projects/upload", status_code=202)
async def upload_project(
    files: list[UploadFile] = File(...),
    name: str = "",
) -> dict[str, Any]:
    """Multipart upload path used by the drag-and-drop zone."""
    state = get_state()
    if not files:
        raise ValidationFailure("No files were uploaded.")
    if len(files) > 32:
        raise LimitExceededError("Up to 32 files can be imported at once.")

    documents: list[SpecPayload] = []
    total = 0
    for upload in files:
        raw = await upload.read()
        total += len(raw)
        if total > state.settings.max_upload_bytes:
            raise LimitExceededError("The uploaded files exceed the size limit in total.")
        filename = _safe_filename(upload.filename or "spec.yaml")
        if not filename.lower().endswith((".json", ".yaml", ".yml")):
            raise ValidationFailure(
                f"'{filename}' is not a .json, .yaml or .yml file.",
                hint="API Galaxy reads OpenAPI documents and Postman collections.",
            )
        try:
            documents.append(SpecPayload(content=raw.decode("utf-8"), filename=filename))
        except UnicodeDecodeError as exc:
            raise ValidationFailure(f"'{filename}' is not UTF-8 text.") from exc

    return await import_project(ImportRequest(name=name, documents=documents))


def _import_body(state: AppState, project_id: str, name: str, sources):
    async def body(handle) -> dict[str, Any]:
        await handle.progress(0.05, "Reading documents", f"{len(sources)} file(s)")
        await asyncio.sleep(0)
        try:
            estate = parse_estate(sources, name=name)
        except SpecLoadError as exc:
            raise ValidationFailure(exc.message, **exc.to_dict()) from exc

        await handle.progress(0.45, "Building the graph",
                              f"{len(estate.all_operations)} operations")
        await asyncio.sleep(0)
        project = analyse(estate, project_id=project_id, project_name=name)

        await handle.progress(0.85, "Running deterministic analysis",
                              f"{len(project.risks)} finding(s)")
        await asyncio.sleep(0)
        state.register(project, source_kind="upload")

        stats = project.graph.stats()
        await handle.progress(1.0, "Done", f"{stats.nodes} nodes, {stats.edges} edges")
        return {
            "project_id": project_id,
            "stats": stats.model_dump(),
            "risks": len(project.risks),
            "journeys": len(project.journeys),
            "diagnostics": len(estate.diagnostics),
        }

    return body


# --------------------------------------------------------------------------------------
# Read
# --------------------------------------------------------------------------------------


@router.get("/projects")
async def list_projects() -> dict[str, Any]:
    return {"projects": get_state().storage.list_projects()}


@router.get("/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    state = get_state()
    live = state.get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    record = state.storage.get_project(project_id) or {}
    project = live.analysed
    return {
        **record,
        "id": project_id,
        "name": project.project_name,
        "stats": project.graph.stats().model_dump(),
        "coverage": project.estate.coverage(),
        "enrichment_label": project.enrichment_label,
        "enrichment_warnings": project.enrichment_warnings,
        "services": [
            {
                "id": node.id,
                "name": node.label,
                "slug": node.attrs.get("slug"),
                "operations": node.attrs.get("operations"),
                "schemas": node.attrs.get("schemas"),
                "source_file": node.attrs.get("source_file"),
            }
            for node in project.graph.nodes_of(NodeType.SERVICE)
        ],
        "scenarios": [
            {"id": s.id, "name": s.name, "changes": len(s.changes)}
            for s in live.scenarios.values()
        ],
    }


@router.get("/projects/{project_id}/overview", response_model=EstateOverview)
async def overview(project_id: str) -> EstateOverview:
    """Everything the Overview screen asks: what is here, what matters, what to do next."""
    state = get_state()
    live = state.get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    project = live.analysed
    graph = project.graph
    stats = graph.stats()
    index = graph.node_index()

    domains = []
    for node in graph.nodes_of(NodeType.DOMAIN):
        members = [
            e.source for e in graph.edges
            if e.type is EdgeType.BELONGS_TO_DOMAIN and e.target == node.id
        ]
        services = [m for m in members if m in index and index[m].type is NodeType.SERVICE]
        operations = [m for m in members if m in index and index[m].type is NodeType.API_OPERATION]
        domains.append(
            {
                "id": node.id,
                "name": node.label,
                "description": node.description,
                "services": [index[s].label for s in services],
                "service_ids": services,
                "operation_count": len(operations),
                "risk_count": sum(
                    1
                    for risk in graph.nodes_of(NodeType.RISK)
                    for e in graph.edges
                    if e.type is EdgeType.AFFECTS
                    and e.source == risk.id
                    and e.target in set(members)
                ),
            }
        )

    journeys = [
        {
            "id": j.id,
            "name": j.name,
            "description": j.description,
            "steps": len(j.steps),
            "services": sorted({
                str(index[s.operation_id].attrs.get("service"))
                for s in j.steps
                if s.operation_id and s.operation_id in index
            }),
            "source": j.provenance.source_kind.value,
            "has_deprecated_step": any(s.deprecated for s in j.steps),
        }
        for j in project.journeys
    ]

    return EstateOverview(
        project_id=project_id,
        project_name=project.project_name,
        counts={
            "services": stats.services,
            "operations": stats.operations,
            "schemas": stats.schemas,
            "fields": stats.fields,
            "domains": stats.domains,
            "journeys": stats.journeys,
            "risks": stats.risks,
            "entities": stats.entities,
            "capabilities": stats.capabilities,
            "nodes": stats.nodes,
            "edges": stats.edges,
            "observed_relationships": stats.observed_edges,
            "inferred_relationships": stats.inferred_edges,
            "accepted_inferences": stats.accepted_inferences,
        },
        domains=domains,
        journeys=journeys,
        top_risks=project.risks[:8],
        ambiguities=project.ambiguities,
        parse_coverage=project.estate.coverage(),
        enrichment={
            "label": project.enrichment_label,
            "warnings": project.enrichment_warnings,
            "is_bundled": project.enrichment_label == "Bundled Demo Analysis",
        },
        derivation=[
            {
                "step": "Parse",
                "detail": f"{len(project.estate.services)} specification(s) were parsed "
                f"deterministically into {stats.operations} operations and {stats.schemas} "
                "schemas. Nothing here was guessed.",
            },
            {
                "step": "Build",
                "detail": f"{stats.nodes} nodes and {stats.observed_edges} observed "
                "relationships were derived from the documents. Every one records the file "
                "and JSON Pointer it came from.",
            },
            {
                "step": "Analyse",
                "detail": f"{len(RULE_CATALOG)} rules ran, producing {len(project.risks)} "
                "finding(s). Rules that make a judgement are labelled heuristic.",
            },
            {
                "step": "Interpret",
                "detail": (
                    f"{stats.inferred_edges} relationship(s) are suggestions rather than "
                    f"statements — from the alias rule and from {project.enrichment_label}. "
                    "They are drawn dashed and you can accept, edit or reject each one."
                ),
            },
        ],
    )


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str) -> dict[str, Any]:
    state = get_state()
    state.forget(project_id)
    removed = state.storage.delete_project(project_id)
    if not removed:
        raise NotFoundError(f"No project with id '{project_id}'.")
    return {"deleted": True, "project_id": project_id}


@router.get("/projects/{project_id}/diagnostics")
async def diagnostics(project_id: str) -> dict[str, Any]:
    live = get_state().get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    return {
        "diagnostics": [d.model_dump(mode="json") for d in live.analysed.estate.diagnostics],
        "coverage": live.analysed.estate.coverage(),
    }


@router.get("/projects/{project_id}/risks")
async def risks(project_id: str, severity: str | None = None) -> dict[str, Any]:
    live = get_state().get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    items = live.analysed.risks
    if severity:
        wanted = {s.strip().lower() for s in severity.split(",")}
        items = [r for r in items if r.severity.value in wanted]
    return {
        "risks": [r.model_dump(mode="json") for r in items],
        "catalog": RULE_CATALOG,
    }


# --------------------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------------------


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    job = get_state().jobs.get(job_id)
    if job is None:
        raise NotFoundError(f"No job with id '{job_id}'.")
    return job.snapshot()


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict[str, Any]:
    cancelled = get_state().jobs.cancel(job_id)
    if not cancelled:
        raise NotFoundError(f"Job '{job_id}' is unknown or already finished.")
    return {"cancelled": True, "job_id": job_id}


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    """Server-sent events for job progress. Closes as soon as the job reaches a terminal
    state so the browser does not hold a connection open forever."""
    state = get_state()
    job = state.jobs.get(job_id)
    if job is None:
        raise NotFoundError(f"No job with id '{job_id}'.")

    async def stream():
        queue = state.jobs.subscribe(job_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
                if payload.get("status") in ("succeeded", "failed", "cancelled"):
                    break
        finally:
            state.jobs.unsubscribe(job_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/meta")
async def meta() -> dict[str, Any]:
    state = get_state()
    return {
        "app": "API Galaxy",
        "version": __version__,
        "data_dir": str(state.settings.data_dir),
        "rules": RULE_CATALOG,
        "limits": {
            "max_upload_bytes": state.settings.max_upload_bytes,
            "max_projects": state.settings.max_projects,
            "allow_remote_refs": state.settings.allow_remote_refs,
        },
    }


# --------------------------------------------------------------------------------------


def _service_name(filename: str) -> str:
    stem = filename.rsplit("/", 1)[-1]
    for suffix in (".yaml", ".yml", ".json"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem or "service"


def _safe_filename(filename: str) -> str:
    """Strip any directory component so an upload cannot name a path."""
    cleaned = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return "".join(ch for ch in cleaned if ch.isalnum() or ch in "-_. ") or "spec.yaml"
