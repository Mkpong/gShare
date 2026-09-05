"""Error envelope + domain exceptions + FastAPI exception handlers.

Envelope shape::

    {"error": {"code", "message", "details", "request_id", "timestamp"}}

Domain exception -> HTTP/code mapping:
    InsufficientCredit -> 402 insufficient_credit
    BudgetExceeded -> 409 budget_exceeded
    QuotaExceeded -> 409 quota_exceeded
    NoCapacity -> 409 no_capacity
    InvalidStateTransition -> 409 invalid_state_transition
    IdempotencyInProgress -> 409 idempotency_in_progress
    IdempotencyKeyRequired -> 400 idempotency_key_required
    Unauthenticated -> 401 unauthenticated
    Forbidden -> 403 forbidden
    NotFound -> 404 not_found
    (pydantic ValidationError) -> 422 validation_failed
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

log = get_logger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class DomainError(Exception):
    """Base domain error carrying code/http/message/details (-> envelope)."""

    code: str = "internal_error"
    http: int = 500

    def __init__(self, message: str | None = None, details: dict[str, Any] | None = None):
        self.message = message or self.code
        self.details = details or {}
        super().__init__(self.message)


# ── Credit / budget ──
class InsufficientCredit(DomainError):
    code, http = "insufficient_credit", 402

    def __init__(self, available: Any = None, need: Any = None):
        super().__init__("insufficient credit", {"available": str(available), "need": str(need)})


class BudgetExceeded(DomainError):
    code, http = "budget_exceeded", 409


# ── Scheduling / capacity ──
class QuotaExceeded(DomainError):
    code, http = "quota_exceeded", 409


class NoCapacity(DomainError):
    code, http = "no_capacity", 409


class RateLimited(DomainError):
    code, http = "rate_limited", 429


class Unserviceable(DomainError):
    # The cluster has no ready device of the requested mode and model at all — queueing would
    # wait forever, so the request is rejected outright rather than enqueued.
    code, http = "unserviceable", 409


class ImbalancedAllocation(DomainError):
    # When a fractional request's core and VRAM shares diverge too far — 1 GB with 100% of the
    # cores, say — it makes the physical GPU useless for compute to every other session on it.
    # Rejected as anti-fragmentation.
    code, http = "imbalanced_allocation", 422


class VramBelowMinimum(DomainError):
    # A fractional slice below GPU_MIN_FRACTIONAL_MEM_MB cannot even hold a CUDA context, so it is
    # unusable in practice. The server-side counterpart to the console disabling tiers under 1 GB
    # for the selected GPU.
    code, http = "vram_below_minimum", 422


class IncompatibleImage(DomainError):
    # The image's CUDA version is below the selected offering's minimum, so it cannot run on that
    # card.
    code, http = "incompatible_image", 422


class NotImplementedFeature(DomainError):
    # The endpoint exists in the contract but the behavior behind it is not built yet. Answering
    # 501 honestly beats returning a fabricated success (a "restoring" that restores nothing).
    code, http = "not_implemented", 501


# ── Lifecycle / idempotency ──
class InvalidStateTransition(DomainError):
    code, http = "invalid_state_transition", 409


class IdempotencyInProgress(DomainError):
    code, http = "idempotency_in_progress", 409


class IdempotencyKeyRequired(DomainError):
    code, http = "idempotency_key_required", 400


# ── Auth ──
class Unauthenticated(DomainError):
    code, http = "unauthenticated", 401


class Forbidden(DomainError):
    code, http = "forbidden", 403


class PasswordChangeRequired(DomainError):
    # Blocks every API call with 403 until the password is changed after a first login or a reset.
    # The console keys off this code to send the user to the change-password screen.
    code, http = "password_change_required", 403


class AlreadyExists(DomainError):
    # A uniqueness collision (same name/type in the same scope). Distinct from quota_exceeded:
    # nothing is full — the name is simply taken, and the console must say so.
    code, http = "already_exists", 409


class NotFound(DomainError):
    code, http = "not_found", 404


# Stable codes for the HTTP statuses the framework raises on its own.
_HTTP_STATUS_CODES = {
    400: "bad_request", 401: "unauthenticated", 403: "forbidden", 404: "not_found",
    405: "method_not_allowed", 409: "conflict", 413: "payload_too_large",
    415: "unsupported_media_type", 429: "rate_limited",
}


def register_exception_handlers(app: FastAPI) -> None:
    """Install envelope handlers on the app."""

    @app.exception_handler(DomainError)
    async def _domain(req: Request, exc: DomainError):  # noqa: ANN202
        return JSONResponse(
            status_code=exc.http,
            content={"error": {
                "code": exc.code, "message": exc.message, "details": exc.details,
                "request_id": getattr(req.state, "request_id", None),
                "timestamp": _utcnow_iso(),
            }},
        )

    # Framework-raised HTTP errors (unknown route → 404, wrong verb → 405, auth dependencies that
    # raise HTTPException) wear the same envelope as domain errors: the console keys off
    # ``error.code`` everywhere, and a bare ``{"detail": ...}`` was the one shape it could not map.
    @app.exception_handler(StarletteHTTPException)
    async def _http(req: Request, exc: StarletteHTTPException):  # noqa: ANN202
        code = _HTTP_STATUS_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) and exc.detail else code.replace("_", " ")
        return JSONResponse(
            status_code=exc.status_code,
            headers=dict(exc.headers) if getattr(exc, "headers", None) else None,
            content={"error": {
                "code": code, "message": message, "details": None,
                "request_id": getattr(req.state, "request_id", None),
                "timestamp": _utcnow_iso(),
            }},
        )

    # Anything else is a bug: log it with the request id so the envelope's id leads straight to
    # the traceback, and never leak the exception text to the caller.
    @app.exception_handler(Exception)
    async def _unhandled(req: Request, exc: Exception):  # noqa: ANN202
        rid = getattr(req.state, "request_id", None)
        log.exception("unhandled error request_id=%s path=%s", rid, req.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": {
                "code": "internal_error", "message": "internal server error", "details": None,
                "request_id": rid, "timestamp": _utcnow_iso(),
            }},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(req: Request, exc: RequestValidationError):  # noqa: ANN202
        # Keep only the JSON-safe fields: a custom field_validator's ValueError rides along in
        # ctx["error"] as the exception OBJECT, and serializing it raised — turning every custom
        # validation failure into a 500 instead of this 422.
        errors = [
            {"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": {
                "code": "validation_failed", "message": "validation failed",
                "details": {"errors": errors},
                "request_id": getattr(req.state, "request_id", None),
                "timestamp": _utcnow_iso(),
            }},
        )
