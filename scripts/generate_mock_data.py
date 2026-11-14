#!/usr/bin/env python
"""Deterministic MOCK data generator (development fixtures only).

    python scripts/generate_mock_data.py              # writes data/mock/
    python scripts/generate_mock_data.py --out DIR    # isolated output (tests)

- Every file is an API envelope with data_status="mock" and a MOCK data_version.
- Same config + same templates + same generator_version -> byte-identical files.
- Values are synthetic placeholders, NOT NASA data and NOT results. Statistics
  (slopes, p-values, scores) are canned from the config; nothing is computed
  from the series except simple counts.
- valid_fraction rule (same for real data, docs/handoff/real_data_dropin.md): monthly = share of the
  month's days with a valid retrieval, always a number, also when the value is withheld (0.06 → value
  null, qc_flag missing); daily = null, because
  one day has no "fraction of days" (qc_flag says ok or missing).
- Never writes into data/processed/. Only files listed in the previous
  manifest are ever deleted (stale-file cleanup).
"""

from __future__ import annotations

import argparse
import calendar
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.advanced_schemas import (  # noqa: E402
    AnomalyBothResult, AnomalyEntry, AnomalyResult, IndicatorResult, IndicatorValue, InteractionResult,
    combined_category,
)
from app.schemas import (  # noqa: E402
    Evidence, FeatureCollection, Period, Region, RegionFeature, RegionsResult, SensitivityRun, SeriesPoint,
    SourceInfo, TimeSeries, TrendMethod, TrendResult, VariableInfo,
)
from app.services import store as layout  # noqa: E402

CONFIG_PATH = REPO_ROOT / "scripts" / "mock_config.json"
EXAMPLES_DIR = REPO_ROOT / "docs" / "examples"
DEFAULT_OUT = REPO_ROOT / "data" / "mock"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
MANIFEST = "manifest.json"
DRY_NOTE = "dry flag not applicable: same-month baseline median below 10 mm/month"
MOCK_LIMITATION = "MOCK fixture: illustrative numbers, not a scientific result."
LABEL_NOTE = "Label rule defined by the team; see Methods."


class Manifest(BaseModel):
    data_status: Literal["mock"]
    data_version: str
    generator_version: str
    files: list[str]


# ----------------------------------------------------------------- small helpers


def rng_for(seed: int, *parts: int) -> np.random.Generator:
    """Independent, reproducible stream per (scenario, region, variable, purpose)."""
    return np.random.default_rng([seed, *parts])


def month_starts(period: Period) -> list[date]:
    y, m = int(period.start[:4]), int(period.start[5:])
    end = (int(period.end[:4]), int(period.end[5:]))
    out = []
    while (y, m) <= end:
        out.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def days_in(period: Period) -> list[date]:
    first = date(int(period.start[:4]), int(period.start[5:]), 1)
    ey, em = int(period.end[:4]), int(period.end[5:])
    last = date(ey, em, calendar.monthrange(ey, em)[1])
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def load_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))["result"]


def sign_of(x: float) -> str:
    return "positive" if x > 0 else "negative" if x < 0 else "zero"


# ----------------------------------------------------------------- metadata


def build_variables(cfg: dict) -> list[VariableInfo]:
    return [VariableInfo(**{k: v for k, v in var.items() if k != "daily_unit"}) for var in cfg["variables"]]


def bbox_polygon(bbox: list[float]) -> list[list[list[float]]]:
    w, s, e, n = bbox
    return [[[w, s], [e, s], [e, n], [w, n], [w, s]]]


def build_regions(cfg: dict, period: Period) -> RegionsResult:
    regions = [
        Region(region_id=r["region_id"], name=r["name"], bbox=r["bbox"], status=r["status"],
               description=r["description"], variables=r["variables"], period_available=period)
        for r in cfg["regions"]
    ]
    features = [
        RegionFeature(type="Feature", id=r.region_id,
                      geometry={"type": "Polygon", "coordinates": bbox_polygon(list(r.bbox))},
                      properties={"region_id": r.region_id, "name": r.name, "status": r.status})
        for r in regions
    ]
    return RegionsResult(regions=regions, geojson=FeatureCollection(type="FeatureCollection", features=features))


