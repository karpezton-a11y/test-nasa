"""Task 6: real-data acceptance checks for Karnish's endpoints.

Runs against APP_ENV=prod + DATA_MODE=real through Adrian's loader. Skipped
automatically until both exist: app/services/real_store.py and files in
data/processed/. The checker functions are also run here on a relabelled copy
of the mock data, so they are known to work before the real files arrive.

Reference files (optional, Group 3): data/processed/reference/<name>.json, each
{"endpoint": "/anomalies", "params": {...}, "result": {...}}; numbers must match
the live endpoint within 1e-6. File layout: docs/handoff/real_data_dropin.md.
"""

from __future__ import annotations

import importlib.util
import json
import math
import shutil
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, ConfigError
from app.main import create_app
from app.services.advanced import INDICATOR_SEASONS, INDICATORS, INTERACTION_SEASONS
from app.services.store import DatasetInfo, MockStore

API = "/api/v1"
PROCESSED = REPO_ROOT / "data" / "processed"
REFERENCE_DIR = PROCESSED / "reference"
TOLERANCE = 1e-6
REFERENCE_ENDPOINTS = ("/anomalies", "/interaction", "/rainfall/indicators")
# Files every real delivery must contain (docs/handoff/real_data_dropin.md). If Adrian's loader settles on
# another layout (decision DS-2), change this list, never skip the check.
REQUIRED_PROCESSED_FILES = ("variables.json", "sources.json")
REGIONS_FILES = ("regions.geojson", "regions.json")
QC_FLAGS = {"ok", "low_coverage", "missing", "suspect"}
UNITS = {("rainfall", "month"): "mm/month", ("rainfall", "day"): "mm/day", ("aod", "month"): "1", ("aod", "day"): "1"}


def _has_real_inputs() -> bool:
    has_loader = importlib.util.find_spec("app.services.real_store") is not None
    has_files = PROCESSED.is_dir() and any(p.is_file() and p.name != ".gitkeep" for p in PROCESSED.rglob("*"))
    return has_loader and has_files


needs_real = pytest.mark.skipif(not _has_real_inputs(),
                                reason="real data not delivered yet (needs real_store.py + data/processed/)")


# ----------------------------------------------------------------- reusable checks (return problem lists)


def advanced_responses(client: TestClient) -> Iterator[tuple[str, dict, Any]]:
    """Every advanced request for every region; yields (path, params, response)."""
    for region in client.get(f"{API}/regions").json()["result"]["regions"]:
        rid = region["region_id"]
        variables = region["variables"] + (["both"] if {"rainfall", "aod"} <= set(region["variables"]) else [])
        for variable in variables:
            params = {"region_id": rid, "variable": variable}
            yield "/anomalies", params, client.get(f"{API}/anomalies", params=params)
        for season in INTERACTION_SEASONS:
            params = {"region_id": rid, "season": season}
            yield "/interaction", params, client.get(f"{API}/interaction", params=params)
        for indicator in INDICATORS:
            for season in INDICATOR_SEASONS:
                params = {"region_id": rid, "indicator": indicator, "season": season}
                yield "/rainfall/indicators", params, client.get(f"{API}/rainfall/indicators", params=params)


def _source_ids(result: dict) -> set[str]:
    if "results" in result:
        return {r["source_id"] for r in result["results"]}
    if "source_ids" in result:
        return set(result["source_ids"].values())
    ids = {result["source_id"]}
    if result.get("trend"):
        ids.add(result["trend"]["source_id"])
    return ids


def _series_problems(store: Any, region_id: str, variable: str, frequency: str, registry: set[str]) -> list[str]:
    tag = f"{region_id}/{variable}/{frequency}"
    if frequency == "day":
        try:
            if store.series(region_id, variable, "month").source_id.startswith("NASA_POWER"):
                return []  # monthly-only NASA POWER import (e.g. SAHEL rainfall): no daily product delivered
        except Exception:  # noqa: BLE001 - reported by the monthly check
            pass
    try:
        series = store.series(region_id, variable, frequency)
    except Exception:  # noqa: BLE001 - absent data is reported as a problem, never faked
        return [f"series {tag} not available"]
    problems = []
    declared = next((v.unit for v in store.variables() if v.variable == variable), None)
    if series.unit != UNITS.get((variable, frequency), declared):  # catalogue variables: their declared unit
        problems.append(f"{tag}: unit {series.unit!r}")
    if series.source_id not in registry:
        problems.append(f"{tag}: source_id {series.source_id!r} not in /meta/sources")
    if frequency == "month" and any(p.date.day != 1 for p in series.points):
        problems.append(f"{tag}: monthly dates must be YYYY-MM-01")
    if any(p.qc_flag not in QC_FLAGS or not (p.valid_fraction is None or 0 <= p.valid_fraction <= 1)
           for p in series.points):
        problems.append(f"{tag}: qc_flag/valid_fraction out of contract")
    return problems


