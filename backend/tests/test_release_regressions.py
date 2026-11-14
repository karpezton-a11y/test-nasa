"""Reproductions found during the combined backend release review."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Event

import pytest
from fastapi.testclient import TestClient

from app.advanced_schemas import ReportRequest
from app.ai.facts import build_facts
from app.ai.guardrails import check
from app.ai.service import ExplanationService, RateLimiter
from app.ai.templates import render
from app.errors import api_error
from app.main import create_app
from app.reports.service import assemble_report
from app.reports.store import ReportFileStore
from app.schemas import Period
from app.services.store import MockStore
from app.config import REPO_ROOT


@pytest.mark.parametrize("endpoint", ["timeseries", "anomalies", "export/csv"])
@pytest.mark.parametrize("parameter", ["start", "end"])
def test_empty_period_parameters_are_invalid(client, endpoint, parameter):
    response = client.get(f"/api/v1/{endpoint}", params={
        "region_id": "IGP", "variable": "aod", parameter: "",
    })
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PERIOD"


def test_period_with_trailing_newline_is_not_iso(client):
    response = client.get("/api/v1/export/csv", params={
        "region_id": "IGP", "variable": "aod", "end": "2024-12\n",
    })
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PERIOD"


@pytest.mark.parametrize("literal", [".987654321", "-.987654321", "+.987654321"])
def test_guardrail_catches_leading_decimal_numbers(literal):
    store = MockStore(REPO_ROOT / "data/mock/normal")
    trend = store.trend("IGP", "aod", Period(start="2003-01", end="2024-12"), "all")
    facts = build_facts([trend], data_status="mock", data_version="MOCK-test")
    output = render(facts)
    output.text += f" The value is {literal}."
    assert "unsupported_number" in check(output, facts)


def test_explain_holds_capacity_for_the_whole_generation(make_settings):
    entered, release = Event(), Event()

    class BlockingClient:
        def generate(self, facts):
            entered.set()
            assert release.wait(5), "test did not release provider"
            return render(facts).model_dump()

    app = create_app(make_settings(LLM_API_KEY="test-only"))
    app.state.explanations = ExplanationService(app.state.settings, BlockingClient())
    # Use one slot to make the concurrency boundary deterministic, without sleeps.
    app.state.explanations.limiter = RateLimiter()
    app.state.explanations.limiter._slots = BoundedSemaphore(1)
    body = {"result_type": "trend", "result_id": "trend_IGP_aod_all_2003-01_2024-12"}
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, "/api/v1/explain", json=body)
        try:
            assert entered.wait(5), "provider did not start"
            busy = client.post("/api/v1/explain", json=body)
            assert busy.status_code == 503
            assert busy.json()["error"]["code"] == "AI_UNAVAILABLE"
            assert "report" not in busy.json()["error"]["message"].lower()
            assert int(busy.headers["Retry-After"]) > 0
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 200
        assert client.post("/api/v1/explain", json=body).status_code == 200


def test_report_coverage_uses_selected_season(monkeypatch):
    store = MockStore(REPO_ROOT / "data/mock/normal")
    original = store.series

    def selected_series(*args):
        series = original(*args)
        series.points = [p if p.date.month in {6, 7, 8, 9} else
                         p.model_copy(update={"value": None, "qc_flag": "missing"}) for p in series.points]
        return series

    def unavailable(*args):
        raise api_error("DATA_NOT_AVAILABLE", "Seasonal result not delivered.", {"dataset": "trend"})

    monkeypatch.setattr(store, "series", selected_series)
    monkeypatch.setattr(store, "trend", unavailable)
    content = assemble_report(store, ReportRequest(region_id="IGP", variables=["rainfall"],
        start="2003-01", end="2024-12", season="JJAS", include=["trend"]), app_name="TrendTrace", contract_version="1.0",
        generated_at="2026-11-14T12:00:00+05:30")
    assert content.season == "JJAS"
    assert any(p.value is None for p in content.variables[0].series.points)


def test_cleanup_failure_does_not_fail_an_already_saved_report(tmp_path, monkeypatch):
    store = ReportFileStore(tmp_path)
    report_id = store.new_id()

    def denied():
        raise PermissionError("simulated directory scan failure")

    monkeypatch.setattr(store, "_saved_reports", denied)
    store.save(report_id, b"%PDF-test")
    assert store.load(report_id) == b"%PDF-test"