def build_sources(cfg: dict) -> list[SourceInfo]:
    return [
        SourceInfo(source_id=s["source_id"], product=f"MOCK stand-in for {s['stands_in_for']} (not NASA data)",
                   short_name="MOCK", version="MOCK", doi=None, access_method="mock_generator (no download)",
                   access_date=None, variable_name="MOCK", citation=None)
        for s in cfg["sources"]
    ]


# ----------------------------------------------------------------- time series


def _rain_month(rng: np.random.Generator, clim: float) -> tuple[float | None, float]:
    noise, u, zero_draw, vf_draw = rng.normal(0, 0.35), rng.random(), rng.random(), rng.uniform(0.8, 0.95)
    if u < 0.01:
        return None, 0.0
    value = 0.0 if (clim < 10 and zero_draw < 0.15) else round(clim * math.exp(noise), 2)
    return value, (round(vf_draw, 2) if u < 0.05 else 1.0)


def _aod_month(rng: np.random.Generator, clim: float, valid: float, drift: float) -> tuple[float | None, float]:
    noise, vf_noise = rng.normal(0, 0.12), rng.normal(0, 0.08)
    vf = round(min(1.0, max(0.0, valid + vf_noise)), 2)
    return (None if vf < 0.1 else round(clim * math.exp(noise) * (1 + drift), 4)), vf


def _qc(value: float | None, vf: float | None) -> str:
    if value is None:
        return "missing"
    return "low_coverage" if vf is not None and vf < 0.3 else "ok"


def monthly_series(region: dict, variable: str, period: Period, rng: np.random.Generator,
                   extra_missing: float, source_id: str, unit: str) -> TimeSeries:
    points = []
    for day in month_starts(period):
        m, years = day.month - 1, day.year - 2003
        if variable == "rainfall":
            value, vf = _rain_month(rng, region["rain_clim"][m])
        else:
            value, vf = _aod_month(rng, region["aod_clim"][m], region["aod_valid"][m],
                                   region["aod_drift_per_year"] * years)
        points.append([day, value, vf])
    if extra_missing:
        for idx in sorted(rng.choice(len(points), size=round(extra_missing * len(points)), replace=False)):
            points[idx][1:] = [None, 0.0]
    return TimeSeries(region_id=region["region_id"], variable=variable, frequency="month", unit=unit,
                      source_id=source_id,
                      points=[SeriesPoint(date=d, value=v, valid_fraction=f, qc_flag=_qc(v, f)) for d, v, f in points])


def daily_series(region: dict, variable: str, period: Period, rng: np.random.Generator,
                 source_id: str, unit: str) -> TimeSeries:
    points = []
    for day in days_in(period):
        m, years = day.month - 1, day.year - 2003
        r1, r2, normal = rng.random(), rng.random(), rng.normal()
        if variable == "rainfall":
            clim = region["rain_clim"][m]
            wet_p = min(0.85, clim / 150 + 0.05)
            amount = rng.gamma(0.8, (clim / 30) / wet_p / 0.8)
            value = None if r2 < 0.002 else (round(float(amount), 2) if r1 < wet_p else 0.0)
        else:
            value = (round(region["aod_clim"][m] * math.exp(0.3 * normal)
                           * (1 + region["aod_drift_per_year"] * years), 4)
                     if r1 < region["aod_valid"][m] else None)
        points.append(SeriesPoint(date=day, value=value, valid_fraction=None,
                                  qc_flag="missing" if value is None else "ok"))
    return TimeSeries(region_id=region["region_id"], variable=variable, frequency="day", unit=unit,
                      source_id=source_id, points=points)


# ----------------------------------------------------------------- trend (E/F), canned


def _counts(series: TimeSeries) -> dict[str, Any]:
    valid = [p for p in series.points if p.value is not None and p.qc_flag != "suspect"]
    fractions = [p.valid_fraction for p in valid if p.valid_fraction is not None]
    n_expected = len(series.points)
    return {
        "n_expected": n_expected, "n_valid": len(valid),
        "valid_obs_pct": 100.0 * len(valid) / n_expected,
        "mean_valid_fraction": round(sum(fractions) / len(fractions), 4) if fractions else None,
        "low_coverage_months": sum(1 for p in series.points if p.qc_flag == "low_coverage"),
    }


