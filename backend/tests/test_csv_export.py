"""Step 5: GET /api/v1/export/csv — data fidelity, metadata headers, errors."""

from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
from datetime import date, datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.advanced_schemas import AnomalyResult
from app.config import REPO_ROOT
from app.errors import ApiError
from app.main import create_app
from app.schemas import Period, SeriesPoint, TimeSeries, TrendResult
from app.services.csv_export import (
    ANOMALY_COLUMNS, SERIES_COLUMNS, TREND_COLUMNS, ExportRequest, build_csv_export, decode_text_cell,
)
from app.services.store import MockStore

URL = "/api/v1/export/csv"
NORMAL = REPO_ROOT / "data" / "mock" / "normal"


def split(content: bytes) -> tuple[list[str], list[list[str]]]:
    text = content.decode("utf-8")
    header = [line for line in text.splitlines() if line.startswith("#")]
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    return header, list(csv.reader(io.StringIO(body)))


def frame(content: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(content), comment="#")


def get(client, **params):
    return client.get(URL, params=params)


# ----------------------------------------------------------------- series


def test_series_export_matches_store_values_and_metadata(client):
    response = get(client, region_id="IGP", variable="aod")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        'attachment; filename="TrendTrace_IGP_aod_month_series_2003-01_2024-12.csv"')
    header, rows = split(response.content)
    joined = "\n".join(header)
    for expected in ("TrendTrace export | MOCK | data_status=mock", "region=IGP", "variable=aod", "frequency=month",
                     "what=series", "start=2003-01", "end=2024-12", "data_version=MOCK-2026-11-13-normal",
                     "doi=not available (MOCK data)", "units: aod 1 (dimensionless", "never zero",
                     "contract_version=1.0", "source_id=MODIS_AQUA_C61_MONTHLY"):
        assert expected in joined
    stamp = joined.split("generated_at=")[1].strip()
    assert datetime.fromisoformat(stamp).utcoffset() is not None

    df = frame(response.content)
    assert list(df.columns) == SERIES_COLUMNS == rows[0]
    series = MockStore(NORMAL).series("IGP", "aod", "month")
    assert len(df) == len(series.points) == 264
    for (_, row), point in zip(df.iterrows(), series.points):
        assert row["date"] == point.date.isoformat()
        if point.value is None:
            assert pd.isna(row["value"]) and row["qc_flag"] == "missing"
        else:
            assert row["value"] == point.value


def test_missing_is_empty_cell_and_real_zero_stays_zero(client):
    _, rows = split(get(client, region_id="IGP", variable="rainfall").content)
    columns, data = rows[0], rows[1:]
    value_at = columns.index("value")
    missing = [r for r in data if r[columns.index("qc_flag")] == "missing"]
    zeros = [r for r in data if r[value_at] == "0.0"]
    assert missing and all(r[value_at] == "" for r in missing)
    assert zeros and all(r[columns.index("qc_flag")] == "ok" for r in zeros)
    flat = {cell for r in data for cell in r}
    assert not flat & {"-9999", "nan", "NaN", "None", "null"}
    df = frame(get(client, region_id="IGP", variable="rainfall").content)
    assert (df["value"] == 0.0).sum() == len(zeros)
    assert df["value"].isna().sum() == len(missing)


def test_sub_period_and_daily_exports(client):
    df = frame(get(client, region_id="TN", variable="rainfall", start="2010-01", end="2010-12").content)
    assert list(df["date"]) == [f"2010-{m:02d}-01" for m in range(1, 13)]
    daily = get(client, region_id="TN", variable="rainfall", frequency="day", start="2015-01", end="2024-12")
    assert daily.status_code == 200
    df = frame(daily.content)
    assert len(df) == 3653 and set(df["unit"]) == {"mm/day"}
    assert (df["value"] == 0.0).any()


# ----------------------------------------------------------------- trend and anomalies


def test_trend_export_is_one_row_with_reconstructable_nested_fields(client):
    response = get(client, region_id="IGP", variable="aod", what="trend")
    assert response.status_code == 200
    header, rows = split(response.content)
    assert "slopes in 1 per decade" in "\n".join(header)
    df = frame(response.content)
    assert list(df.columns) == TREND_COLUMNS and len(df) == 1
    trend = MockStore(NORMAL).trend("IGP", "aod", Period(start="2003-01", end="2024-12"), "all")
    row = df.iloc[0]
    assert row["sen_slope"] == trend.sen_slope and row["p_value"] == trend.p_value
    assert bool(row["significant"]) is trend.significant and row["direction"] == trend.direction
    rebuilt = {}
    for name in TREND_COLUMNS:
        cell = rows[1][TREND_COLUMNS.index(name)]
        rebuilt[name] = json.loads(decode_text_cell(cell)) if cell[:1] in "[{" else cell
    assert TrendResult.model_validate({**trend.model_dump(mode="json"), **{
        k: rebuilt[k] for k in ("period", "method", "slope_ci", "ols_ci", "limitations", "evidence")}}) == trend


