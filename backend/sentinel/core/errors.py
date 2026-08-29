"""Application error hierarchy mapped to a single API error envelope."""

from __future__ import annotations

from typing import Any


class SentinelError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str = "internal error", *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            out["details"] = self.details
        return out


class NotFound(SentinelError):
    status_code = 404
    code = "not_found"


class Conflict(SentinelError):
    status_code = 409
    code = "conflict"


class ValidationFailed(SentinelError):
    status_code = 422
    code = "validation_failed"


class Unauthorized(SentinelError):
    status_code = 401
    code = "unauthorized"


class Forbidden(SentinelError):
    status_code = 403
    code = "forbidden"


class RateLimited(SentinelError):
    status_code = 429
    code = "rate_limited"


class InvalidTransition(Conflict):
    code = "invalid_transition"


class UpstreamUnavailable(SentinelError):
    status_code = 503
    code = "upstream_unavailable"


class CircuitOpen(UpstreamUnavailable):
    code = "circuit_open"
