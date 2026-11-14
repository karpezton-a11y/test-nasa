"""Step 3: deterministic MOCK generator, honest labels, store seam and production guard."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.config import REPO_ROOT, ConfigError
from app.errors import ApiError
from app.main import create_app
from app.schemas import Envelope, Period
from app.services.store import DatasetInfo, MockStore, model_for_path
from app.services.validation import require_coverage, require_min_years
from scripts.generate_mock_data import MANIFEST, generate

MOCK_DIR = REPO_ROOT / "data" / "mock"
FULL = Period(start="2003-01", end="2024-12")


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*"))
            if p.is_file() and "qa_large" not in p.relative_to(root).parts}


@pytest.fixture(scope="module")
def fresh(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("mock_a")
    generate(out)
    return out


def test_generation_is_byte_identical_across_runs_and_dirs(fresh, tmp_path):
    generate(tmp_path)
    assert _tree(tmp_path) == _tree(fresh)
    generate(tmp_path)  # repeat run into the same directory stays stable
    assert _tree(tmp_path) == _tree(fresh)


# qa_large is independently generated and validated by test_large_daily_csv.py.
def test_committed_mock_data_matches_the_generator(fresh):
    assert _tree(MOCK_DIR) == _tree(fresh), "data/mock is stale: run python scripts/generate_mock_data.py"


def test_every_generated_file_is_mock_and_validates_against_its_model(fresh):
    manifest = json.loads((fresh / MANIFEST).read_text())
    assert manifest["data_status"] == "mock"
    for relative in manifest["files"]:
        scenario, inner = relative.split("/", 1)
        raw = json.loads((fresh / relative).read_text())
        envelope = TypeAdapter(Envelope[model_for_path(inner)]).validate_python(raw)
        assert envelope.data_status == "mock"
        assert envelope.data_version == f"MOCK-2026-11-13-{scenario}"


def test_mock_metadata_has_no_real_looking_provenance(fresh):
    text = "\n".join(p.read_text() for p in fresh.rglob("*.json"))
    for forbidden in ("doi:", "10.5067", "https://", "Earthdata"):
        assert forbidden not in text
    sources = json.loads((fresh / "normal" / "sources.json").read_text())["result"]
    assert all(s["doi"] is None and s["citation"] is None and s["access_date"] is None for s in sources)
    assert all("MOCK" in s["product"] for s in sources)


def test_generator_refuses_processed_and_other_repo_dirs():
    with pytest.raises(SystemExit):
        generate(REPO_ROOT / "data" / "processed")
    with pytest.raises(SystemExit):
        generate(REPO_ROOT / "docs")
    # data/processed now holds Group 3's real envelopes; the generator must never have written mock files there.
    assert not any('"data_status": "mock"' in p.read_text(encoding="utf-8")
                   for p in (REPO_ROOT / "data" / "processed").rglob("*.json"))


def test_generation_does_not_touch_examples(tmp_path):
    examples = REPO_ROOT / "docs" / "examples"
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in examples.glob("*.json")}
    generate(tmp_path)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in examples.glob("*.json")}
    assert before == after


def test_regeneration_removes_only_owned_stale_files(tmp_path):
    generate(tmp_path)
    manifest = json.loads((tmp_path / MANIFEST).read_text())
    manifest["files"].append("normal/timeseries/OLD_stale_month.json")
    (tmp_path / MANIFEST).write_text(json.dumps(manifest))
    (tmp_path / "normal" / "timeseries" / "OLD_stale_month.json").write_text("{}")
    (tmp_path / "notes.txt").write_text("not ours")
    generate(tmp_path)
    assert not (tmp_path / "normal" / "timeseries" / "OLD_stale_month.json").exists()
    assert (tmp_path / "notes.txt").exists()


def _points(scenario: str, name: str) -> list[dict]:
    return json.loads((MOCK_DIR / scenario / "timeseries" / name).read_text())["result"]["points"]


def test_normal_series_has_some_nulls_but_enough_coverage():
    points = _points("normal", "IGP_rainfall_month.json")
    nulls = [p for p in points if p["value"] is None]
    assert nulls and all(p["qc_flag"] == "missing" for p in nulls)
    assert len(nulls) / len(points) < 0.3
    assert not any(p["value"] == -9999 for p in points)


def test_real_zero_rainfall_stays_zero_and_is_not_missing():
    zeros = [p for p in _points("normal", "IGP_rainfall_month.json") if p["value"] == 0.0]
    assert zeros and all(p["qc_flag"] == "ok" for p in zeros)


def test_sparse_scenario_is_about_forty_percent_missing():
    for name in ("IGP_rainfall_month.json", "TN_aod_month.json"):
        points = _points("sparse", name)
        missing = sum(p["value"] is None for p in points) / len(points)
        assert 0.38 <= missing <= 0.45


def test_short_scenario_is_under_ten_years():
    regions = json.loads((MOCK_DIR / "short" / "regions.json").read_text())["result"]["regions"]
    assert all(r["period_available"] == {"start": "2019-01", "end": "2024-12"} for r in regions)


def test_indicator_years_below_95_percent_valid_are_null():
    result = json.loads((MOCK_DIR / "normal" / "indicators" / "IGP_heavy_rain_share_annual.json").read_text())["result"]
    low = [v for v in result["values"] if v["valid_fraction"] < 0.95]
    assert low and all(v["value"] is None for v in low)
    assert result["trend"]["direction"] == "no_significant_trend"


# ----------------------------------------------------------------- store + validation


@pytest.fixture(scope="module")
def normal_store() -> MockStore:
    return MockStore(MOCK_DIR / "normal")


def test_store_serves_supported_trend_and_rejects_other_signatures(normal_store):
    trend = normal_store.trend("IGP", "aod", FULL, "all")
    assert trend.period == FULL and trend.region_id == "IGP"
    with pytest.raises(ApiError) as err:
        normal_store.trend("IGP", "aod", Period(start="2005-01", end="2024-12"), "all")
    assert err.value.code == "DATA_NOT_AVAILABLE"
    with pytest.raises(ApiError):
        normal_store.interaction("IGP", "MAM")


def test_store_anomaly_window_is_a_slice_not_a_new_result(normal_store):
    window = Period(start="2024-01", end="2024-12")
    result = normal_store.anomalies("IGP", "both", window, False)
    assert result.result_id == "anomalies_IGP_both_2024-01_2024-12_raw"
    assert all(len(r.anomalies) == 12 for r in result.results)
    assert all(f.date.year == 2024 for f in result.combined_flags)


def test_sparse_series_fails_coverage_and_short_fails_min_years():
    sparse = MockStore(MOCK_DIR / "sparse").series("IGP", "aod", "month")
    with pytest.raises(ApiError) as err:
        require_coverage(sparse, FULL)
    assert err.value.code == "INSUFFICIENT_DATA" and err.value.http_status == 422
    with pytest.raises(ApiError) as err:
        require_min_years(Period(start="2019-01", end="2024-12"))
    assert err.value.code == "PERIOD_TOO_SHORT" and err.value.details["requested_years"] == 6.0


def test_missing_mock_directory_fails_clearly(tmp_path):
    with pytest.raises(ConfigError, match="generate_mock_data"):
        MockStore(tmp_path / "nothing")


# ----------------------------------------------------------------- production guard


class FakeRealStore:
    """Stands in for Member 1's loader: only the provenance seam matters here."""

    def __init__(self, statuses: dict[str, str | None], data_status: str = "real") -> None:
        self.info = DatasetInfo(data_status, "2026-11-14a", "1.0")
        self._statuses = statuses

    def asset_statuses(self) -> dict[str, str | None]:
        return dict(self._statuses)


