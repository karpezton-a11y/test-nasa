"""Tasks 1-3: GET /anomalies, /interaction, /rainfall/indicators on the mock store.

Covers success shapes, every invalid input, unavailable data, the `both` shape,
all three indicators, ok vs too-few-events, null/zero preservation, the result
identity guard and agreement between live responses and docs/examples.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advanced_schemas import (
    INTERACTION_GUARDRAIL, TOO_FEW_EVENTS_NOTE, AnomalyBothResult, AnomalyResult, IndicatorResult,
    InteractionResult,
)
from app.config import REPO_ROOT
from app.main import create_app
from app.schemas import Envelope
from app.services.store import MockStore

API = "/api/v1"
EXAMPLES = REPO_ROOT / "docs" / "examples"
INDICATOR_UNITS = {"heavy_rain_share": "%", "longest_dry_spell": "days", "rx5day": "mm"}


def _error(response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return body["error"]["details"]


def _keys(obj: Any) -> Any:
    """Key structure of a JSON value (first list item stands for the list)."""
    if isinstance(obj, dict):
        return {k: _keys(v) for k, v in obj.items()}
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return [_keys(obj[0])]
    return None


def _example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture
def sparse_client(make_settings, tmp_path):
    """Scenario without advanced fixtures: every advanced route must say DATA_NOT_AVAILABLE."""
    with TestClient(create_app(make_settings(MOCK_SCENARIO="sparse", REPORTS_DIR=str(tmp_path)))) as c:
        yield c


# ----------------------------------------------------------------- G. anomalies


@pytest.mark.parametrize("variable", ["rainfall", "aod"])
def test_single_variable_anomalies_list_every_month_of_the_window(client, variable):
    response = client.get(f"{API}/anomalies", params={"region_id": "TN", "variable": variable,
                                                    "start": "2024-01", "end": "2024-12"})
    assert response.status_code == 200
    envelope = Envelope[AnomalyResult].model_validate(response.json())
    result = envelope.result
    assert envelope.data_status == "mock" and envelope.data_version.startswith("MOCK-")
    assert result.result_id == f"anomalies_TN_{variable}_2024-01_2024-12_raw"
    assert result.period.model_dump() == {"start": "2024-01", "end": "2024-12"}
    assert [a.date.month for a in result.anomalies] == list(range(1, 13))
    assert result.baseline.start == "2003-01" and result.baseline.end == "2024-12"  # baseline always shown


def test_anomalies_default_to_the_full_available_period(client):
    result = client.get(f"{API}/anomalies", params={"region_id": "IGP", "variable": "aod"}).json()["result"]
    assert result["period"] == {"start": "2003-01", "end": "2024-12"}
    assert len(result["anomalies"]) == 22 * 12


def test_detrended_flag_selects_the_detrended_result(client):
    result = client.get(f"{API}/anomalies", params={"region_id": "IGP", "variable": "rainfall",
                                                  "detrended": "true"}).json()["result"]
    assert result["baseline"]["detrended"] is True and result["result_id"].endswith("_detrended")


def test_both_returns_rainfall_then_aod_and_consistent_combined_flags(client):
    response = client.get(f"{API}/anomalies", params={"region_id": "IGP", "variable": "both"})
    result = Envelope[AnomalyBothResult].model_validate(response.json()).result  # validator re-derives flags
    assert [r.variable for r in result.results] == ["rainfall", "aod"]
    assert result.combined_flags, "the mock year range contains at least one both-flagged month"
    assert result.results[0].unit != result.results[1].unit


def test_both_window_slices_combined_flags_too(client):
    full = client.get(f"{API}/anomalies", params={"region_id": "IGP", "variable": "both"}).json()["result"]
    flag_month = full["combined_flags"][0]["date"][:7]
    other = "2003-01" if flag_month != "2003-01" else "2003-02"
    result = client.get(f"{API}/anomalies", params={"region_id": "IGP", "variable": "both",
                                                  "start": other, "end": other}).json()["result"]
    assert result["combined_flags"] == []
    assert [len(r["anomalies"]) for r in result["results"]] == [1, 1]


def test_anomaly_values_are_the_stored_series_values_including_null_and_zero(client):
    series = {p["date"]: p for p in client.app.state.store.series("TN", "rainfall", "month")
              .model_dump(mode="json")["points"]}
    result = client.get(f"{API}/anomalies", params={"region_id": "TN", "variable": "rainfall"}).json()["result"]
    rows = result["anomalies"]
    assert any(r["value"] is None for r in rows) and any(r["value"] == 0 for r in rows)
    for row in rows:
        assert row["value"] == series[row["date"]]["value"]  # null stays null, 0 stays 0
        assert row["qc_flag"] == series[row["date"]]["qc_flag"]
        if row["value"] is None:
            assert row["score"] is None and row["category"] is None


@pytest.mark.parametrize("params,status,code", [
    ({"region_id": "XX", "variable": "aod"}, 400, "INVALID_REGION"),
    ({"region_id": "IGP", "variable": "pm25"}, 400, "INVALID_VARIABLE"),
    ({"region_id": "IGP", "variable": "aod", "start": "2024/01"}, 400, "INVALID_PERIOD"),
    ({"region_id": "IGP", "variable": "aod", "start": "2020-05", "end": "2020-01"}, 400, "INVALID_PERIOD"),
    ({"region_id": "IGP", "variable": "aod", "start": "1999-01"}, 400, "INVALID_PERIOD"),
    ({"region_id": "IGP", "variable": "aod", "end": "2025-01"}, 400, "INVALID_PERIOD"),
    ({"region_id": "IGP", "variable": "aod", "detrended": "maybe"}, 422, "VALIDATION_ERROR"),
    ({"variable": "aod"}, 422, "VALIDATION_ERROR"),
    ({"region_id": "IGP"}, 422, "VALIDATION_ERROR"),
])
def test_anomaly_invalid_inputs(client, params, status, code):
    details = _error(client.get(f"{API}/anomalies", params=params), status, code)
    if code == "INVALID_VARIABLE":
        assert details["allowed"] == ["rainfall", "aod", "both"]
    assert "pm25" not in json.dumps(details) and "2024/01" not in json.dumps(details)  # never echo input


def test_anomalies_unavailable_without_fallback(sparse_client):
    details = _error(sparse_client.get(f"{API}/anomalies", params={"region_id": "IGP", "variable": "both"}),
                     404, "DATA_NOT_AVAILABLE")
    assert details == {"dataset": "anomalies", "region_id": "IGP", "variable": "both", "detrended": False}


# ----------------------------------------------------------------- H. interaction


def _interaction(client, region: str, season: str) -> InteractionResult:
    response = client.get(f"{API}/interaction", params={"region_id": region, "season": season})
    assert response.status_code == 200, response.text
    return Envelope[InteractionResult].model_validate(response.json()).result


def test_interaction_ok_has_test_result_and_guardrail(client):
    result = _interaction(client, "IGP", "JJAS")
    assert result.status == "ok" and result.n_events_used >= 10 and result.note is None
    assert result.p_value is not None and result.median_change_ci is not None
    assert result.guardrail == INTERACTION_GUARDRAIL


@pytest.mark.parametrize("region,season,used", [("TN", "all", 9), ("IGP", "OND", 6), ("TN", "JJAS", 0)])
def test_interaction_too_few_events_keeps_descriptive_fields_only(client, region, season, used):
    result = _interaction(client, region, season)
    assert result.n_events_used == used and result.status == "too_few_events"
    assert result.note == TOO_FEW_EVENTS_NOTE
    assert result.p_value is None and result.median_change_ci is None
    assert result.guardrail == INTERACTION_GUARDRAIL
    assert result.monthly_association.n > 0  # the separate monthly association is kept
    if used == 0:
        assert result.aod_before_median is None and result.median_change is None
    else:
        assert result.aod_before_median is not None and result.median_change is not None


def test_interaction_boundary_ten_events_is_ok_and_nine_is_not():
    data = _example("interaction_ok.json")["result"]
    ok = InteractionResult.model_validate({**data, "n_events": 10, "n_events_used": 10})
    assert ok.status == "ok"
    with pytest.raises(ValueError):
        InteractionResult.model_validate({**data, "n_events": 10, "n_events_used": 9})


def test_interaction_never_claims_causation(client):
    text = json.dumps([_interaction(client, r, s).model_dump(mode="json")
                       for r, s in (("IGP", "JJAS"), ("TN", "OND"))]).lower()
    for word in ("caused", "causes", "because of", "leads to", "pm2.5"):
        assert word not in text


@pytest.mark.parametrize("params,status,code", [
    ({"region_id": "XX", "season": "JJAS"}, 400, "INVALID_REGION"),
    ({"region_id": "IGP", "season": "XYZ"}, 400, "INVALID_SEASON"),
    ({"region_id": "IGP", "season": "annual"}, 400, "INVALID_SEASON"),
    ({"region_id": "IGP"}, 422, "VALIDATION_ERROR"),
])
def test_interaction_invalid_inputs(client, params, status, code):
    details = _error(client.get(f"{API}/interaction", params=params), status, code)
    if code == "INVALID_SEASON":
        assert details["allowed"] == ["all", "JF", "MAM", "JJAS", "OND"]


def test_interaction_season_without_results_is_data_not_available(client, sparse_client):
    for c, season in ((client, "MAM"), (sparse_client, "JJAS")):
        details = _error(c.get(f"{API}/interaction", params={"region_id": "IGP", "season": season}),
                         404, "DATA_NOT_AVAILABLE")
        assert details["dataset"] == "interaction_summary"


# ----------------------------------------------------------------- J. rainfall indicators


@pytest.mark.parametrize("region", ["IGP", "TN"])
@pytest.mark.parametrize("season", ["annual", "JJAS", "OND"])
@pytest.mark.parametrize("indicator", sorted(INDICATOR_UNITS))
def test_every_indicator_and_season(client, region, season, indicator):
    response = client.get(f"{API}/rainfall/indicators",
                          params={"region_id": region, "indicator": indicator, "season": season})
    assert response.status_code == 200, response.text
    result = Envelope[IndicatorResult].model_validate(response.json()).result
    assert (result.region_id, result.indicator, result.season) == (region, indicator, season)
    assert result.unit == INDICATOR_UNITS[indicator] and result.definition
    assert result.min_valid_fraction == 0.95
    assert (result.threshold_baseline is not None) == (indicator == "heavy_rain_share")
    assert (result.trend is None) != (result.trend_note is None)


def test_indicator_years_below_coverage_are_null_not_zero(client):
    body = client.get(f"{API}/rainfall/indicators",
                      params={"region_id": "IGP", "indicator": "longest_dry_spell", "season": "annual"}).json()
    values = body["result"]["values"]
    low = [v for v in values if v["valid_fraction"] is None or v["valid_fraction"] < 0.95]
    assert low and all(v["value"] is None for v in low)
    assert all(v["value"] is not None for v in values if v not in low)


@pytest.mark.parametrize("params,status,code", [
    ({"region_id": "XX", "indicator": "rx5day", "season": "annual"}, 400, "INVALID_REGION"),
    ({"region_id": "IGP", "indicator": "cdd", "season": "annual"}, 400, "INVALID_INDICATOR"),
    ({"region_id": "IGP", "indicator": "rx5day", "season": "all"}, 400, "INVALID_SEASON"),
    ({"region_id": "IGP", "indicator": "rx5day", "season": "MAM"}, 400, "INVALID_SEASON"),
    ({"region_id": "IGP", "season": "annual"}, 422, "VALIDATION_ERROR"),
    ({"region_id": "IGP", "indicator": "rx5day"}, 422, "VALIDATION_ERROR"),
])
def test_indicator_invalid_inputs(client, params, status, code):
    details = _error(client.get(f"{API}/rainfall/indicators", params=params), status, code)
    if code == "INVALID_INDICATOR":
        assert details["allowed"] == ["heavy_rain_share", "longest_dry_spell", "rx5day"]


def test_indicator_missing_file_is_data_not_available(sparse_client):
    details = _error(sparse_client.get(f"{API}/rainfall/indicators",
                                       params={"region_id": "TN", "indicator": "rx5day", "season": "OND"}),
                     404, "DATA_NOT_AVAILABLE")
    assert details["dataset"] == "rainfall_indicators"


# ----------------------------------------------------------------- identity guard + examples


class WrongSeasonStore(MockStore):
    """A buggy store that answers every interaction request with the JJAS result."""

    def interaction(self, region_id, season):
        return super().interaction(region_id, "JJAS")


def test_result_for_another_request_is_never_served(settings):
    store = WrongSeasonStore(settings.mock_dir / settings.mock_scenario)
    with TestClient(create_app(settings, store=store), raise_server_exceptions=False) as c:
        response = c.get(f"{API}/interaction", params={"region_id": "IGP", "season": "OND"})
    _error(response, 500, "INTERNAL_ERROR")
    assert "JJAS" not in response.text


@pytest.mark.parametrize("path,params,example", [
    ("/anomalies", {"region_id": "TN", "variable": "rainfall", "start": "2024-01", "end": "2024-12"},
     "anomaly_rainfall.json"),
    ("/anomalies", {"region_id": "IGP", "variable": "both", "start": "2010-01", "end": "2010-12"},
     "anomaly_both.json"),  # a window with a combined flag (2010-07 in the mock), like the example
    ("/interaction", {"region_id": "IGP", "season": "JJAS"}, "interaction_ok.json"),
    ("/interaction", {"region_id": "IGP", "season": "OND"}, "interaction_too_few_events.json"),
    ("/rainfall/indicators", {"region_id": "IGP", "indicator": "heavy_rain_share", "season": "annual"},
     "rainfall_indicator_heavy_rain_share.json"),
])
def test_live_response_has_the_same_shape_as_the_example(client, path, params, example):
    live = client.get(f"{API}{path}", params=params).json()
    assert _keys(live) == _keys(_example(example))
