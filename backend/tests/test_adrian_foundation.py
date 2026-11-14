"""Phases A–B integration tests. Synthetic inputs exist only in pytest temp dirs."""
import hashlib
import json
import sys
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import ConfigError, REPO_ROOT
from app.errors import ApiError
from app.main import create_app
from app.schemas import Envelope, Evidence, Period, TrendResult
from app.services.real_store import RealStore
from app.services.science import compute_trend
from app.services.store import MockStore, verify_store


@pytest.fixture
def inputs(tmp_path):
    # Test-only construction: NEVER copy these labelled test inputs to processed/.
    root = tmp_path / "processed"
    root.mkdir()
    fixtures = REPO_ROOT / "data/mock/normal"
    def clean(value):
        if isinstance(value, str):
            return value.replace("MOCK", "TEST").replace("mock", "test")
        if isinstance(value, list): return [clean(v) for v in value]
        if isinstance(value, dict): return {k: clean(v) for k, v in value.items()}
        return value
    def envelope(name, target):
        raw = clean(json.loads((fixtures / name).read_text()))
        raw.update(data_status="real", data_version="TEST-only", contract_version="1.0")
        (root / target).write_text(json.dumps(raw))
        return raw
    envelope("variables.json", "variables.json")
    envelope("regions.json", "regions.geojson")
    envelope("sources.json", "sources.json")
    rows = []
    for path in sorted((fixtures / "timeseries").glob("*_month.json")):
        s = clean(json.loads(path.read_text()))["result"]
        for point in s["points"]:
            rows.append({**{k: s[k] for k in ("region_id", "variable", "frequency", "unit", "source_id")}, **point})
    csv = root / "timeseries_monthly.csv"
    next(row for row in rows if row["region_id"] == "IGP" and row["variable"] == "aod").update(value=0.0, qc_flag="ok")
    pd.DataFrame(rows).to_csv(csv, index=False)
    def manifest():
        (root / "manifest.json").write_text(json.dumps({"data_status": "real", "data_version": "TEST-only",
            "contract_version": "1.0", "assets": {csv.name: {"data_status": "real",
              "sha256": hashlib.sha256(csv.read_bytes()).hexdigest()}}}))
    manifest()
    return root, manifest


@pytest.fixture
def real_store(inputs, make_settings):
    return RealStore(make_settings(DATA_MODE="real", PROCESSED_DIR=str(inputs[0])))


def test_real_store_preserves_missing_and_zero_and_loads_once(real_store, inputs):
    series = real_store.series("IGP", "aod", "month")
    assert any(p.value is None and p.qc_flag == "missing" for p in series.points)
    assert any(p.value == 0 for p in series.points)
    (inputs[0] / "timeseries_monthly.csv").unlink()
    assert real_store.series("IGP", "aod", "month") == series
    series.points.clear()
    assert real_store.series("IGP", "aod", "month").points


def test_real_startup_metadata_in_existing_routes(real_store, make_settings):
    settings = make_settings(APP_ENV="prod", DATA_MODE="real")
    verify_store(real_store, settings)
    with TestClient(create_app(settings, store=real_store)) as client:
        for path in ("health", "variables", "regions", "meta/sources"):
            response = client.get("/api/v1/" + path)
            assert response.status_code == 200
            assert response.json()["data_status"] == "real"


def test_missing_daily_is_404_never_mock(real_store):
    with pytest.raises(ApiError) as exc:
        real_store.series("IGP", "aod", "day")
    assert (exc.value.code, exc.value.http_status) == ("DATA_NOT_AVAILABLE", 404)


@pytest.mark.parametrize("change", ["unit", "date", "null", "fraction", "sentinel", "duplicate", "mock"])
def test_corrupt_csv_refused(inputs, make_settings, change):
    root, manifest = inputs
    path = root / "timeseries_monthly.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    edits = {"unit": ("unit", "mm/hr"), "date": ("date", "2003-01-02"),
             "null": ("value", ""), "fraction": ("valid_fraction", "1.2"),
             "sentinel": ("value", "-9999"), "mock": ("source_id", "MOCK_SOURCE")}
    if change == "duplicate": df = pd.concat([df, df.iloc[[0]]])
    else:
        column, value = edits[change]
        df.loc[0, column] = value
        if change == "null": df.loc[0, "qc_flag"] = "ok"
    df.to_csv(path, index=False)
    manifest()
    with pytest.raises((ConfigError, ValidationError)):
        RealStore(make_settings(DATA_MODE="real", PROCESSED_DIR=str(root)))


def test_csv_tamper_requires_updated_manifest(inputs, make_settings):
    root, _ = inputs
    with (root / "timeseries_monthly.csv").open("a") as f: f.write("\n")
    with pytest.raises(ConfigError, match="SHA-256"):
        RealStore(make_settings(DATA_MODE="real", PROCESSED_DIR=str(root)))