def build_trend(t: dict, *, result_id: str, region_id: str, variable: str, source_id: str, period: Period,
                season: str, series_type: str, counts: dict, record_years: float, limitations: list[str],
                notes: list[str], cfg: dict) -> TrendResult:
    method = TrendMethod(**load_example("rainfall_indicator_heavy_rain_share.json")["trend"]["method"])
    significant = t["p_value"] < method.alpha
    slope_sign = sign_of(t["sen_slope"])
    direction = {"positive": "increasing", "negative": "decreasing"}.get(slope_sign, "no_significant_trend")
    lo, hi = t["slope_ci"]
    evidence = Evidence(
        record_years=record_years, n_valid=counts["n_valid"], n_expected=counts["n_expected"],
        valid_obs_pct=counts["valid_obs_pct"], mean_valid_fraction=counts["mean_valid_fraction"],
        low_coverage_months=counts["low_coverage_months"], p_value=t["p_value"], slope_ci=(lo, hi),
        ci_excludes_zero=lo > 0 or hi < 0,
        sensitivity=[SensitivityRun(name=n, sen_slope=s, p_value=p, same_sign=sign_of(s) == slope_sign)
                     for n, s, p in t["sensitivity"]],
        evidence_label=t["label"], label_rule_version="v1", notes=notes,
    )
    return TrendResult(
        result_id=result_id, region_id=region_id, variable=variable, source_id=source_id, period=period,
        season=season, series_type=series_type, method=method,
        direction=direction if significant else "no_significant_trend", slope_sign=slope_sign,
        sen_slope=t["sen_slope"], slope_unit=t["slope_unit"], slope_ci=(lo, hi), p_value=t["p_value"],
        significant=significant, ols_slope=t["ols_slope"], ols_ci=tuple(t["ols_ci"]),
        change_over_period=round(t["sen_slope"] * record_years / 10, 6), baseline_mean=t["baseline_mean"],
        percent_change_per_decade=round(t["sen_slope"] / t["baseline_mean"] * 100, 4),
        n_expected=counts["n_expected"], n_valid=counts["n_valid"],
        missing_pct=100.0 - counts["valid_obs_pct"], record_years=record_years,
        lag1_autocorrelation=t["lag1"], limitations=limitations, evidence=evidence,
        trendlib_version=cfg["trendlib_version"], computed_at=cfg["generated_at"],
    )


# ----------------------------------------------------------------- anomalies (G), canned scores


def _rain_entry(point: SeriesPoint, median: float, rng: np.random.Generator, thr: dict) -> dict:
    # Canned rank k/22, kept on the same side of the median as the value (coherent, not computed).
    above = point.value is not None and point.value >= median
    k = int(rng.integers(12, 23)) if above else int(rng.integers(1, 12))
    entry = {"score": None, "category": None, "note": ""}
    if point.value is None:
        return {**entry, "note": "missing month"}
    if point.valid_fraction is not None and point.valid_fraction < thr["min_valid_fraction"]:
        return {**entry, "note": f"not assessed: valid_fraction {point.valid_fraction} is below {thr['min_valid_fraction']}"}
    score = k / 22
    dry_possible = median >= thr["dry_suppression_median"]
    category = ("unusually_wet" if score >= thr["high"]
                else "unusually_dry" if score <= thr["low"] and dry_possible else None)
    return {"score": score, "category": category, "note": "" if dry_possible else DRY_NOTE}


def _aod_entry(point: SeriesPoint, median: float, rng: np.random.Generator, thr: dict) -> dict:
    # Canned z with the same sign as (value - median): coherent, not computed.
    sign = 1.0 if point.value is not None and point.value >= median else -1.0
    z = round(sign * abs(float(rng.normal(0, 1))), 2)
    if point.value is None:
        return {"score": None, "category": None, "note": "missing month"}
    category = "unusually_high_aod" if z >= thr["high"] else "unusually_low_aod" if z <= thr["low"] else None
    note = (f"low coverage: {round(point.valid_fraction * 100)}% of days had a valid retrieval"
            if point.qc_flag == "low_coverage" else "")
    return {"score": z, "category": category, "note": note}


