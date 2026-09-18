"""RFC 9457 problem-details errors with correlation IDs.

Every failure the API returns has the same shape and a correlation ID that also appears in
the server log, so "it broke" turns into one greppable string.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("api_galaxy")

PROBLEM_MEDIA_TYPE = "application/problem+json"
BASE_TYPE = "https://api-galaxy.local/problems"


class ApiGalaxyError(Exception):
    """Base class for anything we deliberately turn into a problem response."""

    status_code = 400
    problem_type = "error"
    title = "Request failed"

    def __init__(self, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra = extra


class NotFoundError(ApiGalaxyError):
    status_code = 404
    problem_type = "not-found"
    title = "Not found"


class ValidationFailure(ApiGalaxyError):
    status_code = 422
    problem_type = "invalid-specification"
    title = "The document could not be used"


class ConflictError(ApiGalaxyError):
    status_code = 409
    problem_type = "conflict"
    title = "Conflicting request"


class ConsentMissingError(ApiGalaxyError):
    status_code = 428  # Precondition Required — the precondition is the user's consent.
    problem_type = "consent-required"
    title = "Consent required before sending data off this machine"


class ProviderUnavailableError(ApiGalaxyError):
    status_code = 503
    problem_type = "provider-unavailable"
    title = "The selected provider is not available"


class LimitExceededError(ApiGalaxyError):
    status_code = 413
    problem_type = "limit-exceeded"
    title = "Limit exceeded"


def problem(
    *,
    status: int,
    title: str,
    detail: str,
    problem_type: str = "error",
    correlation_id: str | None = None,
    **extra: Any,
) -> JSONResponse:
    correlation_id = correlation_id or uuid.uuid4().hex[:12]
    body: dict[str, Any] = {
        "type": f"{BASE_TYPE}/{problem_type}",
        "title": title,
        "status": status,
        "detail": detail,
        "correlation_id": correlation_id,
    }
    body.update({k: v for k, v in extra.items() if v is not None})
    return JSONResponse(status_code=status, content=body, media_type=PROBLEM_MEDIA_TYPE)


def install_error_handlers(app) -> None:
    @app.exception_handler(ApiGalaxyError)
    async def _handle_known(request: Request, exc: ApiGalaxyError):  # noqa: ARG001
        correlation_id = uuid.uuid4().hex[:12]
        log.warning("[%s] %s: %s", correlation_id, type(exc).__name__, exc.detail)
        return problem(
            status=exc.status_code,
            title=exc.title,
            detail=exc.detail,
            problem_type=exc.problem_type,
            correlation_id=correlation_id,
            **exc.extra,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError):  # noqa: ARG001
        return problem(
            status=422,
            title="The request body was not valid",
            detail="One or more fields did not match the expected shape.",
            problem_type="invalid-request",
            errors=[
                {"field": ".".join(str(p) for p in err.get("loc", [])), "message": err.get("msg")}
                for err in exc.errors()[:12]
            ],
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException):  # noqa: ARG001
        return problem(
            status=exc.status_code,
            title=str(exc.detail) if exc.status_code < 500 else "Server error",
            detail=str(exc.detail),
            problem_type="http-error",
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception):
        correlation_id = uuid.uuid4().hex[:12]
        log.exception("[%s] unhandled error on %s", correlation_id, request.url.path)
        return problem(
            status=500,
            title="Something went wrong",
            detail=(
                "An unexpected error occurred. The details are in the server log under "
                f"correlation ID {correlation_id}."
            ),
            problem_type="internal",
            correlation_id=correlation_id,
        )
