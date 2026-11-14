"""Step 6: PDF report creation/download, number agreement, gaps, IDs, failures."""

from __future__ import annotations

import io
import re
import subprocess
import sys
import time
from dataclasses import replace
from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.advanced_schemas import ReportRequest
from app.config import REPO_ROOT
from app.main import create_app
from app.reports import charts
from app.reports.content import AiSummary
from app.reports.formatting import fmt_number, fmt_p
from app.reports.pdf import build_pdf
from app.reports.service import assemble_report
from app.reports.store import ReportFileStore
from app.schemas import Period, SeriesPoint, TimeSeries
from app.services.store import MockStore

NORMAL = REPO_ROOT / "data" / "mock" / "normal"
FULL = Period(start="2003-01", end="2024-12")
BODY = {"region_id": "IGP", "variables": ["rainfall", "aod"], "start": "2003-01", "end": "2024-12", "season": "all",
        "include": ["trend", "anomalies", "interaction", "indicators"], "include_ai_summary": True}


def pdf_text(content: bytes) -> tuple[list[str], str]:
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(content)).pages]
    return pages, " ".join(" ".join(pages).split())


@pytest.fixture
def created(client):
    response = client.post("/api/v1/report", json=BODY)
    assert response.status_code == 200, response.text
    body = response.json()
    download = client.get(body["result"]["url"])
    return body, download


def test_create_returns_envelope_and_download_returns_same_saved_pdf(client, created, settings):
    body, download = created
    result = body["result"]
    assert body["data_status"] == "mock" and body["data_version"] == "MOCK-2026-11-13-normal"
    assert re.fullmatch(r"rpt_[0-9a-f]{32}", result["report_id"])
    assert result["url"] == f"/api/v1/report/{result['report_id']}"
    assert result["generated_at"] == body["generated_at"]
    assert download.status_code == 200 and download.content.startswith(b"%PDF")
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"] == f'attachment; filename="{result["report_id"]}.pdf"'
    assert len(PdfReader(io.BytesIO(download.content)).pages) == result["pages"]
    again = client.get(result["url"])
    saved = (settings.reports_dir / f"{result['report_id']}.pdf").read_bytes()
    assert again.content == download.content == saved


def test_pdf_numbers_match_the_source_results(created):
    body, download = created
    pages, text = pdf_text(download.content)
    store = MockStore(NORMAL)
    aod, rain = store.trend("IGP", "aod", FULL, "all"), store.trend("IGP", "rainfall", FULL, "all")
    interaction = store.interaction("IGP", "all")
    expected = [
        f"increasing by about {aod.sen_slope:.3f} per decade (unitless)",
        f"95% CI {aod.slope_ci[0]:.3f} to {aod.slope_ci[1]:.3f}", f"p = {aod.p_value:.3f}",
        f"slope {rain.sen_slope:.1f} mm/month per decade", f"95% CI {rain.slope_ci[0]:.1f} to {rain.slope_ci[1]:.1f}",
        "is not statistically significant", f"p = {rain.p_value:.3f}",
        f"{rain.n_valid} / {rain.n_expected}", f"{interaction.median_change:.3f}", f"p = {interaction.p_value:.3f}",
        "Association only. AOD is retrieved in clear skies, so rainy days are under-sampled.",
        "MOCK-2026-11-13-normal", "data_status mock", "Automatic summary",
        "Hamed", "Label rule defined by the team", "2. Charts", "5. Datasets", "7. Limitations",
    ]
    for snippet in expected:
        assert snippet in text, snippet
    assert "Rainfall, Indo-Gangetic Plain (analysis box), 2003-01 to 2024-12 (season: all): decreasing" not in text
    assert all("MOCK sample report" in page and "MOCK DATA" in page for page in pages)
    assert f"Page {len(pages)} of {len(pages)}" in pages[-1]


def test_too_few_events_prints_note_and_no_test(client):
    response = client.post("/api/v1/report", json={**BODY, "region_id": "TN"})
    _, text = pdf_text(client.get(response.json()["result"]["url"]).content)
    assert "too few events for a reliable comparison" in text
    assert "so no test result is reported" in text and "p-value n/a" in text


def test_requested_section_without_data_prints_not_available(client):
    response = client.post("/api/v1/report", json={**BODY, "season": "MAM", "include": ["trend", "interaction"]})
    assert response.status_code == 200
    _, text = pdf_text(client.get(response.json()["result"]["url"]).content)
    assert text.count("Not available:") >= 3  # two trends + interaction


# ----------------------------------------------------------------- formatting and charts


@pytest.mark.parametrize("p,shown", [(0.0, "< 0.001"), (0.0004, "< 0.001"), (0.001, "0.001"), (0.0449, "0.045"),
                                     (None, "n/a")])
def test_p_value_formatting(p, shown):
    assert fmt_p(p) == shown