def structural_problems(client: TestClient) -> list[str]:
    """Dates, units, source IDs, valid_fraction and qc_flag rules on served data."""
    store = client.app.state.store
    registry = {s["source_id"] for s in client.get(f"{API}/meta/sources").json()["result"]}
    problems = [problem
                for region in client.get(f"{API}/regions").json()["result"]["regions"]
                for variable in region["variables"]
                for frequency in (("month", "day") if (variable, "day") in UNITS else ("month",))
                for problem in _series_problems(store, region["region_id"], variable, frequency, registry)]
    for path, params, response in advanced_responses(client):
        if response.status_code == 404 and response.json()["error"]["code"] == "DATA_NOT_AVAILABLE":
            continue  # allowed until H7/H9; the endpoint says so instead of guessing
        if response.status_code != 200:
            problems.append(f"{path} {params}: HTTP {response.status_code}")
            continue
        unknown = _source_ids(response.json()["result"]) - registry
        if unknown:
            problems.append(f"{path} {params}: source_ids {sorted(unknown)} not in /meta/sources")
    return problems


def provenance_problems(client: TestClient) -> list[str]:
    """Every served envelope is real with a non-mock data_version; no mock-labelled asset or text."""
    problems: list[str] = []
    bad_assets = sorted(k for k, v in client.app.state.store.asset_statuses().items() if v != "real")
    if bad_assets:
        problems.append(f"assets without real provenance: {bad_assets[:5]}")
    light = [(p, {}, client.get(f"{API}{p}")) for p in ("/health", "/variables", "/regions", "/meta/sources")]
    for path, params, response in [*light, *advanced_responses(client)]:
        if response.status_code != 200:
            continue
        body = response.json()
        if body["data_status"] != "real" or body["data_version"].upper().startswith("MOCK"):
            problems.append(f"{path} {params}: data_status={body['data_status']} version={body['data_version']}")
        if "MOCK" in json.dumps(body["result"]):
            problems.append(f"{path} {params}: result text contains 'MOCK'")
    return sorted(set(problems))


def numeric_differences(expected: Any, actual: Any, path: str = "result", tol: float = TOLERANCE) -> list[str]:
    """Paths where two JSON values differ (numbers within tol; null must stay null)."""
    if isinstance(expected, bool) or isinstance(actual, bool) or expected is None or actual is None:
        return [] if expected == actual else [path]
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return [] if math.isclose(expected, actual, rel_tol=0.0, abs_tol=tol) else [path]
    if isinstance(expected, dict) and isinstance(actual, dict):
        if set(expected) != set(actual):
            return [f"{path} keys"]
        return [d for k in expected for d in numeric_differences(expected[k], actual[k], f"{path}.{k}", tol)]
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{path} length"]
        return [d for i, (e, a) in enumerate(zip(expected, actual))
                for d in numeric_differences(e, a, f"{path}[{i}]", tol)]
    return [] if expected == actual else [path]


def layout_problems(processed: Path = PROCESSED) -> list[str]:
    """A stray file must not make the real suite look delivered: the core files must all be there."""
    missing = [name for name in REQUIRED_PROCESSED_FILES if not (processed / name).is_file()]
    if not any((processed / name).is_file() for name in REGIONS_FILES):
        missing.append(" or ".join(REGIONS_FILES))
    return [f"data/processed/ is missing {name}" for name in missing]


def _reference_files(reference_dir: Path) -> list[tuple[Path, dict]]:
    files = sorted(reference_dir.glob("*.json")) if reference_dir.is_dir() else []
    return [(path, json.loads(path.read_text(encoding="utf-8"))) for path in files]


def missing_references(client: TestClient, reference_dir: Path = REFERENCE_DIR) -> list[str]:
    """An empty reference folder must not pass: each endpoint needs at least one reference per region."""
    covered = {(ref.get("endpoint"), ref.get("params", {}).get("region_id"))
               for _, ref in _reference_files(reference_dir)}
    regions = [r["region_id"] for r in client.get(f"{API}/regions").json()["result"]["regions"]]
    return [f"no reference file for {endpoint} region {region}"
            for endpoint in REFERENCE_ENDPOINTS for region in regions if (endpoint, region) not in covered]