def build_anomalies(region: dict, series: TimeSeries, rng: np.random.Generator, detrended: bool,
                    period: Period) -> AnomalyResult:
    template = load_example("anomaly_rainfall.json" if series.variable == "rainfall" else "anomaly_aod.json")
    thr = template["thresholds"]
    clim = region["rain_clim" if series.variable == "rainfall" else "aod_clim"]
    entries = []
    for point in series.points:
        median = float(clim[point.date.month - 1])
        part = (_rain_entry(point, median, rng, thr) if series.variable == "rainfall"
                else _aod_entry(point, median, rng, thr))
        entries.append(AnomalyEntry(date=point.date, value=point.value, baseline_median=median,
                                    score_type="percentile" if series.variable == "rainfall" else "z_log",
                                    valid_fraction=point.valid_fraction, qc_flag=point.qc_flag, **part))
    suffix = "detrended" if detrended else "raw"
    return AnomalyResult(
        result_id=f"anomalies_{series.region_id}_{series.variable}_{period.start}_{period.end}_{suffix}",
        region_id=series.region_id, variable=series.variable, source_id=series.source_id, unit=series.unit,
        period=period, baseline={**template["baseline"], "detrended": detrended}, thresholds=thr, anomalies=entries,
    )


def build_both(rain: AnomalyResult, aod: AnomalyResult, detrended: bool) -> AnomalyBothResult:
    rain_cats = {a.date: a.category for a in rain.anomalies if a.category}
    aod_cats = {a.date: a.category for a in aod.anomalies if a.category}
    flags = [{"date": d, "category": combined_category(rain_cats[d], aod_cats[d]),
              "rainfall_category": rain_cats[d], "aod_category": aod_cats[d]}
             for d in sorted(set(rain_cats) & set(aod_cats))]
    suffix = "detrended" if detrended else "raw"
    return AnomalyBothResult(
        result_id=f"anomalies_{rain.region_id}_both_{rain.period.start}_{rain.period.end}_{suffix}",
        region_id=rain.region_id, variable="both", period=rain.period, detrended=detrended,
        results=[rain, aod], combined_flags=flags,
    )


# ----------------------------------------------------------------- interaction (H) and indicators (J)


def build_interaction(item: dict, period: Period) -> InteractionResult:
    data = {**load_example(item["template"]), **item["overrides"]}
    data.update(region_id=item["region_id"], season=item["season"], period=period.model_dump(),
                result_id=f"interaction_{item['region_id']}_{item['season']}_{period.start}_{period.end}")
    return InteractionResult.model_validate(data)


def _indicator_values(spec: dict, season: str, period: Period, rng: np.random.Generator) -> list[IndicatorValue]:
    mean = spec["mean"][season] if isinstance(spec["mean"], dict) else spec["mean"]
    years = list(range(int(period.start[:4]), int(period.end[:4]) + 1))
    gap_year = years[int(rng.integers(0, len(years)))]
    values = []
    for year in years:
        raw, frac_draw, partial = rng.normal(mean, spec["sd"]), rng.uniform(0.97, 0.999), rng.random()
        vf = 0.93 if year == gap_year else (round(float(frac_draw), 3) if partial < 0.15 else 1.0)
        value = None if vf < 0.95 else float(round(max(0.0, float(raw)), spec["decimals"]))
        values.append(IndicatorValue(year=year, value=value, valid_fraction=vf))
    return values


