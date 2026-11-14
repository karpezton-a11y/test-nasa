"""Discovery, demos, research series, any-series analysis, chart detail and scan routes."""
import json
import math
import random

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT
from app.main import create_app

API = "/api/v1"
BANNED = ("cause", "caused", "due to", "because of", "driven by", "leads to")


def _giovanni_csv(years=range(2003, 2015), fill_month=(2008, 7), trend=0.002):
    random.seed(3)
    lines = ["Title:,Time Series, Area-Averaged of Precipitation monthly 0.1 deg. [GPM GPM_3IMERGM v07] mm/hr over 2003-Jan - 2014-Dec, Region 76E, 24N, 88E, 30N",
             "User Start Date:,2003-01-01T00:00:00Z", 'Bounding Box:,"76,24,88,30"',
             "Fill Value (mean_GPM_3IMERGM_07_precipitation):,-9999.9", "", "time,mean_GPM_3IMERGM_07_precipitation"]
    for y in years:
        for m in range(1, 13):
            v = 0.05 + 0.4 * max(0.0, math.sin((m - 4) / 12 * 2 * math.pi)) + trend * (y - 2003) + random.gauss(0, 0.03)
            lines.append(f"{y}-{m:02d}-01,{-9999.9 if (y, m) == fill_month else round(max(v, 0), 4)}")
    return "\n".join(lines) + "\n"


def test_catalog_covers_the_named_missions_with_plain_definitions(client):
    body = client.get(API + "/catalog").json()
    assert body["data_status"] == "mock"
    variables = body["result"]["variables"]
    missions = " ".join(v["mission"] + " " + v["instrument"] for v in variables)
    for name in ("MODIS", "OMI", "AIRS", "GPM", "MERRA-2", "GLDAS"):
        assert name in missions
    assert all(v["plain_definition"] and v["why_trends"] and v["caveat"] for v in variables)
    assert {v["id"] for v in variables if v["available_now"]} == {"rainfall", "aod"}
    assert len({v["id"] for v in variables}) == len(variables)


def test_guided_questions_and_discover_reasons(client):
    q = client.get(API + "/discover/questions").json()["result"]
    assert [x["id"] for x in q["questions"]] == ["theme", "place_type", "question", "region_id"]
    assert any(r["id"] == "IGP" and r["loaded"] for r in q["choices"]["regions"])
    r = client.post(API + "/discover", json={"place_type": "city", "theme": "air",
                                             "question": "Is the air in my city getting more polluted?"})
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    ids = [s["variable_id"] for s in result["suggestions"]]
    assert ids[:2] == ["aod", "no2"]
    first = result["suggestions"][0]
    assert first["available_now"] and first["next_step"]["path"] == "/api/v1/analyze/detail"
    no2 = result["suggestions"][1]
    assert not no2["available_now"] and "Giovanni" in no2["next_step"]["how"]
    assert all(s["reasons"] for s in result["suggestions"])
    assert any(p["id"] == "DELHI" for p in result["region_suggestions"])


@pytest.mark.parametrize("body,code", [({"theme": "cheese"}, "VALIDATION_ERROR"), ({"place_type": "moon"}, "VALIDATION_ERROR"),
                                       ({"region_id": "ATLANTIS"}, "INVALID_REGION"), ({"limit": 99}, "VALIDATION_ERROR")])
def test_discover_rejects_unknown_choices(client, body, code):
    response = client.post(API + "/discover", json=body)
    assert response.json()["error"]["code"] == code


def test_demos_reference_existing_research_series_and_routes(client):
    demos = client.get(API + "/demos").json()["result"]
    research = {s["research_id"] for s in client.get(API + "/research/series").json()["result"]["series"]}
    assert len(demos) >= 4
    for demo in demos:
        for step in demo["steps"]:
            if step["body"] and "research_id" in step["body"]:
                assert step["body"]["research_id"] in research
            if step["method"] == "POST" and step["path"] != "/api/v1/discover":
                response = client.post(step["path"], json=step["body"])
                assert response.status_code == 200, (demo["id"], response.text)


