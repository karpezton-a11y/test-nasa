"""Core endpoint, common-period and seasonal-coverage integration tests."""
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT
from app.core_schemas import CompareResult
from app.main import create_app
from app.schemas import Envelope, TimeSeries, TrendResult, Period
from app.services.store import MockStore
from app.services.validation import coverage

API = "/api/v1"
BODY = {"region_id": "IGP", "variable": "aod", "start": "2003-01", "end": "2024-12", "season": "all"}


def test_timeseries_schema_envelope_and_missing_values(client):
    response = client.get(API + "/timeseries", params={"region_id": "IGP", "variable": "aod"})
    assert response.status_code == 200
    parsed = Envelope[TimeSeries].model_validate(response.json())
    assert parsed.data_status == "mock"
    assert set(response.json()) == {"data_status", "data_version", "contract_version", "generated_at", "result"}
    assert any(p.value is None and p.qc_flag == "missing" for p in parsed.result.points)
    subset = client.get(API + "/timeseries", params={"region_id": "IGP", "variable": "aod", "start": "2024-01", "end": "2024-12"})
    assert len(subset.json()["result"]["points"]) == 12


def test_source_selection_and_daily(client):
    monthly = client.get(API + "/timeseries", params={"region_id": "IGP", "variable": "aod"}).json()["result"]
    chosen = client.get(API + "/timeseries", params={"region_id": "IGP", "variable": "aod", "source_id": monthly["source_id"]})
    assert chosen.json()["result"] == monthly
    daily = client.get(API + "/timeseries", params={"region_id": "IGP", "variable": "aod", "frequency": "day", "start": "2024-01", "end": "2024-12"})
    assert daily.status_code == 200
    Envelope[TimeSeries].model_validate(daily.json())


@pytest.mark.parametrize("params,status,code", [
    ({"region_id": "unknown"}, 400, "INVALID_REGION"),
    ({"variable": "pm25"}, 400, "INVALID_VARIABLE"),
    ({"frequency": "year"}, 422, "VALIDATION_ERROR"),
    ({"start": "03-2003"}, 400, "INVALID_PERIOD"),
    ({"start": "2024-12", "end": "2024-01"}, 400, "INVALID_PERIOD"),
    ({"start": "1990-01"}, 400, "INVALID_PERIOD"),
    ({"frequency": "day"}, 400, "INVALID_PERIOD"),
    ({"source_id": "not-a-source"}, 422, "VALIDATION_ERROR"),
])
def test_timeseries_errors(client, params, status, code):
    response = client.get(API + "/timeseries", params={"region_id": "IGP", "variable": "aod", **params})
    assert response.status_code == status
    assert set(response.json()) == {"error"} and response.json()["error"]["code"] == code


def test_analyze_schema_direction_and_time(client):
    started = perf_counter()
    response = client.post(API + "/analyze", json=BODY)
    assert perf_counter() - started < 2
    assert response.status_code == 200, response.text
    result = Envelope[TrendResult].model_validate(response.json()).result
    expected = ("increasing" if result.sen_slope > 0 else "decreasing" if result.sen_slope < 0 else "no_significant_trend") if result.p_value < result.method.alpha else "no_significant_trend"
    assert result.direction == expected


@pytest.mark.parametrize("patch,status,code", [
    ({"region_id": "bad"}, 400, "INVALID_REGION"),
    ({"variable": "bad"}, 400, "INVALID_VARIABLE"),
    ({"season": "XYZ"}, 400, "INVALID_SEASON"),
    ({"start": "2020-01"}, 422, "PERIOD_TOO_SHORT"),
    ({"start": "2024-12", "end": "2003-01"}, 400, "INVALID_PERIOD"),
    ({"options": {"alpha": 0.2}}, 422, "VALIDATION_ERROR"),
])
def test_analyze_errors(client, patch, status, code):
    response = client.post(API + "/analyze", json={**BODY, **patch})
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


@pytest.mark.parametrize("patch", [{"options": {"alpha": 0.10}}, {"options": {"exclude_low_coverage": True}},
                                   {"season": "JJAS"}, {"season": "OND", "start": "2005-01", "end": "2020-12"}])
def test_analyze_computes_any_valid_selection_in_mock(client, patch):
    """trendlib runs on the labelled mock series: options/seasons/periods no longer need fixtures."""
    response = client.post(API + "/analyze", json={**BODY, **patch})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data_status"] == "mock"
    assert body["result"]["limitations"][0].startswith("MOCK series")


def test_sparse_and_short_scenarios(make_settings):
    for scenario, expected in [("sparse", "INSUFFICIENT_DATA"), ("short", "PERIOD_TOO_SHORT")]:
        with TestClient(create_app(make_settings(MOCK_SCENARIO=scenario))) as client:
            response = client.post(API + "/analyze", json={"region_id": "IGP", "variable": "aod"})
            assert response.status_code == 422 and response.json()["error"]["code"] == expected


def test_seasonal_coverage_counts_only_selected_months():
    store = MockStore(REPO_ROOT / "data/mock/normal")
    series = store.series("IGP", "aod", "month")
    period = Period(start="2003-01", end="2024-12")
    series = series.model_copy(update={"points": [p.model_copy(update={"value": None, "qc_flag": "missing"})
            if p.date.month not in (1, 2) else p for p in series.points]})
    assert coverage(series, period).valid_pct < 70
    assert coverage(series, period, "JF").n_expected == 44
    assert coverage(series, period, "JF").valid_pct >= 70


def test_compare_regions_and_variables(client):
    for body in [
        {"mode": "regions", "region_ids": ["IGP", "TN"], "variable": "aod"},
        {"mode": "variables", "region_id": "IGP", "variables": ["rainfall", "aod"]}]:
        response = client.post(API + "/compare", json=body)
        assert response.status_code == 200, response.text
        parsed = Envelope[CompareResult].model_validate(response.json()).result
        assert len(parsed.results) == 2
        if not all(r.significant for r in parsed.results): assert parsed.summary.same_direction is None
        if body["mode"] == "regions": assert "monthly_association" not in response.json()["result"]
        else: assert parsed.monthly_association is not None


@pytest.mark.parametrize("body", [
    {"mode": "regions", "region_ids": ["IGP"], "variable": "aod"},
    {"mode": "regions", "region_ids": ["IGP", "IGP"], "variable": "aod"},
    {"mode": "variables", "region_id": "IGP", "variables": ["aod", "rainfall"]},
    {"mode": "variables", "region_id": "IGP", "variables": ["rainfall", "aod"], "region_ids": ["IGP", "TN"]},
])
def test_compare_rejects_ambiguous_modes(client, body):
    response = client.post(API + "/compare", json=body)
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_programming_error_is_sanitized(make_settings, monkeypatch):
    from app.services import core
    def broken(*args, **kwargs): raise RuntimeError("private filesystem details")
    monkeypatch.setattr(core, "compute_trend", broken)
    with TestClient(create_app(make_settings()), raise_server_exceptions=False) as client:
        response = client.post(API + "/analyze", json=BODY)
    assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "private filesystem" not in response.text


def test_templates_no_network_core_smoke(client):
    response = client.post(API + "/analyze", json=BODY)
    result = response.json()["result"]
    explanation = client.post(API + "/explain", json={"result_type": "trend", "result_id": result["result_id"]})
    assert explanation.status_code == 200, explanation.text
    assert explanation.json()["result"]["source"] == "template"