@pytest.mark.parametrize("value,unit,shown", [(0.0, "mm/month", "0.0"), (None, "1", "n/a"), (0.12345, "1", "0.123"),
                                              (231.45, "mm/month", "231.4"), (0.0, "1", "0.000"), (12.0, "days", "12")])
def test_number_formatting_keeps_zero_and_marks_missing(value, unit, shown):
    assert fmt_number(value, unit) == shown


def _series(points: list[tuple[date, float | None]]) -> TimeSeries:
    return TimeSeries(region_id="IGP", variable="rainfall", frequency="month", unit="mm/month",
                      source_id="IMERG_V07_FINAL_MONTHLY",
                      points=[SeriesPoint(date=d, value=v, valid_fraction=None if v is None else 1.0,
                                          qc_flag="missing" if v is None else "ok") for d, v in points])


def test_nulls_and_absent_months_become_gaps_not_zeros():
    series = _series([(date(2020, 1, 1), 5.0), (date(2020, 2, 1), None), (date(2020, 3, 1), 0.0),
                      (date(2020, 6, 1), 7.0)])  # April + May absent entirely
    dates, values = charts.gap_arrays(series)
    assert dates[:3] == [date(2020, 1, 1), date(2020, 2, 1), date(2020, 3, 1)]
    assert np.isnan(values[1]) and values[2] == 0.0 and np.isnan(values[3]) and values[-1] == 7.0
    _, all_null = charts.gap_arrays(_series([(date(2020, 1, 1), None), (date(2020, 2, 1), None)]))
    assert np.isnan(all_null).all()


def test_chart_draws_only_observed_line_without_ci_band():
    fig = charts.build_series_figure(_series([(date(2020, m, 1), float(m)) for m in range(1, 13)]),
                                     "Rainfall", "mm/month", "Sen slope 1.0 mm/month per decade")
    ax = fig.axes[0]
    assert len(ax.lines) == 1 and len(ax.collections) == 0
    assert ax.lines[0].get_color() == "#0072B2"
    assert "Rainfall (mm/month)" == ax.get_ylabel()


# ----------------------------------------------------------------- IDs and download errors


@pytest.mark.parametrize("path,status,code", [
    ("/api/v1/report/rpt_" + "0" * 32, 404, "REPORT_NOT_FOUND"),
    ("/api/v1/report/abc", 400, "INVALID_REPORT_ID"),
    ("/api/v1/report/rpt_" + "g" * 32, 400, "INVALID_REPORT_ID"),
    ("/api/v1/report/..%2F..%2Fpyproject", 404, "NOT_FOUND"),
    ("/api/v1/report", 404, "NOT_FOUND"),
    ("/api/v1/report/", 404, "NOT_FOUND"),
])
def test_bad_report_ids_return_json_errors(client, path, status, code):
    response = client.get(path)
    assert response.status_code == status
    assert response.headers["content-type"] == "application/json"
    assert response.json()["error"]["code"] == code


def test_store_never_maps_outside_reports_dir(tmp_path):
    (tmp_path / "secret.pdf").write_bytes(b"%PDF secret")
    files = ReportFileStore(tmp_path / "reports")
    for bad in ("../secret", "secret", "/etc/passwd", "rpt_" + "0" * 31 + "/"):
        with pytest.raises(Exception) as err:
            files.load(bad)
        assert getattr(err.value, "code", "") == "INVALID_REPORT_ID"


