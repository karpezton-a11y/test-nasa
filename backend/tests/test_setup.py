"""Step 1: app skeleton, envelope, error handlers, body limit and startup guard."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.config import ConfigError, load_settings
from app.errors import CONTRACT_ERROR_STATUS, ApiError, api_error
from app.main import create_app

ENVELOPE_KEYS = {"data_status", "data_version", "contract_version", "generated_at", "result"}


class EchoBody(BaseModel):
    name: str
    years: int


def _app_with_test_routes(settings):
    """Test-only routes; production code has no debug/crash endpoints."""
    app = create_app(settings)
    router = APIRouter()

    @router.post("/api/v1/_test/echo")
    def echo(body: EchoBody) -> dict:
        return {"ok": body.name}

    @router.get("/api/v1/_test/api-error")
    def raise_api_error() -> dict:
        raise api_error("PERIOD_TOO_SHORT", "Choose at least 10 years.", {"min_years": 10})

    @router.get("/api/v1/_test/crash")
    def crash() -> dict:
        raise RuntimeError("secret path /etc/passwd token=abc123")

    app.include_router(router)
    return app


@pytest.fixture
def test_client(settings):
    with TestClient(_app_with_test_routes(settings), raise_server_exceptions=False) as c:
        yield c


def test_health_returns_envelope_with_aware_timestamp(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == ENVELOPE_KEYS
    assert body["contract_version"] == "1.0"
    stamp = datetime.fromisoformat(body["generated_at"])
    assert stamp.tzinfo is not None and stamp.utcoffset() is not None
    assert body["result"]["status"] == "ok"
    assert body["result"]["ai_available"] is False


def test_api_error_uses_contract_shape(test_client):
    response = test_client.get("/api/v1/_test/api-error")
    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "PERIOD_TOO_SHORT", "message": "Choose at least 10 years.", "details": {"min_years": 10}}
    }


def test_request_validation_error_uses_contract_shape_without_echoing_input(test_client):
    response = test_client.post("/api/v1/_test/echo", json={"name": "x", "years": "secret-value"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["fields"][0]["loc"] == ["body", "years"]
    assert "secret-value" not in response.text


def test_unexpected_error_is_sanitized(test_client):
    response = test_client.get("/api/v1/_test/crash")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["error"]["details"] == {}
    for leaked in ("passwd", "abc123", "RuntimeError", "Traceback"):
        assert leaked not in response.text


def test_unknown_path_returns_contract_error(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_every_contract_code_has_documented_status():
    assert CONTRACT_ERROR_STATUS == {
        "INVALID_REGION": 400, "INVALID_VARIABLE": 400, "INVALID_SEASON": 400, "INVALID_PERIOD": 400,
        "PERIOD_TOO_SHORT": 422, "INSUFFICIENT_DATA": 422, "DATA_NOT_AVAILABLE": 404,
        "AI_UNAVAILABLE": 503, "REPORT_FAILED": 500, "INTERNAL_ERROR": 500,
    }
    with pytest.raises(KeyError):
        api_error("NOT_A_CODE", "x")
    assert isinstance(api_error("INVALID_REGION", "x"), ApiError)


def test_prod_with_mock_data_refuses_to_start(make_settings):
    app = create_app(make_settings(APP_ENV="prod", DATA_MODE="mock"))
    with pytest.raises(ConfigError, match="prod"):
        with TestClient(app):
            pass


@pytest.mark.parametrize("env", [
    {"APP_ENV": "staging"}, {"DATA_MODE": "fake"}, {"ALLOWED_ORIGIN": "*"}, {"MAX_BODY_BYTES": "0"},
])
def test_invalid_config_values_fail_clearly(env):
    with pytest.raises(ConfigError):
        load_settings(env=env, env_file=None)


def test_body_limit_rejects_declared_oversized_body(make_settings, tmp_path):
    app = _app_with_test_routes(make_settings(MAX_BODY_BYTES="64", REPORTS_DIR=str(tmp_path)))
    with TestClient(app) as c:
        response = c.post("/api/v1/_test/echo", json={"name": "x" * 200, "years": 1})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_body_limit_counts_streamed_body_without_content_length(make_settings, tmp_path):
    app = _app_with_test_routes(make_settings(MAX_BODY_BYTES="64", REPORTS_DIR=str(tmp_path)))

    def chunks():
        for _ in range(10):
            yield b"0123456789"

    with TestClient(app) as c:
        response = c.post("/api/v1/_test/echo", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_cors_allows_only_the_configured_origin(make_settings, tmp_path):
    settings = make_settings(ALLOWED_ORIGIN="https://frontend.example", REPORTS_DIR=str(tmp_path))
    preflight = {"Access-Control-Request-Method": "GET"}
    with TestClient(create_app(settings)) as c:
        allowed = c.options("/api/v1/health", headers={"Origin": "https://frontend.example", **preflight})
        other = c.options("/api/v1/health", headers={"Origin": "https://evil.example", **preflight})
        simple = c.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert allowed.headers.get("access-control-allow-origin") == "https://frontend.example"
    assert "access-control-allow-origin" not in other.headers
    assert "access-control-allow-origin" not in simple.headers


def test_debug_is_off_in_every_environment(make_settings, tmp_path):
    for env in ("dev", "prod"):
        app = create_app(make_settings(APP_ENV=env, DATA_MODE="real" if env == "prod" else "mock",
                                       REPORTS_DIR=str(tmp_path)))
        assert app.debug is False


def test_body_within_limit_is_passed_through(test_client):
    response = test_client.post("/api/v1/_test/echo", json={"name": "ok", "years": 10})
    assert response.status_code == 200
    assert response.json() == {"ok": "ok"}