def test_research_series_are_real_annual_values(client):
    listing = client.get(API + "/research/series").json()["result"]
    assert listing["data_status"] == "real" and len(listing["series"]) == 8
    one = client.get(API + "/research/series/IGP_aod_annual_mean").json()["result"]
    assert [v["year"] for v in one["values"]] == list(range(2003, 2025))
    assert client.get(API + "/research/series/nope").json()["error"]["code"] == "DATA_NOT_AVAILABLE"


def test_analyze_series_research_real_aod_is_significant_and_rainfall_is_not(client):
    aod = client.post(API + "/analyze/series", json={"research_id": "IGP_aod_annual_mean"}).json()["result"]
    assert aod["significant"] and aod["direction"] == "increasing" and aod["input_origin"] == "research_real_annual"
    assert aod["input_provenance"]["data_status"] == "real"
    assert "statistically significant" in aod["plain_language"]
    rain = client.post(API + "/analyze/series", json={"research_id": "IGP_rainfall_annual_total"}).json()["result"]
    assert not rain["significant"] and rain["detection"]["years_needed"] > rain["detection"]["years_available"]
    assert "no statistically significant trend" in rain["plain_language"]
    for text in (aod["plain_language"], rain["plain_language"]):
        assert not any(word in text.lower().replace("not its cause", "") for word in BANNED)


def test_analyze_series_giovanni_csv_with_unit_conversion(client):
    response = client.post(API + "/analyze/series", json={"giovanni_csv": _giovanni_csv(), "conversion": "mmhr_to_mm_month",
                                                         "place": "Indo-Gangetic Plain"})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["unit"] == "mm/month" and result["label"].startswith("Precipitation")
    assert result["input_origin"] == "giovanni_csv" and result["input_provenance"]["bbox"] == [76.0, 24.0, 88.0, 30.0]
    assert result["series_type"] == "monthly_deseasonalised" and result["n"] == 143  # one fill value stays missing
    assert result["climatology"] is not None and len(result["climatology"]) == 12


def test_analyze_series_inline_and_errors(client):
    years = [f"{y}-01-01" for y in range(2000, 2015)]
    ok = client.post(API + "/analyze/series", json={"dates": years, "values": [float(i) for i in range(15)],
                                                     "frequency": "year", "unit": "cm", "label": "Test"})
    assert ok.status_code == 200 and ok.json()["result"]["direction"] == "increasing"
    short = client.post(API + "/analyze/series", json={"dates": years[:5], "values": [1, 2, 3, 4, 5], "frequency": "year"})
    assert short.json()["error"]["code"] == "INSUFFICIENT_DATA"
    both = client.post(API + "/analyze/series", json={"research_id": "IGP_aod_annual_mean", "dates": years, "values": [1] * 15})
    assert both.json()["error"]["code"] == "VALIDATION_ERROR"
    bad_dates = client.post(API + "/analyze/series", json={"dates": ["soon"] * 15, "values": [1.0] * 15, "frequency": "year"})
    assert bad_dates.json()["error"]["code"] == "VALIDATION_ERROR"
    bad_csv = client.post(API + "/analyze/series", json={"giovanni_csv": "hello,world\n1,2\n"})
    assert bad_csv.json()["error"]["code"] == "VALIDATION_ERROR"


def test_analyze_detail_gives_chart_fit_change_point_and_detection(client):
    response = client.post(API + "/analyze/detail", json={"region_id": "IGP", "variable": "aod", "season": "JJAS"})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["trend"]["season"] == "JJAS" and result["trend"]["series_type"] == "seasonal_mean"
    analysis = result["analysis"]
    # One point per complete JJAS season; seasons with a missing month are skipped, never averaged.
    assert len(analysis["fit"]) == analysis["n"] <= 22 and {"date", "value", "fitted", "lower", "upper"} <= set(analysis["fit"][0])
    assert analysis["sen_slope_per_decade"] == pytest.approx(result["trend"]["sen_slope"], abs=1e-6)
    assert {"years_needed", "years_available", "method"} <= set(analysis["detection"])
    assert result["plain_language"].startswith("MOCK development data.")


