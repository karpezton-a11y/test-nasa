"""Audit LOW items: single value lists, frozen results, pinned sub-dependencies, origin check,
security headers, CORS on unexpected 500s, typed stub, no app built at import time, no unused parameter."""

from __future__ import annotations

import importlib
import inspect
import re
from typing import get_args, get_type_hints

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import REPO_ROOT, ConfigError
from app.main import create_app
from app.schemas import PERIOD_PATTERN, Frequency, Season
from app.services import validation
from app.services.store import MockStore
from app.services.unavailable_store import UnavailableRealStore

API = "/api/v1"
ORIGIN = "https://frontend.example"


# ----------------------------------------------------------------- one definition per value list


def test_validation_lists_come_from_the_schema_types():
    assert validation.SEASONS == get_args(Season)
    assert validation.FREQUENCIES == get_args(Frequency)
    assert validation.PERIOD_RE.pattern == PERIOD_PATTERN


# ----------------------------------------------------------------- shared cached results cannot be changed


def test_cached_results_are_frozen(settings):
    store = MockStore(settings.mock_dir / settings.mock_scenario)
    result = store.interaction("IGP", "JJAS")
    with pytest.raises(ValidationError):
        result.guardrail = "changed"
    assert store.interaction("IGP", "JJAS").guardrail.startswith("Association only.")


# ----------------------------------------------------------------- sub-dependencies are pinned


def _pins(name: str) -> dict[str, str]:
    lines = (REPO_ROOT / name).read_text(encoding="utf-8").splitlines()
    pairs = [re.split(r"==", line.split("#")[0].strip(), maxsplit=1) for line in lines]
    return {p[0].lower().replace("_", "-"): p[1] for p in pairs if len(p) == 2}


def test_lock_file_pins_every_direct_dependency_to_the_same_version():
    direct, locked = _pins("requirements.txt"), _pins("requirements.lock")
    assert direct and {name: locked.get(name) for name in direct} == direct
    assert {"starlette", "pillow", "pydantic-core", "numpy"} <= set(locked)


def test_render_installs_with_the_lock_file():
    assert "pip install -r requirements.txt -c requirements.lock" in (REPO_ROOT / "render.yaml").read_text()


# ----------------------------------------------------------------- ALLOWED_ORIGIN must be one real origin


@pytest.mark.parametrize("origin", ["https://frontend.example/", "https://a.example,https://b.example",
                                    "frontend.example", "ftp://frontend.example", "https://frontend.example/app",
                                    "https://frontend.example https://b.example"])
def test_allowed_origin_must_be_scheme_host_and_optional_port(make_settings, origin):
    with pytest.raises(ConfigError, match="ALLOWED_ORIGIN"):
        make_settings(ALLOWED_ORIGIN=origin)


@pytest.mark.parametrize("origin", ["http://localhost:5173", "https://trendtrace.netlify.app", "http://127.0.0.1:8000"])
def test_valid_origins_are_accepted(make_settings, origin):
    assert make_settings(ALLOWED_ORIGIN=origin).allowed_origin == origin


# ----------------------------------------------------------------- headers


@pytest.mark.parametrize("path", ["/health", "/export/csv?region_id=IGP&variable=aod", "/regions?x=1",
                                  "/anomalies?region_id=XX&variable=aod"])
def test_security_headers_on_every_response(client, path):
    response = client.get(f"{API}{path}")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_unexpected_500_keeps_cors_headers_and_contract_body(make_settings, tmp_path, monkeypatch):
    def crash(self):
        raise RuntimeError("bug with /secret/path inside")

    monkeypatch.setattr(MockStore, "variables", crash)
    settings = make_settings(ALLOWED_ORIGIN=ORIGIN, REPORTS_DIR=str(tmp_path))
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        response = c.get(f"{API}/variables", headers={"Origin": ORIGIN})
    assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.headers.get("access-control-allow-origin") == ORIGIN
    assert "secret" not in response.text and response.headers["x-content-type-options"] == "nosniff"


# ----------------------------------------------------------------- code quality items


def test_dev_stub_methods_are_fully_typed():
    for name, method in inspect.getmembers(UnavailableRealStore, inspect.isfunction):
        if not name.startswith("__"):
            hints = get_type_hints(method)
            params = [p for p in inspect.signature(method).parameters if p != "self"]
            assert "return" in hints and all(p in hints for p in params), name


def test_importing_main_builds_no_app_until_asked(monkeypatch):
    import app.main as main

    monkeypatch.setenv("APP_ENV", "not-an-env")
    reloaded = importlib.reload(main)  # a broken environment must not fail at import time
    try:
        with pytest.raises(ConfigError, match="APP_ENV"):
            reloaded.app  # noqa: B018 - uvicorn's `app.main:app` lookup builds it here
    finally:
        monkeypatch.delenv("APP_ENV")
        importlib.reload(main)


def test_assemble_report_has_no_unused_ai_summary_parameter():
    from app.reports.service import assemble_report

    assert "ai_summary" not in inspect.signature(assemble_report).parameters


def test_valid_fraction_rule_monthly_share_daily_null(settings):
    store = MockStore(settings.mock_dir / settings.mock_scenario)
    monthly = store.series("IGP", "aod", "month").points
    daily = store.series("IGP", "aod", "day").points
    assert all(p.valid_fraction is not None and 0 <= p.valid_fraction <= 1 for p in monthly)
    assert any(p.value is None for p in monthly)  # thin months keep their true fraction (e.g. 0.06), value null
    assert all(p.valid_fraction is None for p in daily)
