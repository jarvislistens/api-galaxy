"""The FastAPI application.

Local-first means the server binds to loopback by default, CORS is limited to the dev web
app, and there is no authentication because there is no multi-user story — your data
never leaves the machine unless you explicitly consent to an external provider call.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api_galaxy import __version__
from api_galaxy.app.errors import install_error_handlers, problem
from api_galaxy.app.routers import (
    ask,
    exports,
    graph,
    journeys,
    missions,
    projects,
    providers,
    scenarios,
)
from api_galaxy.app.settings import get_settings
from api_galaxy.app.state import get_state

log = logging.getLogger("api_galaxy")

DESCRIPTION = """\
API Galaxy turns OpenAPI specifications into a living, evidence-backed model of an API
estate — one you can explore, question, safely break, repair, compare across models and
share.

Two things are true of every response from this API:

* every node, edge, risk, answer and impact item records where it came from, and
* deterministic facts and model inferences are never merged.
"""


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="API Galaxy",
        description=DESCRIPTION,
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _install_rate_limit(app, settings.request_rate_limit_per_minute)
    install_error_handlers(app)

    for router in (
        projects.router,
        graph.router,
        journeys.router,
        ask.router,
        scenarios.router,
        providers.router,
        exports.router,
        missions.router,
    ):
        app.include_router(router)

    @app.get("/api/v1/health", tags=["meta"])
    async def health() -> dict[str, Any]:
        state = get_state()
        return {
            "status": "ok",
            "version": __version__,
            "projects": state.project_count(),
            "data_dir": str(state.settings.data_dir),
            "cache": state.cache.stats(),
        }

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, Any]:
        return {
            "name": "API Galaxy",
            "version": __version__,
            "docs": "/api/docs",
            "health": "/api/v1/health",
            "promise": "Drop your API. Watch it come alive. Ask how it works. "
            "Break it before production does.",
        }

    return app


@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    state = get_state()
    log.info(
        "API Galaxy %s ready — data dir %s, %d project(s)",
        __version__,
        state.settings.data_dir,
        state.project_count(),
    )
    yield


def _install_rate_limit(app: FastAPI, per_minute: int) -> None:
    """A token-bucket-ish limiter so a runaway client cannot pin the machine.

    Deliberately in-memory and per-process: this protects a single-user local app from a
    loop in the browser, not a public endpoint from an attacker.
    """
    buckets: dict[str, deque[float]] = defaultdict(deque)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            client = request.client.host if request.client else "local"
            now = time.monotonic()
            window = buckets[client]
            while window and now - window[0] > 60.0:
                window.popleft()
            if len(window) >= per_minute:
                return problem(
                    status=429,
                    title="Too many requests",
                    detail=f"More than {per_minute} requests in a minute from this client.",
                    problem_type="rate-limited",
                )
            window.append(now)
        return await call_next(request)


app = create_app()