def test_scan_reports_what_where_how_much_with_fdr(client):
    response = client.get(API + "/scan", params={"season": "all"})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["tested"] == 4 and result["multiple_testing"] == "benjamini_hochberg_fdr"
    for row in result["rows"]:
        assert row["q_value"] >= row["p_value"] - 1e-12
        assert row["headline"]
    # The mock series trend in opposite directions for AOD (IGP up, TN down): the challenge's key idea.
    assert result["opposite_directions"] and result["opposite_directions"][0]["variable"] == "aod"
    assert client.get(API + "/scan", params={"alpha": 0.2}).json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get(API + "/scan", params={"variable": "nope"}).json()["error"]["code"] == "INVALID_VARIABLE"


def test_explain_accepts_trend_ids_with_option_suffixes(client):
    first = client.post(API + "/analyze", json={"region_id": "IGP", "variable": "aod"}).json()["result"]
    second = client.post(API + "/analyze", json={"region_id": "IGP", "variable": "aod", "options": {"alpha": 0.10}}).json()["result"]
    assert first["result_id"] != second["result_id"]  # no registry ambiguity between alphas
    for rid in (first["result_id"], second["result_id"]):
        response = client.post(API + "/explain", json={"result_type": "trend", "result_id": rid})
        assert response.status_code == 200, response.text


