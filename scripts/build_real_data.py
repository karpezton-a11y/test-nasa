"""Build the real-mode data folder (data/processed/) from Group 3's observed-research package.

Input:  group3_pipeline/results/  (Sritharan's executed pipeline: 12 NASA Giovanni exports, 2003-2024)
Output: data/processed/  in the loader layout of docs/implementation/real-data-layout.md

* timeseries_monthly.csv / timeseries_daily.csv   copied unchanged (nine contract columns)
* variables.json, sources.json, regions.geojson    contract envelopes built from Group 3 metadata/provenance
* anomalies/*.json                                 Group 3's dated anomaly outcomes in contract G shape
* rainfall_indicators_annual.csv + _metadata.json  Group 3's indicators (ALL -> annual) with trendlib trends
* manifest.json                                    data_status=real, data_version, SHA-256 of every CSV

Nothing is recomputed except the indicator trends (trendlib); no value is filled, rounded or interpolated.
Re-run after Group 3 updates its results:  python scripts/build_real_data.py
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import json
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "analysis"), str(ROOT / "backend")]

import trendlib  # noqa: E402
from trendlib.interaction import compute_interaction  # noqa: E402

from app.advanced_schemas import (AnomalyBothResult, AnomalyResult, IndicatorResult,  # noqa: E402
                                  InteractionResult, combined_category)
from app.schemas import RegionsResult, SourceInfo, VariableInfo  # noqa: E402

SRC = ROOT / "group3_pipeline"
RESULTS = SRC / "results"
OUT = ROOT / "data" / "processed"
IST = timezone(timedelta(hours=5, minutes=30))
CONTRACT = "1.0"
PERIOD = {"start": "2003-01", "end": "2024-12"}
GENERATED = "2026-11-14T00:00:00+05:30"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def envelope(result, version):
    return {"data_status": "real", "data_version": version, "contract_version": CONTRACT,
            "generated_at": GENERATED, "result": result}


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


SEASON_MONTHS = {"annual": set(range(1, 13)), "JJAS": {6, 7, 8, 9}, "OND": {10, 11, 12}}


def rx5day_rows(daily_csv: Path, min_valid: float = 0.95) -> dict:
    """Rx5day per region, season and year from daily regional-mean IMERG rainfall (mm/day).

    The largest 5-consecutive-day total; a window counts only if all 5 days are valid and inside
    the same year/season. Years with less than ``min_valid`` of their days valid get no value.
    """
    series = defaultdict(dict)
    for r in csv.DictReader(daily_csv.open(encoding="utf-8")):
        if r["variable"] == "rainfall" and r["frequency"] == "day":
            series[r["region_id"]][date.fromisoformat(r["date"])] = None if r["value"] == "" else float(r["value"])
    out = defaultdict(list)
    first, last = int(PERIOD["start"][:4]), int(PERIOD["end"][:4])
    for rid, by_day in sorted(series.items()):
        for season, months in SEASON_MONTHS.items():
            for year in range(first, last + 1):
                days = sorted(d for d in by_day if d.year == year and d.month in months)
                n_total = sum(calendar.monthrange(year, m)[1] for m in months)
                vals = [by_day[d] for d in days]
                valid_fraction = sum(v is not None for v in vals) / n_total
                best = None
                for i in range(len(days) - 4):
                    window = vals[i:i + 5]
                    if None in window or (days[i + 4] - days[i]).days != 4:
                        continue
                    best = sum(window) if best is None else max(best, sum(window))
                value = round(best, 4) if (best is not None and valid_fraction >= min_valid) else None
                out[(rid, "rx5day", season)].append({
                    "region_id": rid, "indicator": "rx5day", "season": season, "year": str(year),
                    "value": "" if value is None else repr(value), "valid_fraction": repr(round(valid_fraction, 6)),
                    "unit": "mm", "source_id": "IMERG_V07_FINAL_DAILY"})
    return out


def build(out: Path = OUT) -> dict:
    ui = json.loads((SRC / "docs" / "ui_science_text.json").read_text(encoding="utf-8"))
    g3_sources = {s["source_id"]: s for s in json.loads((SRC / "metadata" / "sources.json").read_text(encoding="utf-8"))}
    provenance = json.loads((RESULTS / "provenance.json").read_text(encoding="utf-8"))
    raw_hashes = sorted(p["raw_sha256"] for p in provenance)
    version = "REAL-G3-2026-11-14-" + hashlib.sha256("".join(raw_hashes).encode()).hexdigest()[:8]

    if out.exists():
        for child in out.iterdir():
            if child.name != ".gitkeep":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
    out.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- time series (unchanged copies)
    shutil.copyfile(RESULTS / "timeseries_monthly.csv", out / "timeseries_monthly.csv")
    shutil.copyfile(RESULTS / "timeseries_daily.csv", out / "timeseries_daily.csv")

    # ---------------------------------------------------------------- sources
    prov_by_source: dict[str, dict] = {}
    for p in provenance:
        prov_by_source.setdefault(p["source_id"], p)
    sources = []
    for sid, s in g3_sources.items():
        p = prov_by_source[sid]
        primary = s["role"].startswith("primary")
        access = ("NASA Giovanni area-averaged export (authenticated); monthly temporal coverage from the matched daily product"
                  if primary and sid.endswith("MONTHLY") else
                  "NASA Giovanni area-averaged export (authenticated); daily spatial coverage unknown" if sid.endswith("DAILY") else
                  "NASA Giovanni area-averaged export (authenticated); comparison series, temporal coverage not exported")
        title = s.get("catalogue_title") or f"{s['product']} version {s['version']}"
        url = s.get("catalogue_url") or p["source_url"]
        sources.append(SourceInfo.model_validate({
            "source_id": sid, "product": title, "short_name": s["product"], "version": s["version"], "doi": None,
            "access_method": access, "access_date": p["accessed_at"][:10], "variable_name": p["source_variable"],
            "citation": f"{title}. NASA. Area-averaged time series via NASA Giovanni, accessed {p['accessed_at'][:10]}. {url}",
        }).model_dump(mode="json"))
    write(out / "sources.json", envelope(sources, version))

    # ---------------------------------------------------------------- variables
    variables = [
        VariableInfo.model_validate({"variable": "rainfall", "label": "Rainfall", "unit": "mm/month", "unit_label": "mm/month",
                                     "sources": ["IMERG_V07_FINAL_MONTHLY", "IMERG_V07_FINAL_DAILY"],
                                     "description": ui["rainfall"] + " Source: GPM IMERG Final V07.",
                                     "caveat": "Daily values are in mm/day. " + ui["missing"]}).model_dump(),
        VariableInfo.model_validate({"variable": "aod", "label": "Aerosol optical depth (AOD)", "unit": "1", "unit_label": "unitless",
                                     "sources": ["MODIS_AQUA_C61_MONTHLY", "MODIS_AQUA_C61_DAILY",
                                                 "MODIS_TERRA_C61_MONTHLY", "MERRA2_MONTHLY_TOTEXTTAU"],
                                     "description": ui["aod"] + " Primary: Aqua MODIS C6.1; Terra MODIS and MERRA-2 are separate comparison series.",
                                     "caveat": ui["aod_surface_warning"] + " " + ui["interaction_warning"].split(". ")[1]}).model_dump(),
    ]
    write(out / "variables.json", envelope(variables, version))

    # ---------------------------------------------------------------- regions
    names = {"IGP": "Indo-Gangetic Plain (analysis box)", "TN": "Tamil Nadu region (analysis box)"}
    geo = json.loads((SRC / "metadata" / "regions.geojson").read_text(encoding="utf-8"))
    regions, features = [], []
    for f in geo["features"]:
        props = f["properties"]
        rid = props["region_id"]
        regions.append({"region_id": rid, "name": names.get(rid, rid), "bbox": props["bbox"], "status": props["status"],
                        "description": props["description"] + " " + ui["region_warning"],
                        "variables": ["rainfall", "aod"], "period_available": PERIOD})
        features.append({"type": "Feature", "id": rid, "geometry": f["geometry"],
                         "properties": {"region_id": rid, "name": names.get(rid, rid), "status": props["status"]}})
    regions_result = RegionsResult.model_validate({"regions": regions, "geojson": {"type": "FeatureCollection", "features": features}})
    write(out / "regions.geojson", envelope(regions_result.model_dump(mode="json"), version))

    # ---------------------------------------------------------------- anomalies (contract G)
    qc = {(r["region_id"], r["variable"], r["source_id"], r["date"]): r["qc_flag"]
          for r in csv.DictReader((RESULTS / "timeseries_monthly_primary.csv").open(encoding="utf-8"))}
    rows = defaultdict(list)
    for r in csv.DictReader((RESULTS / "anomalies_monthly_primary.csv").open(encoding="utf-8")):
        rows[(r["region_id"], r["variable"])].append(r)
    singles = {}
    for (rid, var), items in sorted(rows.items()):
        rain = var == "rainfall"
        entries = []
        for r in sorted(items, key=lambda x: x["date"]):
            value = None if r["value"] == "" else float(r["value"])
            evaluated = r["evaluation_status"] == "evaluated" and r["score"] != ""
            category = None if r["category"] in ("typical", "") else r["category"]
            entries.append({"date": r["date"], "value": value,
                            "baseline_median": None if r["baseline_median"] == "" else float(r["baseline_median"]),
                            "score": float(r["score"]) if evaluated else None,
                            "score_type": "percentile" if rain else "z_log", "category": category,
                            "valid_fraction": None if r["valid_fraction"] == "" else float(r["valid_fraction"]),
                            "qc_flag": qc.get((rid, var, r["source_id"], r["date"]), "ok" if value is not None else "missing"),
                            "note": r["note"]})
        high, low = (0.9, 0.1) if rain else (2.0, -2.0)
        if rain:
            # Group 3 flags rainfall with linear P10/P90 *values*; the contract states thresholds on the score
            # (mid-rank percentile) scale. With 22 baseline values, value >= linear P90 is exactly mid-rank >= 39/44
            # (0.886) and value <= P10 is mid-rank <= 5/44 (0.114). Derive the equivalent cut-offs from the flags and
            # verify every unflagged month lies strictly between them (dry-suppressed months excepted).
            wet = [e["score"] for e in entries if e["category"] == "unusually_wet"]
            dry = [e["score"] for e in entries if e["category"] == "unusually_dry"]
            high, low = min(wet), max(dry)
            for e in entries:
                if e["category"] is None and e["score"] is not None and "suppressed" not in e["note"]:
                    assert low < e["score"] < high, (rid, e["date"], e["score"])
        result = AnomalyResult.model_validate({
            "result_id": f"anomalies_{rid}_{var}_{PERIOD['start']}_{PERIOD['end']}_raw", "region_id": rid, "variable": var,
            "source_id": items[0]["source_id"], "unit": "mm/month" if rain else "1", "period": PERIOD,
            "baseline": {"start": PERIOD["start"], "end": PERIOD["end"], "method": "same_calendar_month",
                         "statistic": "empirical_percentile" if rain else "z_log", "detrended": False},
            "thresholds": {"high": high, "low": low,
                           "min_valid_fraction": 0.9 if rain else None, "dry_suppression_median": 10.0 if rain else None},
            "anomalies": entries})
        singles[(rid, var)] = result
        write(out / "anomalies" / f"{rid}_{var}_raw.json", envelope(result.model_dump(mode="json"), version))
    for rid in sorted({r for r, _ in singles}):
        rain, aod = singles[(rid, "rainfall")], singles[(rid, "aod")]
        rc = {a.date: a.category for a in rain.anomalies if a.category}
        ac = {a.date: a.category for a in aod.anomalies if a.category}
        flags = [{"date": d.isoformat(), "category": combined_category(rc[d], ac[d]), "rainfall_category": rc[d],
                  "aod_category": ac[d]} for d in sorted(set(rc) & set(ac))]
        both = AnomalyBothResult.model_validate({
            "result_id": f"anomalies_{rid}_both_{PERIOD['start']}_{PERIOD['end']}_raw", "region_id": rid, "variable": "both",
            "period": PERIOD, "detrended": False, "results": [rain.model_dump(mode="json"), aod.model_dump(mode="json")],
            "combined_flags": flags})
        write(out / "anomalies" / f"{rid}_both_raw.json", envelope(both.model_dump(mode="json"), version))

    # ---------------------------------------------------------------- rainfall indicators (contract J)
    definitions = {"heavy_rain_share": ui["heavy_rain_share"] + " Wet day: at least 1 mm/day; rain strictly above the wet-day P95 "
                                       "divided by all wet-day rain.",
                   "longest_dry_spell": ui["dry_spell"] + " Year/season boundaries end a run."}
    definitions["rx5day"] = ("Rx5day: the largest rainfall total over any 5 consecutive days in the year or season, "
                             "from the regional daily mean of GPM IMERG Final V07. Only windows with 5 valid days count; "
                             "windows do not cross year or season boundaries.")
    grouped = defaultdict(list)
    for r in csv.DictReader((RESULTS / "rainfall_indicators_annual.csv").open(encoding="utf-8")):
        grouped[(r["region_id"], r["indicator"], "annual" if r["season"] == "ALL" else r["season"])].append(r)
    for key, rows in rx5day_rows(RESULTS / "timeseries_daily.csv").items():
        grouped[key].extend(rows)
    csv_rows, metadata = [], []
    for (rid, ind, season), items in sorted(grouped.items()):
        items.sort(key=lambda x: int(x["year"]))
        values = [{"year": int(r["year"]), "value": None if r["value"] == "" else float(r["value"]),
                   "valid_fraction": None if r["valid_fraction"] == "" else float(r["valid_fraction"])} for r in items]
        for v in values:
            csv_rows.append({"region_id": rid, "indicator": ind, "season": season, "year": v["year"],
                             "value": "" if v["value"] is None else repr(v["value"]),
                             "valid_fraction": "" if v["valid_fraction"] is None else repr(v["valid_fraction"])})
        valid = [v for v in values if v["value"] is not None]
        unit = items[0]["unit"]
        variable = f"{ind}_{season}"
        trend, note = None, None
        if len(valid) >= 10:
            trend = trendlib.compute_annual_trend(
                [v["year"] for v in values], [v["value"] for v in values], region_id=rid, variable=variable,
                source_id=items[0]["source_id"], unit=unit, season="annual",
                limitations=[ui["regional_indicator_warning"]])
            trend["result_id"] = f"trend_{rid}_{ind}_{season}_{PERIOD['start']}_{PERIOD['end']}"
            trend["computed_at"] = GENERATED  # deterministic rebuilds: identical inputs give identical files
        else:
            note = "Fewer than 10 valid years: no trend is reported."
        result = IndicatorResult.model_validate({
            "result_id": f"indicator_{rid}_{ind}_{season}_{PERIOD['start']}_{PERIOD['end']}", "region_id": rid,
            "indicator": ind, "season": season, "period": PERIOD, "source_id": items[0]["source_id"], "unit": unit,
            "definition": definitions[ind], "spatial_method": "regional_mean",
            "threshold_baseline": PERIOD if ind == "heavy_rain_share" else None, "min_valid_fraction": 0.95,
            "values": values, "trend": trend, "trend_note": note})
        metadata.append(result.model_dump(mode="json"))
    with (out / "rainfall_indicators_annual.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["region_id", "indicator", "season", "year", "value", "valid_fraction"],
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows)
    write(out / "rainfall_indicators_metadata.json", envelope(metadata, version))

    # ---------------------------------------------------------------- rainfall-AOD interaction (contract H)
    def load(path, freq):
        series = defaultdict(dict)
        for r in csv.DictReader(path.open(encoding="utf-8")):
            series[(r["region_id"], r["variable"], r["source_id"])][date.fromisoformat(r["date"])] = \
                None if r["value"] == "" else float(r["value"])
        return series
    daily = load(RESULTS / "timeseries_daily.csv", "day")
    monthly = load(RESULTS / "timeseries_monthly_primary.csv", "month")
    ids = {"rainfall_daily": "IMERG_V07_FINAL_DAILY", "aod_daily": "MODIS_AQUA_C61_DAILY",
           "rainfall_monthly": "IMERG_V07_FINAL_MONTHLY", "aod_monthly": "MODIS_AQUA_C61_MONTHLY"}
    interactions, thresholds = [], {}
    for rid in ("IGP", "TN"):
        for season in ("all", "JF", "MAM", "JJAS", "OND"):
            raw = compute_interaction(region_id=rid, season=season, period=PERIOD, source_ids=ids,
                                      rain_daily=daily[(rid, "rainfall", ids["rainfall_daily"])],
                                      aod_daily=daily[(rid, "aod", ids["aod_daily"])],
                                      rain_monthly=monthly[(rid, "rainfall", ids["rainfall_monthly"])],
                                      aod_monthly=monthly[(rid, "aod", ids["aod_monthly"])])
            thresholds[f"{rid}_{season}"] = raw.pop("_threshold_mm_day")
            interactions.append(InteractionResult.model_validate(raw).model_dump(mode="json"))
    write(out / "interaction_summary.json", envelope(interactions, version))

    # ---------------------------------------------------------------- manifest
    assets = {name: {"data_status": "real", "sha256": sha(out / name)}
              for name in ("timeseries_monthly.csv", "timeseries_daily.csv", "rainfall_indicators_annual.csv")}
    write(out / "manifest.json", {"data_status": "real", "data_version": version, "contract_version": CONTRACT,
                                  "source_package": "group3_pipeline (Sritharan observed-research package)",
                                  "raw_export_sha256": raw_hashes,
                                  "interaction_p90_thresholds_mm_day": thresholds,
                                  "computed_here": ["indicator trends (trendlib)", "interaction composites (trendlib.interaction)"],
                                  "assets": assets})
    return {"data_version": version, "anomaly_files": len(singles) + 2, "indicator_results": len(metadata)}


def build_research_annual() -> None:
    """Full-precision annual series for the 'Real data' tab (replaces the rounded slide-chart values)."""
    monthly = defaultdict(lambda: defaultdict(list))
    for r in csv.DictReader((RESULTS / "timeseries_monthly_primary.csv").open(encoding="utf-8")):
        if r["value"] != "":
            monthly[(r["region_id"], r["variable"])][int(r["date"][:4])].append(float(r["value"]))
    indicators = defaultdict(dict)
    for r in csv.DictReader((RESULTS / "rainfall_indicators_annual.csv").open(encoding="utf-8")):
        if r["season"] == "ALL" and r["value"] != "":
            indicators[(r["region_id"], r["indicator"])][int(r["year"])] = float(r["value"])
    names = {"IGP": "Indo-Gangetic Plain box [76,24,88,30]", "TN": "Tamil Nadu box [76.5,8,80.5,13.5]"}
    spec = [("rainfall_annual_total", "Annual rainfall total", "mm/year", "water",
             "Sum of 12 monthly IMERG Final V07 regional values (GPM_3IMERGM)",
             lambda rid: {y: sum(v) for y, v in monthly[(rid, "rainfall")].items() if len(v) == 12}),
            ("aod_annual_mean", "Annual mean aerosol optical depth", "1", "air",
             "Mean of 12 monthly Aqua MODIS MYD08_M3 C6.1 combined DT/DB AOD at 550 nm",
             lambda rid: {y: sum(v) / 12 for y, v in monthly[(rid, "aod")].items() if len(v) == 12}),
            ("longest_dry_spell", "Longest dry spell (regional daily mean < 1 mm/day)", "days", "water",
             "Longest run of IMERG daily regional-mean rainfall below 1 mm/day within each calendar year",
             lambda rid: indicators[(rid, "longest_dry_spell")]),
            ("heavy_rain_share", "Share of wet-day rain above baseline wet-day P95", "%", "water",
             "Rain strictly above the 2003-2024 wet-day P95 divided by all wet-day rain (IMERG daily, regional mean)",
             lambda rid: indicators[(rid, "heavy_rain_share")])]
    series = []
    for vid, label, unit, theme, method, getter in spec:
        for rid in ("IGP", "TN"):
            values = getter(rid)
            series.append({"research_id": f"{rid}_{vid}", "region_id": rid, "region_name": names[rid], "variable": vid,
                           "label": label, "unit": unit, "frequency": "year", "theme": theme, "method": method,
                           "source_slide": None, "source_file": "group3_pipeline/results/",
                           "values": [{"year": y, "value": values[y]} for y in range(2003, 2025) if y in values]})
    doc = {"dataset": "research_annual", "data_status": "real",
           "data_origin": "Group 3 (Sritharan) observed-research package, group3_pipeline/results (12 NASA Giovanni exports)",
           "precision_note": "Full recorded precision from Group 3's processed CSVs.",
           "period": {"start": "2003", "end": "2024"},
           "limitations": ["Regional box averages, not administrative areas.",
                           "AOD is a column optical measure, not ground-level PM2.5; clear-sky sampling.",
                           "Annual aggregation removes the seasonal cycle but leaves only 22 values per series."],
           "series": series}
    write(ROOT / "data" / "research" / "annual_series.json", doc)


def import_extras(out: Path = OUT) -> list[str]:
    """Add the extra NASA series listed in data/raw/imports.json (NASA POWER / Giovanni CSVs)."""
    spec_path = ROOT / "data" / "raw" / "imports.json"
    if not spec_path.is_file():
        return []
    import importlib.util
    spec = importlib.util.spec_from_file_location("import_giovanni", ROOT / "scripts" / "import_giovanni.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    done = []
    for item in json.loads(spec_path.read_text(encoding="utf-8"))["imports"]:
        module.import_csv(ROOT / "data" / "raw" / item["file"], region_id=item["region_id"], variable=item["variable"],
                          processed=out, conversion=item.get("conversion", "none"), unit=item.get("unit"),
                          source_id=item["source_id"])
        done.append(item["file"])
    return done


if __name__ == "__main__":
    info = build()
    extras = import_extras()
    if extras:
        print(f"Imported {len(extras)} extra NASA series: {', '.join(extras)}")
    build_research_annual()
    print(f"Built {OUT} — data_version {info['data_version']}, {info['anomaly_files']} anomaly files, "
          f"{info['indicator_results']} indicator results; refreshed data/research/annual_series.json")