def test_anomaly_export_lists_window_months_with_baseline_header(client):
    response = get(client, region_id="TN", variable="rainfall", what="anomalies", start="2024-01", end="2024-12")
    assert response.status_code == 200
    header, _ = split(response.content)
    joined = "\n".join(header)
    assert "baseline: start=2003-01 | end=2024-12 | method=same_calendar_month" in joined
    assert "thresholds: high=0.9 | low=0.1" in joined
    df = frame(response.content)
    assert list(df.columns) == ANOMALY_COLUMNS and len(df) == 12
    expected = MockStore(NORMAL).anomalies("TN", "rainfall", Period(start="2024-01", end="2024-12"), False)
    for (_, row), entry in zip(df.iterrows(), expected.anomalies):
        assert row["date"] == entry.date.isoformat()
        assert (pd.isna(row["score"]) and entry.score is None) or row["score"] == entry.score


# ----------------------------------------------------------------- errors


@pytest.mark.parametrize("params,status,code", [
    ({"region_id": "XX", "variable": "aod"}, 400, "INVALID_REGION"),
    ({"region_id": "IGP", "variable": "pm25"}, 400, "INVALID_VARIABLE"),
    ({"region_id": "IGP", "variable": "aod", "frequency": "week"}, 422, "VALIDATION_ERROR"),
    ({"region_id": "IGP", "variable": "aod", "start": "2003-13"}, 400, "INVALID_PERIOD"),
    ({"region_id": "IGP", "variable": "aod", "start": "2010-01", "end": "2005-01"}, 400, "INVALID_PERIOD"),
    ({"region_id": "IGP", "variable": "aod", "start": "1999-01"}, 400, "INVALID_PERIOD"),
    ({"region_id": "IGP", "variable": "aod", "frequency": "day", "start": "2014-12", "end": "2024-12"}, 400, "INVALID_PERIOD"),
    ({"region_id": "IGP", "variable": "aod", "what": "pdf"}, 400, "INVALID_EXPORT_TYPE"),
    ({"region_id": "IGP", "variable": "aod", "what": "trend", "start": "2016-01"}, 422, "PERIOD_TOO_SHORT"),
    ({"region_id": "IGP", "variable": "aod", "what": "trend", "start": "2014-01"}, 404, "DATA_NOT_AVAILABLE"),
    ({"region_id": "IGP", "variable": "aod", "what": "trend", "frequency": "day"}, 422, "VALIDATION_ERROR"),
    ({"variable": "aod"}, 422, "VALIDATION_ERROR"),
])
def test_errors_are_json_never_csv(client, params, status, code):
    response = get(client, **params)
    assert response.status_code == status
    assert response.headers["content-type"] == "application/json"
    assert "content-disposition" not in response.headers
    assert response.json()["error"]["code"] == code


def test_daily_limit_reason_is_reported(client):
    body = get(client, region_id="IGP", variable="aod", frequency="day", start="2014-12", end="2024-12").json()
    assert body["error"]["details"]["reason"] == "daily_limit_exceeded"


@pytest.fixture
def scenario_client(make_settings, tmp_path):
    def _client(scenario: str) -> TestClient:
        return TestClient(create_app(make_settings(MOCK_SCENARIO=scenario, REPORTS_DIR=str(tmp_path))))
    return _client


def test_sparse_series_returns_insufficient_data(scenario_client):
    with scenario_client("sparse") as c:
        response = get(c, region_id="IGP", variable="aod")
        daily = get(c, region_id="IGP", variable="aod", frequency="day", start="2015-01", end="2024-12")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "INSUFFICIENT_DATA" and error["details"]["valid_pct"] < 70
    assert daily.status_code == 404 and daily.json()["error"]["code"] == "DATA_NOT_AVAILABLE"


def test_short_record_trend_is_too_short(scenario_client):
    with scenario_client("short") as c:
        response = get(c, region_id="TN", variable="rainfall", what="trend")
    assert response.status_code == 422 and response.json()["error"]["code"] == "PERIOD_TOO_SHORT"