def test_mock_or_mixed_json_rejected(inputs, make_settings):
    root, _ = inputs
    path = root / "sources.json"
    raw = json.loads(path.read_text()); raw["data_version"] = "another-release"
    path.write_text(json.dumps(raw))
    with pytest.raises(ConfigError, match="Mixed data"):
        RealStore(make_settings(DATA_MODE="real", PROCESSED_DIR=str(root)))


def test_empty_real_dev_returns_404_prod_refused(tmp_path, make_settings):
    settings = make_settings(DATA_MODE="real", PROCESSED_DIR=str(tmp_path))
    store = RealStore(settings)
    with TestClient(create_app(settings)) as client:
        res = client.get("/api/v1/variables")
        assert res.status_code == 404 and res.json()["error"]["code"] == "DATA_NOT_AVAILABLE"
    assert store.asset_statuses() == {}
    with pytest.raises(ConfigError, match="production requires"):
        RealStore(make_settings(DATA_MODE="real", APP_ENV="prod", PROCESSED_DIR=str(tmp_path)))


@pytest.fixture
def trend_fixture():
    store = MockStore(REPO_ROOT / "data/mock/normal")
    period = Period(start="2003-01", end="2024-12")
    return store.series("IGP", "aod", "month"), period, store.trend("IGP", "aod", period, "all")


def test_science_mock_does_not_import_trendlib(monkeypatch, trend_fixture):
    series, period, trend = trend_fixture
    monkeypatch.setitem(sys.modules, "trendlib", None)
    assert compute_trend(series, period, "all", mock_lookup=lambda: trend) == trend


def test_science_absent_is_unavailable(monkeypatch, trend_fixture):
    monkeypatch.setitem(sys.modules, "trendlib", None)
    with pytest.raises(ApiError) as exc:
        compute_trend(*trend_fixture[:2], "all")
    assert exc.value.code == "DATA_NOT_AVAILABLE"


def test_science_calls_g3_and_cache_protects_results(monkeypatch, real_store, trend_fixture):
    _, period, trend = trend_fixture
    raw = json.loads(trend.model_dump_json().replace("MOCK", "TEST").replace("mock", "test"))
    raw["source_id"] = real_store.series("IGP", "aod", "month").source_id
    calls = []
    def compute(frame, **kwargs):
        calls.append((frame, kwargs)); return raw.copy()
    monkeypatch.setitem(sys.modules, "trendlib", SimpleNamespace(compute_trend=compute,
        compute_evidence=lambda frame, result, **kwargs: raw["evidence"]))
    first = real_store.trend("IGP", "aod", period, "all")
    first.limitations.clear()
    second = real_store.trend("IGP", "aod", period, "all")
    assert second.limitations and len(calls) == 1
    assert calls[0][1] == {"season": "all", "alpha": 0.05}
    assert calls[0][0].attrs["unit"] == "1"


def test_science_only_maps_named_data_exceptions(monkeypatch, trend_fixture):
    class InsufficientDataError(Exception): pass
    def fail(*args, **kwargs): raise InsufficientDataError("private details")
    module = SimpleNamespace(compute_trend=fail, InsufficientDataError=InsufficientDataError)
    monkeypatch.setitem(sys.modules, "trendlib", module)
    with pytest.raises(ApiError) as exc:
        compute_trend(*trend_fixture[:2], "all")
    assert exc.value.code == "INSUFFICIENT_DATA" and "private" not in exc.value.message
    def bug(*args, **kwargs): raise ValueError("programming bug")
    module.compute_trend = bug
    with pytest.raises(ValueError, match="programming bug"):
        compute_trend(*trend_fixture[:2], "all")


def test_science_rejects_bad_contract_and_missing_evidence(monkeypatch, trend_fixture):
    raw = trend_fixture[2].model_dump()
    raw["direction"] = "decreasing" if raw["direction"] != "decreasing" else "increasing"
    module = SimpleNamespace(compute_trend=lambda *a, **kw: raw)
    monkeypatch.setitem(sys.modules, "trendlib", module)
    with pytest.raises(ValidationError): compute_trend(*trend_fixture[:2], "all")
    raw.pop("evidence")
    with pytest.raises(ApiError) as exc: compute_trend(*trend_fixture[:2], "all")
    assert exc.value.details["dataset"] == "evidence"
    raw["evidence"] = None
    with pytest.raises(ApiError) as exc: compute_trend(*trend_fixture[:2], "all")
    assert exc.value.details["dataset"] == "evidence"


