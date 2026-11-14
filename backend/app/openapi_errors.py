"""OpenAPI error documentation (audit M3): every error response shows the real contract shape.

Routes list the codes they can return with ``error_responses(...)``. ``install_contract_openapi`` then
fixes every other operation (for example Member 1's routes) when ``/openapi.json`` is built: FastAPI's
default 422 schema ``{"detail": [...]}`` becomes ``ErrorResponse`` and a 500 ``INTERNAL_ERROR`` is added.
The wire format itself is set by errors.py; this module only changes the documentation.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from .advanced_schemas import ErrorResponse
from .errors import ERROR_STATUS, GENERIC_INTERNAL_MESSAGE, error_body

COMPONENTS_REF = "#/components/schemas/{model}"
ERROR_SCHEMA_REF = COMPONENTS_REF.format(model="ErrorResponse")
FASTAPI_DEFAULT_SCHEMAS = ("HTTPValidationError", "ValidationError")
EXAMPLE_MESSAGES = {
    "INTERNAL_ERROR": GENERIC_INTERNAL_MESSAGE,
    "VALIDATION_ERROR": "The request is missing a field or has a value in the wrong format.",
}
DEFAULT_EXAMPLE_MESSAGE = "A short message for the user (exact texts: docs/contract.md section I)."


def _examples(codes: list[str]) -> dict[str, Any]:
    return {code: {"summary": code, "value": error_body(code, EXAMPLE_MESSAGES.get(code, DEFAULT_EXAMPLE_MESSAGE))}
            for code in codes}


def error_responses(*codes: str) -> dict[int | str, dict[str, Any]]:
    """``responses=`` for a route: one entry per HTTP status, one example per code. INTERNAL_ERROR is implied."""
    all_codes = list(dict.fromkeys((*codes, "INTERNAL_ERROR")))
    statuses = sorted({ERROR_STATUS[code] for code in all_codes})  # KeyError = unregistered code, fails at import
    return {
        status: {
            "model": ErrorResponse,
            "description": "Error: " + ", ".join(c for c in all_codes if ERROR_STATUS[c] == status),
            "content": {"application/json": {"examples": _examples(
                [c for c in all_codes if ERROR_STATUS[c] == status])}},
        }
        for status in statuses
    }


def _fallback(code: str) -> dict[str, Any]:
    return {"description": f"Error: {code}",
            "content": {"application/json": {"schema": {"$ref": ERROR_SCHEMA_REF}, "examples": _examples([code])}}}


def _patch_operation(operation: dict[str, Any]) -> dict[str, Any]:
    responses = operation.get("responses", {})
    default_422 = "422" in responses and "HTTPValidationError" in json.dumps(responses["422"])
    patched = {**responses, **({"422": _fallback("VALIDATION_ERROR")} if default_422 else {})}
    return {**operation, "responses": {**patched, "500": patched.get("500", _fallback("INTERNAL_ERROR"))}}


def _error_component_schemas() -> dict[str, Any]:
    schema = ErrorResponse.model_json_schema(ref_template=COMPONENTS_REF)
    nested = schema.pop("$defs", {})
    return {**nested, "ErrorResponse": schema}


def contract_openapi(app: FastAPI) -> dict[str, Any]:
    schema = get_openapi(title=app.title, version=app.version, openapi_version=app.openapi_version,
                         description=app.description, routes=app.routes, tags=app.openapi_tags,
                         servers=app.servers)
    paths = {path: {method: _patch_operation(op) for method, op in item.items()}
             for path, item in schema.get("paths", {}).items()}
    components = schema.get("components", {})
    kept = {name: s for name, s in components.get("schemas", {}).items() if name not in FASTAPI_DEFAULT_SCHEMAS}
    return {**schema, "paths": paths,
            "components": {**components, "schemas": {**kept, **_error_component_schemas()}}}


def install_contract_openapi(app: FastAPI) -> None:
    """Replace app.openapi so /openapi.json and /docs show the contract error shape (built once, cached)."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = contract_openapi(app)
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