def test_unexpected_store_failure_is_sanitized(settings):
    class Broken(MockStore):
        def series(self, *args, **kwargs):
            raise RuntimeError("disk /secret/path exploded")

    with TestClient(create_app(settings, store=Broken(NORMAL)), raise_server_exceptions=False) as c:
        response = get(c, region_id="IGP", variable="aod")
    assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text


# ----------------------------------------------------------------- service-level fidelity cases


class TenMonthStore(MockStore):
    """10-month region; `n_valid` of the months carry values (boundary tests)."""

    def __init__(self, n_valid: int, values: list[float] | None = None) -> None:
        super().__init__(NORMAL)
        self._n_valid, self._values = n_valid, values

    def regions(self):
        result = super().regions()
        regions = [r.model_copy(update={"period_available": Period(start="2020-01", end="2020-10")})
                   for r in result.regions]
        return result.model_copy(update={"regions": regions})

    def series(self, region_id, variable, frequency):
        values = self._values or [0.5] * 10
        points = [SeriesPoint(date=date(2020, m, 1), value=values[m - 1] if m <= self._n_valid else None,
                              valid_fraction=1.0 if m <= self._n_valid else 0.0,
                              qc_flag="ok" if m <= self._n_valid else "missing") for m in range(1, 11)]
        return TimeSeries(region_id=region_id, variable=variable, frequency="month", unit="1",
                          source_id="MODIS_AQUA_C61_MONTHLY", points=points)


def _export(store, what="series", **kw):
    req = ExportRequest(kw.get("region_id", "IGP"), kw.get("variable", "aod"), "month", None, None, what)
    return build_csv_export(store, req, app_name="TrendTrace", contract_version="1.0",
                            generated_at="2026-11-13T12:00:00+05:30")


def test_seventy_percent_boundary_passes_and_below_fails():
    assert len(frame(_export(TenMonthStore(7)).content)) == 10
    with pytest.raises(ApiError) as err:
        _export(TenMonthStore(6))
    assert err.value.code == "INSUFFICIENT_DATA" and err.value.details["valid_pct"] == 60.0


def test_high_precision_values_survive_unrounded():
    values = [0.12345678901234566, 123456.78901234567, 1e-12, 0.1, 0.0, 2.5, 3.0, 7.75, 1 / 3, 9.999999999999998]
    content = _export(TenMonthStore(10, values)).content
    _, rows = split(content)
    parsed = [float(r[SERIES_COLUMNS.index("value")]) for r in rows[1:]]
    assert parsed == values  # exact float round-trip, no rounding
    assert list(frame(content)["value"]) == values


def test_text_with_hash_comma_quote_newline_survives_pandas():
    tricky = 'note #1, "quoted", line\nbreak \\ end'

    class TrickyStore(MockStore):
        def anomalies(self, region_id, variable, period, detrended):
            result: AnomalyResult = super().anomalies(region_id, variable, period, detrended)
            rows = [a.model_copy(update={"note": tricky}) for a in result.anomalies]
            return result.model_copy(update={"anomalies": rows})

    req = ExportRequest("IGP", "aod", "month", "2024-01", "2024-03", "anomalies")
    content = build_csv_export(TrickyStore(NORMAL), req, app_name="Trend#Trace", contract_version="1.0",
                               generated_at="2026-11-13T12:00:00+05:30").content
    df = frame(content)
    assert len(df) == 3 and list(df.columns) == ANOMALY_COLUMNS
    assert all(decode_text_cell(n) == tricky for n in df["note"])


def test_empty_anomaly_list_gives_header_only_csv():
    class EmptyStore(MockStore):
        def anomalies(self, region_id, variable, period, detrended):
            return super().anomalies(region_id, variable, period, detrended).model_copy(update={"anomalies": []})

    req = ExportRequest("IGP", "aod", "month", "2024-01", "2024-12", "anomalies")
    df = frame(build_csv_export(EmptyStore(NORMAL), req, app_name="TrendTrace", contract_version="1.0",
                                generated_at="2026-11-13T12:00:00+05:30").content)
    assert list(df.columns) == ANOMALY_COLUMNS and len(df) == 0


def test_csv_module_does_not_import_pdf_libraries():
    code = ("import sys; sys.path.insert(0, 'backend'); import app.routers.export; "
            "assert 'reportlab' not in sys.modules and 'matplotlib' not in sys.modules")
    subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, check=True)