def build_indicator(region_id: str, name: str, season: str, spec: dict, period: Period,
                    rng: np.random.Generator, cfg: dict) -> IndicatorResult:
    values = _indicator_values(spec, season, period, rng)
    slope = round(float(rng.normal(0, spec["sd"] * 0.4)), 2)
    width_lo, width_hi = (round(abs(float(rng.normal(spec["sd"] * 0.6, 0.2))) + 0.1, 2) for _ in range(2))
    p_value = round(float(rng.uniform(0.12, 0.9)), 3)
    valid = [v for v in values if v.value is not None]
    t = {"sen_slope": slope, "slope_unit": spec["slope_unit"],
         "slope_ci": [round(min(slope - width_lo, -0.01), 2), round(max(slope + width_hi, 0.01), 2)],
         "p_value": p_value, "ols_slope": round(slope * 1.05, 2),
         "ols_ci": [round(min(slope * 1.05 - width_lo, -0.01), 2), round(max(slope * 1.05 + width_hi, 0.01), 2)],
         "baseline_mean": round(sum(v.value for v in valid) / len(valid), 2), "lag1": 0.05, "label": "weak",
         "sensitivity": [["end_2021", round(slope * 1.1, 2), min(0.99, round(p_value + 0.03, 3))],
                         ["ols", round(slope * 1.05, 2), p_value]]}
    counts = {"n_expected": len(values), "n_valid": len(valid), "valid_obs_pct": 100.0 * len(valid) / len(values),
              "mean_valid_fraction": round(sum(v.valid_fraction for v in values) / len(values), 4),
              "low_coverage_months": 0}
    trend = build_trend(
        t, result_id=f"trend_{region_id}_{name}_{season}_{period.start}_{period.end}", region_id=region_id,
        variable="rainfall", source_id="IMERG_V07_FINAL_DAILY", period=period, season=season,
        series_type="annual_indicator", counts=counts, record_years=float(len(values)),
        limitations=[MOCK_LIMITATION, "Regional-mean indicator: averaging a large box hides local extremes."],
        notes=[LABEL_NOTE, "MOCK fixture: illustrative numbers.", "Counts refer to years (annual indicator)."], cfg=cfg,
    )
    return IndicatorResult(
        result_id=f"indicator_{region_id}_{name}_{season}_{period.start}_{period.end}", region_id=region_id,
        indicator=name, season=season, period=period, source_id="IMERG_V07_FINAL_DAILY", unit=spec["unit"],
        definition=spec["definition"], spatial_method="regional_mean",
        threshold_baseline=period if name == "heavy_rain_share" else None, min_valid_fraction=0.95,
        values=values, trend=trend, trend_note=None,
    )


# ----------------------------------------------------------------- scenario assembly


def _source_ids(cfg: dict, variable: str) -> tuple[str, str]:
    sources = next(v["sources"] for v in cfg["variables"] if v["variable"] == variable)
    return sources[0], sources[1]  # (monthly, daily)


def build_scenario(cfg: dict, name: str, index: int) -> dict[str, BaseModel | list]:
    sc = cfg["scenarios"][name]
    period = Period(**sc["period"])
    seed = cfg["seed"]
    files: dict[str, Any] = {
        layout.variables_path(): build_variables(cfg),
        layout.regions_path(): build_regions(cfg, period),
        layout.sources_path(): build_sources(cfg),
    }
    for r_i, region in enumerate(cfg["regions"]):
        rid = region["region_id"]
        monthly: dict[str, TimeSeries] = {}
        for v_i, var in enumerate(cfg["variables"]):
            variable = var["variable"]
            monthly_src, daily_src = _source_ids(cfg, variable)
            series = monthly_series(region, variable, period, rng_for(seed, index, r_i, v_i, 1),
                                    sc["extra_missing_fraction"], monthly_src, var["unit"])
            monthly[variable] = series
            files[layout.series_path(rid, variable, "month")] = series
            if sc["daily"]:
                files[layout.series_path(rid, variable, "day")] = daily_series(
                    region, variable, period, rng_for(seed, index, r_i, v_i, 2), daily_src, var["daily_unit"])
        if sc["results"]:
            files.update(build_results(cfg, region, r_i, monthly, period, index))
    return files


