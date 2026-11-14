"""Public trendlib API used by the TrendTrace backend (science adapter, decision SCI-01).

Protocol implemented (Aadarsh's handbook v2.0, pp14, 22-27):

1. **Selection.** ``season="all"``: every month, with the calendar-month climatology removed
   (deseasonalised anomalies). ``JF/MAM/JJAS/OND``: one seasonal mean per year, using only
   years where every month of that season is valid (no partial-season bias).
2. **Time.** Actual decimal-year timestamps; gaps are never compressed.
3. **Significance.** Hamed-Rao modified Mann-Kendall (autocorrelation-aware).
4. **Rate.** Theil-Sen slope per decade with a rank interval that uses the *same corrected
   variance*, so the interval and the p-value agree. OLS slope, t-test and interval are a
   parametric cross-check.
5. **Evidence.** Team label rule v1 with sensitivity runs (low-coverage exclusion, ending in
   2021, Seasonal Kendall, OLS).

Missing values stay missing: nothing is filled, interpolated or smoothed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

import numpy as np
import pandas as pd

from . import stats
from .exceptions import DataQualityError, InsufficientDataError

__all__ = ["compute_trend", "compute_evidence", "analyze_values", "analyze_frame", "LABEL_RULE_VERSION"]

VERSION = "1.0.0"
LABEL_RULE_VERSION = "v1"
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
SEASON_MONTHS = {"all": tuple(range(1, 13)), "JF": (1, 2), "MAM": (3, 4, 5),
                 "JJAS": (6, 7, 8, 9), "OND": (10, 11, 12)}
MIN_MONTHLY_VALUES = 60
MIN_YEARLY_VALUES = 10
MIN_PER_CALENDAR_MONTH = 3
MAX_DROPPED_CALENDAR_MONTHS = 4
INVALID_FLAGS = {"missing", "suspect"}


@dataclass
class Prepared:
    t: np.ndarray                 # decimal years
    x: np.ndarray                 # analysed values (anomalies or seasonal means)
    raw: np.ndarray               # raw values for the same points (for baseline mean)
    grid: np.ndarray              # integer position on the regular grid (month or year number)
    month: np.ndarray             # calendar month of each point (monthly only, else 0)
    dates: list[date]
    obs_per_year: int
    series_type: str
    n_valid_months: int
    n_expected_months: int
    low_coverage_months: int
    mean_valid_fraction: float | None
    climatology: dict[int, float] = field(default_factory=dict)
    excluded_calendar_months: list[int] = field(default_factory=list)


# ----------------------------------------------------------------------------- preparation


def _months_between(start: str, end: str) -> list[tuple[int, int]]:
    y1, m1 = int(start[:4]), int(start[5:7])
    y2, m2 = int(end[:4]), int(end[5:7])
    out = []
    for k in range((y2 - y1) * 12 + (m2 - m1) + 1):
        y, m0 = divmod(y1 * 12 + m1 - 1 + k, 12)
        out.append((y, m0 + 1))
    return out


def _frame_period(frame: pd.DataFrame) -> tuple[str, str]:
    period = frame.attrs.get("period")
    if period:
        return period["start"], period["end"]
    dates = pd.to_datetime(frame["date"])
    return dates.min().strftime("%Y-%m"), dates.max().strftime("%Y-%m")


def _valid_mask(frame: pd.DataFrame, exclude_low_coverage: bool) -> np.ndarray:
    values = pd.to_numeric(frame["value"], errors="coerce").to_numpy(dtype=float)
    flags = frame["qc_flag"].fillna("ok").astype(str).to_numpy() if "qc_flag" in frame else np.array(["ok"] * len(frame))
    ok = np.isfinite(values) & ~np.isin(flags, list(INVALID_FLAGS))
    if exclude_low_coverage:
        ok &= flags != "low_coverage"
    return ok


def prepare_monthly(frame: pd.DataFrame, season: str, *, exclude_low_coverage: bool = False,
                    end_override: str | None = None) -> Prepared:
    if season not in SEASON_MONTHS:
        raise DataQualityError(f"unknown season {season!r}")
    if frame.attrs.get("frequency", "month") != "month":
        raise DataQualityError("trend analysis uses monthly series")
    start, end = _frame_period(frame)
    if end_override is not None:
        end = min(end, end_override)
    dates = pd.to_datetime(frame["date"])
    if dates.duplicated().any():
        raise DataQualityError("duplicate dates")
    if (dates.dt.day != 1).any():
        raise DataQualityError("monthly dates must be the first of the month")
    in_period = (dates.dt.strftime("%Y-%m") >= start) & (dates.dt.strftime("%Y-%m") <= end)
    frame = frame.loc[in_period.to_numpy()].copy()
    dates = dates[in_period].reset_index(drop=True)
    frame = frame.reset_index(drop=True)
    months_wanted = set(SEASON_MONTHS[season])
    in_season = dates.dt.month.isin(months_wanted).to_numpy()
    valid = _valid_mask(frame, exclude_low_coverage) & in_season
    values = pd.to_numeric(frame["value"], errors="coerce").to_numpy(dtype=float)
    flags = frame["qc_flag"].fillna("ok").astype(str).to_numpy() if "qc_flag" in frame else np.array(["ok"] * len(frame))
    vf = pd.to_numeric(frame.get("valid_fraction"), errors="coerce").to_numpy(dtype=float) \
        if "valid_fraction" in frame else np.full(len(frame), np.nan)
    expected = [(y, m) for (y, m) in _months_between(start, end) if m in months_wanted]
    sel_vf = vf[in_season & np.isfinite(vf)]
    common = dict(n_valid_months=int(valid.sum()), n_expected_months=len(expected),
                  low_coverage_months=int(np.sum(in_season & (flags == "low_coverage"))),
                  mean_valid_fraction=float(sel_vf.mean()) if len(sel_vf) else None)
    years = dates.dt.year.to_numpy()
    months = dates.dt.month.to_numpy()

    if season == "all":
        clim: dict[int, float] = {}
        dropped: list[int] = []
        for m in range(1, 13):
            sel = valid & (months == m)
            if sel.sum() < MIN_PER_CALENDAR_MONTH:
                # A climatology from 0-2 values is meaningless; leave that calendar month out
                # (recorded in excluded_calendar_months) instead of inventing a baseline.
                dropped.append(m)
                continue
            clim[m] = float(values[sel].mean())
        if len(dropped) > MAX_DROPPED_CALENDAR_MONTHS:
            raise InsufficientDataError(f"{len(dropped)} calendar months have fewer than {MIN_PER_CALENDAR_MONTH} valid values")
        valid &= ~np.isin(months, dropped)
        common["n_valid_months"] = int(valid.sum())
        idx = np.flatnonzero(valid)
        if len(idx) < MIN_MONTHLY_VALUES:
            raise InsufficientDataError("too few valid monthly values")
        x = np.array([values[i] - clim[months[i]] for i in idx])
        t = years[idx] + (months[idx] - 0.5) / 12.0
        return Prepared(t=t, x=x, raw=values[idx], grid=years[idx] * 12 + months[idx] - 1, month=months[idx],
                        dates=[date(int(years[i]), int(months[i]), 1) for i in idx], obs_per_year=12,
                        series_type="monthly_deseasonalised", climatology=clim,
                        excluded_calendar_months=dropped, **common)

    # Seasonal: one mean per year from complete seasons only.
    season_list = sorted(months_wanted)
    t_list, x_list, grid, out_dates = [], [], [], []
    for year in sorted(set(y for y, _ in expected)):
        sel = valid & (years == year)
        got = set(months[sel].tolist())
        if got != set(season_list):
            continue
        x_list.append(float(values[sel].mean()))
        t_list.append(year + (np.mean(season_list) - 0.5) / 12.0)
        grid.append(year)
        out_dates.append(date(year, season_list[0], 1))
    if len(x_list) < MIN_YEARLY_VALUES:
        raise InsufficientDataError(f"fewer than {MIN_YEARLY_VALUES} complete {season} seasons")
    x = np.array(x_list)
    return Prepared(t=np.array(t_list), x=x, raw=x.copy(), grid=np.array(grid), month=np.zeros(len(x), dtype=int),
                    dates=out_dates, obs_per_year=1, series_type="seasonal_mean", **common)


def prepare_values(dates: Iterable[Any], values: Iterable[Any], frequency: str, *, deseasonalise: bool = True) -> Prepared:
    """Prepare an arbitrary user series: ``frequency`` 'month' or 'year'. Nulls stay missing."""
    try:
        d = pd.to_datetime(pd.Series([str(x) for x in dates]), format="ISO8601")
    except (ValueError, TypeError) as exc:
        raise DataQualityError("dates must be ISO dates such as 2003-01-01") from exc
    v = pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(dtype=float)
    if len(d) != len(v):
        raise DataQualityError("dates and values differ in length")
    if d.duplicated().any():
        raise DataQualityError("duplicate dates")
    if not d.is_monotonic_increasing:
        order = np.argsort(d.to_numpy())
        d, v = d.iloc[order].reset_index(drop=True), v[order]
    ok = np.isfinite(v)
    if frequency == "year":
        years = d.dt.year.to_numpy()
        idx = np.flatnonzero(ok)
        if len(idx) < MIN_YEARLY_VALUES:
            raise InsufficientDataError(f"need at least {MIN_YEARLY_VALUES} valid yearly values")
        span = int(years.max() - years.min() + 1)
        return Prepared(t=years[idx] + 0.5, x=v[idx], raw=v[idx], grid=years[idx], month=np.zeros(len(idx), dtype=int),
                        dates=[date(int(years[i]), 1, 1) for i in idx], obs_per_year=1, series_type="annual",
                        n_valid_months=len(idx), n_expected_months=span, low_coverage_months=0, mean_valid_fraction=None)
    if frequency != "month":
        raise DataQualityError("frequency must be 'month' or 'year'")
    frame = pd.DataFrame({"date": d.dt.to_period("M").dt.to_timestamp().dt.date, "value": v,
                          "qc_flag": np.where(ok, "ok", "missing"), "valid_fraction": np.nan})
    if frame["date"].duplicated().any():
        raise DataQualityError("more than one value in a month; supply monthly values")
    frame.attrs.update(frequency="month",
                       period={"start": d.min().strftime("%Y-%m"), "end": d.max().strftime("%Y-%m")})
    if deseasonalise:
        return prepare_monthly(frame, "all")
    idx = np.flatnonzero(ok)
    if len(idx) < MIN_MONTHLY_VALUES:
        raise InsufficientDataError("too few valid monthly values")
    years, months = d.dt.year.to_numpy(), d.dt.month.to_numpy()
    return Prepared(t=years[idx] + (months[idx] - 0.5) / 12, x=v[idx], raw=v[idx], grid=years[idx] * 12 + months[idx] - 1,
                    month=months[idx], dates=[date(int(years[i]), int(months[i]), 1) for i in idx], obs_per_year=12,
                    series_type="monthly_raw", n_valid_months=len(idx),
                    n_expected_months=len(_months_between(d.min().strftime("%Y-%m"), d.max().strftime("%Y-%m"))),
                    low_coverage_months=0, mean_valid_fraction=None)


# ----------------------------------------------------------------------------- core analysis


def analyze_prepared(p: Prepared, alpha: float = 0.05) -> dict[str, Any]:
    """Every statistic for one prepared series (slopes per year here; callers scale)."""
    ci_level = 1 - alpha
    mk = stats.hamed_rao_mk(p.t, p.x, p.grid)
    sen = stats.sen_with_ci(p.t, p.x, mk.var_s, ci_level)
    ols = stats.ols(p.t, p.x, ci_level)
    resid = p.x - (sen.intercept + sen.slope * p.t)
    size = int(p.grid.max() - p.grid.min()) + 1
    grid_resid = np.full(size, np.nan)
    grid_resid[p.grid - p.grid.min()] = resid
    phi = stats.lag1(grid_resid)
    noise_sd = float(np.std(resid, ddof=1)) if len(resid) > 2 else 0.0
    # Pettitt on the Sen-detrended residuals: a significant result means a step change
    # *beyond* the straight-line trend (a steady trend alone would always look like a step).
    cp_idx, cp_k, cp_p = stats.pettitt(resid)
    detect = stats.years_to_detect(sen.slope, noise_sd, phi, p.obs_per_year, alpha=alpha)
    return {"mk": mk, "sen": sen, "ols": ols, "phi": phi, "noise_sd": noise_sd,
            "change_point": {"index": cp_idx, "k": cp_k, "p_value": cp_p,
                             "before_mean": float(np.mean(resid[: cp_idx + 1])),
                             "after_mean": float(np.mean(resid[cp_idx + 1:]))},
            "years_to_detect": detect}


def _sign(v: float) -> str:
    return "positive" if v > 0 else "negative" if v < 0 else "zero"


def _direction(sig: bool, slope: float) -> str:
    if not sig or slope == 0:
        return "no_significant_trend"
    return "increasing" if slope > 0 else "decreasing"


def _round(v: float, nd: int = 6) -> float:
    return float(round(v, nd)) if math.isfinite(v) else 0.0


def _record_years(start: str, end: str) -> float:
    return len(_months_between(start, end)) / 12.0


def _limitations(variable: str, season: str, series_type: str) -> list[str]:
    out = []
    if variable.startswith("aod"):
        out.append("AOD is a column optical measurement, not ground-level PM2.5; clear-sky retrieval under-samples cloudy and rainy months.")
    if series_type == "monthly_deseasonalised":
        out.append("The calendar-month seasonal cycle was removed before testing; the slope describes change in the deseasonalised series.")
    else:
        out.append(f"One {season} mean per year from complete seasons only; years with a missing month in the season are skipped.")
    out.append("Significance uses the Hamed-Rao autocorrelation correction; a non-significant result does not prove there is no change.")
    out.append("Regional box averages smooth local variation; results describe the analysis box, not an administrative area.")
    return out


def _sensitivity_runs(frame: pd.DataFrame, season: str, alpha: float, main_slope_dec: float,
                      main: dict[str, Any], p: Prepared, exclude_low_coverage: bool) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []

    def add(name: str, slope_dec: float | None, pv: float | None) -> None:
        same = None if slope_dec is None or main_slope_dec == 0 else (np.sign(slope_dec) == np.sign(main_slope_dec))
        runs.append({"name": name, "sen_slope": None if slope_dec is None else _round(slope_dec),
                     "p_value": None if pv is None else _round(min(max(pv, 0.0), 1.0)), "same_sign": None if same is None else bool(same)})

    if not exclude_low_coverage and p.low_coverage_months > 0:
        try:
            q = prepare_monthly(frame, season, exclude_low_coverage=True)
            r = analyze_prepared(q, alpha)
            add("exclude_low_coverage", r["sen"].slope * 10, r["mk"].p_value)
        except InsufficientDataError:
            add("exclude_low_coverage", None, None)
    start, end = _frame_period(frame)
    if end > "2021-12" and _record_years(start, "2021-12") >= 10:
        try:
            q = prepare_monthly(frame, season, exclude_low_coverage=exclude_low_coverage, end_override="2021-12")
            r = analyze_prepared(q, alpha)
            add("end_2021", r["sen"].slope * 10, r["mk"].p_value)
        except InsufficientDataError:
            add("end_2021", None, None)
    if season == "all":
        sk_slope, sk_p = stats.seasonal_kendall(p.t, p.raw, p.month)
        add("seasonal_kendall", sk_slope * 10, sk_p)
    add("ols", main["ols"].slope * 10, main["ols"].p_value)
    return runs


def evidence_label(*, record_years: float, valid_obs_pct: float, p_value: float, alpha: float,
                   ci_excludes_zero: bool, sensitivity: list[dict[str, Any]]) -> str:
    """Team label rule v1 (handbook pp26-27). A team convention, not an official NASA score."""
    if record_years < 10 or valid_obs_pct < 70:
        return "insufficient_data"
    runs = [r for r in sensitivity if r["same_sign"] is not None]
    same = sum(1 for r in runs if r["same_sign"]) / len(runs) if runs else 0.0
    sig = sum(1 for r in runs if r["p_value"] is not None and r["p_value"] < alpha) / len(runs) if runs else 0.0
    core = p_value < alpha and ci_excludes_zero
    if core and len(runs) >= 2 and same == 1.0 and sig >= 2 / 3 and valid_obs_pct >= 90:
        return "strong"
    if core and same >= 2 / 3:
        return "moderate"
    return "weak"


def compute_trend(frame: pd.DataFrame, *, season: str = "all", alpha: float = 0.05,
                  exclude_low_coverage: bool = False) -> dict[str, Any]:
    """Return a contract TrendResult (section E/F) dictionary for one monthly series frame.

    ``frame`` columns: date, value, valid_fraction, qc_flag. ``frame.attrs``: region_id,
    variable, source_id, unit, frequency, period {start, end}.
    """
    attrs = frame.attrs
    start, end = _frame_period(frame)
    p = prepare_monthly(frame, season, exclude_low_coverage=exclude_low_coverage)
    a = analyze_prepared(p, alpha)
    mk, sen, ols = a["mk"], a["sen"], a["ols"]
    slope_dec, lo_dec, hi_dec = sen.slope * 10, sen.lower * 10, sen.upper * 10
    p_value = _round(min(max(mk.p_value, 0.0), 1.0), 8)
    significant = p_value < alpha
    record_years = _record_years(start, end)
    baseline_mean = float(np.mean(p.raw))
    n_expected, n_valid = p.n_expected_months, p.n_valid_months
    valid_pct = 100.0 * n_valid / n_expected if n_expected else 0.0
    ci = (_round(lo_dec), _round(hi_dec))
    ci_excl = ci[0] > 0 or ci[1] < 0
    sens = _sensitivity_runs(frame, season, alpha, slope_dec, a, p, exclude_low_coverage)
    label = evidence_label(record_years=record_years, valid_obs_pct=valid_pct, p_value=p_value, alpha=alpha,
                           ci_excludes_zero=ci_excl, sensitivity=sens)
    region, variable = attrs.get("region_id", "custom"), attrs.get("variable", "value")
    unit = attrs.get("unit", "")
    suffix = ("" if abs(alpha - 0.05) < 1e-12 else f"_a{alpha:.2f}") + ("_xlc" if exclude_low_coverage else "")
    notes = ["Label rule defined by the team (v1); see docs/methods.md.",
             f"Hamed-Rao variance correction factor {a['mk'].correction_factor:.3f}; Sen interval uses the corrected variance."]
    if a["years_to_detect"] is not None and not significant:
        notes.append(f"At the current rate and noise, about {a['years_to_detect']:.0f} years of record would be needed "
                     "to detect this trend (Weatherhead et al. 1998, 90% power).")
    sen_slope = _round(slope_dec)
    if sen_slope == 0.0 and slope_dec != 0:
        sen_slope = float(f"{slope_dec:.6g}")
    return {
        "result_id": f"trend_{region}_{variable}_{season}_{start}_{end}{suffix}",
        "region_id": region, "variable": variable, "source_id": attrs.get("source_id", "custom"),
        "period": {"start": start, "end": end}, "season": season, "series_type": p.series_type,
        "method": {"test": "mann_kendall_hamed_rao", "slope": "theil_sen", "alpha": alpha, "ci_level": round(1 - alpha, 4)},
        "direction": _direction(significant, sen_slope), "slope_sign": _sign(sen_slope),
        "sen_slope": sen_slope, "slope_unit": f"{unit} per decade".strip(),
        "slope_ci": [min(ci[0], sen_slope), max(ci[1], sen_slope)], "p_value": p_value, "significant": significant,
        "ols_slope": _round(ols.slope * 10), "ols_ci": [_round(ols.lower * 10), _round(ols.upper * 10)],
        "change_over_period": _round(sen.slope * record_years),
        "baseline_mean": _round(baseline_mean),
        "percent_change_per_decade": _round(100 * slope_dec / baseline_mean) if baseline_mean else 0.0,
        "n_expected": n_expected, "n_valid": n_valid, "missing_pct": _round(100 - valid_pct),
        "record_years": record_years, "lag1_autocorrelation": _round(a["phi"]),
        "limitations": _limitations(variable, season, p.series_type) + ([
            "Calendar months with fewer than 3 valid values were left out: "
            + ", ".join(str(m) for m in p.excluded_calendar_months) + "."] if p.excluded_calendar_months else []),
        "evidence": {
            "record_years": record_years, "n_valid": n_valid, "n_expected": n_expected,
            "valid_obs_pct": _round(valid_pct), "mean_valid_fraction": None if p.mean_valid_fraction is None else _round(p.mean_valid_fraction),
            "low_coverage_months": p.low_coverage_months, "p_value": p_value,
            "slope_ci": [min(ci[0], sen_slope), max(ci[1], sen_slope)], "ci_excludes_zero": ci_excl,
            "sensitivity": sens, "evidence_label": label, "label_rule_version": LABEL_RULE_VERSION, "notes": notes,
        },
        "trendlib_version": VERSION,
        "computed_at": datetime.now(IST).replace(microsecond=0).isoformat(),
    }


def compute_evidence(frame: pd.DataFrame, result: dict[str, Any], sensitivity: bool = True) -> dict[str, Any]:
    """Evidence block (section F). compute_trend already includes it; recomputed only if absent."""
    if result.get("evidence") is not None:
        return result["evidence"]
    return compute_trend(frame, season=result["season"], alpha=result["method"]["alpha"])["evidence"]


# ----------------------------------------------------------------------------- rich detail (charts, insights)


def _detail(p: Prepared, a: dict[str, Any], alpha: float, unit: str) -> dict[str, Any]:
    sen, mk, ols = a["sen"], a["mk"], a["ols"]
    t_mid = float(np.mean(p.t))
    # Band: Sen line pivoting at the data centroid with the interval slopes.
    x_mid = sen.intercept + sen.slope * t_mid
    fit = []
    for d, t, x, r in zip(p.dates, p.t, p.x, p.raw):
        dt = float(t - t_mid)
        ends = (x_mid + sen.lower * dt, x_mid + sen.upper * dt)
        fit.append({"date": d.isoformat(), "value": _round(float(r)), "analysed": _round(float(x)),
                    "fitted": _round(float(sen.intercept + sen.slope * t)),
                    "lower": _round(float(min(ends))), "upper": _round(float(max(ends)))})
    cp = a["change_point"]
    cp_date = p.dates[cp["index"] + 1].isoformat() if cp["index"] + 1 < len(p.dates) else None
    span_years = float(p.t.max() - p.t.min()) + 1.0 / p.obs_per_year
    detect = a["years_to_detect"]
    return {
        "series_type": p.series_type, "n": int(len(p.x)), "obs_per_year": p.obs_per_year,
        "unit": unit, "alpha": alpha,
        "sen_slope_per_decade": _round(sen.slope * 10), "sen_ci_per_decade": [_round(sen.lower * 10), _round(sen.upper * 10)],
        "mk_p_value": _round(mk.p_value, 8), "mk_p_value_uncorrected": _round(mk.p_value_plain, 8),
        "kendall_tau": _round(mk.tau), "hamed_rao_factor": _round(mk.correction_factor),
        "ols_slope_per_decade": _round(ols.slope * 10), "ols_ci_per_decade": [_round(ols.lower * 10), _round(ols.upper * 10)],
        "ols_p_value": _round(ols.p_value, 8), "lag1_autocorrelation": _round(a["phi"]), "noise_sd": _round(a["noise_sd"]),
        "significant": bool(mk.p_value < alpha), "direction": _direction(mk.p_value < alpha, sen.slope),
        "record_years": _round(span_years, 3),
        "change_point": {"date": cp_date, "p_value": _round(cp["p_value"], 8), "significant": bool(cp["p_value"] < alpha),
                         "step_size": _round(cp["after_mean"] - cp["before_mean"]),
                         "method": "pettitt_1979_on_detrended_residuals",
                         "note": "Tests for an abrupt shift beyond the straight-line trend (e.g. a sensor change or regime shift)."},
        "detection": {"years_needed": None if detect is None else _round(detect, 1),
                      "years_available": _round(span_years, 1),
                      "additional_years": None if detect is None else _round(max(0.0, detect - span_years), 1),
                      "method": "weatherhead_1998", "power": 0.9,
                      "note": "Years of record needed to detect a trend of the current size with 90% probability, "
                              "given the current noise and autocorrelation. Assumes the rate stays constant."},
        "climatology": {str(k): _round(v) for k, v in p.climatology.items()} or None,
        "excluded_calendar_months": p.excluded_calendar_months,
        "fit": fit,
    }


def analyze_frame(frame: pd.DataFrame, *, season: str = "all", alpha: float = 0.05,
                  exclude_low_coverage: bool = False) -> dict[str, Any]:
    """Chart-ready detail for a store series: fitted line/band, change point, detection time."""
    p = prepare_monthly(frame, season, exclude_low_coverage=exclude_low_coverage)
    return _detail(p, analyze_prepared(p, alpha), alpha, frame.attrs.get("unit", ""))


def analyze_values(dates: Iterable[Any], values: Iterable[Any], *, frequency: str = "month", alpha: float = 0.05,
                   deseasonalise: bool = True, unit: str = "") -> dict[str, Any]:
    """Full analysis of any user series (monthly or yearly), e.g. a Giovanni area-averaged CSV."""
    p = prepare_values(dates, values, frequency, deseasonalise=deseasonalise)
    a = analyze_prepared(p, alpha)
    out = _detail(p, a, alpha, unit)
    baseline = float(np.mean(p.raw))
    out["baseline_mean"] = _round(baseline)
    out["percent_change_per_decade"] = _round(100 * a["sen"].slope * 10 / baseline) if baseline else None
    out["change_over_record"] = _round(a["sen"].slope * out["record_years"])
    ci_excl = out["sen_ci_per_decade"][0] > 0 or out["sen_ci_per_decade"][1] < 0
    runs = [{"name": "ols", "sen_slope": out["ols_slope_per_decade"], "p_value": out["ols_p_value"],
             "same_sign": None if a["sen"].slope == 0 else bool(np.sign(a["ols"].slope) == np.sign(a["sen"].slope))}]
    if p.obs_per_year == 12:
        sk_slope, sk_p = stats.seasonal_kendall(p.t, p.raw, p.month)
        runs.append({"name": "seasonal_kendall", "sen_slope": _round(sk_slope * 10), "p_value": _round(sk_p, 8),
                     "same_sign": None if a["sen"].slope == 0 else bool(np.sign(sk_slope) == np.sign(a["sen"].slope))})
    valid_pct = 100.0 * p.n_valid_months / p.n_expected_months if p.n_expected_months else 0.0
    out["valid_obs_pct"] = _round(valid_pct)
    out["sensitivity"] = runs
    out["evidence_label"] = evidence_label(record_years=out["record_years"], valid_obs_pct=valid_pct,
                                           p_value=out["mk_p_value"], alpha=alpha, ci_excludes_zero=ci_excl, sensitivity=runs)
    return out


def compute_annual_trend(years: Iterable[int], values: Iterable[float | None], *, region_id: str, variable: str,
                         source_id: str, unit: str, alpha: float = 0.05, season: str = "annual",
                         series_type: str = "annual_indicator", limitations: list[str] | None = None) -> dict[str, Any]:
    """Contract TrendResult for one value per year (decision J-2: annual indicators).

    Counts are in years; low_coverage_months is 0. Sensitivity: end_2021 (when >= 10 years remain) and OLS.
    """
    years, values = list(years), list(values)
    p = prepare_values([f"{y}-01-01" for y in years], values, "year")
    a = analyze_prepared(p, alpha)
    sen, mk, ols = a["sen"], a["mk"], a["ols"]
    slope_dec = sen.slope * 10
    sen_slope = _round(slope_dec)
    p_value = _round(min(max(mk.p_value, 0.0), 1.0), 8)
    significant = p_value < alpha
    start, end = f"{min(years)}-01", f"{max(years)}-12"
    record_years = float(max(years) - min(years) + 1)
    n_expected, n_valid = len(years), int(p.n_valid_months)
    valid_pct = 100.0 * n_valid / n_expected if n_expected else 0.0
    ci = [min(_round(sen.lower * 10), sen_slope), max(_round(sen.upper * 10), sen_slope)]
    ci_excl = ci[0] > 0 or ci[1] < 0
    runs: list[dict[str, Any]] = []
    cut = [(y, v) for y, v in zip(years, values) if y <= 2021]
    if max(years) > 2021 and len([v for _, v in cut if v is not None]) >= MIN_YEARLY_VALUES:
        q = prepare_values([f"{y}-01-01" for y, _ in cut], [v for _, v in cut], "year")
        r = analyze_prepared(q, alpha)
        runs.append({"name": "end_2021", "sen_slope": _round(r["sen"].slope * 10), "p_value": _round(r["mk"].p_value, 8),
                     "same_sign": None if slope_dec == 0 else bool(np.sign(r["sen"].slope) == np.sign(slope_dec))})
    runs.append({"name": "ols", "sen_slope": _round(ols.slope * 10), "p_value": _round(ols.p_value, 8),
                 "same_sign": None if slope_dec == 0 else bool(np.sign(ols.slope) == np.sign(slope_dec))})
    label = evidence_label(record_years=record_years, valid_obs_pct=valid_pct, p_value=p_value, alpha=alpha,
                           ci_excludes_zero=ci_excl, sensitivity=runs)
    baseline = float(np.mean(p.raw))
    notes = ["Label rule defined by the team (v1); see docs/methods.md.",
             "Annual series: counts are years; the seasonal cycle does not apply."]
    if not significant and a["years_to_detect"] is not None:
        notes.append(f"At the current rate and noise, about {a['years_to_detect']:.0f} years of record would be needed "
                     "to detect this trend (Weatherhead et al. 1998, 90% power).")
    return {
        "result_id": f"trend_{region_id}_{variable}_{season}_{start}_{end}",
        "region_id": region_id, "variable": variable, "source_id": source_id,
        "period": {"start": start, "end": end}, "season": season, "series_type": series_type,
        "method": {"test": "mann_kendall_hamed_rao", "slope": "theil_sen", "alpha": alpha, "ci_level": round(1 - alpha, 4)},
        "direction": _direction(significant, sen_slope), "slope_sign": _sign(sen_slope),
        "sen_slope": sen_slope, "slope_unit": f"{unit} per decade".strip(), "slope_ci": ci,
        "p_value": p_value, "significant": significant,
        "ols_slope": _round(ols.slope * 10), "ols_ci": [_round(ols.lower * 10), _round(ols.upper * 10)],
        "change_over_period": _round(sen.slope * record_years), "baseline_mean": _round(baseline),
        "percent_change_per_decade": _round(100 * slope_dec / baseline) if baseline else 0.0,
        "n_expected": n_expected, "n_valid": n_valid, "missing_pct": _round(100 - valid_pct),
        "record_years": record_years, "lag1_autocorrelation": _round(a["phi"]),
        "limitations": list(limitations or []) + [
            "Significance uses the Hamed-Rao autocorrelation correction; a non-significant result does not prove there is no change."],
        "evidence": {"record_years": record_years, "n_valid": n_valid, "n_expected": n_expected,
                     "valid_obs_pct": _round(valid_pct), "mean_valid_fraction": None, "low_coverage_months": 0,
                     "p_value": p_value, "slope_ci": ci, "ci_excludes_zero": ci_excl, "sensitivity": runs,
                     "evidence_label": label, "label_rule_version": LABEL_RULE_VERSION, "notes": notes},
        "trendlib_version": VERSION,
        "computed_at": datetime.now(IST).replace(microsecond=0).isoformat(),
    }