def test_schema_rejects_nonfinite_and_impossible_evidence(trend_fixture):
    raw = trend_fixture[2].model_dump()
    raw["sen_slope"] = float("nan")
    with pytest.raises(ValidationError): TrendResult.model_validate(raw)
    evidence = trend_fixture[2].evidence.model_dump(); evidence["n_valid"] = evidence["n_expected"] + 1
    with pytest.raises(ValidationError): Evidence.model_validate(evidence)


def test_advanced_result_envelopes_serve_without_router_edits(inputs, make_settings):
    root, _ = inputs
    fixtures = REPO_ROOT / "data/mock/normal"
    for folder in ("anomalies", "interaction", "indicators"):
        (root / folder).mkdir()
        for path in (fixtures / folder).glob("*.json"):
            raw = json.loads(path.read_text().replace("MOCK", "TEST").replace("mock", "test"))
            raw.update(data_status="real", data_version="TEST-only")
            (root / folder / path.name).write_text(json.dumps(raw))
    settings = make_settings(DATA_MODE="real", APP_ENV="prod", PROCESSED_DIR=str(root))
    with TestClient(create_app(settings)) as client:
        for path, params in [
            ("anomalies", {"region_id": "IGP", "variable": "both", "start": "2024-01", "end": "2024-12"}),
            ("interaction", {"region_id": "IGP", "season": "JJAS"}),
            ("rainfall/indicators", {"region_id": "IGP", "indicator": "heavy_rain_share", "season": "annual"})]:
            response = client.get("/api/v1/" + path, params=params)
            assert response.status_code == 200, response.text
            assert response.json()["data_status"] == "real"


def test_production_refuses_empty_monthly_input(inputs, make_settings):
    root, manifest = inputs
    csv = root / "timeseries_monthly.csv"
    csv.write_text("date,region_id,variable,frequency,value,unit,source_id,valid_fraction,qc_flag\n")
    manifest()
    with pytest.raises(ConfigError, match="observations"):
        RealStore(make_settings(APP_ENV="prod", DATA_MODE="real", PROCESSED_DIR=str(root)))


def test_duplicate_regions_and_mismatched_geojson_refused(inputs, make_settings):
    root, _ = inputs
    path = root / "regions.geojson"
    raw = json.loads(path.read_text())
    original = json.loads(json.dumps(raw))
    raw["result"]["regions"].append(raw["result"]["regions"][0])
    path.write_text(json.dumps(raw))
    with pytest.raises(ConfigError, match="Duplicate metadata"):
        RealStore(make_settings(DATA_MODE="real", PROCESSED_DIR=str(root)))
    original["result"]["geojson"]["features"][0]["id"] = "OTHER"
    path.write_text(json.dumps(original))
    with pytest.raises(ConfigError, match="GeoJSON features"):
        RealStore(make_settings(DATA_MODE="real", PROCESSED_DIR=str(root)))


def test_optional_csv_export_metadata_is_checked_not_served(inputs, make_settings):
    root, manifest = inputs
    path = root / "timeseries_monthly.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame["data_version"] = "TEST-only"
    frame["method"] = "test-only observed export method"
    frame.to_csv(path, index=False)
    manifest()
    store = RealStore(make_settings(DATA_MODE="real", PROCESSED_DIR=str(root)))
    assert "method" not in store.series("IGP", "aod", "month").model_dump()
    frame.loc[0, "data_version"] = "different-release"
    frame.to_csv(path, index=False)
    manifest()
    with pytest.raises(ConfigError, match="data_version"):
        RealStore(make_settings(DATA_MODE="real", PROCESSED_DIR=str(root)))


def test_monthly_unknown_coverage_does_not_pass_real_import(inputs, make_settings):
    root, manifest = inputs
    path = root / "timeseries_monthly.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.loc[0, "valid_fraction"] = ""
    frame.to_csv(path, index=False); manifest()
    with pytest.raises(ConfigError, match="Monthly temporal valid_fraction"):
        RealStore(make_settings(DATA_MODE="real", PROCESSED_DIR=str(root)))


def test_daily_coverage_is_unknown_not_fabricated(inputs, make_settings):
    root, manifest = inputs
    frame = pd.read_csv(root / "timeseries_monthly.csv", dtype=str, keep_default_na=False)
    row = frame[(frame.variable == "aod") & (frame.region_id == "IGP")].iloc[0].to_dict()
    row.update(date="2024-01-01", frequency="day", source_id="MODIS_AQUA_C61_DAILY", valid_fraction="0.8")
    path = root / "timeseries_daily.csv"
    pd.DataFrame([row]).to_csv(path, index=False)
    manifest_path = root / "manifest.json"
    meta = json.loads(manifest_path.read_text())
    meta["assets"][path.name] = {"data_status": "real", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(meta))
    with pytest.raises(ConfigError, match="Daily valid_fraction"):
        RealStore(make_settings(DATA_MODE="real", PROCESSED_DIR=str(root)))