def build_results(cfg: dict, region: dict, r_i: int, monthly: dict[str, TimeSeries], period: Period,
                  index: int) -> dict[str, Any]:
    rid, seed, out = region["region_id"], cfg["seed"], {}
    for t in (t for t in cfg["trends"] if t["region_id"] == rid):
        series = monthly[t["variable"]]
        out[layout.trend_path(rid, t["variable"], "all", period)] = build_trend(
            t, result_id=f"trend_{rid}_{t['variable']}_all_{period.start}_{period.end}", region_id=rid,
            variable=t["variable"], source_id=series.source_id, period=period, season="all",
            series_type="monthly_deseasonalised", counts=_counts(series), record_years=len(series.points) / 12,
            limitations=[MOCK_LIMITATION, cfg["trend_limitations"][t["variable"]]],
            notes=[LABEL_NOTE, "MOCK fixture: illustrative numbers."], cfg=cfg)
    for detrended in (False, True):
        single = {v: build_anomalies(region, monthly[v], rng_for(seed, index, r_i, v_i, 3, int(detrended)),
                                     detrended, period)
                  for v_i, v in enumerate(("rainfall", "aod"))}
        for v, result in single.items():
            out[layout.anomalies_path(rid, v, detrended)] = result
        out[layout.anomalies_path(rid, "both", detrended)] = build_both(single["rainfall"], single["aod"], detrended)
    for item in (i for i in cfg["interactions"] if i["region_id"] == rid):
        out[layout.interaction_path(rid, item["season"])] = build_interaction(item, period)
    for k_i, (name, spec) in enumerate(cfg["indicators"].items()):
        for s_i, season in enumerate(cfg["indicator_seasons"]):
            out[layout.indicator_path(rid, name, season)] = build_indicator(
                rid, name, season, spec, period, rng_for(seed, index, r_i, 10 + k_i, s_i), cfg)
    return out


# ----------------------------------------------------------------- writing (deterministic, owned files only)


def _dump(obj: Any) -> Any:
    if isinstance(obj, list):
        return [_dump(o) for o in obj]
    return obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj


def serialize(cfg: dict, scenario: str, relative: str, result: Any) -> bytes:
    envelope = {"data_status": "mock", "data_version": f"{cfg['data_version']}-{scenario}",
                "contract_version": cfg["contract_version"], "generated_at": cfg["generated_at"],
                "result": _dump(result)}
    if relative.startswith("timeseries/"):
        text = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(envelope, ensure_ascii=False, indent=2)
    return (text + "\n").encode("utf-8")


def guard_output_dir(out_dir: Path) -> Path:
    out = out_dir.resolve()
    processed = PROCESSED_DIR.resolve()
    if out == processed or processed in out.parents or out in processed.parents:
        raise SystemExit("Refusing to write mock data into or around data/processed/")
    mock_root = DEFAULT_OUT.resolve()
    if REPO_ROOT.resolve() in out.parents and out != mock_root and mock_root not in out.parents:
        raise SystemExit("Inside the repository, mock data may only be written to data/mock/")
    return out


def _old_files(out: Path) -> set[str]:
    path = out / MANIFEST
    if not path.is_file():
        return set()
    return set(Manifest.model_validate_json(path.read_text(encoding="utf-8")).files)


def generate(out_dir: Path = DEFAULT_OUT, config_path: Path = CONFIG_PATH) -> list[str]:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    out = guard_output_dir(out_dir)
    written: dict[str, bytes] = {}
    for index, scenario in enumerate(cfg["scenarios"]):
        for relative, result in build_scenario(cfg, scenario, index).items():
            written[f"{scenario}/{relative}"] = serialize(cfg, scenario, relative, result)
    for stale in sorted(_old_files(out) - set(written)):
        target = (out / stale).resolve()
        if out in target.parents and target.is_file():
            target.unlink()
    for relative, payload in sorted(written.items()):
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    manifest = Manifest(data_status="mock", data_version=cfg["data_version"],
                        generator_version=cfg["generator_version"], files=sorted(written))
    (out / MANIFEST).write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return sorted(written)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate MOCK fixtures (never real data).")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (default: data/mock)")
    args = parser.parse_args()
    files = generate(args.out)
    print(f"Wrote {len(files)} MOCK files + {MANIFEST} to {args.out}")


if __name__ == "__main__":
    main()