def reference_problems(client: TestClient, reference_dir: Path = REFERENCE_DIR) -> list[str]:
    problems: list[str] = []
    for ref_file, ref in _reference_files(reference_dir):
        if ref.get("endpoint") not in REFERENCE_ENDPOINTS:
            continue  # /analyze references (trend_results_reference.json) are Adrian's test
        response = client.get(f"{API}{ref['endpoint']}", params=ref["params"])
        if response.status_code != 200:
            problems.append(f"{ref_file.name}: HTTP {response.status_code}")
            continue
        diffs = numeric_differences(ref["result"], response.json()["result"])
        if diffs:
            problems.append(f"{ref_file.name}: differs at {diffs[:5]}")
    return problems


# ----------------------------------------------------------------- real data (skipped until delivered)


@pytest.fixture(scope="module")
def real_client(tmp_path_factory) -> Iterator[TestClient]:
    from app.config import load_settings

    settings = load_settings(env={"APP_ENV": "prod", "DATA_MODE": "real",
                                  "REPORTS_DIR": str(tmp_path_factory.mktemp("reports"))}, env_file=None)
    with TestClient(create_app(settings)) as client:
        yield client


@needs_real
def test_real_data_has_the_expected_layout():
    assert layout_problems() == []


@needs_real
def test_real_data_structure(real_client):
    assert structural_problems(real_client) == []


@needs_real
def test_real_data_provenance_and_no_mock_in_prod(real_client):
    assert provenance_problems(real_client) == []


@needs_real
@pytest.mark.skipif(not REFERENCE_DIR.is_dir(),
                    reason="Aadarsh's independent reference outputs not delivered; Group 3's own values are "
                           "checked by test_real_values_match_group3_csv")
def test_real_results_equal_group3_references(real_client):
    assert missing_references(real_client) == []  # nothing compared is a failure, not a pass
    assert reference_problems(real_client) == []


# ----------------------------------------------------------------- the checkers themselves (always run)


class RelabelledStore(MockStore):
    """Mock fixtures relabelled 'real' (in memory only): proves the checkers catch leftover mock text."""

    def __init__(self, scenario_dir: Path) -> None:
        super().__init__(scenario_dir)
        self.info = DatasetInfo("real", "2026-11-14-test", self.info.contract_version)

    def _envelope(self, relative: str):
        envelope = self._load(relative)
        self._loaded[relative] = "real"
        return envelope.model_copy(update={"data_status": "real", "data_version": self.info.data_version})


@pytest.fixture
def relabelled_client(make_settings, tmp_path) -> Iterator[TestClient]:
    copy = tmp_path / "normal"
    shutil.copytree(REPO_ROOT / "data" / "mock" / "normal", copy)
    settings = make_settings(APP_ENV="dev", DATA_MODE="real", REPORTS_DIR=str(tmp_path / "reports"))
    with TestClient(create_app(settings, store=RelabelledStore(copy))) as client:
        yield client


def test_structural_checker_accepts_contract_shaped_data(relabelled_client):
    assert structural_problems(relabelled_client) == []


def test_provenance_checker_flags_leftover_mock_text(relabelled_client):
    assert any("contains 'MOCK'" in p for p in provenance_problems(relabelled_client))


def test_reference_checker_uses_tolerance_and_null_rule(relabelled_client, tmp_path):
    params = {"region_id": "IGP", "season": "JJAS"}
    live = relabelled_client.get(f"{API}/interaction", params=params).json()["result"]
    close = {**live, "median_change": live["median_change"] + 5e-7}
    far = {**live, "median_change": live["median_change"] + 1e-3}
    nulled = {**live, "p_value": None}
    for name, result in (("close", close), ("far", far), ("nulled", nulled)):
        (tmp_path / f"{name}.json").write_text(json.dumps({"endpoint": "/interaction", "params": params,
                                                           "result": result}), encoding="utf-8")
    problems = reference_problems(relabelled_client, tmp_path)
    assert [p.split(":")[0] for p in problems] == ["far.json", "nulled.json"]


def test_empty_reference_folder_is_reported_not_passed(relabelled_client, tmp_path):
    missing = missing_references(relabelled_client, tmp_path / "reference")
    assert len(missing) == 2 * len(REFERENCE_ENDPOINTS)
    assert "no reference file for /interaction region TN" in missing


