"""Regressions for the issues found in the 15 Nov review: each test reproduces one report."""

from __future__ import annotations

import json
import re

import pandas as pd
import pytest
from conftest import build_settings
from fastapi.testclient import TestClient

from app.config import REPO_ROOT
from app.main import create_app

FRONTEND = REPO_ROOT / "frontend"


@pytest.fixture(scope="module")
def real_client():
    with TestClient(create_app(build_settings(DATA_MODE="real"))) as client:
        yield client


@pytest.mark.parametrize("body", [{"dates": [], "values": []},
                                  {"dates": ["not-a-date", "nope"], "values": [1, 2]}])
def test_bad_inline_series_is_a_validation_error_not_a_500(real_client, body):
    res = real_client.post("/api/v1/analyze/series", json=body)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("region", ["IGP", "TN"])
@pytest.mark.parametrize("season", ["annual", "JJAS", "OND"])
def test_rx5day_is_served(real_client, region, season):
    res = real_client.get(f"/api/v1/rainfall/indicators?region_id={region}&indicator=rx5day&season={season}")
    assert res.status_code == 200
    r = res.json()["result"]
    assert r["unit"] == "mm" and len(r["values"]) == 22 and r["trend"] is not None


def test_rx5day_matches_an_independent_rolling_sum():
    daily = pd.read_csv(REPO_ROOT / "group3_pipeline" / "results" / "timeseries_daily.csv", parse_dates=["date"])
    rain = daily[(daily.region_id == "IGP") & (daily.variable == "rainfall")].set_index("date")["value"]
    meta = json.loads((REPO_ROOT / "data" / "processed" / "rainfall_indicators_metadata.json").read_text())["result"]
    served = next(r for r in meta if (r["region_id"], r["indicator"], r["season"]) == ("IGP", "rx5day", "annual"))
    for v in served["values"]:
        year = rain[str(v["year"])]
        expected = year.rolling(5, min_periods=5).sum().max()
        if v["value"] is not None:
            assert v["value"] == pytest.approx(round(expected, 4), abs=1e-3), v["year"]


def test_csv_link_carries_the_analysed_period_and_the_export_honours_it(real_client):
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert "&start=${encodeURIComponent(tr.period.start)}&end=${encodeURIComponent(tr.period.end)}" in js
    body = real_client.get("/api/v1/export/csv?region_id=IGP&variable=aod&start=2010-01&end=2020-12").text
    rows = [line for line in body.splitlines() if line and not line.startswith("#")][1:]
    assert rows[0].startswith("2010-01") and rows[-1].startswith("2020-12")


def test_lab_waits_for_metadata_before_submitting():
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert 'getElementById("lab-panels").addEventListener("submit"' in js and "if (metaLoaded) return;" in js


def test_charts_break_at_missing_data_and_invent_no_bands():
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")
    guide = (FRONTEND / "guide.js").read_text(encoding="utf-8")
    assert "function gapSegments" in app and "segs.push([])" in guide
    assert "2013.5" not in app            # no browser-built trend band for rainfall indicators
    assert re.search(r"hasBand \? el\(", app)   # the band legend appears only when a band is drawn


def test_back_to_orbit_scrolls_the_window():
    fx = (FRONTEND / "fx.js").read_text(encoding="utf-8")
    assert "a[href=\"#top\"]" in fx and "window.scrollTo({ top: 0" in fx
