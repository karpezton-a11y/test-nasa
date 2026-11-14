"""Contract error format (section 6-I) and exception handlers (shared seam).

Wire format for every error, on every endpoint:
    {"error": {"code": "...", "message": "...", "details": {...}}}

Services raise ``ApiError``; the handlers registered here format it. Anything
unexpected is logged server-side and returned as a sanitized INTERNAL_ERROR.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("trendtrace.errors")

# Codes from contract section 6-I (approved draft).
CONTRACT_ERROR_STATUS: dict[str, int] = {
    "INVALID_REGION": 400,
    "INVALID_VARIABLE": 400,
    "INVALID_SEASON": 400,
    "INVALID_PERIOD": 400,
    "PERIOD_TOO_SHORT": 422,
    "INSUFFICIENT_DATA": 422,
    "DATA_NOT_AVAILABLE": 404,
    "AI_UNAVAILABLE": 503,
    "REPORT_FAILED": 500,
    "INTERNAL_ERROR": 500,
}

# [PROVISIONAL] starter codes, listed as decision D-02 for Member 1 / tonight's freeze.
PROPOSED_ERROR_STATUS: dict[str, int] = {
    "VALIDATION_ERROR": 422,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "PAYLOAD_TOO_LARGE": 413,
    "INVALID_EXPORT_TYPE": 400,
    "INVALID_INDICATOR": 400,
    "INVALID_REPORT_ID": 400,
    "REPORT_NOT_FOUND": 404,
    "HTTP_ERROR": 400,
    # Audit M1 (additive): PDF generation limits. details.retry_after_s also sets a Retry-After header.
    "RATE_LIMITED": 429,
    "REPORT_BUSY": 503,
}

ERROR_STATUS: dict[str, int] = {**CONTRACT_ERROR_STATUS, **PROPOSED_ERROR_STATUS}

GENERIC_INTERNAL_MESSAGE = "Something went wrong on the server. Please try again."


class ApiError(Exception):
    """Domain error raised by services: ApiError(code, http_status, message, details)."""

    def __init__(
        self,
        code: str,
        http_status: int,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.message = message
        self.details = dict(details or {})


def api_error(code: str, message: str, details: dict[str, Any] | None = None) -> ApiError:
    """Build an ApiError with the HTTP status registered for ``code``."""
    if code not in ERROR_STATUS:
        raise KeyError(f"Unknown error code {code!r}; add it to errors.py first")
    return ApiError(code, ERROR_STATUS[code], message, details)


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": dict(details or {})}}


def error_response(code: str, http_status: int, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(status_code=http_status, content=error_body(code, message, details))


def _safe_validation_fields(exc: RequestValidationError) -> list[dict[str, Any]]:
    # Only location, message and error type: never echo the submitted input.
    return [
        {"loc": [str(part) for part in err.get("loc", ())], "msg": str(err.get("msg", "")), "type": str(err.get("type", ""))}
        for err in exc.errors()
    ]


async def _handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
    response = error_response(exc.code, exc.http_status, exc.message, exc.details)
    retry_after = exc.details.get("retry_after_s", exc.details.get("retry_after_seconds"))
    if isinstance(retry_after, int) and retry_after > 0:
        response.headers["Retry-After"] = str(retry_after)
    return response


async def _handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        "VALIDATION_ERROR", 422, "The request is missing a field or has a value in the wrong format.",
        {"fields": _safe_validation_fields(exc)},
    )


async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return error_response("NOT_FOUND", 404, "No such endpoint.")
    if exc.status_code == 405:
        return error_response("METHOD_NOT_ALLOWED", 405, "This HTTP method is not allowed here.")
    if exc.status_code >= 500:
        logger.error("HTTP %s raised inside the app", exc.status_code)
        return error_response("INTERNAL_ERROR", 500, GENERIC_INTERNAL_MESSAGE)
    return error_response("HTTP_ERROR", exc.status_code, "The request could not be processed.")


async def _handle_response_validation(request: Request, exc: ResponseValidationError) -> JSONResponse:
    logger.error("Response failed contract validation on %s: %s", request.url.path, exc.errors())
    return error_response("INTERNAL_ERROR", 500, GENERIC_INTERNAL_MESSAGE)


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response("INTERNAL_ERROR", 500, GENERIC_INTERNAL_MESSAGE)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_request_validation)
    app.add_exception_handler(ResponseValidationError, _handle_response_validation)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)