def test_fetch_nasa_power_box_average_with_fake_api(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("fetch_nasa_power", REPO_ROOT / "scripts" / "fetch_nasa_power.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        lat = float(request.url.params["latitude"])
        values = {f"2003{m:02d}": (-999.0 if m == 7 and lat > 25 else 20.0 + lat / 10) for m in range(1, 14)}
        return httpx.Response(200, json={"properties": {"parameter": {"T2M": values}},
                                         "parameters": {"T2M": {"units": "C", "longname": "Temperature at 2 Meters"}}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as fake:
        series, units, longname, n = module.fetch("T2M", [76, 24, 78, 26], 2003, 2003, step=1.0, client=fake)
    assert n == len(calls) == 9 and units == "C" and len(series) == 12  # month 13 (annual) dropped
    lats = sorted({float(c["latitude"]) for c in calls})
    assert series["2003-07"] == pytest.approx(20.0 + sum(lats[:2]) / 2 / 10)  # fill values (northern row) excluded
    assert series["2003-01"] == pytest.approx(20.0 + sum(lats) / 3 / 10)
    text = module.to_giovanni_csv(series, "T2M", units, longname, [76, 24, 78, 26], n)
    with TestClient(create_app(_settings())) as client:
        assert client.post(API + "/analyze/series", json={"giovanni_csv": text}).json()["error"]["code"] == "INSUFFICIENT_DATA"
    from app.services.giovanni import parse_giovanni_csv
    parsed = parse_giovanni_csv(text)
    assert parsed.unit == "C" and parsed.frequency == "month" and parsed.bbox == [76.0, 24.0, 78.0, 26.0]


def _settings(**extra):
    from conftest import build_settings
    return build_settings(**extra)


def test_import_giovanni_then_real_mode_serves_and_analyses_new_variable(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("import_giovanni", REPO_ROOT / "scripts" / "import_giovanni.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = tmp_path / "igp_rain.csv"
    raw.write_text(_giovanni_csv(years=range(2003, 2025)), encoding="utf-8")
    processed = tmp_path / "processed"
    info = module.import_csv(raw, region_id="IGP", variable="rainfall", processed=processed, conversion="mmhr_to_mm_month",
                             data_version="REAL-TEST-1")
    assert info["unit"] == "mm/month" and info["missing"] == 1
    # A second, new catalogue variable in a preset region.
    no2 = tmp_path / "delhi_no2.csv"
    no2.write_text(_giovanni_csv(years=range(2005, 2024)).replace("GPM_3IMERGM_07_precipitation", "OMNO2d_003_ColumnAmountNO2TropCloudScreened")
                   .replace("mm/hr", "1/cm2"), encoding="utf-8")
    module.import_csv(no2, region_id="DELHI", variable="no2", processed=processed, unit="molecules/cm2")
    with pytest.raises(SystemExit):
        module.import_csv(no2, region_id="DELHI", variable="no2", processed=processed, unit="molecules/cm2")
    manifest = json.loads((processed / "manifest.json").read_text())
    assert manifest["data_status"] == "real" and manifest["data_version"] == "REAL-TEST-1"
    settings = _settings(DATA_MODE="real", PROCESSED_DIR=str(processed))
    with TestClient(create_app(settings)) as client:
        regions = client.get(API + "/regions").json()
        assert regions["data_status"] == "real"
        assert {r["region_id"] for r in regions["result"]["regions"]} == {"IGP", "DELHI"}
        trend = client.post(API + "/analyze", json={"region_id": "DELHI", "variable": "no2"})
        assert trend.status_code == 200, trend.text
        assert trend.json()["result"]["period"] == {"start": "2005-01", "end": "2023-12"}
        assert trend.json()["result"]["slope_unit"] == "molecules/cm2 per decade"
        catalog = client.get(API + "/catalog").json()["result"]["variables"]
        assert {v["id"] for v in catalog if v["available_now"]} == {"rainfall", "no2"}
        scan = client.get(API + "/scan").json()["result"]
        assert scan["tested"] == 2


def test_simple_frontend_is_served_without_hiding_api_errors(client):
    page = client.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"] and "TrendTrace" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/world.js").status_code == 200  # map outlines
    missing = client.get("/api/v1/does-not-exist")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "NOT_FOUND"


def test_discover_next_step_targets_a_region_that_has_the_variable(make_settings):
    from conftest import build_settings
    with TestClient(create_app(build_settings(DATA_MODE="real"))) as client:
        regions = {r["region_id"]: r["variables"] for r in client.get(API + "/regions").json()["result"]["regions"]}
        for question in ("haze pollution", "rain flood", "heat temperature"):
            for s in client.post(API + "/discover", json={"question": question}).json()["result"]["suggestions"]:
                if s["available_now"]:
                    body = s["next_step"]["body"]
                    assert s["variable_id"] in regions[body["region_id"]]
                    assert client.post(API + "/analyze/detail", json=body).status_code == 200


def test_giovanni_keeps_negative_retrievals_and_averages_daily_to_monthly():
    from app.services.giovanni import daily_to_monthly, parse_giovanni_csv
    lines = ["Title:,Time Series, Area-Averaged of NO2 daily", "Fill Value (mean_OMNO2d_003_ColumnAmountNO2TropCloudScreened):, -1.267651e+30",
             "", "time, mean_OMNO2d_003_ColumnAmountNO2TropCloudScreened"]
    lines += [f"2005-01-{d:02d},{v}" for d, v in zip(range(1, 32), ["-1.5e+15"] + ["-1.267651e+30"] * 2 + ["4.0e+15"] * 28)]
    lines += [f"2005-02-{d:02d},-1.267651e+30" for d in range(1, 25)] + [f"2005-02-{d:02d},5.0e+15" for d in range(25, 29)]
    series = parse_giovanni_csv("\n".join(lines) + "\n", allow_daily=True)
    assert series.frequency == "day" and series.values[0] == -1.5e15  # a real negative retrieval, not a fill
    assert series.values[1] is None and series.unit == "molecules/cm2"
    dates, values, fractions = daily_to_monthly(series)
    assert [d.isoformat() for d in dates] == ["2005-01-01", "2005-02-01"]
    assert values[0] == pytest.approx((-1.5e15 + 28 * 4.0e15) / 29) and fractions[0] == round(29 / 31, 4)
    assert values[1] is None and fractions[1] == round(4 / 28, 4)  # fewer than 5 valid days: missing, not filled