@pytest.mark.parametrize("statuses", [
    {"timeseries_monthly.csv": "real", "variables.json": "mock"},  # one mock-marked loaded asset
    {"timeseries_monthly.csv": None},                              # unknown provenance
    {},                                                            # nothing attested
])
def test_prod_real_refuses_unsafe_provenance(make_settings, statuses):
    app = create_app(make_settings(APP_ENV="prod", DATA_MODE="real"), store=FakeRealStore(statuses))
    with pytest.raises(ConfigError, match="Production start refused"):
        with TestClient(app):
            pass


def test_prod_real_with_attested_store_starts_even_with_mock_files_on_disk(make_settings):
    assert (MOCK_DIR / "normal").is_dir()  # unused mock files are present in the checkout
    store = FakeRealStore({"timeseries_monthly.csv": "real", "variables.json": "real"})
    with TestClient(create_app(make_settings(APP_ENV="prod", DATA_MODE="real"), store=store)) as c:
        body = c.get("/api/v1/health").json()
    assert body["data_status"] == "real" and body["result"]["data_status"] == "real"


def test_store_status_must_match_data_mode(make_settings):
    app = create_app(make_settings(DATA_MODE="real"), store=FakeRealStore({"x": "mock"}, data_status="mock"))
    with pytest.raises(ConfigError, match="relabel"):
        with TestClient(app):
            pass


def test_prod_real_mode_without_the_loader_refuses_to_start(make_settings, tmp_path):
    # An empty processed folder: real mode with nothing delivered (data/processed now holds Group 3's files).
    with pytest.raises(ConfigError, match="real_store"):
        with TestClient(create_app(make_settings(APP_ENV="prod", DATA_MODE="real", PROCESSED_DIR=str(tmp_path / "empty")))):
            pass


@pytest.mark.parametrize("path,params", [
    ("/variables", {}), ("/regions", {}), ("/meta/sources", {}),
    ("/anomalies", {"region_id": "IGP", "variable": "aod"}),
    ("/interaction", {"region_id": "IGP", "season": "JJAS"}),
    ("/rainfall/indicators", {"region_id": "IGP", "indicator": "rx5day", "season": "annual"}),
    ("/export/csv", {"region_id": "IGP", "variable": "aod"}),
])
def test_dev_real_mode_without_the_loader_serves_no_data_and_no_mock(make_settings, tmp_path, path, params):
    with TestClient(create_app(make_settings(DATA_MODE="real", REPORTS_DIR=str(tmp_path),
                                             PROCESSED_DIR=str(tmp_path / "empty")))) as c:
        health = c.get("/api/v1/health").json()
        response = c.get(f"/api/v1{path}", params=params)
    assert health["data_status"] == "real" and health["data_version"] == "REAL-DATA-NOT-LOADED"
    assert response.status_code == 404 and response.json()["error"]["code"] == "DATA_NOT_AVAILABLE"
    assert "MOCK" not in response.text


def test_data_version_pin_mismatch_fails(make_settings):
    with pytest.raises(ConfigError, match="pin"):
        with TestClient(create_app(make_settings(DATA_VERSION="2026-11-14a"))):
            pass