def test_failed_atomic_write_leaves_no_files(tmp_path, monkeypatch):
    files = ReportFileStore(tmp_path)
    monkeypatch.setattr("app.reports.store.os.replace", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        files.save(files.new_id(), b"%PDF partial")
    assert list(tmp_path.iterdir()) == []


# ----------------------------------------------------------------- failures and CSV independence


def test_chart_failure_returns_report_failed_and_saves_nothing(client, settings, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("matplotlib exploded at /secret/path")

    monkeypatch.setattr(charts, "series_chart_png", boom)
    response = client.post("/api/v1/report", json=BODY)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "REPORT_FAILED" and "secret" not in response.text
    assert not settings.reports_dir.exists() or list(settings.reports_dir.iterdir()) == []
    csv = client.get("/api/v1/export/csv", params={"region_id": "IGP", "variable": "aod"})
    assert csv.status_code == 200  # CSV still works while PDF creation fails


def test_write_failure_returns_report_failed(client, monkeypatch):
    def fail(self, report_id, content):
        raise OSError("read-only file system")

    monkeypatch.setattr(ReportFileStore, "save", fail)
    response = client.post("/api/v1/report", json=BODY)
    assert response.status_code == 500 and response.json()["error"]["code"] == "REPORT_FAILED"


def test_app_without_pdf_libraries_still_serves_csv(tmp_path):
    code = f"""
import sys
sys.modules['reportlab'] = None
sys.path.insert(0, 'backend')
from fastapi.testclient import TestClient
from app.config import load_settings
from app.main import create_app
settings = load_settings(env={{'REPORTS_DIR': r'{tmp_path}'}}, env_file=None)
with TestClient(create_app(settings)) as c:
    assert c.get('/api/v1/export/csv', params={{'region_id': 'IGP', 'variable': 'aod'}}).status_code == 200
    r = c.post('/api/v1/report', json={BODY!r})
    assert r.status_code == 500 and r.json()['error']['code'] == 'REPORT_FAILED', r.text
"""
    subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, check=True, capture_output=True)


# ----------------------------------------------------------------- hooks and validation


def test_methods_and_ai_hooks_are_escaped_and_labelled():
    content = assemble_report(MockStore(NORMAL), ReportRequest(**{**BODY, "include": ["trend"]}),
                              app_name="TrendTrace", contract_version="1.0", generated_at="2026-11-13T12:00:00+05:30",
                              methods_text="<b>Mann-Kendall</b> & Sen <script>\n\nSecond paragraph.")
    content = replace(content, ai_summary=AiSummary(text="AOD rose <i>slowly</i>.", source="llm"))
    _, text = pdf_text(build_pdf(content).content)
    assert "<b>Mann-Kendall</b> & Sen <script>" in text and "Second paragraph." in text
    assert "AI-generated explanation of computed results" in text and "AOD rose <i>slowly</i>." in text


@pytest.mark.parametrize("change,status,code", [
    ({"region_id": "XX"}, 400, "INVALID_REGION"),
    ({"variables": ["pm25"]}, 400, "INVALID_VARIABLE"),
    ({"season": "XYZ"}, 400, "INVALID_SEASON"),
    ({"start": "2016-01"}, 422, "PERIOD_TOO_SHORT"),
    ({"start": "2003/01"}, 400, "INVALID_PERIOD"),
    ({"variables": ["rainfall", "aod", "aod"]}, 422, "VALIDATION_ERROR"),
    ({"include": ["maps"]}, 422, "VALIDATION_ERROR"),
    ({"unexpected": 1}, 422, "VALIDATION_ERROR"),
])
def test_invalid_report_requests_keep_their_own_errors(client, change, status, code):
    response = client.post("/api/v1/report", json={**BODY, **change})
    assert response.status_code == status and response.json()["error"]["code"] == code


def test_sparse_data_report_is_insufficient(make_settings, tmp_path):
    with TestClient(create_app(make_settings(MOCK_SCENARIO="sparse", REPORTS_DIR=str(tmp_path)))) as c:
        response = c.post("/api/v1/report", json=BODY)
    assert response.status_code == 422 and response.json()["error"]["code"] == "INSUFFICIENT_DATA"


# ----------------------------------------------------------------- dates: never print a result under the wrong period


def test_results_for_other_periods_are_not_shown_under_requested_dates(client):
    body = {**BODY, "start": "2010-01", "end": "2024-12"}
    response = client.post("/api/v1/report", json=body)
    assert response.status_code == 200
    _, text = pdf_text(client.get(response.json()["result"]["url"]).content)
    interaction = MockStore(NORMAL).interaction("IGP", "all")
    assert f"{interaction.median_change:.3f}" not in text  # the 2003-2024 interaction number is not printed
    assert "exists only for 2003-01 to 2024-12, not for the requested 2010-01 to 2024-12" in text
    assert text.count("Not available:") >= 6  # 2 trends + interaction + 3 indicators
    assert "heavy_rain_share (annual)" not in text  # no indicator rows for the wrong years


def test_every_printed_result_shows_its_own_period(created):
    _, download = created
    _, text = pdf_text(download.content)
    assert "Analysis period 2003-01 to 2024-12" in text
    assert "Interaction (all, 2003-01 to 2024-12)" in text
    assert "heavy_rain_share (annual) 2003-2024 % 21 / 22" in text


def test_trend_with_a_different_period_or_season_is_unavailable():
    class ShiftedStore(MockStore):
        def trend(self, region_id, variable, period, season):
            real = super().trend(region_id, variable, FULL, "all")
            return real.model_copy(update={"season": "JJAS"}) if variable == "aod" else real.model_copy(
                update={"period": Period(start="2004-01", end="2024-12")})

    content = assemble_report(ShiftedStore(NORMAL), ReportRequest(**{**BODY, "include": ["trend"]}),
                              app_name="TrendTrace", contract_version="1.0", generated_at="x")
    rain, aod = content.variables
    assert "exists only for 2004-01 to 2024-12" in rain.trend.reason
    assert "only for season JJAS" in aod.trend.reason


def test_one_region_report_builds_well_under_ten_seconds(client):
    started = time.perf_counter()
    assert client.post("/api/v1/report", json=BODY).status_code == 200
    assert time.perf_counter() - started < 10.0  # full path: store + charts + PDF + write (local machine)
