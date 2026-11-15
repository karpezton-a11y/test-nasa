"""Insight services built on trendlib: chart detail, multi-region scan, any-series analysis.

Every number comes from trendlib; this module selects data, formats and explains.
Plain-language text is deterministic, states significance exactly, and never uses
causal wording (same rules as the guarded /explain templates).
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from ..config import REPO_ROOT
from ..core_schemas import AnalyzeRequest
from ..errors import ApiError, api_error
from ..schemas import TrendResult
from .advanced import find_region
from .core import analyze_for, series_for
from .catalog import load_catalog
from .giovanni import parse_giovanni_csv
from .science import _trendlib, quality_errors, series_frame
from .validation import SEASONS, require_choice, resolve_period

RESEARCH_PATH = REPO_ROOT / "data" / "research" / "annual_series.json"


def fmt(value: float | None, variable: str = "") -> str:
    """Contract display rule: AOD 3 d.p., rainfall 1 d.p.; other variables 3 significant figures."""
    if value is None:
        return "not available"
    if variable.startswith("aod"):
        return f"{value:.3f}"
    if variable.startswith("rainfall"):
        return f"{value:.1f}"
    return f"{value:.3g}"


def p_text(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def _label(variable: str) -> str:
    """Readable name: AOD/rainfall as before, catalogue names for the other variables (e.g. NO2)."""
    fixed = {"aod": "AOD", "rainfall": "rainfall", "no2": "NO2 (tropospheric column)"}
    if variable in fixed:
        return fixed[variable]
    entry = next((v for v in load_catalog()["variables"] if v["id"] == variable), None)
    return entry["name"].lower() if entry else variable.replace("_", " ")


TEMPERATURE_UNITS = ("degC", "C", "K", "°C")


def percent_meaningful(unit: str) -> bool:
    """A % change of a temperature in C or K is not meaningful (no true zero on a human scale)."""
    return unit.replace(" per decade", "").strip() not in TEMPERATURE_UNITS


def q_text(q: float) -> str:
    return "q < 0.001" if q < 0.001 else f"q = {q:.3f}"


def per_decade(unit: str) -> str:
    """'1 per decade' reads badly for dimensionless quantities such as AOD."""
    unit = unit.strip()
    if unit == "%":
        return "percentage points per decade"
    return "per decade" if unit in ("", "1") else f"{unit} per decade"


def plain_language(*, what: str, where: str, period: str, variable: str, unit_per_decade: str,
                   slope: float, ci: tuple[float, float] | list[float], p: float, alpha: float,
                   significant: bool, percent_per_decade: float | None, years_needed: float | None,
                   years_available: float | None, change_point: dict[str, Any] | None = None) -> str:
    if not percent_meaningful(unit_per_decade):
        percent_per_decade = None
    unit_per_decade = per_decade(unit_per_decade.removesuffix("per decade"))
    s = fmt(abs(slope) if significant else slope, variable)
    lo, hi = fmt(ci[0], variable), fmt(ci[1], variable)
    pct = "" if percent_per_decade is None else f" ({percent_per_decade:+.1f}% per decade)"
    if significant:
        verb = "increased" if slope > 0 else "decreased"
        text = (f"{what} in {where} {verb} by about {s} {unit_per_decade}{pct} over {period} "
                f"(likely range {lo} to {hi}). With {p_text(p)}, this trend is statistically significant at "
                f"alpha = {alpha:g}: a change this consistent would be unlikely if there were no real trend.")
    else:
        text = (f"{what} in {where} shows no statistically significant trend over {period} ({p_text(p)}, alpha = {alpha:g}). "
                f"The best estimate is {s} {unit_per_decade}{pct}, but the likely range {lo} to {hi} includes zero.")
        if years_needed is not None and years_available is not None:
            if years_needed > years_available:
                text += (f" If the rate and year-to-year noise stay the same, about {years_needed:.0f} years of data "
                         f"(we have {years_available:.0f}) would be needed to detect it reliably.")
            else:
                text += " The record is long enough to detect a trend of this size, so the slope is likely small or not steady."
    if change_point and change_point.get("significant") and change_point.get("date"):
        text += (f" There is also an abrupt shift around {change_point['date'][:7]} beyond the straight-line trend "
                 f"(Pettitt test on residuals, {p_text(change_point['p_value'])}); check the chart, as a step can come "
                 "from a sudden event or a change in the instrument.")
    return text + " This describes a statistical pattern, not its cause."


# ----------------------------------------------------------------------------- store-series detail


def detail_for(store, req: AnalyzeRequest) -> dict[str, Any]:
    trend = analyze_for(store, req)
    module = _trendlib()
    series = series_for(store, req.region_id, req.variable, start=trend.period.start, end=trend.period.end)
    try:
        detail = module.analyze_frame(series_frame(series, trend.period), season=req.season, alpha=req.options.alpha,
                                      exclude_low_coverage=req.options.exclude_low_coverage)
    except quality_errors() as exc:
        raise api_error("INSUFFICIENT_DATA", "There are not enough reliable observations for this analysis.",
                        {"dataset": "trend"}) from exc
    region = find_region(store, req.region_id)
    text = plain_language(
        what=_label(trend.variable) + ("" if req.season == "all" else f" ({req.season} season mean)"),
        where=region.name, period=f"{trend.period.start} to {trend.period.end}", variable=trend.variable,
        unit_per_decade=trend.slope_unit, slope=trend.sen_slope, ci=trend.slope_ci, p=trend.p_value,
        alpha=trend.method.alpha, significant=trend.significant, percent_per_decade=trend.percent_change_per_decade,
        years_needed=detail["detection"]["years_needed"], years_available=detail["detection"]["years_available"],
        change_point=detail["change_point"])
    if store.info.data_status == "mock":
        text = "MOCK development data. " + text
    return {"trend": trend, "analysis": detail, "plain_language": text}


# ----------------------------------------------------------------------------- scan: what/where/how much


def scan_for(store, *, variables: list[str] | None, season: str, alpha: float,
             start: str | None, end: str | None) -> dict[str, Any]:
    require_choice(season, SEASONS, "INVALID_SEASON", "season")
    module = _trendlib()
    rows, skipped = [], []
    regions = store.regions().regions
    known = {v.variable for v in store.variables()}
    if variables:
        for v in variables:
            require_choice(v, sorted(known), "INVALID_VARIABLE", "variable")
    for region in regions:
        for variable in region.variables:
            if variables and variable not in variables:
                continue
            try:
                period = resolve_period(start, end, region.period_available)
                trend: TrendResult = analyze_for(store, AnalyzeRequest(region_id=region.region_id, variable=variable,
                                                                       start=period.start, end=period.end, season=season,
                                                                       options={"alpha": alpha}))
            except ApiError as exc:
                skipped.append({"region_id": region.region_id, "variable": variable, "reason": exc.code,
                                "message": exc.message})
                continue
            rows.append(trend)
    q_values = module.stats.bh_fdr([t.p_value for t in rows])
    out = []
    for trend, q in zip(rows, q_values):
        region = next(r for r in regions if r.region_id == trend.region_id)
        sig_fdr = q < alpha
        if trend.significant and sig_fdr:
            status = "significant"
        elif trend.significant:
            status = "significant_before_fdr_only"
        else:
            status = "not_significant"
        direction = trend.direction if sig_fdr else "no_significant_trend"
        headline = (f"{_label(trend.variable)} in {region.name}: "
                    + (f"{'increasing' if trend.sen_slope > 0 else 'decreasing'} by {fmt(abs(trend.sen_slope), trend.variable)} "
                       f"{per_decade(trend.slope_unit.removesuffix('per decade'))}"
                       + (f" ({trend.percent_change_per_decade:+.1f}% per decade)" if percent_meaningful(trend.slope_unit) else "")
                       + f", significant after multiple-testing correction ({q_text(q)})." if status == "significant" else
                       f"no trend that survives multiple-testing correction ({q_text(q)}; estimate "
                       f"{fmt(trend.sen_slope, trend.variable)} {per_decade(trend.slope_unit.removesuffix('per decade'))})."))
        out.append({"region_id": trend.region_id, "region_name": region.name, "variable": trend.variable,
                    "season": trend.season, "period": trend.period.model_dump(), "sen_slope": trend.sen_slope,
                    "slope_unit": trend.slope_unit, "slope_ci": list(trend.slope_ci),
                    "percent_change_per_decade": trend.percent_change_per_decade if percent_meaningful(trend.slope_unit) else None,
                    "p_value": trend.p_value,
                    "q_value": round(q, 8), "status": status, "direction_after_fdr": direction,
                    "evidence_label": trend.evidence.evidence_label, "result_id": trend.result_id, "headline": headline})
    out.sort(key=lambda r: (r["status"] != "significant", -abs(r["percent_change_per_decade"] or 0), r["p_value"]))
    contrasts = []
    for variable in sorted({r["variable"] for r in out}):
        sig = [r for r in out if r["variable"] == variable and r["status"] == "significant"]
        ups = [r["region_name"] for r in sig if r["sen_slope"] > 0]
        downs = [r["region_name"] for r in sig if r["sen_slope"] < 0]
        if ups and downs:
            contrasts.append({"variable": variable, "increasing_in": ups, "decreasing_in": downs,
                              "note": "The same variable trends in opposite directions in different regions."})
    n_sig = sum(r["status"] == "significant" for r in out)
    summary = (f"{n_sig} of {len(out)} region-variable series show a trend that stays significant after "
               f"Benjamini-Hochberg false-discovery-rate correction at {alpha:g}.")
    return {"season": season, "alpha": alpha, "multiple_testing": "benjamini_hochberg_fdr", "summary": summary,
            "rows": out, "opposite_directions": contrasts, "skipped": skipped,
            "tested": len(out), "significant": n_sig}


# ----------------------------------------------------------------------------- research data + any series


@lru_cache(maxsize=1)
def research_dataset() -> dict[str, Any]:
    return json.loads(RESEARCH_PATH.read_text(encoding="utf-8"))


def research_list() -> dict[str, Any]:
    data = research_dataset()
    return {k: v for k, v in data.items() if k != "series"} | {
        "series": [{k: v for k, v in s.items() if k != "values"} | {"n": len(s["values"])} for s in data["series"]]}


def research_series(research_id: str) -> dict[str, Any]:
    for s in research_dataset()["series"]:
        if s["research_id"] == research_id:
            return s
    raise api_error("DATA_NOT_AVAILABLE", "Unknown research series.", {"dataset": "research_annual",
                                                                       "allowed": [s["research_id"] for s in research_dataset()["series"]]})


def analyze_series(body) -> dict[str, Any]:
    """Analyse a research series, an inline series, or a Giovanni CSV with trendlib."""
    module = _trendlib()
    provenance: dict[str, Any]
    if body.research_id is not None:
        s = research_series(body.research_id)
        dates = [f"{v['year']}-01-01" for v in s["values"]]
        values = [v["value"] for v in s["values"]]
        frequency, unit, label, variable = "year", s["unit"], s["label"], s["variable"]
        where = s["region_name"]
        origin = "research_real_annual"
        data = research_dataset()
        provenance = {"data_status": data["data_status"], "origin": data["data_origin"], "method": s["method"],
                      "source_slide": s["source_slide"], "precision_note": data["precision_note"]}
    elif body.giovanni_csv is not None:
        g = parse_giovanni_csv(body.giovanni_csv, body.conversion)
        dates, values, frequency = g.dates, g.values, g.frequency
        unit, variable = body.unit or g.unit, g.variable_id
        known = next((v for v in load_catalog()["variables"] if v.get("giovanni_id") == g.variable_id), None)
        label = body.label or (known["name"] if known else g.variable_id)
        if known:
            variable = known["id"]
        where = body.place or (f"box {g.bbox}" if g.bbox else "the selected area")
        origin = "giovanni_csv"
        provenance = {"data_status": "user_supplied", "title": g.title, "bbox": g.bbox,
                      "reproduce_url_present": any("URL" in k for k in g.metadata), "conversion": body.conversion}
    else:
        dates, values = body.dates, body.values
        frequency, unit, label, variable = body.frequency, body.unit or "", body.label or "value", body.label or "value"
        where, origin = body.place or "the selected area", "user_supplied"
        provenance = {"data_status": "user_supplied"}
    try:
        result = module.analyze_values(dates, values, frequency=frequency, alpha=body.alpha,
                                       deseasonalise=body.deseasonalise, unit=unit)
    except quality_errors() as exc:
        name = type(exc).__name__
        code = "INSUFFICIENT_DATA" if name == "InsufficientDataError" else "VALIDATION_ERROR"
        raise api_error(code, f"The series cannot be analysed: {exc}", {"dataset": "series"}) from exc
    except (ValueError, TypeError) as exc:   # e.g. dates that are not dates: the caller's input, not a server fault
        raise api_error("VALIDATION_ERROR", f"The series cannot be analysed: {exc}", {"dataset": "series"}) from exc
    if not body.deseasonalise or frequency == "year":
        result["climatology"] = None
    first, last = result["fit"][0]["date"][:7], result["fit"][-1]["date"][:7]
    period = f"{first[:4]} to {last[:4]}" if frequency == "year" else f"{first} to {last}"
    result["plain_language"] = plain_language(
        what=label, where=where, period=period, variable=variable, unit_per_decade=f"{unit} per decade".strip(),
        slope=result["sen_slope_per_decade"], ci=result["sen_ci_per_decade"], p=result["mk_p_value"], alpha=body.alpha,
        significant=result["significant"], percent_per_decade=result.get("percent_change_per_decade"),
        years_needed=result["detection"]["years_needed"], years_available=result["detection"]["years_available"],
        change_point=result["change_point"])
    result["input_origin"] = origin
    result["input_provenance"] = provenance
    result["label"] = label
    result["frequency"] = frequency
    result["method"] = {"test": "mann_kendall_hamed_rao", "slope": "theil_sen", "parametric_check": "ols_t_test",
                        "change_point": "pettitt", "detection_time": "weatherhead_1998",
                        "trendlib_version": getattr(module, "__version__", None)}
    return result