def test_reference_coverage_counts_each_endpoint_and_region(relabelled_client, tmp_path):
    for endpoint in REFERENCE_ENDPOINTS:
        for region in ("IGP", "TN"):
            name = f"{endpoint.strip('/').replace('/', '_')}_{region}.json"
            (tmp_path / name).write_text(json.dumps({"endpoint": endpoint, "params": {"region_id": region},
                                                     "result": {}}), encoding="utf-8")
    assert missing_references(relabelled_client, tmp_path) == []
    (tmp_path / "rainfall_indicators_TN.json").unlink()
    assert missing_references(relabelled_client, tmp_path) == ["no reference file for /rainfall/indicators region TN"]


def test_a_stray_file_is_not_a_real_delivery(tmp_path):
    (tmp_path / "notes.txt").write_text("draft", encoding="utf-8")
    assert len(layout_problems(tmp_path)) == 3
    for name in ("variables.json", "sources.json", "regions.geojson"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert layout_problems(tmp_path) == []


def test_prod_refuses_a_store_that_attests_any_mock_asset(make_settings):
    class HalfMock(RelabelledStore):
        def asset_statuses(self):
            return {"variables.json": "real", "anomalies/IGP_aod_raw.json": "mock"}

    store = HalfMock(REPO_ROOT / "data" / "mock" / "normal")
    with pytest.raises(ConfigError, match="Production start refused"):
        with TestClient(create_app(make_settings(APP_ENV="prod", DATA_MODE="real"), store=store)):
            pass


# ----------------------------------------------------------------- served values equal Group 3's own CSVs


GROUP3_RESULTS = REPO_ROOT / "group3_pipeline" / "results"


@needs_real
@pytest.mark.skipif(not GROUP3_RESULTS.is_dir(), reason="group3_pipeline/results not present")
def test_real_values_match_group3_csv(real_client):
    """Every served anomaly, indicator and series value equals Group 3's original CSV (no conversion drift)."""
    import csv
    problems = []
    for rid in ("IGP", "TN"):
        for var in ("rainfall", "aod"):
            served = real_client.get(f"{API}/anomalies", params={"region_id": rid, "variable": var}).json()["result"]
            by_date = {a["date"]: a for a in served["anomalies"]}
            rows = [r for r in csv.DictReader((GROUP3_RESULTS / "anomalies_monthly_primary.csv").open(encoding="utf-8"))
                    if r["region_id"] == rid and r["variable"] == var]
            assert len(rows) == len(by_date) == 264
            for r in rows:
                a = by_date[r["date"]]
                for key in ("value", "baseline_median", "score"):
                    if not math.isclose(float(r[key]), a[key], abs_tol=1e-9):
                        problems.append((rid, var, r["date"], key))
                if (r["category"] if r["category"] != "typical" else None) != a["category"]:
                    problems.append((rid, var, r["date"], "category"))
            series = real_client.get(f"{API}/timeseries", params={"region_id": rid, "variable": var}).json()["result"]
            g3 = {r["date"]: r for r in csv.DictReader((GROUP3_RESULTS / "timeseries_monthly_primary.csv").open(encoding="utf-8"))
                  if r["region_id"] == rid and r["variable"] == var}
            for p in series["points"]:
                if not math.isclose(float(g3[p["date"]]["value"]), p["value"], abs_tol=1e-12):
                    problems.append((rid, var, p["date"], "series"))
    for r in csv.DictReader((GROUP3_RESULTS / "rainfall_indicators_annual.csv").open(encoding="utf-8")):
        season = "annual" if r["season"] == "ALL" else r["season"]
        served = real_client.get(f"{API}/rainfall/indicators",
                                 params={"region_id": r["region_id"], "indicator": r["indicator"], "season": season}).json()["result"]
        value = next(v["value"] for v in served["values"] if v["year"] == int(r["year"]))
        if not math.isclose(float(r["value"]), value, abs_tol=1e-9):
            problems.append((r["region_id"], r["indicator"], season, r["year"]))
    assert problems == []


@needs_real
def test_real_interaction_is_computed_with_guardrail_and_honest_status(real_client):
    for rid in ("IGP", "TN"):
        for season in INTERACTION_SEASONS:
            body = real_client.get(f"{API}/interaction", params={"region_id": rid, "season": season}).json()
            result = body["result"]
            assert body["data_status"] == "real"
            assert result["guardrail"].startswith("Association only")
            assert (result["status"] == "ok") == (result["n_events_used"] >= 10)
