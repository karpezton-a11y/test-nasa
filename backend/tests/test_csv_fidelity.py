"""Task 8: CSV exports equal the matching API results for the same request.

series -> the store series the API serves (sliced to the period)
trend  -> the stored TrendResult for that period/season
anomalies -> exactly GET /anomalies for the same region/variable/period
Plus: header metadata, null vs zero, pandas comment='#' round trip, and CSV keeps
working when the PDF stack cannot be imported.
"""

from __future__ import annotations

import io
import sys

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import Period
from app.services.csv_codec import read_export
from app.services.csv_export import ANOMALY_COLUMNS, SERIES_COLUMNS
from app.services.validation import slice_series

API = "/api/v1"


def _export(client, **params) -> bytes:
    response = client.get(f"{API}/export/csv", params=params)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    return response.content


@pytest.mark.parametrize("region,variable,start,end", [
    ("TN", "rainfall", "2003-01", "2024-12"), ("IGP", "aod", "2015-01", "2019-12"),
])
def test_anomaly_csv_equals_the_anomalies_api_result(client, region, variable, start, end):
    params = {"region_id": region, "variable": variable, "start": start, "end": end}
    api = client.get(f"{API}/anomalies", params=params).json()
    decoded = read_export(_export(client, what="anomalies", **params))
    result = api["result"]
    assert decoded.columns == ANOMALY_COLUMNS
    expected = [{"region_id": region, "variable": variable, "source_id": result["source_id"],
                 "unit": result["unit"], **{k: a[k] for k in ANOMALY_COLUMNS if k in a}}
                for a in result["anomalies"]]
    assert decoded.rows == expected
    meta = decoded.metadata
    assert (meta["start"], meta["end"]) == (start, end)
    assert meta["result_id"] == result["result_id"]
    assert meta["source_id"] == result["source_id"] and meta["data_version"] == api["data_version"]
    assert meta["data_status"] == api["data_status"] == "mock"
    assert meta["baseline.start"] == result["baseline"]["start"]


def test_series_csv_equals_the_served_series_for_the_period(client):
    store = client.app.state.store
    content = _export(client, region_id="TN", variable="rainfall", start="2010-01", end="2014-12")
    decoded = read_export(content)
    served = slice_series(store.series("TN", "rainfall", "month"), Period(start="2010-01", end="2014-12"))
    assert decoded.columns == SERIES_COLUMNS
    assert [(r["date"], r["value"], r["valid_fraction"], r["qc_flag"]) for r in decoded.rows] == [
        (p.date.isoformat(), p.value, p.valid_fraction, p.qc_flag) for p in served.points]
    assert {r["unit"] for r in decoded.rows} == {"mm/month"}
    assert {r["source_id"] for r in decoded.rows} == {served.source_id}
    assert b"# units: rainfall mm/month" in content


def test_trend_csv_equals_the_stored_trend(client):
    store = client.app.state.store
    decoded = read_export(_export(client, region_id="IGP", variable="aod", what="trend"))
    trend = store.trend("IGP", "aod", Period(start="2003-01", end="2024-12"), "all")
    assert len(decoded.rows) == 1
    assert decoded.rows[0] == trend.model_dump(mode="json")


def test_null_stays_empty_and_zero_stays_zero_in_pandas(client):
    content = _export(client, region_id="TN", variable="rainfall")
    frame = pd.read_csv(io.BytesIO(content), comment="#")
    served = client.app.state.store.series("TN", "rainfall", "month").points
    assert frame["value"].isna().sum() == sum(p.value is None for p in served) > 0
    assert (frame["value"] == 0).sum() == sum(p.value == 0 for p in served) > 0
    assert b",," in content and b",0.0," in content  # empty cell for missing, literal 0.0 for zero


def test_anomaly_csv_reads_with_pandas_comment_hash(client):
    content = _export(client, region_id="IGP", variable="aod", what="anomalies", start="2020-01", end="2020-12")
    frame = pd.read_csv(io.BytesIO(content), comment="#")
    assert list(frame.columns) == ANOMALY_COLUMNS and len(frame) == 12
    assert set(frame["date"]) == {f"2020-{m:02d}-01" for m in range(1, 13)}


def test_csv_still_works_when_the_pdf_stack_cannot_be_imported(settings, monkeypatch):
    import app.routers

    monkeypatch.setitem(sys.modules, "app.routers.reports", None)  # importing it now raises ImportError
    monkeypatch.delattr(app.routers, "reports", raising=False)
    with TestClient(create_app(settings)) as c:
        csv_response = c.get(f"{API}/export/csv", params={"region_id": "IGP", "variable": "aod"})
        report = c.post(f"{API}/report", json={"region_id": "IGP", "variables": ["aod"], "start": "2003-01",
                                               "end": "2024-12"})
    assert csv_response.status_code == 200 and csv_response.text.startswith("# TrendTrace export")
    assert report.status_code == 500 and report.json()["error"]["code"] == "REPORT_FAILED"
